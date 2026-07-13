"use client";

import { useState } from "react";

type DecisionPayload = {
  recommendation?: "go" | "no-go" | string;
  reasons?: string[];
};

type DecisionCardProps = {
  payload: DecisionPayload;
  resolve: (value: unknown) => void;
};

export function DecisionCard({ payload, resolve }: DecisionCardProps) {
  const [note, setNote] = useState("");
  const recommendation = payload.recommendation ?? "unknown";

  const decide = (decision: "go" | "no-go") => {
    resolve({ decision, note: note || undefined });
  };

  return (
    <div style={{ border: "2px solid #7d3c98", borderRadius: 8, padding: 12, margin: "8px 0" }}>
      <strong>Go / No-Go decision required</strong>
      <p>
        Agent recommendation:{" "}
        <span style={{ color: recommendation === "go" ? "#1e8449" : "#c0392b", fontWeight: 700 }}>
          {recommendation.toUpperCase()}
        </span>
      </p>
      <ul style={{ margin: "4px 0 12px 18px" }}>
        {(payload.reasons ?? []).map((reason, index) => (
          <li key={index}>{reason}</li>
        ))}
      </ul>
      <input
        placeholder="Optional note"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        style={{ marginRight: 8, padding: 4 }}
      />
      <button onClick={() => decide("go")} style={{ marginRight: 8 }}>
        Go
      </button>
      <button onClick={() => decide("no-go")}>No-Go</button>
    </div>
  );
}
