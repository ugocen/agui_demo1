"use client";

import {
  Chip,
  CardTitle,
  ListSection,
  Placeholder,
  cardBox,
  subtleLabel,
} from "@/components/cards/storyPrimitives";

type DesignContextProps = {
  screen_name?: string;
  fields_and_controls?: string[];
  visible_states?: string[];
  visible_messages?: string[];
  lists_or_tables?: string[];
  roles_or_modes?: string[];
  uncertain?: string[];
};

const MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

/** Warn palette, copied from the shared TONES table so the block matches a warn Chip. */
const WARN = { fg: "#a86400", bg: "#fdf3e3", border: "#f0dcb4" };

function clean(items?: string[]): string[] {
  return (items ?? []).map((item) => String(item ?? "").trim()).filter((item) => item !== "");
}

/**
 * Like `clean`, but never touches the string itself — blank entries are dropped and
 * everything else is left byte for byte. The message block exists so the user can
 * check the wording against the screenshot character by character, and the box it
 * renders in is `pre-wrap`, so a stray leading or trailing space in the real UI is
 * visible there. Trimming would quietly show wording the screenshot does not have.
 */
function verbatim(items?: string[]): string[] {
  return (items ?? []).map((item) => String(item ?? "")).filter((item) => item.trim() !== "");
}

export function DesignContextCard(props: DesignContextProps) {
  const screenName = (props.screen_name ?? "").trim();
  const messages = verbatim(props.visible_messages);
  const uncertain = clean(props.uncertain);
  const hasAnything =
    screenName !== "" ||
    messages.length > 0 ||
    uncertain.length > 0 ||
    clean(props.fields_and_controls).length > 0 ||
    clean(props.visible_states).length > 0 ||
    clean(props.lists_or_tables).length > 0 ||
    clean(props.roles_or_modes).length > 0;

  if (!hasAnything) {
    return <Placeholder>Reading the screenshot…</Placeholder>;
  }

  return (
    <div style={cardBox}>
      <CardTitle
        title={screenName ? `Screen facts — ${screenName}` : "Screen facts"}
        right={<Chip tone="info">read from screenshot</Chip>}
      />

      <ListSection label="Fields and controls" items={props.fields_and_controls} />
      <ListSection label="Visible states" items={props.visible_states} />
      <ListSection label="Lists and tables" items={props.lists_or_tables} />
      <ListSection label="Roles and modes" items={props.roles_or_modes} />

      {messages.length > 0 ? (
        <div style={{ marginTop: 10 }}>
          <div style={subtleLabel}>Exact message text</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {messages.map((message, index) => (
              <code
                key={index}
                style={{
                  fontFamily: MONO,
                  fontSize: 13,
                  background: "#f4f4f6",
                  border: "1px solid #dcdce2",
                  borderRadius: 4,
                  padding: "2px 6px",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                }}
              >
                {`"${message}"`}
              </code>
            ))}
          </div>
        </div>
      ) : null}

      {uncertain.length > 0 ? (
        <div
          style={{
            marginTop: 10,
            background: WARN.bg,
            border: `1px solid ${WARN.border}`,
            borderRadius: 6,
            padding: "8px 10px",
          }}
        >
          <div style={{ ...subtleLabel, color: WARN.fg }}>Not certain — please confirm</div>
          <ul style={{ margin: "0 0 0 18px", padding: 0, color: WARN.fg }}>
            {uncertain.map((item, index) => (
              <li key={index}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
