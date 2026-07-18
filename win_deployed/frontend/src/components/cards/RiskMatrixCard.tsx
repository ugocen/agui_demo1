"use client";

type Risk = {
  name?: string;
  probability?: number;
  impact?: number;
  mitigation?: string;
};

function riskColor(score: number): string {
  if (score >= 12) {
    return "#c0392b";
  }
  if (score >= 6) {
    return "#d68910";
  }
  return "#1e8449";
}

export function RiskMatrixCard({ risks }: { risks?: Risk[] }) {
  if (!risks || risks.length === 0) {
    return <div style={{ padding: 8, color: "#888" }}>Assessing risks…</div>;
  }
  return (
    <table style={{ borderCollapse: "collapse", margin: "8px 0", minWidth: 420 }}>
      <thead>
        <tr>
          {["Risk", "P", "I", "Score", "Mitigation"].map((heading) => (
            <th
              key={heading}
              style={{ border: "1px solid #ddd", padding: "6px 10px", textAlign: "left" }}
            >
              {heading}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {risks.map((risk, index) => {
          const score = (risk.probability ?? 0) * (risk.impact ?? 0);
          return (
            <tr key={index}>
              <td style={{ border: "1px solid #ddd", padding: "6px 10px" }}>{risk.name}</td>
              <td style={{ border: "1px solid #ddd", padding: "6px 10px" }}>{risk.probability}</td>
              <td style={{ border: "1px solid #ddd", padding: "6px 10px" }}>{risk.impact}</td>
              <td
                style={{
                  border: "1px solid #ddd",
                  padding: "6px 10px",
                  color: riskColor(score),
                  fontWeight: 600,
                }}
              >
                {score}
              </td>
              <td style={{ border: "1px solid #ddd", padding: "6px 10px" }}>{risk.mitigation}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
