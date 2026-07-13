"""Bug Report Assistant agent, Strands + AG-UI, served on the AgentCore runtime contract.

A form-wizard agent. The user describes a problem in chat, the agent analyses
it and proposes a structured bug report by calling the draft_bug_report tool
with filled-in field values. The frontend renders an editable form (the card),
the user edits and submits it, and the agent confirms the final report.

draft_bug_report is a human-in-the-loop tool owned by the frontend: CopilotKit
sends its definition in RunAgentInput.tools, ag-ui-strands registers it as a
client proxy tool, and the run pauses until the browser returns the submitted
form. There are no backend-side tools for this agent.
"""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()  # existing env vars win (override=False); .env fills the rest
except ImportError:
    pass

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


SYSTEM_PROMPT = """You are a bug report assistant that turns a user's description into a well-structured bug report.
When the user describes a problem, analyse it and call draft_bug_report exactly once with sensible proposed values for every field: title, severity (one of critical, high, medium, low), steps_to_reproduce, expected_behavior, actual_behavior, environment.
Infer reasonable values from what the user said, keep each field concise and specific.
The user then reviews and edits the form and submits it. After they submit, confirm the final bug report in a short text summary.
Never claim a bug was filed without calling draft_bug_report first and waiting for the submission. Bug filing itself is simulated in this phase.
Keep chat text short, the form carries the detail."""


def build_agent() -> StrandsAgent:
    model = build_gateway_model()
    agent = Agent(model=model, system_prompt=SYSTEM_PROMPT, tools=[])
    return StrandsAgent(
        agent=agent,
        name="bug-report",
        description="Structured bug report assistant",
    )


app = AGUIApp()
app.entrypoint(build_agent())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
