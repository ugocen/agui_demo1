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

/** A labelled block that renders nothing at all when it has no items. */
export function ListSection({ label, items }: { label: string; items?: string[] }) {
  const filled = (items ?? []).filter((item) => String(item ?? "").trim() !== "");
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
