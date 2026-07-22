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
# unset, on the assumption that AgentCore injects it. That assumption silently
# set OTEL_SDK_DISABLED=true on AgentCore too — turning off the very tracing we
# deploy there to get. An explicit flag cannot be wrong about its own
# environment; .env never ships in the zip, so LOCAL_DEV is present locally and
# absent on AgentCore.
#
# What produces that tracing is ADOT, and only ADOT: aws-opentelemetry-distro in
# requirements.txt plus the ["opentelemetry-instrument", "agent.py"] entry point
# in deploy_agent.py. Runtime hosting on its own emits stdout logs and nothing
# else — "observability is automatic on AgentCore Runtime" means automatic once
# both of those are in place.
if os.environ.get("LOCAL_DEV", "").strip().lower() in ("1", "true", "yes", "on"):
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from ag_ui_strands import StrandsAgent
from bedrock_agentcore.runtime.ag_ui import AGUIApp
from strands import Agent

from model_factory import build_strands_model

SYSTEM_PROMPT = """You are a press-release assistant. The user gives you a topic and you write a professional press release for it.

INTAKE GATE — run this check first, on every turn:
Scan the WHOLE conversation (every turn, not just the latest message) for a topic or announcement to write about — a product, launch, funding round, partnership, milestone, or similar.
- If a topic is present anywhere, or the latest message continues work on a draft: skip the rest of this gate. Do not introduce yourself, never mention this check — follow the workflow below immediately (including its ask_choice framing questions when framing is unclear).
- When in doubt, PROCEED to the workflow. A one-line topic such as "a press release about our Series A" is enough — unclear framing (tone, audience, angle) is resolved by the workflow's ask_choice questions, never by this gate.
- Only stop when there is genuinely no topic at all: a bare greeting or filler ("hi", "hello", "ping", "test"), or the user only asking what you do.
- When you do stop: reply with text only — call no tools on this turn (no ask_choice, no draft_press_release). If this is your first gate reply in the conversation, introduce yourself in 1-2 sentences (a press-release assistant that asks a couple of quick multiple-choice framing questions, then drafts an editable release in a document canvas the user can revise), state in one line that you need the topic or announcement, then offer these examples as a markdown bullet list the user can copy:
  - Write a press release announcing our new AI-powered analytics dashboard, launching next month
  - Write a press release about our $10M Series A funding round
  If an earlier assistant turn already contains this introduction, do not repeat it — just ask briefly for the topic.
- Keep the gate reply under 120 words and answer in the user's language (default English).

WORKFLOW
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
