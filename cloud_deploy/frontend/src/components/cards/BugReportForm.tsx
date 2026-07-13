"use client";

import { useEffect, useState } from "react";

type BugReport = {
  title?: string;
  severity?: string;
  steps_to_reproduce?: string;
  expected_behavior?: string;
  actual_behavior?: string;
  environment?: string;
};

type BugReportFormProps = {
  proposed: BugReport;
  respond?: (result: unknown) => Promise<void>;
  result?: string;
  onSubmit?: (bug: BugReport) => void;
};

const SEVERITIES = ["critical", "high", "medium", "low"];

const FIELDS: { key: keyof BugReport; label: string; multiline?: boolean }[] = [
  { key: "title", label: "Title" },
  { key: "steps_to_reproduce", label: "Steps to reproduce", multiline: true },
  { key: "expected_behavior", label: "Expected behavior", multiline: true },
  { key: "actual_behavior", label: "Actual behavior", multiline: true },
  { key: "environment", label: "Environment" },
];

export function BugReportForm({ proposed, respond, result, onSubmit }: BugReportFormProps) {
  const [form, setForm] = useState<BugReport>(proposed);

  useEffect(() => {
    setForm(proposed);
  }, [proposed]);

  const submit = () => {
    onSubmit?.(form);
    respond?.(form);
  };

  if (result) {
    let submitted: BugReport = {};
    try {
      submitted = JSON.parse(result);
    } catch {
      submitted = form;
    }
    return (
      <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12, margin: "8px 0" }}>
        Bug report submitted: <strong>{submitted.title ?? form.title}</strong>{" "}
        <span style={{ color: "#888" }}>({submitted.severity ?? form.severity})</span>
      </div>
    );
  }

  const update = (key: keyof BugReport, value: string) =>
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
    <div style={{ border: "2px solid #b8860b", borderRadius: 8, padding: 14, margin: "8px 0" }}>
      <strong>Review bug report</strong>
      <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 10 }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span style={{ fontSize: 13, color: "#555" }}>Severity</span>
          <select
            value={form.severity ?? "medium"}
            onChange={(event) => update("severity", event.target.value)}
            style={inputStyle}
          >
            {SEVERITIES.map((severity) => (
              <option key={severity} value={severity}>
                {severity}
              </option>
            ))}
          </select>
        </label>
        {FIELDS.map((field) => (
          <label key={field.key} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span style={{ fontSize: 13, color: "#555" }}>{field.label}</span>
            {field.multiline ? (
              <textarea
                value={form[field.key] ?? ""}
                onChange={(event) => update(field.key, event.target.value)}
                rows={2}
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
      <button
        onClick={submit}
        disabled={!respond}
        style={{ marginTop: 12, padding: "6px 14px" }}
      >
        Submit bug report
      </button>
    </div>
  );
}
