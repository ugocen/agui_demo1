"use client";

/**
 * Shared visual vocabulary for the story-writing cards.
 *
 * The four original cards each inlined their own borders and colours, which was
 * fine at four and stops being fine at ten: the same "this passed / this needs a
 * decision" idea would end up three different greens. So the tones are named
 * once here, and a card picks a tone rather than a hex.
 *
 * Inline styles, deliberately — every card in this directory is styled inline
 * and `globals.css` is app chrome, not card CSS. Following the existing idiom
 * keeps a card readable next to its neighbours instead of introducing a second
 * styling system for one feature.
 */

export type Tone = "neutral" | "info" | "good" | "warn" | "bad";

const TONES: Record<Tone, { fg: string; bg: string; border: string }> = {
  neutral: { fg: "#555", bg: "#f4f4f6", border: "#dcdce2" },
  info: { fg: "#1f5f9e", bg: "#eaf2fb", border: "#c3daf1" },
  good: { fg: "#1e8449", bg: "#eaf6ee", border: "#c2e3ce" },
  warn: { fg: "#a86400", bg: "#fdf3e3", border: "#f0dcb4" },
  bad: { fg: "#c0392b", bg: "#fdeeec", border: "#f3cdc7" },
};

export const cardBox: React.CSSProperties = {
  border: "1px solid #ddd",
  borderRadius: 8,
  padding: 12,
  margin: "8px 0",
  fontSize: 14,
};

export const subtleLabel: React.CSSProperties = {
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  color: "#888",
  marginBottom: 4,
};

export function Placeholder({ children }: { children: React.ReactNode }) {
  return <div style={{ padding: 8, color: "#888" }}>{children}</div>;
}

export function Chip({ tone = "neutral", children }: { tone?: Tone; children: React.ReactNode }) {
  const palette = TONES[tone] ?? TONES.neutral;
  return (
    <span
      style={{
        display: "inline-block",
        padding: "1px 8px",
        borderRadius: 999,
        fontSize: 12,
        lineHeight: "18px",
        color: palette.fg,
        background: palette.bg,
        border: `1px solid ${palette.border}`,
        whiteSpace: "nowrap",
        // A chip is almost always placed in a flex row, where the default
        // `align-items: stretch` makes it as TALL as its tallest sibling. Next to
        // a three-line user story that turned the 999px radius into a giant green
        // disc with the label stranded at the top of it. Chips size to their own
        // text, always — so the chip itself opts out rather than relying on every
        // parent to remember `alignItems`.
        alignSelf: "flex-start",
      }}
    >
      {children}
    </span>
  );
}

export function CardTitle({ title, right }: { title: string; right?: React.ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: 8,
        marginBottom: 8,
      }}
    >
      <strong>{title}</strong>
      {right ? <span style={{ display: "flex", gap: 6 }}>{right}</span> : null}
    </div>
  );
}

/**
 * Turn one raw agent value into text that is safe to render.
 *
 * Card props are unvalidated model output: `useRenderTool` hands a card the tool
 * call's arguments as they stream, so a field declared `string[]` can arrive
 * holding a number, a null, or an object — and a list streaming in as
 * `[{"name": "Results"` parses to `[{}]` for a frame or two on the way. React
 * throws on an object child and takes the whole chat down with it, so no agent
 * value may reach JSX without passing through here first.
 *
 * An object is flattened to its leaf text rather than dropped, because the model
 * did see something and showing it imperfectly beats losing it silently in a
 * card whose whole job is fidelity. Anything carrying no text at all — `{}`,
 * `[]`, null — comes back "" so the caller can drop it.
 */
export function displayText(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return joinText(value, ", ");
  if (typeof value === "object") return joinText(Object.values(value), " — ");
  return "";
}

function joinText(values: unknown[], separator: string): string {
  return values
    .map(displayText)
    .filter((text) => text.trim() !== "")
    .join(separator);
}

/**
 * An agent list as renderable text, blanks dropped. A bare value counts as a
 * one-item list — a model asked for a list sometimes sends a single string, and
 * that is content, not an error.
 *
 * Items are emptiness-tested trimmed but returned untrimmed: a card may show
 * wording the user checks character by character against a screenshot, in a
 * `pre-wrap` box where a stray leading space is a real difference rather than
 * noise. Test with `.trim()`, keep the bytes.
 */
export function textList(items?: unknown): string[] {
  const values = Array.isArray(items) ? items : items === null || items === undefined ? [] : [items];
  return values.map(displayText).filter((text) => text.trim() !== "");
}

/** A labelled block that renders nothing at all when it has no items. */
export function ListSection({ label, items }: { label: string; items?: unknown }) {
  // `unknown`, not `string[]`: the declared type is what the agent is supposed to
  // send, and this is where that stops being an assumption.
  const filled = textList(items);
  if (filled.length === 0) return null;
  return (
    <div style={{ marginTop: 10 }}>
      <div style={subtleLabel}>{label}</div>
      <ul style={{ margin: "0 0 0 18px", padding: 0 }}>
        {filled.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
    </div>
  );
}
