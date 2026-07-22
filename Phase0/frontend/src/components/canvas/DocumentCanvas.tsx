"use client";

/**
 * Document canvas — the side panel that shows a draft as a DOCUMENT while the
 * chat shows it as an editable form.
 *
 * Generic by construction, like the card and A2UI catalogs (AGENTS.md invariant
 * 5): it renders whatever field list the form hands it and branches on no agent
 * id. Every `draft_*` HITL form publishes through `useDocumentCanvas().publish`,
 * so press-release, bug-report, and any draft tool added later get the canvas
 * for free. The version deleted in f98cff8 was two hand-written panels mounted
 * behind `agentId === "pressrelease"` / `=== "bugreport"` — that is what made it
 * per-agent code, and is not how this one works.
 *
 * The document shape is a stated convention over the form's field ORDER, not a
 * per-tool template:
 *   field[0]             → the title (h1)
 *   field[1], if single-line → a subtitle line under it
 *   the rest             → labeled sections
 * For press release that reads headline / subheadline / dateline+body+…, and for
 * a bug report title / severity / steps+expected+… — the same two layouts the
 * old per-agent canvases hand-coded.
 *
 * Values stream in token by token, so empty fields are skipped rather than
 * rendered as empty headings.
 *
 * A draft comes in one of two shapes, and the second exists because some
 * artifacts ARE their exact bytes:
 *
 *   fields + values → a structured document. The panel renders a readable
 *                     preview and offers HTML / Markdown / JSON exports.
 *   raw             → a verbatim text artifact. The panel renders it monospace,
 *                     as literal characters, and offers copy and download only.
 *
 * The raw shape is not a styling preference. An artifact that will be pasted
 * into another system — Jira markup, a config file, a patch — is defined by its
 * exact characters, so rendering `h1.` as an HTML heading or offering a
 * "Markdown" tab would misrepresent it: the value is copy FIDELITY, and any
 * conversion destroys the thing the user came for. Both shapes stay generic —
 * whatever publishes a raw artifact gets this panel, exactly as every `draft_*`
 * form gets the structured one (AGENTS.md invariant 5).
 */

import { createContext, useCallback, useContext, useMemo, useState } from "react";

export type DocumentField = { key: string; label: string; multiline?: boolean };

/** A verbatim text artifact — rendered as characters, never interpreted. */
export type RawArtifact = {
  text: string;
  /** Suggested download name, e.g. "workspace-search-v1.0.txt". */
  filename?: string;
  /** Free-form label for the format chip, e.g. "Jira markup". */
  format?: string;
};

export type DocumentDraft = {
  /** AG-UI tool call id — one document per draft; a re-draft is a new id. */
  id: string;
  /** Document kind, shown in the panel header (e.g. "Press release"). */
  title: string;
  fields?: DocumentField[];
  values?: Record<string, string>;
  raw?: RawArtifact;
};

type CanvasContextValue = {
  draft: DocumentDraft | null;
  publish: (draft: DocumentDraft) => void;
  close: () => void;
};

const CanvasContext = createContext<CanvasContextValue>({
  draft: null,
  publish: () => {},
  close: () => {},
});

export function useDocumentCanvas(): CanvasContextValue {
  return useContext(CanvasContext);
}

type Store = { activeId: string | null; drafts: Record<string, DocumentDraft> };

function sameDraft(a: DocumentDraft, b: DocumentDraft): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function DocumentCanvasProvider({ children }: { children: React.ReactNode }) {
  const [store, setStore] = useState<Store>({ activeId: null, drafts: {} });

  const publish = useCallback((draft: DocumentDraft) => {
    setStore((prev) => {
      const known = prev.drafts[draft.id];
      // Publishing happens on every streamed character; bail on a no-op so the
      // provider cannot re-render its subtree in a loop.
      if (known && sameDraft(known, draft)) return prev;
      return {
        // A draft the canvas has not seen takes over the panel. Updates to an
        // older one — a completed form still mounted further up the transcript —
        // refresh its stored copy without stealing the view from the newest.
        activeId: known ? prev.activeId : draft.id,
        drafts: { ...prev.drafts, [draft.id]: draft },
      };
    });
  }, []);

  const close = useCallback(() => setStore((prev) => ({ ...prev, activeId: null })), []);

  const value = useMemo<CanvasContextValue>(
    () => ({ draft: store.activeId ? (store.drafts[store.activeId] ?? null) : null, publish, close }),
    [store, publish, close]
  );

  return <CanvasContext.Provider value={value}>{children}</CanvasContext.Provider>;
}

// ---- export formats -------------------------------------------------------

type Section = { label: string; value: string; multiline?: boolean };

/** Split a draft into the document convention above, dropping empty fields. */
function outline(draft: DocumentDraft): { title: string; subtitle: string | null; sections: Section[] } {
  const filled = (draft.fields ?? [])
    .map((field) => ({ ...field, value: (draft.values?.[field.key] ?? "").trim() }))
    .filter((field) => field.value !== "");
  const [head, ...rest] = filled;
  const takeSubtitle = rest.length > 0 && !rest[0].multiline;
  return {
    title: head?.value ?? "",
    subtitle: takeSubtitle ? rest[0].value : null,
    sections: (takeSubtitle ? rest.slice(1) : rest).map((field) => ({
      label: field.label,
      value: field.value,
      multiline: field.multiline,
    })),
  };
}

