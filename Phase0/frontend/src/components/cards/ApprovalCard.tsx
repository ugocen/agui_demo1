"use client";

import { useState } from "react";

type Ticket = { title?: string; points?: number };

type ApprovalCardProps = {
  summary?: string;
  tickets?: Ticket[];
  respond?: (result: unknown) => Promise<void>;
  result?: string;
};

export function ApprovalCard({ summary, tickets, respond, result }: ApprovalCardProps) {
  const [note, setNote] = useState("");

  if (result) {
    let decision = result;
    try {
      decision = JSON.parse(result).decision ?? result;
    } catch {
      // plain string result
    }
    return (
      <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12, margin: "8px 0" }}>
        Ticket approval decision: <strong>{String(decision)}</strong>
      </div>
    );
  }

  const decide = (decision: "approved" | "rejected") => {
    if (!respond) {
      return;
    }
    if (decision === "approved") {
      // Phase 0 simulates ticket creation, this log line stands in for it.
      console.log("SIMULATED ticket creation:", tickets);
    }
    respond({ decision, note: note || undefined });
  };

  return (
    <div style={{ border: "2px solid #2c6fbb", borderRadius: 8, padding: 12, margin: "8px 0" }}>
      <strong>Ticket approval required</strong>
      <p>{summary}</p>
      <ul style={{ margin: "4px 0 12px 18px" }}>
        {(tickets ?? []).map((ticket, index) => (
          <li key={index}>
            {ticket.title} ({ticket.points} pts)
          </li>
        ))}
      </ul>
      <input
        placeholder="Optional note"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        style={{ marginRight: 8, padding: 4 }}
      />
      <button onClick={() => decide("approved")} disabled={!respond} style={{ marginRight: 8 }}>
        Approve
      </button>
      <button onClick={() => decide("rejected")} disabled={!respond}>
        Reject
      </button>
    </div>
  );
}
