"use client";

/**
 * Rich A2UI catalog — extends the renderer's basic catalog (Text, Card, Row,
 * Column, Button, …) with a few *grammar-based* components that each cover a
 * huge surface with one component:
 *
 *   - Mermaid  → any diagram (flowchart, sequence, gantt, class, state, ER…)
 *   - Chart    → any chart (bar, line, pie, doughnut, radar, polarArea) via Chart.js
 *   - Markdown → tables + rich text
 *   - Html     → open-ended escape hatch (sandboxed via DOMPurify)
 *
 * Wired into <CopilotKitProvider a2ui={{ catalog: richCatalog, includeSchema: true }}>.
 * `includeSchema` sends these component schemas (below) to the agent so its LLM
 * knows they exist and what props they take — which is why the Zod fields carry
 * `.describe(...)`.
 *
 * Schemas are built with `zod/v3` (not the app's default zod v4) because A2UI's
 * GenericBinder + schema extraction read zod v3 internals (`_def.typeName` /
 * `_def.shape()`). Heavy browser-only libs (mermaid/chart.js/dompurify/marked)
 * are `import()`-ed inside effects so they stay out of SSR and the initial bundle.
 */

import { createCatalog } from "@copilotkit/a2ui-renderer";
import { useEffect, useId, useRef, useState } from "react";
import { z } from "zod/v3";

export const RICH_CATALOG_ID = "copilotkit://rich-catalog";

// A soft, theme-friendly palette for chart series (falls back / cycles).
const CHART_PALETTE = [
  "#6d5ef3",
  "#d6457b",
  "#d6453d",
  "#2fa8a1",
  "#e0a83d",
  "#4f8ef7",
  "#8a5cf6",
  "#3fb27f",
];

// ---------------------------------------------------------------------------
// Shared frame: optional title + a bordered surface that matches the app theme.
// ---------------------------------------------------------------------------
function Frame({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-md, 12px)",
        background: "var(--surface, #fff)",
        padding: 16,
        margin: "4px 0",
        overflowX: "auto",
      }}
    >
      {title ? (
        <div
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: "var(--text-secondary, #63636e)",
            marginBottom: 10,
          }}
        >
          {title}
        </div>
      ) : null}
      {children}
    </div>
  );
}

function ErrorNote({ label, detail }: { label: string; detail?: string }) {
  return (
    <div style={{ color: "var(--accent, #d6453d)", fontSize: 13 }}>
      {label}
      {detail ? <div style={{ color: "var(--text-muted)", marginTop: 4 }}>{detail}</div> : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mermaid — one component covers every mermaid diagram type.
// ---------------------------------------------------------------------------
function MermaidView({ props }: { props: { code?: string; title?: string } }) {
  const code = (props?.code ?? "").trim();
  const ref = useRef<HTMLDivElement>(null);
  const rawId = useId();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!code) return;
    const domId = `mermaid-${rawId.replace(/[^a-zA-Z0-9]/g, "")}`;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "default" });
        const { svg } = await mermaid.render(domId, code);
        if (!cancelled && ref.current) {
          ref.current.innerHTML = svg;
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, rawId]);

  return (
    <Frame title={props?.title}>
      {error ? (
        <ErrorNote label="Diagram could not be rendered" detail={error} />
      ) : (
        <div ref={ref} style={{ display: "flex", justifyContent: "center" }}>
          <span style={{ color: "var(--text-muted)", fontSize: 13 }}>Rendering diagram…</span>
        </div>
      )}
    </Frame>
  );
}

// ---------------------------------------------------------------------------
// Chart — one component covers every Chart.js chart type.
// ---------------------------------------------------------------------------
type ChartDataset = { label?: string; data?: number[] };
function ChartView({
  props,
}: {
  props: {
    chartType?: string;
    labels?: string[];
    datasets?: ChartDataset[];
    title?: string;
  };
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [error, setError] = useState<string | null>(null);

  const chartType = props?.chartType ?? "bar";
  const labels = Array.isArray(props?.labels) ? props.labels : [];
  const datasets = Array.isArray(props?.datasets) ? props.datasets : [];
  const depKey = JSON.stringify({ chartType, labels, datasets });

  useEffect(() => {
    let cancelled = false;
    let instance: { destroy: () => void } | null = null;
    if (!canvasRef.current || datasets.length === 0) return;
    (async () => {
      try {
        const { Chart, registerables } = await import("chart.js");
        Chart.register(...registerables);
        if (cancelled || !canvasRef.current) return;
        const perPoint = ["pie", "doughnut", "polarArea"].includes(chartType);
        const styled = datasets.map((ds, i) => {
          const color = CHART_PALETTE[i % CHART_PALETTE.length];
          const pointColors = (ds.data ?? []).map((_, j) => CHART_PALETTE[j % CHART_PALETTE.length]);
          return {
            label: ds.label ?? `Series ${i + 1}`,
            data: ds.data ?? [],
            backgroundColor: perPoint ? pointColors : color,
            borderColor: color,
            borderWidth: chartType === "line" ? 2 : 1,
            fill: chartType === "line" ? false : undefined,
          };
        });
        instance = new Chart(canvasRef.current, {
          type: chartType as never,
          data: { labels, datasets: styled as never },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: datasets.length > 1 || perPoint } },
          },
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
        } as any);
        setError(null);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
      if (instance) instance.destroy();
    };
  }, [depKey]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Frame title={props?.title}>
      {error ? (
        <ErrorNote label="Chart could not be rendered" detail={error} />
      ) : (
        <div style={{ position: "relative", height: 280, width: "100%" }}>
          <canvas ref={canvasRef} />
        </div>
      )}
    </Frame>
  );
}

