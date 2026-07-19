"use client";

type EstimateItem = {
  story_id?: string;
  points?: number;
  confidence?: string;
};

export function EstimateTable({ items }: { items?: EstimateItem[] }) {
  if (!items || items.length === 0) {
    return <div style={{ padding: 8, color: "#888" }}>Estimating…</div>;
  }
  return (
    <table style={{ borderCollapse: "collapse", margin: "8px 0", minWidth: 320 }}>
      <thead>
        <tr>
          {["Story", "Points", "Confidence"].map((heading) => (
            <th
              key={heading}
              style={{ border: "1px solid #ddd", padding: "6px 12px", textAlign: "left" }}
            >
              {heading}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {items.map((item, index) => (
          <tr key={item.story_id ?? index}>
            <td style={{ border: "1px solid #ddd", padding: "6px 12px" }}>{item.story_id}</td>
            <td style={{ border: "1px solid #ddd", padding: "6px 12px" }}>{item.points}</td>
            <td style={{ border: "1px solid #ddd", padding: "6px 12px" }}>{item.confidence}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
