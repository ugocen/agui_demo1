"""SDLC Planner agent, Strands + AG-UI, served on the AgentCore runtime contract.

Serves POST /invocations (SSE), GET /ping and /ws on port 8080 via the
official bedrock-agentcore AGUIApp helper.
"""

import os

import boto3
from ag_ui_strands import StrandsAgent
from bedrock_agentcore.runtime.ag_ui import AGUIApp
from strands import Agent
from strands.models import BedrockModel

from tools import show_estimates, show_user_stories

# --- Enterprise Bedrock gateway ---------------------------------------------
# Bedrock AgentCore / standard Bedrock are not available on this enterprise
# account. Model calls go through the J&J GenAI API gateway, which speaks the
# Bedrock Runtime Converse API but authenticates with an `x-api-key` header
# instead of SigV4. We build a bedrock-runtime client pointed at the gateway
# with dummy AWS credentials, register a before-call hook that injects the key,
# and hand that client's model to Strands. Set BEDROCK_API_KEY in the env.
BEDROCK_ENDPOINT_URL = os.environ.get("BEDROCK_ENDPOINT_URL", "https://genaiapigwna.jnj.com")
BEDROCK_API_KEY = os.environ.get("BEDROCK_API_KEY", "")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-opus-4-8")
GATEWAY_REGION = os.environ.get("AWS_REGION", "us-east-1")


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
    )

    def _add_api_key(model, params, request_signer, **kwargs):  # noqa: ARG001
        params["headers"]["x-api-key"] = BEDROCK_API_KEY

    events = model.client.meta.events
    for op in ("Converse", "ConverseStream", "CountTokens"):
        events.register(f"before-call.bedrock-runtime.{op}", _add_api_key)
    return model

SYSTEM_PROMPT = """You are an SDLC planning assistant for backlog refinement and sprint planning.
For story generation draft 3 to 5 user stories with acceptance criteria and call show_user_stories exactly once with all of them.
For estimation call show_estimates once, covering every current story id.
Never claim tickets were created directly. When asked to create tickets, call request_ticket_approval first, wait for the user decision, then confirm the outcome in text. Ticket creation is simulated in this phase.
Keep chat text short, the cards carry the detail."""


def build_agent() -> StrandsAgent:
    model = build_gateway_model()
    agent = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[show_user_stories, show_estimates],
    )
    return StrandsAgent(
        agent=agent,
        name="sdlc-planner",
        description="Backlog refinement and sprint planning assistant",
    )


app = AGUIApp()
app.entrypoint(build_agent())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
