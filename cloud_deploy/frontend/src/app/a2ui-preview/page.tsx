"use client";

import { useState } from "react";

import { A2UISurfaceView, type A2UIOperation } from "@/components/a2ui/A2UISurfaceView";
import { RICH_CATALOG_ID, richCatalog } from "@/components/a2ui/richCatalog";

// Self-contained A2UI v0.9 surfaces — the kind of JSON an `a2ui` agent emits via
// the render_a2ui tool. Painted by the renderer + the RICH catalog (basic +
// Mermaid/Chart/Markdown/Html) with no agent / no Bedrock. Proves the render path,
// including the rich components, works end to end.
const SAMPLE_OPS: A2UIOperation[] = [
  {
    version: "v0.9",
    createSurface: { surfaceId: "preview", catalogId: RICH_CATALOG_ID },
  },
  {
    version: "v0.9",
    updateComponents: {
      surfaceId: "preview",
      components: [
        { id: "root", component: "Card", child: "col" },
        {
          id: "col",
          component: "Column",
          children: ["h", "body", "chart", "diagram", "md", "field", "btn"],
        },
        { id: "h", component: "Text", text: "Rich A2UI live render", variant: "h3" },
        {
          id: "body",
          component: "Text",
          text: "A2UI v0.9 JSON painted by the renderer with the rich catalog — basic components plus Chart, Mermaid and Markdown.",
          variant: "body",
        },
        // Chart (Chart.js) — the component that used to be "Unknown component: BarChart".
        {
          id: "chart",
          component: "Chart",
          title: "Login Activity",
          chartType: "bar",
          labels: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
          datasets: [{ label: "Logins", data: [120, 200, 150, 80, 220, 90, 60] }],
        },
        // Mermaid — one component, any diagram type.
        {
          id: "diagram",
          component: "Mermaid",
          title: "Login flow",
          code: "graph TD; A[User] --> B{Has session?}; B -- yes --> C[Dashboard]; B -- no --> D[Login form]; D --> E[Submit]; E --> B;",
        },
        // Markdown — tables + rich text.
        {
          id: "md",
          component: "Markdown",
          title: "Notes",
          content:
            "**Top days**\n\n| Day | Logins |\n|-----|-------|\n| Fri | 220 |\n| Tue | 200 |\n| Wed | 150 |",
        },
        { id: "field", component: "TextField", label: "Your name", text: { path: "/form/name" } },
        {
          id: "btn",
          component: "Button",
          child: "btnText",
          variant: "primary",
          action: { event: { name: "greet", context: { name: { path: "/form/name" } } } },
        },
        { id: "btnText", component: "Text", text: "Say hello" },
      ],
    },
  },
  {
    version: "v0.9",
    updateDataModel: { surfaceId: "preview", value: { form: { name: "" } } },
  },
];

export default function A2UIPreviewPage() {
  const [lastAction, setLastAction] = useState<string | null>(null);

  return (
    <div className="home-main">
      <div className="home-container">
        <div className="hero-title">A2UI render preview</div>
        <p className="hero-sub">
          A self-contained A2UI v0.9 surface, painted by <code>@copilotkit/a2ui-renderer</code> with
          the rich catalog (Chart, Mermaid, Markdown). No agent, no Bedrock — proof the render path
          works.
        </p>
        <div style={{ maxWidth: 560, marginTop: 8 }}>
          <A2UISurfaceView
            surfaceId="preview"
            operations={SAMPLE_OPS}
            catalog={richCatalog}
            onAction={(action) => setLastAction(JSON.stringify(action))}
          />
        </div>
        {lastAction ? (
          <p style={{ color: "var(--text-muted)", marginTop: 16 }}>
            Last A2UI action: <code>{lastAction}</code>
          </p>
        ) : null}
      </div>
    </div>
  );
}