// ---------------------------------------------------------------------------
// Markdown — tables + rich text (sanitized).
// ---------------------------------------------------------------------------
function MarkdownView({ props }: { props: { content?: string; title?: string } }) {
  const content = props?.content ?? "";
  const [html, setHtml] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [{ marked }, DOMPurify] = await Promise.all([
        import("marked"),
        import("dompurify").then((m) => m.default),
      ]);
      const parsed = await marked.parse(content);
      if (!cancelled) setHtml(DOMPurify.sanitize(parsed));
    })();
    return () => {
      cancelled = true;
    };
  }, [content]);

  return (
    <Frame title={props?.title}>
      <div className="a2ui-markdown" dangerouslySetInnerHTML={{ __html: html }} />
    </Frame>
  );
}

// ---------------------------------------------------------------------------
// Html — open-ended escape hatch (sandboxed via DOMPurify).
// ---------------------------------------------------------------------------
function HtmlView({ props }: { props: { html?: string; title?: string } }) {
  const raw = props?.html ?? "";
  const [clean, setClean] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const DOMPurify = (await import("dompurify")).default;
      if (!cancelled) setClean(DOMPurify.sanitize(raw));
    })();
    return () => {
      cancelled = true;
    };
  }, [raw]);

  return (
    <Frame title={props?.title}>
      <div dangerouslySetInnerHTML={{ __html: clean }} />
    </Frame>
  );
}

// ---------------------------------------------------------------------------
// Definitions (model-facing schema) + renderers, merged with the basic catalog.
// ---------------------------------------------------------------------------
const definitions = {
  Mermaid: {
    description:
      "Render a diagram from Mermaid source. Use for flowcharts, sequence, gantt, class, state, ER and other diagrams.",
    props: z.object({
      code: z
        .string()
        .describe("Mermaid diagram source, e.g. 'graph TD; A-->B;' or 'sequenceDiagram ...'"),
      title: z.string().optional().describe("Optional heading shown above the diagram"),
    }),
  },
  Chart: {
    description:
      "Render a chart with Chart.js. Use for bar/line/pie/doughnut/radar/polarArea visualizations of numeric data.",
    props: z.object({
      chartType: z
        .enum(["bar", "line", "pie", "doughnut", "radar", "polarArea"])
        .describe("Chart type"),
      labels: z.array(z.string()).describe("X-axis / category labels, one per data point"),
      datasets: z
        .array(
          z.object({
            label: z.string().optional().describe("Series name (shown in legend)"),
            data: z.array(z.number()).describe("Numeric values, aligned to labels"),
          })
        )
        .describe("One or more data series"),
      title: z.string().optional().describe("Optional heading shown above the chart"),
    }),
  },
  Markdown: {
    description: "Render Markdown text, including tables and lists. Good for structured explanations.",
    props: z.object({
      content: z.string().describe("Markdown source"),
      title: z.string().optional().describe("Optional heading shown above the content"),
    }),
  },
  Html: {
    description:
      "Render sanitized HTML. Escape hatch for rich content not covered by other components. Avoid scripts.",
    props: z.object({
      html: z.string().describe("HTML markup (sanitized before rendering)"),
      title: z.string().optional().describe("Optional heading shown above the content"),
    }),
  },
};

const renderers = {
  Mermaid: MermaidView,
  Chart: ChartView,
  Markdown: MarkdownView,
  Html: HtmlView,
};

/** Basic catalog (Text/Card/Row/Column/Button/…) + the rich components above. */
export const richCatalog = createCatalog(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  definitions as any,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  renderers as any,
  { includeBasicCatalog: true, catalogId: RICH_CATALOG_ID }
);
