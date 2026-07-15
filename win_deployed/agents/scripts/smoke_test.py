# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx==0.28.1"]
# ///
"""Phase 0 smoke tests, gate G0 mapping.

Usage: uv run scripts/smoke_test.py

Runs S0 (every catalog agent's runtime answers) plus the scripted S1 to S5
behaviour checks, through the local FastAPI backend proxy against the deployed
AgentCore runtimes, and prints a G0 report.

S0 probes EVERY agent the catalog returns — ids are never hardcoded, so a newly
deployed agent is covered automatically. S1-S5 exercise `planner` and `release`
in depth. That split is deliberate: a deep behaviour test per agent would cost a
full LLM run each, while the failure that actually shipped (an agent whose
runtime never boots) is caught by the cheap probe.

Prerequisites: backend running on BACKEND_URL, and a catalog synced from
AgentCore.
Entra mode: export SMOKE_BEARER_TOKEN (pilot user) and optionally
SMOKE_BEARER_TOKEN_NO_ROLE (user without the app role) before running.
"""

import json
import os
import sys
import uuid
from pathlib import Path

import httpx

PHASE0_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = PHASE0_DIR / ".env"

RESULTS = []

APPROVAL_TOOL_DEF = {
    "name": "request_ticket_approval",
    "description": (
        "Ask the human to approve or reject ticket creation before any ticket is created. "
        "Returns the decision."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "tickets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "points": {"type": "number"},
                    },
                    "required": ["title", "points"],
                },
            },
        },
        "required": ["summary", "tickets"],
    },
}


def load_env() -> dict:
    values = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


ENV = load_env()
BACKEND_URL = ENV.get("BACKEND_URL", "http://localhost:8000")
AUTH_MODE = ENV.get("AUTH_MODE", "iam").lower()
TOKEN = os.environ.get("SMOKE_BEARER_TOKEN", "")
TOKEN_NO_ROLE = os.environ.get("SMOKE_BEARER_TOKEN_NO_ROLE", "")


def auth_headers() -> dict:
    if AUTH_MODE == "entra" and TOKEN:
        return {"Authorization": f"Bearer {TOKEN}"}
    return {}


def record(check: str, passed: bool, detail: str = "") -> bool:
    RESULTS.append((check, passed, detail))
    marker = "PASS" if passed else "FAIL"
    print(f"[{marker}] {check}" + (f" — {detail}" if detail else ""))
    return passed


class StreamResult:
    def __init__(self):
        self.events = []
        self.tool_calls = {}
        self.tool_call_order = []
        self.progress_labels = []
        self.interrupt_value = None
        self.text = ""
        self.final_messages = []
        self.error = None

    def tool_names(self) -> list:
        return [self.tool_calls[cid]["name"] for cid in self.tool_call_order]


def run_agui(agent_id: str, messages: list, tools: list, forwarded_props: dict, thread_id: str) -> StreamResult:
    payload = {
        "threadId": thread_id,
        "runId": f"run-{uuid.uuid4().hex[:8]}",
        "messages": messages,
        "tools": tools,
        "context": [],
        "state": {},
        "forwardedProps": forwarded_props,
    }
    result = StreamResult()
    args_buffers = {}
    with httpx.Client(timeout=httpx.Timeout(connect=10, read=180, write=30, pool=10)) as client:
        with client.stream(
            "POST",
            f"{BACKEND_URL}/api/agui/{agent_id}",
            json=payload,
            headers={"Accept": "text/event-stream", **auth_headers()},
        ) as response:
            if response.status_code != 200:
                response.read()
                result.error = f"HTTP {response.status_code}: {response.text[:300]}"
                return result
            for line in response.iter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                except ValueError:
                    continue
                result.events.append(event)
                etype = event.get("type")
                if etype == "TOOL_CALL_START":
                    call_id = event.get("toolCallId")
                    result.tool_calls[call_id] = {"name": event.get("toolCallName"), "args": None}
                    result.tool_call_order.append(call_id)
                    args_buffers[call_id] = ""
                elif etype == "TOOL_CALL_ARGS":
                    args_buffers[event.get("toolCallId")] = (
                        args_buffers.get(event.get("toolCallId"), "") + event.get("delta", "")
                    )
                elif etype == "TOOL_CALL_END":
                    call_id = event.get("toolCallId")
                    try:
                        result.tool_calls[call_id]["args"] = json.loads(args_buffers.get(call_id) or "{}")
                    except ValueError:
                        result.tool_calls[call_id]["args"] = {}
                elif etype == "STATE_SNAPSHOT":
                    progress = (event.get("snapshot") or {}).get("progress") or {}
                    if progress.get("label"):
                        result.progress_labels.append(progress["label"])
                elif etype == "CUSTOM" and event.get("name") == "on_interrupt":
                    raw = event.get("value")
                    if isinstance(raw, str):
                        try:
                            result.interrupt_value = json.loads(raw)
                        except ValueError:
                            result.interrupt_value = {"raw": raw}
                    else:
                        result.interrupt_value = raw
                elif etype == "TEXT_MESSAGE_CONTENT":
                    result.text += event.get("delta", "")
                elif etype == "MESSAGES_SNAPSHOT":
                    result.final_messages = event.get("messages", [])
                elif etype == "RUN_ERROR":
                    result.error = event.get("message")
    return result


