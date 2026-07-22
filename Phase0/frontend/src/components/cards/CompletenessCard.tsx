"use client";

import { CardTitle, Chip, Placeholder, cardBox, subtleLabel } from "@/components/cards/storyPrimitives";

type Finding = {
  ac_id?: string;
  category?: number;
  gap?: string;
  is_mechanical?: boolean;
  resolution?: string;
};

const CATEGORY_LABELS: Record<number, string> = {
  1: "Empty, none, zero",
  2: "Search, filter, sort scope",
  3: "Transition state and context",
  4: "Type and fallback",
  5: "Role and persona difference",
  6: "Ownership and source",
};

const CATEGORY_IDS = Object.keys(CATEGORY_LABELS)
  .map(Number)
  .sort((a, b) => a - b);

export function CompletenessCard({ findings }: { findings?: Finding[] }) {
  const all = findings ?? [];
  if (all.length === 0) {
    return <Placeholder>Checking boundary cases…</Placeholder>;
  }

  const resolved = all.filter((finding) => finding.is_mechanical).length;
  const escalated = all.length - resolved;

  // A finding whose category is missing or outside 1..6 still has to be seen, so the
  // known categories are followed by an "Other" bucket that catches everything else.
  const groups = CATEGORY_IDS.map((id) => ({
    heading: `${id}. ${CATEGORY_LABELS[id]}`,
    items: all.filter((finding) => finding.category === id),
  }))
    .concat([
      {
        heading: "Other",
        items: all.filter(
          (finding) => finding.category === undefined || !CATEGORY_IDS.includes(finding.category),
        ),
      },
    ])
    .filter((group) => group.items.length > 0);

  return (
    <div style={cardBox}>
      <CardTitle
        title="Completeness"
        right={
          <>
            {resolved > 0 ? <Chip tone="good">{resolved} resolved</Chip> : null}
            {escalated > 0 ? <Chip tone="warn">{escalated} need a decision</Chip> : null}
          </>
        }
      />
      {groups.map((group) => (
        <div key={group.heading} style={{ marginTop: 10 }}>
          <div style={subtleLabel}>{group.heading}</div>
          {group.items.map((finding, index) => {
            // Trimmed, because a whitespace-only resolution is an empty one: it would
            // otherwise print the "resolved by default:" colon with nothing after it.
            const acId = (finding.ac_id ?? "").trim();
            const resolution = (finding.resolution ?? "").trim();
            return (
              <div key={index} style={{ padding: "4px 0" }}>
                {acId ? (
                  <>
                    <Chip>{acId}</Chip>{" "}
                  </>
                ) : null}
                <span>{finding.gap ?? ""}</span>
                <div style={{ marginTop: 3 }}>
                  {finding.is_mechanical ? (
                    <>
                      <Chip tone="good">
                        {resolution !== "" ? "resolved by default:" : "resolved by default"}
                      </Chip>
                      {resolution !== "" ? <span> {resolution}</span> : null}
                    </>
                  ) : (
                    <Chip tone="warn">needs a business decision</Chip>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
