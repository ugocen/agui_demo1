"""Press Release Assistant — Strands + AG-UI, static-card (genUI) agent.

Writes a press release on a topic the user gives, using hand-authored cards:

  * ask_choice — a multiple-choice question the user answers by clicking an option
    (tone, audience, angle…). Frontend-owned HITL tool; the run pauses until the
    user clicks. Use it to resolve ambiguity before drafting.
  * draft_press_release — proposes the full release (headline, subheadline,
    dateline, body, boilerplate, contact). The frontend renders an editable card +
    a document canvas; the user edits, submits, or gives feedback in chat, and the
    agent revises and re-drafts.

Both tools are defined by the frontend (CopilotKit sends them in RunAgentInput.tools;
ag-ui-strands registers them as client proxy tools). This agent has no backend tools;
it only calls them by name — the UI carries the detail.
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

SYSTEM_PROMPT = """You are a press-release assistant. The user gives you a topic and you write a professional press release for it.

Workflow:
1. If key framing is unclear, ask ONE multiple-choice question at a time with `ask_choice` (question + 2-4 options the user clicks) — e.g. tone (Formal / Enthusiastic / Technical), target audience, or the main angle. Do not ask more than two questions before drafting; infer sensible defaults for the rest.
2. Call `draft_press_release` exactly once with a complete, well-written draft: `headline`, `subheadline`, `dateline` (e.g. "SAN FRANCISCO, June 5, 2025 —"), `body` (2-4 tight paragraphs, AP-style, with a quote), `boilerplate` (a short "About" paragraph), and `contact` (media contact block).
3. The user reviews the editable card and submits it, or gives feedback in chat. When they give feedback, revise and call `draft_press_release` again with the improved version.

Keep chat text to one short sentence — the card and document carry the content. Never claim the release is published; drafting is simulated in this phase."""


def build_agent() -> StrandsAgent:
    model = build_strands_model()
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=[])
    return StrandsAgent(
        agent=agent,
        name="press-release",
        description="Writes and revises a press release with editable cards + a document canvas",
    )


app = AGUIApp()
app.entrypoint(build_agent())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
