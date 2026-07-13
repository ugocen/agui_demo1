"use client";

import { createContext, useContext, useMemo, useState } from "react";

import { bugToHtml, bugToJson, bugToMarkdown, BugReport } from "./bugFormats";

type CanvasContextValue = {
  bug: BugReport | null;
  showBug: (bug: BugReport) => void;
  close: () => void;
};

const CanvasContext = createContext<CanvasContextValue>({
  bug: null,
  showBug: () => {},
  close: () => {},
});

export function useBugCanvas(): CanvasContextValue {
  return useContext(CanvasContext);
}

export function BugCanvasProvider({ children }: { children: React.ReactNode }) {
  const [bug, setBug] = useState<BugReport | null>(null);
  const value = useMemo<CanvasContextValue>(
    () => ({ bug, showBug: setBug, close: () => setBug(null) }),
    [bug]
  );
  return <CanvasContext.Provider value={value}>{children}</CanvasContext.Provider>;
}

type Format = "html" | "markdown" | "json";

const FORMATS: { key: Format; label: string }[] = [
  { key: "html", label: "HTML" },
  { key: "markdown", label: "Markdown" },
  { key: "json", label: "JSON" },
];

export function BugCanvasPanel() {
  const { bug, close } = useBugCanvas();
  const [format, setFormat] = useState<Format>("html");

  const source = useMemo(() => {
    if (!bug) {
      return "";
    }
    if (format === "json") {
      return bugToJson(bug);
    }
    if (format === "markdown") {
      return bugToMarkdown(bug);
    }
    return bugToHtml(bug);
  }, [bug, format]);

  if (!bug) {
    return null;
  }

  const copy = () => navigator.clipboard?.writeText(source);

  return (
    <aside className="canvas">
      <div className="canvas-header">
        <div className="canvas-title">Bug document</div>
        <button className="canvas-close" onClick={close} aria-label="Close document">
          ✕
        </button>
      </div>

      <div className="canvas-tabs">
        {FORMATS.map((entry) => (
          <button
            key={entry.key}
            className={`canvas-tab ${format === entry.key ? "active" : ""}`}
            onClick={() => setFormat(entry.key)}
          >
            {entry.label}
          </button>
        ))}
        <button className="ghost-btn canvas-copy" onClick={copy}>
          Copy
        </button>
      </div>

      <div className="canvas-body">
        {format === "html" ? (
          <div className="canvas-preview" dangerouslySetInnerHTML={{ __html: bugToHtml(bug) }} />
        ) : null}
        <pre className="canvas-source">{source}</pre>
      </div>
    </aside>
  );
}
