"use client";

import { CardTitle, Chip, Placeholder, cardBox, subtleLabel } from "@/components/cards/storyPrimitives";

type ChecklistResult = { item_id?: number; status?: string; reason?: string };

/** The semantic items the model grades. Format items are checked in Python and never arrive here. */
const ITEM_NAMES: Record<number, string> = {
  2: "Uses As / I want to / So that",
  3: "Persona is specific",
  4: "So that shows business value",
  5: "Story covers all criteria",
  6: "Story is clear and concise",
  15: "All criteria testable through observable output",
  16: "No non-observable criteria",
  17: "No hardcoded test data",
  18: "No invented information",
  19: "Descriptive language",
  20: "Specific",
  21: "Measurable",
  22: "Achievable",
  23: "Relevant",
  24: "Testable",
  25: "Empty and no-match results stated",
  26: "Search, filter and sort scope stated",
  27: "Transition behaviour stated",
  28: "Owning system named",
  29: "Role differences stated",
  30: "Validation condition, message and outcome stated",
};

const GROUPS: { label: string; ids: number[] }[] = [
  { label: "User story", ids: [2, 3, 4, 5, 6] },
  { label: "Content", ids: [15, 16, 17, 18, 19] },
  { label: "S.M.A.R.T.", ids: [20, 21, 22, 23, 24] },
  { label: "Completeness", ids: [25, 26, 27, 28, 29, 30] },
];

const GROUPED_IDS = new Set(GROUPS.flatMap((group) => group.ids));

const statusOf = (item: ChecklistResult) => String(item.status ?? "").trim().toUpperCase();
const isPass = (item: ChecklistResult) => statusOf(item) === "PASS";
// Absent status means "not graded yet", not "failed" — the props arrive as a partial
// stream, so an item lands before its verdict does. Treating that as a failure paints
// the whole card red for the length of the stream.
const isFail = (item: ChecklistResult) => statusOf(item) !== "" && !isPass(item);
const nameOf = (id?: number) => (id === undefined ? "Ungraded item" : (ITEM_NAMES[id] ?? `Item ${id}`));
const reasonOf = (item: ChecklistResult) => String(item.reason ?? "").trim();
/** A streaming delta can land the object before any of its fields; that is not an item yet. */
const isBlank = (item: ChecklistResult) =>
  item.item_id === undefined && statusOf(item) === "" && reasonOf(item) === "";

export function ChecklistScorecard({ items, loop }: { items?: ChecklistResult[]; loop?: number }) {
  const graded = (items ?? []).filter((item) => Boolean(item) && !isBlank(item));
  if (graded.length === 0) {
    return <Placeholder>Reviewing the story…</Placeholder>;
  }

  const passed = graded.filter(isPass).length;
  const failed = graded.filter(isFail);
  const rows = [
    ...GROUPS.map((group) => ({
      label: group.label,
      members: graded.filter((item) => item.item_id !== undefined && group.ids.includes(item.item_id)),
    })),
    // Anything the model graded outside the known groups still has to be visible.
    { label: "Other", members: graded.filter((i) => i.item_id === undefined || !GROUPED_IDS.has(i.item_id)) },
  ].filter((row) => row.members.length > 0);

  return (
    <div style={cardBox}>
      <CardTitle
        title="Checklist"
        right={
          <>
            <Chip tone={failed.length === 0 ? "good" : "bad"}>
              {passed} of {graded.length} passing
            </Chip>
            {(loop ?? 0) > 0 ? <Chip tone="neutral">repair loop {loop}</Chip> : null}
          </>
        }
      />
      {rows.map((row) => (
        <div key={row.label} style={{ marginTop: 8 }}>
          <div style={subtleLabel}>{row.label}</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {row.members.map((item, index) => {
              const why = isFail(item) ? reasonOf(item) : "";
              // Chip takes no title prop, so the hover explanation lives on a wrapper.
              return (
                <span
                  key={`${item.item_id ?? "x"}-${index}`}
                  title={why ? `${nameOf(item.item_id)} — ${why}` : nameOf(item.item_id)}
                >
                  <Chip tone={isPass(item) ? "good" : isFail(item) ? "bad" : "neutral"}>
                    {item.item_id ?? "?"}
                  </Chip>
                </span>
              );
            })}
          </div>
        </div>
      ))}
      {failed.length > 0 ? (
        <div style={{ marginTop: 10 }}>
          <div style={subtleLabel}>Failed</div>
          {failed.map((item, index) => (
            <div key={`${item.item_id ?? "f"}-${index}`} style={{ marginBottom: 6 }}>
              <div>
                {item.item_id ?? "?"}. {nameOf(item.item_id)}
              </div>
              {reasonOf(item) !== "" ? <div style={{ color: "#888" }}>{reasonOf(item)}</div> : null}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