function paragraphs(value: string): string[] {
  return value.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean);
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export function toMarkdown(draft: DocumentDraft): string {
  const { title, subtitle, sections } = outline(draft);
  const lines: string[] = [];
  if (title) lines.push(`# ${title}`, "");
  if (subtitle) lines.push(`_${subtitle}_`, "");
  for (const section of sections) {
    lines.push(`## ${section.label}`, "", section.value, "");
  }
  return lines.join("\n").trimEnd() + "\n";
}

export function toHtml(draft: DocumentDraft): string {
  const { title, subtitle, sections } = outline(draft);
  const lines: string[] = [];
  if (title) lines.push(`<h1>${escapeHtml(title)}</h1>`);
  if (subtitle) lines.push(`<p class="subtitle">${escapeHtml(subtitle)}</p>`);
  for (const section of sections) {
    lines.push(`<h2>${escapeHtml(section.label)}</h2>`);
    for (const block of paragraphs(section.value)) {
      lines.push(`<p>${escapeHtml(block).replace(/\n/g, "<br />")}</p>`);
    }
  }
  return lines.join("\n") + "\n";
}

export function toJson(draft: DocumentDraft): string {
  return JSON.stringify(draft.values ?? {}, null, 2);
}

// ---- panel ----------------------------------------------------------------

type Format = "html" | "markdown" | "json";

const FORMATS: { key: Format; label: string }[] = [
  { key: "html", label: "HTML" },
  { key: "markdown", label: "Markdown" },
  { key: "json", label: "JSON" },
];

/** Save `text` as a file without a server round-trip. */
function download(filename: string, text: string): void {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  // Same-tick revoke aborts the download in Safari; a frame is enough for the
  // click to have been consumed.
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

/**
 * A verbatim artifact: line-numbered, monospace, and NOT interpreted.
 *
 * `h1.` stays the four characters `h1.` — this is the panel for text whose
 * value is that it pastes byte-for-byte into another system, so rendering it
 * would defeat the purpose.
 */
function RawArtifactView({ raw }: { raw: RawArtifact }) {
  const lines = useMemo(() => raw.text.split("\n"), [raw.text]);
  return (
    <div className="canvas-raw">
      <pre className="canvas-raw-gutter" aria-hidden="true">
        {lines.map((_, index) => `${index + 1}\n`).join("")}
      </pre>
      <pre className="canvas-raw-text">{raw.text}</pre>
    </div>
  );
}

export function DocumentCanvasPanel() {
  const { draft, close } = useDocumentCanvas();
  const [format, setFormat] = useState<Format>("html");
  const [copied, setCopied] = useState(false);

  const source = useMemo(() => {
    if (!draft) return "";
    // A raw artifact has exactly one representation — itself.
    if (draft.raw) return draft.raw.text;
    if (format === "json") return toJson(draft);
    if (format === "markdown") return toMarkdown(draft);
    return toHtml(draft);
  }, [draft, format]);

  if (!draft) return null;

  const raw = draft.raw;
  const { title, subtitle, sections } = outline(draft);

  const copy = () => {
    navigator.clipboard?.writeText(source).then(
      () => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      },
      () => setCopied(false)
    );
  };

  return (
    <aside className="canvas">
      <div className="canvas-header">
        <div className="canvas-title">{draft.title}</div>
        <button className="canvas-close" onClick={close} aria-label="Close document">
          ✕
        </button>
      </div>

      <div className="canvas-tabs">
        {raw ? (
          <>
            <span className="canvas-tab active" title="Raw text — copies exactly as shown">
              {raw.format || "Raw text"}
            </span>
            <button
              className="ghost-btn"
              onClick={() => download(raw.filename || "artifact.txt", raw.text)}
            >
              Download .txt
            </button>
          </>
        ) : (
          FORMATS.map((entry) => (
            <button
              key={entry.key}
              className={`canvas-tab ${format === entry.key ? "active" : ""}`}
              onClick={() => setFormat(entry.key)}
            >
              {entry.label}
            </button>
          ))
        )}
        <button className="ghost-btn canvas-copy" onClick={copy}>
          {copied ? "Copied" : raw ? "Copy .txt" : "Copy"}
        </button>
      </div>

      <div className="canvas-body">
        {raw ? (
          <RawArtifactView raw={raw} />
        ) : (
          <>
            {/* Rendered as React, never innerHTML: the text is model-authored, and
                the HTML tab already shows the same document as escaped source. */}
            <div className="canvas-preview">
              {title ? <h1>{title}</h1> : null}
              {subtitle ? <div className="severity">{subtitle}</div> : null}
              {sections.map((section) => (
                <div key={section.label}>
                  <h2>{section.label}</h2>
                  {paragraphs(section.value).map((block, index) => (
                    <p key={index} style={{ whiteSpace: "pre-wrap" }}>
                      {block}
                    </p>
                  ))}
                </div>
              ))}
            </div>
            <pre className="canvas-source">{source}</pre>
          </>
        )}
      </div>
    </aside>
  );
}
