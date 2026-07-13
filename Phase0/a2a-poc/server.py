"""Minimal Agent-to-Agent (A2A) server — Phase 0 proof of concept.

A self-contained, dependency-light A2A endpoint that speaks the parts of the A2A
protocol that matter for a demo:

  * Discovery  — GET /.well-known/agent-card.json returns an Agent Card.
  * Invocation — POST / handles JSON-RPC 2.0 `message/send`.
  * Health     — GET /ping.

It deliberately mirrors Amazon Bedrock AgentCore's A2A contract, so the same code
can later be containerised and deployed unchanged as an AgentCore A2A runtime:
port 9000, host 0.0.0.0, root path "/", health "/ping", card at
/.well-known/agent-card.json, JSON-RPC over HTTP (AgentCore adds SigV4/OAuth).

The skill logic is deterministic (no Bedrock) so the POC runs and verifies locally
with no AWS. In production this handler would delegate to a real agent (e.g. the
Strands SDLC planner over AG-UI) — the A2A wire protocol stays identical.
"""

import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

AGENT_PORT = 9000
AGENT_URL = f"http://localhost:{AGENT_PORT}/"

app = FastAPI(title="A2A POC — SDLC Planner")

# The Agent Card is how other agents/clients discover what this agent is and how
# to call it. Shape follows the A2A spec (protocolVersion, capabilities, skills…).
AGENT_CARD = {
    "protocolVersion": "0.3.0",
    "name": "SDLC Planner (A2A demo)",
    "description": (
        "Turns a feature request into a short, structured delivery plan. "
        "Phase 0 A2A proof of concept — deterministic demo logic."
    ),
    "url": AGENT_URL,
    "preferredTransport": "JSONRPC",
    "version": "0.1.0",
    "capabilities": {"streaming": False, "pushNotifications": False},
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": [
        {
            "id": "plan",
            "name": "Draft delivery plan",
            "description": "Break a feature request into steps with a rough estimate.",
            "tags": ["sdlc", "planning"],
            "examples": ["Plan: add Microsoft SSO login to the web app"],
        }
    ],
}


def _demo_plan(text: str) -> str:
    """Deterministic stand-in for a real planning agent."""
    feature = text.strip() or "the requested feature"
    steps = [
        f"1. Clarify scope and acceptance criteria for: {feature}",
        "2. Design and break into tasks (backend, frontend, tests)",
        "3. Implement behind a feature flag",
        "4. Verify end to end, then roll out",
    ]
    points = min(13, 2 + len(feature.split()))  # toy estimate
    return "Delivery plan\n" + "\n".join(steps) + f"\n\nRough estimate: {points} story points."


def _text_from_message(message: dict) -> str:
    parts = message.get("parts", []) if isinstance(message, dict) else []
    chunks = [p.get("text", "") for p in parts if isinstance(p, dict) and p.get("kind") == "text"]
    return " ".join(c for c in chunks if c).strip()


def _jsonrpc_error(req_id, code: int, message: str) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


@app.get("/ping")
def ping() -> dict:
    return {"status": "ok"}


@app.get("/.well-known/agent-card.json")
def agent_card() -> dict:
    return AGENT_CARD


@app.post("/")
async def jsonrpc(request: Request):
    try:
        body = await request.json()
    except Exception:
        return _jsonrpc_error(None, -32700, "Parse error")

    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0" or "method" not in body:
        return _jsonrpc_error(body.get("id") if isinstance(body, dict) else None, -32600, "Invalid Request")

    req_id = body.get("id")
    method = body.get("method")

    # A2A core method: send a message and get the agent's reply.
    if method != "message/send":
        return _jsonrpc_error(req_id, -32601, f"Method not found: {method}")

    params = body.get("params") or {}
    user_text = _text_from_message(params.get("message") or {})

    result_message = {
        "role": "agent",
        "parts": [{"kind": "text", "text": _demo_plan(user_text)}],
        "messageId": str(uuid.uuid4()),
        "kind": "message",
    }
    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": result_message})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