def user_message(content: str) -> dict:
    return {"id": f"msg-{uuid.uuid4().hex[:8]}", "role": "user", "content": content}


def fetch_agents() -> list:
    """The catalog's registered, enabled agents. Ids are never hardcoded (invariant 2)."""
    try:
        response = httpx.get(f"{BACKEND_URL}/api/agents", headers=auth_headers(), timeout=30)
    except httpx.HTTPError as error:
        return [{"_error": f"{type(error).__name__}: {error}"}]
    if response.status_code != 200:
        return [{"_error": f"HTTP {response.status_code}: {response.text[:200]}"}]
    return response.json()


def explain_run_error(message: str) -> str:
    """Turn AgentCore's least helpful error into the three things worth checking."""
    if "initialization" in (message or "").lower():
        return (
            "runtime never went healthy. It is NOT a slow cold start: the container "
            "either never bound port 8080 (the port AgentCore probes) or raised at "
            "import — a missing BEDROCK_ENDPOINT_URL / BEDROCK_API_KEY / "
            "BEDROCK_MODEL_ID looks identical from here. The real traceback is in "
            "the runtime's [runtime-logs] CloudWatch stream. "
            f"Raw: {message[:120]}"
        )
    return (message or "empty RUN_ERROR")[:220]


def ping_agent(agent_id: str) -> tuple:
    """Open a run and stop at the first event — a liveness probe, not a full run.

    RUN_STARTED is emitted before the model is called, so reaching it proves the
    whole path is up (catalog -> proxy -> SigV4 -> AgentCore -> the container
    booted and the agent started) while costing almost no tokens.

    An actual invoke is the only way to check this. The control plane reports a
    runtime READY whether or not its container can boot: the port bug that made
    press-release undeployable sat behind a READY runtime.
    """
    payload = {
        "threadId": f"smoke-ping-{uuid.uuid4().hex}",
        "runId": f"run-{uuid.uuid4().hex[:8]}",
        "messages": [user_message("ping")],
        "tools": [],
        "context": [],
        "state": {},
        "forwardedProps": {},
    }
    # Read generously: AgentCore takes ~30s to give up on an unhealthy runtime, and
    # that verdict is exactly what this probe exists to capture.
    timeout = httpx.Timeout(connect=10, read=75, write=30, pool=10)
    try:
        with httpx.Client(timeout=timeout) as client:
            with client.stream(
                "POST",
                f"{BACKEND_URL}/api/agui/{agent_id}",
                json=payload,
                headers={"Accept": "text/event-stream", **auth_headers()},
            ) as response:
                if response.status_code != 200:
                    response.read()
                    return False, f"HTTP {response.status_code}: {response.text[:200]}"
                for line in response.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                    except ValueError:
                        continue
                    etype = event.get("type")
                    if etype == "RUN_STARTED":
                        return True, "RUN_STARTED — container booted, agent running"
                    if etype == "RUN_ERROR":
                        return False, explain_run_error(event.get("message"))
                return False, "stream closed without RUN_STARTED or RUN_ERROR"
    except httpx.HTTPError as error:
        return False, f"{type(error).__name__}: {error}"


def scenario_agent_health() -> None:
    """S0: every agent in the catalog has a runtime that actually answers.

    Covers all registered agents, not a hand-picked subset. The port bug of
    2026-07-15 shipped to the enterprise because this file only exercised
    `planner` and `release` — both of which happened to be correct.
    """
    agents = fetch_agents()
    if agents and isinstance(agents[0], dict) and agents[0].get("_error"):
        record("S0 catalog reachable", False, agents[0]["_error"])
        return
    if not agents:
        record(
            "S0 catalog reachable",
            False,
            "/api/agents returned no agents — the catalog is empty or unsynced from AgentCore",
        )
        return
    ids = [a.get("id", "?") for a in agents]
    record("S0 catalog reachable", True, f"{len(ids)} agent(s): {', '.join(ids)}")
    for agent_id in ids:
        alive, detail = ping_agent(agent_id)
        record(f"S0 runtime alive: {agent_id}", alive, detail)


