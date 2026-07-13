"""Release readiness graph.

Linear three-node StateGraph: collect_checks -> assess_risks -> recommend.
Each node emits its card tool call and the shared progress state through
AG-UI custom events, the final node pauses on a LangGraph interrupt for the
go/no-go decision (HITL) and then streams an LLM summary.
"""

import os
import re
import uuid
from typing import Annotated, TypedDict

import boto3
from langchain_aws import ChatBedrockConverse
from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

# --- Enterprise Bedrock gateway ---------------------------------------------
# Bedrock AgentCore / standard Bedrock are not available on this enterprise
# account. Model calls go through the J&J GenAI API gateway, which speaks the
# Bedrock Runtime Converse API but authenticates with an `x-api-key` header
# instead of SigV4. We build a bedrock-runtime client pointed at the gateway
# with dummy AWS credentials, register a before-call hook that injects the key,
# and hand it to ChatBedrockConverse. Set BEDROCK_API_KEY in the env.
BEDROCK_ENDPOINT_URL = os.environ.get("BEDROCK_ENDPOINT_URL", "https://genaiapigwna.jnj.com")
BEDROCK_API_KEY = os.environ.get("BEDROCK_API_KEY", "")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-opus-4-8")
GATEWAY_REGION = os.environ.get("AWS_REGION", "us-east-1")


def build_gateway_model() -> ChatBedrockConverse:
    session = boto3.Session(aws_access_key_id="dummy", aws_secret_access_key="dummy")
    client = session.client(
        "bedrock-runtime",
        endpoint_url=BEDROCK_ENDPOINT_URL,
        region_name=GATEWAY_REGION,
    )

    def _add_api_key(model, params, request_signer, **kwargs):  # noqa: ARG001
        params["headers"]["x-api-key"] = BEDROCK_API_KEY

    for op in ("Converse", "ConverseStream", "CountTokens"):
        client.meta.events.register(f"before-call.bedrock-runtime.{op}", _add_api_key)
    return ChatBedrockConverse(model=BEDROCK_MODEL_ID, client=client)


class ReleaseState(TypedDict):
    messages: Annotated[list, add_messages]
    version: str
    checks: list
    risks: list
    progress: dict


TOTAL_STEPS = 3

CHECKLIST_TOOL = "show_release_checklist"
RISK_MATRIX_TOOL = "show_risk_matrix"
GO_NOGO_TOOL = "request_go_nogo"

# Fixture data: simulated CI, coverage and open-bug results for the spike.
# Phase 0 has no external systems, these values stand in for real checks.
FIXTURE_CHECKS = [
    {"name": "CI pipeline", "status": "pass", "detail": "Latest build green on main"},
    {"name": "Test coverage", "status": "warn", "detail": "78 percent, target is 80 percent"},
    {"name": "Open critical bugs", "status": "fail", "detail": "2 critical bugs still open"},
    {"name": "Performance baseline", "status": "pass", "detail": "p95 latency within budget"},
    {"name": "Security scan", "status": "pass", "detail": "No high severity findings"},
]


def _extract_version(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage) and isinstance(message.content, str):
            match = re.search(r"\b(\d+\.\d+(?:\.\d+)*)\b", message.content)
            if match:
                return match.group(1)
    return "unspecified"


async def _emit_progress(state: ReleaseState, step: int, label: str) -> dict:
    progress = {"step": step, "total": TOTAL_STEPS, "label": label}
    await adispatch_custom_event(
        "manually_emit_state",
        {
            "version": state.get("version", ""),
            "checks": state.get("checks", []),
            "risks": state.get("risks", []),
            "progress": progress,
        },
    )
    return progress


async def _emit_card(tool_name: str, payload: dict) -> list:
    tool_call_id = f"call_{uuid.uuid4().hex}"
    await adispatch_custom_event(
        "manually_emit_tool_call",
        {"id": tool_call_id, "name": tool_name, "args": payload},
    )
    ai_message = AIMessage(
        content="",
        tool_calls=[{"id": tool_call_id, "name": tool_name, "args": payload}],
    )
    tool_message = ToolMessage(content="displayed", tool_call_id=tool_call_id)
    return [ai_message, tool_message]


