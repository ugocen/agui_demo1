"use client";

import { CardTitle, Chip, Placeholder, cardBox, type Tone } from "@/components/cards/storyPrimitives";

type Criterion = {
  title?: string;
  given?: string[];
  when?: string[];
  then?: string[];
  but?: string[];
  source?: string;
  status?: string;
};

type StoryCriteriaCardProps = {
  persona?: string;
  goal?: string;
  benefit?: string;
  coverage?: string;
  acceptance_criteria?: Criterion[];
};

type ClauseProps = { lead: string; items?: string[]; continuation?: string; indentAll?: boolean };

const muted: React.CSSProperties = { color: "#888" };
const keyword: React.CSSProperties = {
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
  fontWeight: 700,
  marginRight: 6,
};

/** The props are agent JSON, so a "string" can arrive as a number or null: coerce, then trim. */
const clean = (value?: string) => String(value ?? "").trim();

function statusTone(status?: string): Tone {
  const value = clean(status).toLowerCase();
  if (value === "validated") return "good";
  if (value === "needs_fix") return "bad";
  return "neutral";
}

function CoverageChip({ coverage }: { coverage?: string }) {
  const note = clean(coverage);
  if (!note) return null;
  if (note.toLowerCase() === "complete") return <Chip tone="good">covers all criteria</Chip>;
  return <Chip tone="warn">{note}</Chip>;
}

/** One keyword group: `lead` on the first line, `continuation` (indented) on the rest. */
function ClauseGroup({ lead, items, continuation = "AND", indentAll = false }: ClauseProps) {
  const lines = (items ?? []).filter((text) => String(text ?? "").trim() !== "");
  if (lines.length === 0) return null;
  return (
    <>
      {lines.map((text, index) => {
        const indented = indentAll || index > 0;
        return (
          <div key={index} style={{ paddingLeft: indented ? 20 : 0, margin: "2px 0" }}>
            <span style={keyword}>{indented ? continuation : lead}</span>
            {text}
          </div>
        );
      })}
    </>
  );
}

export function StoryCriteriaCard(props: StoryCriteriaCardProps) {
  const story = [
    { lead: "As a ", value: clean(props.persona), comma: true },
    { lead: "I want to ", value: clean(props.goal), comma: false },
    { lead: "So that ", value: clean(props.benefit), comma: false },
  ];
  // A line whose content has not streamed in yet would render as a bare
  // connective (and "As a" would trail a stray comma), so hold it back.
  const told = story.filter((line) => line.value !== "");
  const coverage = clean(props.coverage);
  const criteria = props.acceptance_criteria ?? [];
  if (criteria.length === 0 && told.length === 0 && coverage === "") {
    return <Placeholder>Writing acceptance criteria…</Placeholder>;
  }

  return (
    <div>
      {told.length > 0 || coverage !== "" ? (
        <div style={{ ...cardBox, display: "flex", justifyContent: "space-between", gap: 8 }}>
          <div style={{ lineHeight: 1.6 }}>
            {told.map((line) => (
              <div key={line.lead}>
                <span style={muted}>{line.lead}</span>
                <strong>{line.value}</strong>
                {line.comma ? <span style={muted}>,</span> : null}
              </div>
            ))}
          </div>
          <CoverageChip coverage={coverage} />
        </div>
      ) : null}

      {criteria.length === 0 ? <Placeholder>Writing acceptance criteria…</Placeholder> : null}
      {/* Numbered by position — flat, continuous numbering is a spec rule, so the data
          never gets a say in it. */}
      {criteria.map((criterion, index) => {
        // A streaming delta can land a null/partial entry in the array, so every
        // field is read through `?.` — one null would otherwise take the card down.
        const title = clean(criterion?.title);
        const status = clean(criterion?.status);
        const source = clean(criterion?.source);
        return (
          <div key={index} style={cardBox}>
            <CardTitle
              title={`AC ${index + 1}${title ? `- ${title}` : ""}`}
              right={
                <>
                  {source ? <Chip>{source}</Chip> : null}
                  {status ? <Chip tone={statusTone(status)}>{status}</Chip> : null}
                </>
              }
            />
            <ClauseGroup lead="GIVEN that" items={criterion?.given} />
            <ClauseGroup lead="WHEN" items={criterion?.when} />
            <ClauseGroup lead="THEN" items={criterion?.then} />
            <ClauseGroup lead="BUT" continuation="BUT" indentAll items={criterion?.but} />
          </div>
        );
      })}
    </div>
  );
}
