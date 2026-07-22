"use client";

/**
 * The published artifact: a compact verdict in the chat, the document itself on
 * the canvas.
 *
 * This card is the one place in the catalog that reads a tool's RESULT rather
 * than its arguments, and the reason is the whole design of the agent. The
 * markup is rendered by Python — `jira_render.py` owns section order, keyword
 * bolding and the two-space AND/BUT indent — precisely so a model cannot drift
 * on it. The rendered text therefore exists only on the way back, in the tool
 * result, never in the arguments the model wrote.
 *
 * CopilotKit hands that result over as a STRING (the adapter JSON-encodes the
 * tool's return value), so it is parsed here and treated as untrusted: a
 * half-streamed or malformed payload must degrade to "still rendering", not
 * throw inside a chat transcript.
 */

import { useEffect, useMemo } from "react";

import { useDocumentCanvas } from "@/components/canvas/DocumentCanvas";
import { Chip, CardTitle, Placeholder, cardBox } from "@/components/cards/storyPrimitives";

type FormatCheck = {
  item?: number;
  name?: string;
  status?: string;
  detail?: string;
};

type Published = {
  document?: string;
  title?: string;
  version?: string;
  filename?: string;
  summary?: string;
  format_checks?: FormatCheck[];
  failed?: FormatCheck[];
  review?: FormatCheck[];
};

function parse(result: unknown): Published | null {
  if (result && typeof result === "object") return result as Published;
  if (typeof result !== "string" || result.trim() === "") return null;
  try {
    const parsed: unknown = JSON.parse(result);
    return parsed && typeof parsed === "object" ? (parsed as Published) : null;
  } catch {
    return null;
  }
}

export function JiraArtifactCard({
  toolCallId,
  result,
}: {
  toolCallId?: string;
  result?: unknown;
}) {
  const published = useMemo(() => parse(result), [result]);
  const { publish } = useDocumentCanvas();

  const document = published?.document ?? "";
  const title = published?.title ?? "Jira story";
  const version = published?.version ?? "";
  const filename = published?.filename ?? "jira-story.txt";
  const id = toolCallId ?? "jira-story";

  useEffect(() => {
    if (!document) return;
    publish({
      id,
      title: version ? `${title} (v${version})` : title,
      raw: { text: document, filename, format: "Jira markup" },
    });
  }, [id, title, version, document, filename, publish]);

  if (!published || !document) {
    return <Placeholder>Rendering the Jira artifact…</Placeholder>;
  }

  const failed = published.failed ?? [];
  const review = published.review ?? [];

  return (
    <div style={cardBox}>
      <CardTitle
        title={version ? `${title} — v${version}` : title}
        right={
          <>
            <Chip tone={failed.length > 0 ? "bad" : "good"}>
              {published.summary ?? `${failed.length} format issue(s)`}
            </Chip>
            {review.length > 0 ? <Chip tone="warn">{review.length} to confirm</Chip> : null}
          </>
        }
      />
      <div style={{ color: "#666" }}>
        Open in the document canvas — copy or download it as {filename}.
      </div>

      {/* Only the checks that need the reader's attention are listed. A passing
          format check is not news; a failing one names the exact line. */}
      {[...failed, ...review].map((check, index) => (
        <div key={check.item ?? index} style={{ marginTop: 8 }}>
          <Chip tone={check.status === "FAIL" ? "bad" : "warn"}>
            {check.item}. {check.name}
          </Chip>
          {check.detail ? (
            <div style={{ color: "#666", marginTop: 2, fontSize: 13 }}>{check.detail}</div>
          ) : null}
        </div>
      ))}
    </div>
  );
}