def scenario_planner() -> None:
    thread_id = f"smoke-planner-{uuid.uuid4().hex}"
    messages = [user_message("Generate user stories for a password reset feature")]

    s1 = run_agui("planner", messages, [APPROVAL_TOOL_DEF], {}, thread_id)
    if s1.error:
        record("S1 story generation", False, s1.error)
        record("S2 estimation", False, "skipped, S1 failed")
        record("S3 ticket approval HITL", False, "skipped, S1 failed")
        return
    story_calls = [c for c in s1.tool_calls.values() if c["name"] == "show_user_stories"]
    stories = story_calls[0]["args"].get("stories", []) if story_calls else []
    record(
        "S1 story generation",
        len(story_calls) == 1 and 3 <= len(stories) <= 5,
        f"{len(story_calls)} call(s), {len(stories)} stories",
    )
    story_ids = {story.get("id") for story in stories}

    messages = list(s1.final_messages) or messages
    messages.append(user_message("Estimate the backlog"))
    s2 = run_agui("planner", messages, [APPROVAL_TOOL_DEF], {}, thread_id)
    estimate_calls = [c for c in s2.tool_calls.values() if c["name"] == "show_estimates"]
    estimated_ids = {
        item.get("story_id")
        for call in estimate_calls
        for item in call["args"].get("items", [])
    }
    record(
        "S2 estimation",
        bool(estimate_calls) and story_ids <= estimated_ids if story_ids else bool(estimate_calls),
        f"estimated ids {sorted(estimated_ids)}" + (f", error {s2.error}" if s2.error else ""),
    )

    messages = list(s2.final_messages) or messages
    messages.append(user_message("Create tickets for the approved stories"))
    s3 = run_agui("planner", messages, [APPROVAL_TOOL_DEF], {}, thread_id)
    approval_calls = [
        (cid, c) for cid, c in s3.tool_calls.items() if c["name"] == "request_ticket_approval"
    ]
    if not approval_calls or s3.error:
        record(
            "S3 ticket approval HITL",
            False,
            s3.error or "agent did not call request_ticket_approval",
        )
        return
    approval_id = approval_calls[0][0]
    print("  S3 paused on request_ticket_approval, sending approval (simulated ticket creation)")

    messages = list(s3.final_messages) or messages
    messages.append(
        {
            "id": f"msg-{uuid.uuid4().hex[:8]}",
            "role": "tool",
            "content": json.dumps({"decision": "approved", "note": "smoke test approval"}),
            "toolCallId": approval_id,
        }
    )
    s3_resume = run_agui("planner", messages, [APPROVAL_TOOL_DEF], {}, thread_id)
    record(
        "S3 ticket approval HITL",
        bool(s3_resume.text.strip()) and not s3_resume.error,
        f"agent confirmation: {s3_resume.text.strip()[:120]!r}" + (f", error {s3_resume.error}" if s3_resume.error else ""),
    )


def scenario_release() -> None:
    thread_id = f"smoke-release-{uuid.uuid4().hex}"
    messages = [user_message("Assess release readiness for version 1.4.0")]

    s4 = run_agui("release", messages, [], {}, thread_id)
    if s4.error:
        record("S4 readiness assessment", False, s4.error)
        record("S5 go/no-go HITL", False, "skipped, S4 failed")
        return
    names = s4.tool_names()
    checklist_before_matrix = (
        "show_release_checklist" in names
        and "show_risk_matrix" in names
        and names.index("show_release_checklist") < names.index("show_risk_matrix")
    )
    record(
        "S4 readiness assessment",
        checklist_before_matrix and len(s4.progress_labels) >= 2 and s4.interrupt_value is not None,
        f"tools {names}, progress updates {len(s4.progress_labels)}, paused on "
        f"{(s4.interrupt_value or {}).get('tool', 'no interrupt')}",
    )

    decision = {"decision": "no-go", "note": "smoke test decision"}
    s5 = run_agui("release", messages, [], {"command": {"resume": decision}}, thread_id)
    record(
        "S5 go/no-go HITL",
        bool(s5.text.strip()) and not s5.error,
        f"summary: {s5.text.strip()[:120]!r}" + (f", error {s5.error}" if s5.error else ""),
    )


def scenario_auth() -> None:
    if AUTH_MODE != "entra":
        print("[SKIP] Entra auth checks, AUTH_MODE=iam")
        return
    with httpx.Client(timeout=15) as client:
        no_token = client.get(f"{BACKEND_URL}/api/agents")
        record("Entra: request without token is 401", no_token.status_code == 401, f"got {no_token.status_code}")
        if TOKEN_NO_ROLE:
            no_role = client.get(
                f"{BACKEND_URL}/api/agents",
                headers={"Authorization": f"Bearer {TOKEN_NO_ROLE}"},
            )
            record("Entra: token without app role is 403", no_role.status_code == 403, f"got {no_role.status_code}")
        else:
            print("[SKIP] 403 check, set SMOKE_BEARER_TOKEN_NO_ROLE to run it")


def main() -> None:
    print(f"Backend: {BACKEND_URL}, auth mode: {AUTH_MODE}")
    if AUTH_MODE == "entra" and not TOKEN:
        sys.exit("FAIL: AUTH_MODE=entra needs SMOKE_BEARER_TOKEN exported")

    scenario_auth()
    scenario_agent_health()
    scenario_planner()
    scenario_release()

    print("\n=== G0 REPORT ===")
    failed = 0
    for check, passed, detail in RESULTS:
        print(f"  {'PASS' if passed else 'FAIL'}  {check}")
        if not passed:
            failed += 1
    print("\nManual step (not automated): start a release assessment in the browser,")
    print("kill the backend mid-stream (Ctrl+C), and confirm the frontend shows an")
    print("error state without crashing, then restart the backend and retry.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
