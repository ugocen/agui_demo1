"use client";

type Progress = { step?: number; total?: number; label?: string };

export function ProgressIndicator({ progress }: { progress?: Progress }) {
  if (!progress || !progress.total) {
    return null;
  }
  const step = progress.step ?? 0;
  const total = progress.total ?? 1;
  const percent = Math.min(100, Math.round((step / total) * 100));
  return (
    <div style={{ padding: "8px 16px", borderBottom: "1px solid #eee" }}>
      <div style={{ fontSize: 13, marginBottom: 4 }}>
        Step {step} of {total}: {progress.label}
      </div>
      <div style={{ background: "#eee", borderRadius: 4, height: 8, maxWidth: 420 }}>
        <div
          style={{
            width: `${percent}%`,
            background: "#2c6fbb",
            height: 8,
            borderRadius: 4,
            transition: "width 300ms",
          }}
        />
      </div>
    </div>
  );
}
