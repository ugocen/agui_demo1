"use client";

import {
  CardTitle,
  Chip,
  ListSection,
  Placeholder,
  cardBox,
  displayText,
  subtleLabel,
  textList,
} from "@/components/cards/storyPrimitives";

type TranscriptionFlag = { token?: string; guess?: string; why?: string };

type IntakeSummaryProps = {
  persona?: string;
  goal?: string;
  benefit?: string;
  problem_statement?: string;
  targets_a_screen?: boolean;
  user_supplied_ac_count?: number;
  backend_notes?: string[];
  frontend_notes?: string[];
  infra_notes?: string[];
  transcription_flags?: TranscriptionFlag[];
};

const mono: React.CSSProperties = {
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
  background: "#f4f4f6",
  border: "1px solid #dcdce2",
  borderRadius: 4,
  padding: "0 4px",
};

const clean = (value?: unknown) => displayText(value).trim();

export function IntakeSummaryCard(props: IntakeSummaryProps) {
  const acCount = props.user_supplied_ac_count ?? 0;
  const flags = (props.transcription_flags ?? []).filter(
    (flag) => clean(flag?.token) !== "" || clean(flag?.guess) !== "",
  );
  const notes = [props.backend_notes, props.frontend_notes, props.infra_notes];

  // Label/value pairs, blanks dropped — a half-streamed intake should show only
  // what has actually arrived, never an empty row waiting to be filled.
  const fields: { label: string; value: string }[] = [
    { label: "Persona", value: clean(props.persona) },
    { label: "Goal", value: clean(props.goal) },
    { label: "Benefit", value: clean(props.benefit) },
    { label: "Problem statement", value: clean(props.problem_statement) },
  ].filter((field) => field.value !== "");

  // Same blank-dropping rule ListSection applies, so "is there anything?" agrees
  // with what renders.
  const hasNotes = notes.some((list) => textList(list).length > 0);
  const empty =
    fields.length === 0 && flags.length === 0 && !hasNotes && !props.targets_a_screen && acCount <= 0;
  if (empty) {
    return <Placeholder>Reading your input…</Placeholder>;
  }

  return (
    <div style={cardBox}>
      <CardTitle
        title="Intake"
        right={
          <>
            {props.targets_a_screen ? <Chip tone="info">targets a screen</Chip> : null}
            {acCount > 0 ? <Chip tone="neutral">{acCount} user criteria</Chip> : null}
            {flags.length > 0 ? <Chip tone="warn">{flags.length} transcription flags</Chip> : null}
          </>
        }
      />

      {fields.map((field) => (
        <div key={field.label} style={{ marginBottom: 8 }}>
          <div style={subtleLabel}>{field.label}</div>
          <div>{field.value}</div>
        </div>
      ))}

      <ListSection label="Backend notes" items={props.backend_notes} />
      <ListSection label="Frontend notes" items={props.frontend_notes} />
      <ListSection label="Infra notes" items={props.infra_notes} />

      {flags.length > 0 ? (
        <div style={{ marginTop: 10 }}>
          <div style={subtleLabel}>Possible mishearings</div>
          <ul style={{ margin: "0 0 0 18px", padding: 0 }}>
            {flags.map((flag, index) => {
              // A half-arrived flag has one side only; show that side rather than an
              // empty monospace box or an arrow pointing at nothing.
              const token = clean(flag.token);
              const guess = clean(flag.guess);
              const why = clean(flag.why);
              return (
                <li key={index}>
                  {token !== "" ? <span style={mono}>{token}</span> : null}
                  {token !== "" && guess !== "" ? " → " : null}
                  {guess !== "" ? <span>{guess}</span> : null}
                  {why !== "" ? <span style={{ color: "#888" }}> — {why}</span> : null}
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
