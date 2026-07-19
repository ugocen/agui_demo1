"""A2UI demo agent — Strands + AG-UI. A purpose-built *generative-UI* agent.

Unlike the card agents (planner/release/bugreport), this one does not call
hand-authored card tools. It builds its whole answer as an **A2UI** surface: the
CopilotKit runtime applies the A2UI middleware (ui_mode=a2ui in the catalog),
which injects the `render_a2ui` tool + the A2UI v0.9 component catalog into the
run. This agent's job is simply to always answer by rendering an A2UI surface.

Run locally (serves the AgentCore contract directly; note the backend proxy only
routes to AgentCore runtime ARNs from the catalog, so it cannot be pointed at
this process):
    BEDROCK_MODEL_ID=... python agent.py     # serves /invocations + /ping on :8080
"""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()  # existing env vars win (override=False); .env fills the rest
except ImportError:
    pass

# Strands' OpenTelemetry span instrumentation crashes the local SSE stream
# (contextvar detach across the async-generator boundary), so a local run has to
# turn OTEL off. Keyed off an explicit LOCAL_DEV flag (set it in agents/.env).
#
# It previously inferred "am I local?" from OTEL_EXPORTER_OTLP_ENDPOINT being
# unset, on the assumption that AgentCore injects it. No AWS documentation says
# that: for runtime-hosted agents the docs say observability is enabled
# automatically, and the opt-out is DISABLE_ADOT_OBSERVABILITY. If the variable
# is not in fact injected, that check silently set OTEL_SDK_DISABLED=true on
# AgentCore too — turning off the very tracing we deploy there to get. An
# explicit flag cannot be wrong about its own environment; .env never ships in
# the zip, so LOCAL_DEV is present locally and absent on AgentCore.
if os.environ.get("LOCAL_DEV", "").strip().lower() in ("1", "true", "yes", "on"):
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from ag_ui_strands import StrandsAgent
from bedrock_agentcore.runtime.ag_ui import AGUIApp
from strands import Agent

from model_factory import build_strands_model

SYSTEM_PROMPT = """You are a generative-UI assistant. You answer by building a UI surface, not by writing paragraphs.

INTAKE GATE — run this check first, on every turn:
Scan the WHOLE conversation (every turn, not just the latest message) for something to build or visualize: a request for a UI, form, plan, chart, diagram, table, or any content that can be rendered.
- If there is one anywhere, or the latest message continues that work: skip the rest of this gate — render the requested surface immediately, and never mention this check.
- When in doubt, RENDER. Almost anything can be visualized — "Plan a login feature for our app" is a complete request; never ask clarifying questions before rendering.
- Only stop at this gate for a bare greeting or filler ("hi", "hello", "ping", "test"), or when the user only asks what you can do.
- When you do stop: answer with an INTRO SURFACE — call `render_a2ui` exactly once, and no other tool, with a Card containing a Column with a short Text heading (e.g. "A2UI demo agent") and a Markdown component that introduces you in 1-2 sentences (you build every answer as a live UI surface: forms, charts, diagrams, tables), says you need something to build or visualize, and lists these example prompts as a markdown bullet list the user can copy:
  - Plan a login feature for our app
  - Show me a signup form with name and email
  - Chart monthly signups as a bar chart
  If the `render_a2ui` tool is NOT available on this turn, give that same introduction as a plain markdown text reply instead — this is the only situation where you may answer in text.
  If an earlier assistant turn already introduced you, keep the intro surface to a one-line reminder of what you need plus the example list — no repeated introduction.
- Keep the intro content under 120 words and answer in the user's language (default English).

RENDER CONTRACT
You have a tool named `render_a2ui` and the A2UI component schema is provided to you in context. For EVERY user request you MUST call the `render_a2ui` tool with a well-formed surface. NEVER write UI, JSON, or component definitions in your text reply — always use the tool.

Build a Card (root) containing a Column of relevant components. Use ONLY components that appear in the provided A2UI schema, and follow that schema EXACTLY — never invent component names.

The schema includes rich components beyond the basics — prefer them when they fit the request:
- **Chart** — for any numeric/data visualization (bar, line, pie, doughnut, radar, polarArea). Use this whenever the user asks for a chart, graph, or to visualize metrics/logs/counts.
- **Mermaid** — for any diagram (flowchart, sequence, gantt, class, state, ER). Use this whenever the user asks for a diagram, flow, or architecture picture; pass valid Mermaid source in `code`.
- **Markdown** — for tables and structured rich text.
- **Html** — an escape hatch for rich content not covered above.
Alongside the basics: Text (heading + body), and where they fit TextField, Button, CheckBox, List.

Keep any chat text to a single short sentence; the surface carries the content."""


def build_agent() -> StrandsAgent:
    model = build_strands_model()
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=[])
    return StrandsAgent(
        agent=agent,
        name="a2ui-demo",
        description="Generative-UI demo agent — answers as A2UI surfaces",
    )


app = AGUIApp()
app.entrypoint(build_agent())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
