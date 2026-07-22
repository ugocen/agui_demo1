"use client";

/**
 * Prepare an attached image so it survives the whole hop to the model.
 *
 * Two things go wrong without this, and both fail SILENTLY — the block is
 * dropped with a server-side log line and the user is told nothing:
 *
 * 1. FORMAT. `ag_ui_strands` maps a MIME type to a Bedrock image format by
 *    taking the text after the last "/" and checking it against exactly
 *    {png, jpeg, gif, webp}. So `image/jpg` — which some tools and a few
 *    drag-and-drop sources still emit — parses to "jpg", misses the set, and the
 *    image vanishes. The extension is the more reliable signal, so it wins.
 *
 * 2. SIZE. Bedrock Converse caps an image at 3.75 MB and 8000 px, and the whole
 *    conversation is re-sent on every turn, so an oversized screenshot is not
 *    just a rejected request — it is a rejected request on every subsequent turn
 *    too. Anything above the budget is downscaled here, once, in the browser.
 *
 * A file that is already an allowed format and within budget is passed through
 * byte-for-byte. Re-encoding a screenshot that did not need it would soften the
 * text the model is being asked to read.
 */

import type { AttachmentUploadResult } from "@copilotkit/shared";

/** Exactly the formats the Strands adapter can turn into a Bedrock image block. */
export const ACCEPTED_IMAGE_TYPES = "image/png,image/jpeg,image/gif,image/webp";

/** Bedrock's per-image ceiling is 3.75 MB; stay clear of it. */
const MAX_INLINE_BYTES = 3_000_000;
/** Claude's images are sampled at ~1568 px on the long edge; beyond that is waste. */
const MAX_EDGE_PX = 1568;

const BY_EXTENSION: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  gif: "image/gif",
  webp: "image/webp",
};

const ALLOWED = new Set(Object.values(BY_EXTENSION));

/** The MIME type the adapter will accept, preferring the extension over file.type. */
export function canonicalImageType(file: File): string | null {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  return BY_EXTENSION[extension] ?? (ALLOWED.has(file.type) ? file.type : null);
}

function toBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    // The result is a data URL; everything after the comma is the bare base64
    // the AG-UI data source expects.
    reader.onload = () => resolve(String(reader.result ?? "").split(",")[1] ?? "");
    reader.onerror = () => reject(reader.error ?? new Error("could not read the file"));
    reader.readAsDataURL(blob);
  });
}

async function downscale(file: File): Promise<{ blob: Blob; mimeType: string }> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_EDGE_PX / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  const context = canvas.getContext("2d");
  if (!context) throw new Error("this browser could not resize the image");
  context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();

  const encode = (type: string, quality?: number) =>
    new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, type, quality));

  // PNG first: a UI screenshot is mostly flat colour and text, where PNG is both
  // smaller and sharper than JPEG. Only fall back to lossy when it is still big.
  const png = await encode("image/png");
  if (png && png.size <= MAX_INLINE_BYTES) return { blob: png, mimeType: "image/png" };
  const jpeg = await encode("image/jpeg", 0.85);
  if (jpeg) return { blob: jpeg, mimeType: "image/jpeg" };
  if (png) return { blob: png, mimeType: "image/png" };
  throw new Error(`could not compress this image below ${Math.round(MAX_INLINE_BYTES / 1e6)} MB`);
}

/**
 * CopilotKit `AttachmentsConfig.onUpload` handler.
 *
 * Returns an inline data source rather than a URL on purpose. The adapter fetches
 * a URL source from INSIDE the AgentCore runtime with `urllib.urlopen`, which the
 * enterprise's closed intranet cannot do — a URL there would resolve to nothing
 * and the image would disappear with only a warning in the runtime's log.
 */
export async function prepareScreenshot(file: File): Promise<AttachmentUploadResult> {
  const mimeType = canonicalImageType(file);
  if (!mimeType) {
    throw new Error(`${file.name} is not a PNG, JPEG, GIF or WEBP image`);
  }
  if (file.size <= MAX_INLINE_BYTES) {
    return { type: "data", value: await toBase64(file), mimeType };
  }
  const resized = await downscale(file);
  return { type: "data", value: await toBase64(resized.blob), mimeType: resized.mimeType };
}
