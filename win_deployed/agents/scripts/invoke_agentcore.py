# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3==1.43.46", "botocore[crt]==1.43.46"]
# ///
"""Invoke a deployed AGUI agent straight against Bedrock AgentCore — no backend.

Usage:
  uv run scripts/invoke_agentcore.py <agent-name|runtime-arn> ["your prompt"]

Why this exists
  smoke_test.py exercises an agent THROUGH the backend (catalog -> proxy -> SigV4).
  That is the right end-to-end test, but it needs the backend running and the
  catalog synced. This script answers a narrower, earlier question: "I just
  uploaded a zip to an AgentCore runtime — did that upload actually work?" It calls
  the runtime directly with SigV4 (via boto3 InvokeAgentRuntime), so it needs
  nothing but AWS credentials and the region.

Why AGUI is not the console "Test" button
  An AGUI runtime does not take a plain prompt and return a JSON answer. It speaks
  the AG-UI protocol: POST /invocations receives a RunAgentInput object and streams
  back Server-Sent Events (RUN_STARTED, TEXT_MESSAGE_CONTENT, TOOL_CALL_START, ...).
  The console's test panel sends whatever JSON you paste and shows the raw bytes,
  so it works only if you hand-craft a valid RunAgentInput and are willing to read
  a raw SSE stream. This script builds the RunAgentInput for you and renders the
  event stream.

Config
  AWS_REGION           required (env or ~/.aws/config)
  AWS credentials      the default boto3 chain (~/.aws, SSO, or a role)
  The agent's gateway env (BEDROCK_ENDPOINT_URL/API_KEY/MODEL_ID) is NOT set here —
  it lives on the runtime, baked in at deploy time.

Exit code: 0 if the run started and ended without a RUN_ERROR; non-zero otherwise.
"""

import json
import os
import sys
import uuid

import boto3
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_REGION", "").strip()

# The runtime name is the agent directory name with '-' replaced by '_'
# (deploy_agent.py:runtime_name_for). Used to resolve an ARN from a friendly name.
AGENT_NAME_TO_RUNTIME = {
    "sdlc-planner-strands": "sdlc_planner_strands",
    "release-readiness-langgraph": "release_readiness_langgraph",
    "bug-report-strands": "bug_report_strands",
    "a2ui-demo-strands": "a2ui_demo_strands",
    "press-release-strands": "press_release_strands",
}


def resolve_arn(control, target: str) -> str:
    """Accept a full runtime ARN as-is, or resolve an agent/runtime name to one."""
    if target.startswith("arn:"):
        return target
    wanted = AGENT_NAME_TO_RUNTIME.get(target, target).replace("-", "_")
    token = None
    while True:
        kwargs = {"maxResults": 100}
        if token:
            kwargs["nextToken"] = token
        page = control.list_agent_runtimes(**kwargs)
        for runtime in page.get("agentRuntimes", []):
            if runtime.get("agentRuntimeName") == wanted:
                return runtime["agentRuntimeArn"]
        token = page.get("nextToken")
        if not token:
            sys.exit(
                f"FAIL: no runtime named '{wanted}' in {REGION}. "
                f"Known names: {', '.join(sorted(AGENT_NAME_TO_RUNTIME.values()))}. "
                f"Or pass the full runtime ARN."
            )


def run_agent_input(prompt: str) -> dict:
    """A minimal but valid AG-UI RunAgentInput."""
    return {
        "threadId": f"probe-{uuid.uuid4().hex}",
        "runId": f"run-{uuid.uuid4().hex[:8]}",
        "messages": [{"id": f"msg-{uuid.uuid4().hex[:8]}", "role": "user", "content": prompt}],
        "tools": [],
        "context": [],
        "state": {},
        "forwardedProps": {},
    }


def render_stream(lines) -> tuple:
    """Render an AG-UI SSE stream. Returns (started, error). Shared so the parser
    can be exercised locally against an agent's /invocations without AgentCore."""
    started = False
    error = None
    text_open = False
    for raw in lines:
        line = raw.decode() if isinstance(raw, (bytes, bytearray)) else raw
        if not line or not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[5:].lstrip())
        except ValueError:
            continue
        etype = event.get("type")
        if etype == "RUN_STARTED":
            started = True
            print("  RUN_STARTED — container booted, agent running")
        elif etype == "TEXT_MESSAGE_CONTENT":
            if not text_open:
                sys.stdout.write("  text: ")
                text_open = True
            sys.stdout.write(event.get("delta", ""))
            sys.stdout.flush()
        elif etype == "TOOL_CALL_START":
            if text_open:
                print()
                text_open = False
            print(f"  TOOL_CALL_START — {event.get('toolCallName')}")
        elif etype == "STATE_SNAPSHOT":
            label = ((event.get("snapshot") or {}).get("progress") or {}).get("label")
            if label:
                print(f"  progress: {label}")
        elif etype == "RUN_ERROR":
            error = event.get("message") or "empty RUN_ERROR"
        elif etype in ("RUN_FINISHED", "RUN_ENDED"):
            if text_open:
                print()
                text_open = False
            print("  RUN_FINISHED")
    if text_open:
        print()
    return started, error


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: invoke_agentcore.py <agent-name|runtime-arn> [\"prompt\"]")
    if not REGION:
        sys.exit("FAIL: AWS_REGION is not set (env or ~/.aws/config)")
    target = sys.argv[1]
    prompt = sys.argv[2] if len(sys.argv) > 2 else "Give me a one-sentence hello."

    session = boto3.Session(region_name=REGION)
    control = session.client("bedrock-agentcore-control")
    data = session.client("bedrock-agentcore")

    arn = resolve_arn(control, target)
    print(f"Runtime: {arn}")
    print(f"Region : {REGION}")

    # A runtime session id must be reasonably long; the backend pads short ones to
    # 33+ chars, and a uuid4 hex (32) + prefix clears that comfortably.
    payload = json.dumps(run_agent_input(prompt)).encode()
    try:
        response = data.invoke_agent_runtime(
            agentRuntimeArn=arn,
            qualifier="DEFAULT",
            runtimeSessionId=f"probe-{uuid.uuid4().hex}",
            contentType="application/json",
            accept="text/event-stream",
            payload=payload,
        )
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code", "?")
        msg = error.response.get("Error", {}).get("Message", str(error))
        sys.exit(f"FAIL: InvokeAgentRuntime {code}: {msg}")

    print("--- stream ---")
    body = response.get("response")
    started, run_error = render_stream(body.iter_lines() if body is not None else [])
    print("---")

    if run_error:
        if "initialization" in run_error.lower():
            print(
                "FAIL: the runtime never went healthy. Not a slow cold start — the "
                "container never bound port 8080, or raised at import (a missing "
                "BEDROCK_ENDPOINT_URL / BEDROCK_API_KEY / BEDROCK_MODEL_ID looks "
                "identical from here). The real traceback is in the runtime's "
                "[runtime-logs] CloudWatch stream."
            )
        print(f"FAIL: RUN_ERROR: {run_error}")
        sys.exit(1)
    if not started:
        sys.exit("FAIL: stream ended without RUN_STARTED — the runtime did not begin a run.")
    print("OK: the agent booted and streamed AG-UI events.")


if __name__ == "__main__":
    main()