async def collect_checks(state: ReleaseState) -> dict:
    await _emit_progress(state, 1, "Collecting release checks")
    version = state.get("version") or _extract_version(state.get("messages", []))
    checks = FIXTURE_CHECKS
    messages = await _emit_card(CHECKLIST_TOOL, {"release": version, "items": checks})
    progress = await _emit_progress(
        {"version": version, "checks": checks, "risks": []}, 1, "Release checks collected"
    )
    return {"messages": messages, "version": version, "checks": checks, "progress": progress}


def _derive_risks(checks: list) -> list:
    risks = []
    for check in checks:
        if check["status"] == "fail":
            risks.append(
                {
                    "name": f"{check['name']} not clean",
                    "probability": 4,
                    "impact": 4,
                    "mitigation": f"Resolve before release: {check['detail']}",
                }
            )
        elif check["status"] == "warn":
            risks.append(
                {
                    "name": f"{check['name']} below target",
                    "probability": 3,
                    "impact": 2,
                    "mitigation": f"Track and improve: {check['detail']}",
                }
            )
    risks.append(
        {
            "name": "Rollback complexity",
            "probability": 2,
            "impact": 3,
            "mitigation": "Keep previous version deployable, rehearse rollback",
        }
    )
    return risks


async def assess_risks(state: ReleaseState) -> dict:
    await _emit_progress(state, 2, "Assessing release risks")
    risks = _derive_risks(state["checks"])
    messages = await _emit_card(RISK_MATRIX_TOOL, {"risks": risks})
    progress = await _emit_progress(
        {
            "version": state.get("version", ""),
            "checks": state.get("checks", []),
            "risks": risks,
        },
        2,
        "Risk assessment complete",
    )
    return {"messages": messages, "risks": risks, "progress": progress}


def _build_recommendation(checks: list, risks: list) -> tuple[str, list]:
    blocking = [risk for risk in risks if risk["probability"] * risk["impact"] >= 12]
    reasons = []
    for check in checks:
        if check["status"] != "pass":
            reasons.append(f"{check['name']}: {check['detail']}")
    if blocking:
        for risk in blocking:
            reasons.append(f"Blocking risk: {risk['name']}")
        return "no-go", reasons
    reasons.append("All release checks pass or are within tolerance")
    return "go", reasons


async def recommend(state: ReleaseState) -> dict:
    await _emit_progress(state, 3, "Preparing go or no-go recommendation")
    recommendation, reasons = _build_recommendation(state["checks"], state["risks"])

    decision = interrupt(
        {"tool": GO_NOGO_TOOL, "recommendation": recommendation, "reasons": reasons}
    )
    if not isinstance(decision, dict):
        decision = {"decision": str(decision)}

    model = build_gateway_model()
    prompt = [
        SystemMessage(
            content="You are a release readiness assistant. Summarize the release decision in at most four short sentences. Be factual, no markdown headers."
        ),
        HumanMessage(
            content=(
                f"Release version: {state.get('version', 'unspecified')}\n"
                f"Checks: {state.get('checks', [])}\n"
                f"Risks: {state.get('risks', [])}\n"
                f"Recommendation was: {recommendation} (reasons: {reasons})\n"
                f"Human decision: {decision.get('decision', 'unknown')}"
                f" (note: {decision.get('note', 'none')})\n"
                "Write the final summary of the decision."
            )
        ),
    ]
    summary = None
    async for chunk in model.astream(prompt):
        summary = chunk if summary is None else summary + chunk
    summary_message = AIMessage(content=summary.text() if summary else "Decision recorded.", id=getattr(summary, "id", None))

    progress = await _emit_progress(state, 3, "Decision recorded")
    return {"messages": [summary_message], "progress": progress}


def build_graph():
    builder = StateGraph(ReleaseState)
    builder.add_node("collect_checks", collect_checks)
    builder.add_node("assess_risks", assess_risks)
    builder.add_node("recommend", recommend)
    builder.add_edge(START, "collect_checks")
    builder.add_edge("collect_checks", "assess_risks")
    builder.add_edge("assess_risks", "recommend")
    builder.add_edge("recommend", END)
    return builder.compile(checkpointer=InMemorySaver())
