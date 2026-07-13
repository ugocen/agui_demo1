"use client";

import { createContext, useContext, useMemo, useState } from "react";

import { PressRelease, pressToHtml, pressToJson, pressToMarkdown } from "./pressFormats";

type CanvasContextValue = {
  press: PressRelease | null;
  showPress: (press: PressRelease) => void;
  close: () => void;
};

const CanvasContext = createContext<CanvasContextValue>({
  press: null,
  showPress: () => {},
  close: () => {},
});

export function usePressCanvas(): CanvasContextValue {
  return useContext(CanvasContext);
}

export function PressCanvasProvider({ children }: { children: React.ReactNode }) {
  const [press, setPress] = useState<PressRelease | null>(null);
  const value = useMemo<CanvasContextValue>(
    () => ({ press, showPress: setPress, close: () => setPress(null) }),
    [press]
  );
  return <CanvasContext.Provider value={value}>{children}</CanvasContext.Provider>;
}

type Format = "html" | "markdown" | "json";

const FORMATS: { key: Format; label: string }[] = [
  { key: "html", label: "HTML" },
  { key: "markdown", label: "Markdown" },
  { key: "json", label: "JSON" },
];

export function PressCanvasPanel() {
  const { press, close } = usePressCanvas();
  const [format, setFormat] = useState<Format>("html");

  const source = useMemo(() => {
    if (!press) {
      return "";
    }
    if (format === "json") {
      return pressToJson(press);
    }
    if (format === "markdown") {
      return pressToMarkdown(press);
    }
    return pressToHtml(press);
  }, [press, format]);

  if (!press) {
    return null;
  }

  const copy = () => navigator.clipboard?.writeText(source);

  return (
    <aside className="canvas">
      <div className="canvas-header">
        <div className="canvas-title">Press release</div>
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
          <div className="canvas-preview" dangerouslySetInnerHTML={{ __html: pressToHtml(press) }} />
        ) : null}
        <pre className="canvas-source">{source}</pre>
      </div>
    </aside>
  );
}
