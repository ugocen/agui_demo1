"""A2UI demo agent — Strands + AG-UI. A purpose-built *generative-UI* agent.

Unlike the card agents (planner/release/bugreport), this one does not call
hand-authored card tools. It builds its whole answer as an **A2UI** surface: the
CopilotKit runtime applies the A2UI middleware (ui_mode=a2ui in the catalog),
which injects the `render_a2ui` tool + the A2UI v0.9 component catalog into the
run. This agent's job is simply to always answer by rendering an A2UI surface.

Run locally (points the proxy at it via LOCAL_AGENT_URL_A2UIDEMO):
    BEDROCK_MODEL_ID=... python agent.py     # serves /invocations + /ping on :8090
"""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()  # existing env vars win (override=False); .env fills the rest
except ImportError:
    pass

# Strands' OpenTelemetry span instrumentation raises a contextvar
# "detach ... created in a different Context" error under local async streaming,
# which aborts the SSE mid-run (empty A2UI surface). Disable it ONLY for local
# dev — detected by the absence of an OTEL exporter endpoint. On AgentCore the
# runtime sets OTEL_EXPORTER_OTLP_ENDPOINT (its ADOT collector), so we leave OTEL
# ON there and traces flow to CloudWatch as usual. Must run before importing strands.
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


SYSTEM_PROMPT = """You are a generative-UI assistant. You answer by building a UI surface, not by writing paragraphs.

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
    model = build_gateway_model()
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=[])
    return StrandsAgent(
        agent=agent,
        name="a2ui-demo",
        description="Generative-UI demo agent — answers as A2UI surfaces",
    )


app = AGUIApp()
app.entrypoint(build_agent())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090)
