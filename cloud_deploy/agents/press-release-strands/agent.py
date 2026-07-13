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
# (contextvar detach across the async-generator boundary). Disable it ONLY for
# local dev (no OTEL exporter endpoint). On AgentCore the runtime sets
# OTEL_EXPORTER_OTLP_ENDPOINT, so OTEL stays on and traces flow to CloudWatch.
if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
    os.environ.setdefault("OTEL_SDK_DISABLED", "true")

import boto3
from ag_ui_strands import StrandsAgent
from bedrock_agentcore.runtime.ag_ui import AGUIApp
from strands import Agent
from strands.models import BedrockModel

# --- Enterprise Bedrock gateway ---------------------------------------------
# Bedrock AgentCore / standard Bedrock are not available on this enterprise
# account. Model calls go through the J&J GenAI API gateway, which speaks the
# Bedrock Runtime Converse API but authenticates with an `x-api-key` header
# instead of SigV4. We build a bedrock-runtime client pointed at the gateway
# with dummy AWS credentials, register a before-call hook that injects the key,
# and hand that client's model to Strands. Set BEDROCK_API_KEY in the env.
BEDROCK_ENDPOINT_URL = os.environ.get("BEDROCK_ENDPOINT_URL", "https://genaiapigwna.jnj.com")
BEDROCK_API_KEY = os.environ.get("BEDROCK_API_KEY", "")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-5-20250929-v1:0")
GATEWAY_REGION = os.environ.get("AWS_REGION", "us-east-1")
# Streaming toggle. The gateway's documented call style is per-model /invoke
# (InvokeModel); whether it also proxies converse-stream is unverified. Set
# BEDROCK_STREAMING=false to make Strands use non-streaming converse and rebuild
# the AG-UI event stream locally — flip without touching code.
BEDROCK_STREAMING = os.environ.get("BEDROCK_STREAMING", "true").strip().lower() not in ("0", "false", "no", "off")


def build_gateway_model() -> BedrockModel:
    session = boto3.Session(
        aws_access_key_id="dummy",
        aws_secret_access_key="dummy",
        region_name=GATEWAY_REGION,
    )
    model = BedrockModel(
        model_id=BEDROCK_MODEL_ID,
        boto_session=session,
        endpoint_url=BEDROCK_ENDPOINT_URL,
        streaming=BEDROCK_STREAMING,
    )

    def _add_api_key(model, params, request_signer, **kwargs):  # noqa: ARG001
        params["headers"]["x-api-key"] = BEDROCK_API_KEY

    events = model.client.meta.events
    for op in ("Converse", "ConverseStream", "CountTokens"):
        events.register(f"before-call.bedrock-runtime.{op}", _add_api_key)
    return model


SYSTEM_PROMPT = """You are a press-release assistant. The user gives you a topic and you write a professional press release for it.

Workflow:
1. If key framing is unclear, ask ONE multiple-choice question at a time with `ask_choice` (question + 2-4 options the user clicks) — e.g. tone (Formal / Enthusiastic / Technical), target audience, or the main angle. Do not ask more than two questions before drafting; infer sensible defaults for the rest.
2. Call `draft_press_release` exactly once with a complete, well-written draft: `headline`, `subheadline`, `dateline` (e.g. "SAN FRANCISCO, June 5, 2025 —"), `body` (2-4 tight paragraphs, AP-style, with a quote), `boilerplate` (a short "About" paragraph), and `contact` (media contact block).
3. The user reviews the editable card and submits it, or gives feedback in chat. When they give feedback, revise and call `draft_press_release` again with the improved version.

Keep chat text to one short sentence — the card and document carry the content. Never claim the release is published; drafting is simulated in this phase."""


def build_agent() -> StrandsAgent:
    model = build_gateway_model()
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=[])
    return StrandsAgent(
        agent=agent,
        name="press-release",
        description="Writes and revises a press release with editable cards + a document canvas",
    )


app = AGUIApp()
app.entrypoint(build_agent())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8091)
