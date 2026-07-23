# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3==1.43.46", "botocore[crt]==1.43.46"]
# ///
"""Invoke a deployed AGUI agent straight against Bedrock AgentCore — no backend.

Usage:
  uv run scripts/invoke_agentcore.py <agent|runtime-arn> ["your prompt"]

  <agent> is an agent directory name (a2ui-demo-strands), a catalog agent id
  (a2uidemo) or a runtime name (A2UI_demo) — see "How the target is resolved".

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

How the target is resolved
  Catalog first, in the same order as deploy_agent.py — the two MUST agree, or
  you probe a different runtime than you deployed to and read the result as if it
  were the same one:

    1. a full runtime ARN is used as-is;
    2. otherwise the platform catalog DB (backend/phase0.db, table agent_catalog
       — what the backend proxy routes on) is matched by agent id, then by
       runtime name;
    3. otherwise the name-derived runtime ("-" -> "_") is looked up in
       list_agent_runtimes: an agent the catalog does not know yet, i.e. one
       deployed but not synced, or a runtime name passed directly.

  Step 2 is what this script was missing. Several live runtimes were hand-created
  under names the convention cannot derive, so the catalog routes 'a2uidemo' to
  A2UI_demo-… while the convention derives a2ui_demo_strands — a RETIRED runtime.
  Resolving by convention alone therefore failed on exactly the agents that
  deploy_agent.py handles correctly. It also printed its "known names" from a
  hardcoded map rather than from the lookup's own list_agent_runtimes call, so
  the failure denied a name while listing it as known.

Config
  AWS_REGION           required: env, then Phase0/.env (where deploy_agent.py
                       reads it), then the default boto3 chain (~/.aws/config)
  AWS credentials      the default boto3 chain (~/.aws, SSO, or a role)
  CATALOG_DB_PATH      optional, from Phase0/.env — same override deploy_agent.py
                       honours when the backend's SQLite file lives elsewhere. A
                       non-SQLite catalog (Postgres DATABASE_URL) cannot be read
                       here, so resolution falls through to step 3.
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

# Resolution is SHARED with deploy_agent.py rather than reimplemented: a second
# copy of "which runtime is this agent?" is what broke this script — its local
# name map went stale and never learned the catalog. Both files always sit in the
# same directory (Phase0/scripts/ here, agents/scripts/ in the enterprise
# payload — see win_deployed/scripts/_payload.sh), which Python puts on sys.path
# as the script's own directory, and deploy_agent.py does nothing at import time.
from deploy_agent import (
    list_runtimes,
    load_env,
    resolve_catalog_target,
    runtime_name_for,
)


def resolve_region(env: dict) -> str:
    """AWS_REGION from the process env, then Phase0/.env — deploy_agent.py reads it
    there, and a region set only in that file used to work for a deploy but not for
    a probe — then the default boto3 chain (AWS_PROFILE, ~/.aws/config)."""
    region = os.environ.get("AWS_REGION", "").strip() or env.get("AWS_REGION", "").strip()
    return region or (boto3.Session().region_name or "")


def resolve_runtime(control, env: dict, region: str, target: str) -> tuple[str, str, str]:
    """Resolve <agent|runtime-arn> to a runtime ARN. Returns (arn, source, how).

    Catalog first, then the name-derived runtime — deploy_agent.py's order, so
    what this probes is what that deployed. See the module docstring.
    """
    if target.startswith("arn:"):
        return target, "arn", "the ARN you passed"

    derived = runtime_name_for(target)
    catalog = resolve_catalog_target(env, target, derived)
    if catalog:
        how = f"catalog entry '{catalog['agent_id']}' -> {catalog['runtime_name'] or catalog['runtime_arn']}"
        # Call out the divergence that used to make this script fail — but only
        # when the naming convention was actually in play. Passing the catalog id
        # ('a2uidemo') derives a name nobody expected to be a runtime, so noting
        # that it "would have picked a2uidemo" is noise, not a warning.
        if target != catalog["agent_id"] and (catalog["runtime_name"] or "") != derived:
            how += f"  (NOT the name-derived '{derived}' — deploy_agent.py targets the catalog too)"
        return catalog["runtime_arn"], "catalog", how

    # No catalog entry. Fall back to the naming convention, and build the failure
    # message from THIS list — the one just searched — so it cannot contradict it.
    runtimes = list_runtimes(control)
    match = next((r for r in runtimes if r.get("agentRuntimeName") == derived), None)
    if match:
        return match["agentRuntimeArn"], "name", f"the runtime named '{derived}' (no catalog entry for '{target}')"

    known = ", ".join(sorted(r.get("agentRuntimeName", "") for r in runtimes)) or "(none)"
    sys.exit(
        f"FAIL: '{target}' matches no catalog entry, and no runtime named '{derived}' exists in {region}.\n"
        f"  Runtimes in {region}: {known}\n"
        "  Pass one of those names, a catalog agent id, or a full runtime ARN."
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
        sys.exit("usage: invoke_agentcore.py <agent|runtime-arn> [\"prompt\"]")
    target = sys.argv[1]
    prompt = sys.argv[2] if len(sys.argv) > 2 else "Give me a one-sentence hello."

    env = load_env(required=False)
    region = resolve_region(env)
    if not region:
        sys.exit("FAIL: no AWS region — set AWS_REGION in the environment or in Phase0/.env, or configure a profile")

    session = boto3.Session(region_name=region)
    control = session.client("bedrock-agentcore-control")
    data = session.client("bedrock-agentcore")

    arn, source, how = resolve_runtime(control, env, region, target)
    print(f"Runtime : {arn}")
    print(f"Resolved: {how}")
    print(f"Region  : {region}")

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
        hint = ""
        if source == "catalog" and code in ("ResourceNotFoundException", "ValidationException"):
            hint = (
                "\n  The catalog routes this agent to a runtime that cannot be invoked, so the entry is "
                "stale: re-sync it from AgentCore or fix it on /admin. deploy_agent.py resolves the same "
                "entry, which means the live app is pointed at this ARN too."
            )
        sys.exit(f"FAIL: InvokeAgentRuntime {code}: {msg}{hint}")

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
