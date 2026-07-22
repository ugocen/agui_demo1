"use client";

import { CardTitle, Chip, ListSection, Placeholder, cardBox, subtleLabel } from "@/components/cards/storyPrimitives";

type BusinessDecision = {
  question?: string;
  recommended_default?: string;
  context?: string;
  blocking?: boolean;
};

type StoryReportCardProps = {
  changes_made?: string[];
  open_business_decisions?: BusinessDecision[];
  recommendations?: string[];
};

const text = (value?: string) => String(value ?? "").trim();

const decisionBox: React.CSSProperties = { border: "1px solid #ddd", borderRadius: 8, padding: 12, margin: "8px 0" };

const decisionHead: React.CSSProperties = {
  display: "flex",
  alignItems: "baseline",
  justifyContent: "space-between",
  gap: 8,
};

export function StoryReportCard({
  changes_made,
  open_business_decisions,
  recommendations,
}: StoryReportCardProps) {
  const changes = (changes_made ?? []).filter((entry) => text(entry) !== "");
  const advice = (recommendations ?? []).filter((entry) => text(entry) !== "");
  // A streaming delta can land a decision object before any of its fields
  // arrive; an all-empty one would render as an empty bordered block.
  const decisions = (open_business_decisions ?? []).filter(
    (d) => text(d?.question) + text(d?.recommended_default) + text(d?.context) !== "",
  );
  const blocking = decisions.filter((d) => d?.blocking === true).length;

  if (changes.length === 0 && decisions.length === 0 && advice.length === 0) {
    return <Placeholder>Preparing the report…</Placeholder>;
  }

  return (
    <div style={cardBox}>
      <CardTitle
        title="Report"
        right={
          <>
            {changes.length > 0 ? <Chip>{changes.length} changes</Chip> : null}
            {decisions.length > 0 ? <Chip tone="warn">{decisions.length} open decisions</Chip> : null}
            {blocking > 0 ? <Chip tone="bad">{blocking} blocking</Chip> : null}
          </>
        }
      />

      <ListSection label="Changes made" items={changes} />

      {decisions.length > 0 ? (
        <div style={{ marginTop: 10 }}>
          <div style={subtleLabel}>Open business decisions</div>
          {decisions.map((decision, index) => (
            <div key={index} style={decisionBox}>
              <div style={decisionHead}>
                <strong>{text(decision?.question)}</strong>
                {decision?.blocking === true ? (
                  <Chip tone="bad">blocking</Chip>
                ) : (
                  <Chip tone="warn">open</Chip>
                )}
              </div>
              {text(decision?.recommended_default) !== "" ? (
                <div style={{ marginTop: 6 }}>
                  <span style={{ color: "#666" }}>Recommended default: </span>
                  {text(decision?.recommended_default)}
                </div>
              ) : null}
              {text(decision?.context) !== "" ? (
                <div style={{ marginTop: 4, color: "#888" }}>{text(decision?.context)}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      <ListSection label="Recommendations" items={advice} />
    </div>
  );
}
