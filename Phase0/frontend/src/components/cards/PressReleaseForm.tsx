"use client";

import { useEffect, useState } from "react";

import { PressRelease } from "@/components/canvas/pressFormats";

type PressReleaseFormProps = {
  proposed: PressRelease;
  respond?: (result: unknown) => Promise<void>;
  result?: string;
  onSubmit?: (press: PressRelease) => void;
};

const FIELDS: { key: keyof PressRelease; label: string; multiline?: boolean }[] = [
  { key: "headline", label: "Headline" },
  { key: "subheadline", label: "Subheadline" },
  { key: "dateline", label: "Dateline" },
  { key: "body", label: "Body", multiline: true },
  { key: "boilerplate", label: "Boilerplate", multiline: true },
  { key: "contact", label: "Media contact", multiline: true },
];

export function PressReleaseForm({ proposed, respond, result, onSubmit }: PressReleaseFormProps) {
  const [form, setForm] = useState<PressRelease>(proposed);

  // Re-drafts (feedback loop) arrive as new `proposed` — refresh the editable form.
  useEffect(() => {
    setForm(proposed);
  }, [proposed]);

  const submit = () => {
    onSubmit?.(form);
    respond?.(form);
  };

  if (result) {
    let submitted: PressRelease = {};
    try {
      submitted = JSON.parse(result);
    } catch {
      submitted = form;
    }
    return (
      <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12, margin: "8px 0" }}>
        Press release submitted: <strong>{submitted.headline ?? form.headline}</strong>
      </div>
    );
  }

  const update = (key: keyof PressRelease, value: string) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: 6,
    border: "1px solid #ccc",
    borderRadius: 4,
    fontFamily: "inherit",
    fontSize: 14,
    boxSizing: "border-box",
  };

  return (
    <div style={{ border: "2px solid #2f6feb", borderRadius: 8, padding: 14, margin: "8px 0" }}>
      <strong>Review press release</strong>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 10 }}>
        {FIELDS.map((field) => (
          <label key={field.key} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 13, color: "#555" }}>{field.label}</span>
            {field.multiline ? (
              <textarea
                value={form[field.key] ?? ""}
                onChange={(event) => update(field.key, event.target.value)}
                rows={field.key === "body" ? 6 : 2}
                style={inputStyle}
              />
            ) : (
              <input
                value={form[field.key] ?? ""}
                onChange={(event) => update(field.key, event.target.value)}
                style={inputStyle}
              />
            )}
          </label>
        ))}
      </div>
      <button onClick={submit} disabled={!respond} style={{ marginTop: 12, padding: "6px 14px" }}>
        Submit press release
      </button>
    </div>
  );
}
