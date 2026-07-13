"use client";

type ChecklistItem = { name?: string; status?: string; detail?: string };

const STATUS_ICONS: Record<string, string> = {
  pass: "✅",
  warn: "⚠️",
  fail: "❌",
};

export function ChecklistCard({ release, items }: { release?: string; items?: ChecklistItem[] }) {
  if (!items || items.length === 0) {
    return <div style={{ padding: 8, color: "#888" }}>Collecting checks…</div>;
  }
  return (
    <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12, margin: "8px 0" }}>
      <strong>Release checklist, {release}</strong>
      <ul style={{ listStyle: "none", margin: "8px 0 0", padding: 0 }}>
        {items.map((item, index) => (
          <li key={index} style={{ padding: "3px 0" }}>
            {STATUS_ICONS[item.status ?? ""] ?? "•"} <strong>{item.name}</strong> — {item.detail}
          </li>
        ))}
      </ul>
    </div>
  );
}
