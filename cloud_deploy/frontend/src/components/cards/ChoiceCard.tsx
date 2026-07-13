"use client";

type ChoiceCardProps = {
  question: string;
  options: string[];
  respond?: (result: unknown) => Promise<void>;
  result?: string;
};

/** A multiple-choice question the user answers by clicking one option. Used by
 *  agents to resolve ambiguity (tone, audience, angle…) before/while drafting. */
export function ChoiceCard({ question, options, respond, result }: ChoiceCardProps) {
  if (result) {
    return (
      <div style={{ border: "1px solid #ddd", borderRadius: 8, padding: 12, margin: "8px 0" }}>
        <span style={{ color: "#555" }}>{question}</span> → <strong>{result}</strong>
      </div>
    );
  }

  return (
    <div style={{ border: "2px solid #6d5ef3", borderRadius: 8, padding: 14, margin: "8px 0" }}>
      <div style={{ fontWeight: 600, marginBottom: 10 }}>{question}</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {options.map((option) => (
          <button
            key={option}
            className="ghost-btn"
            disabled={!respond}
            onClick={() => respond?.(option)}
            style={{ padding: "6px 14px", borderRadius: 999 }}
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}
