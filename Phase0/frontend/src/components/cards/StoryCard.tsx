"use client";

type Story = {
  id?: string;
  title?: string;
  acceptance_criteria?: string[];
  priority?: string;
};

const PRIORITY_COLORS: Record<string, string> = {
  high: "#c0392b",
  medium: "#d68910",
  low: "#1e8449",
};

export function StoryCard({ stories }: { stories?: Story[] }) {
  if (!stories || stories.length === 0) {
    return <div style={{ padding: 8, color: "#888" }}>Drafting user stories…</div>;
  }
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10, margin: "8px 0" }}>
      {stories.map((story, index) => (
        <div
          key={story.id ?? index}
          style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12 }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
            <strong>
              {story.id}: {story.title}
            </strong>
            <span style={{ color: PRIORITY_COLORS[story.priority ?? ""] ?? "#555" }}>
              {story.priority}
            </span>
          </div>
          <ul style={{ margin: "8px 0 0 18px" }}>
            {(story.acceptance_criteria ?? []).map((criterion, i) => (
              <li key={i}>{criterion}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
