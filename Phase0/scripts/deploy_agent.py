# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3==1.43.46", "botocore[crt]==1.43.46"]
# ///
"""Deploy one agent zip to Bedrock AgentCore Runtime via direct code deployment.

Usage: uv run scripts/deploy_agent.py <agent-name> <zip-path>

Uploads the zip to s3://$DEPLOY_BUCKET/<agent-name>/deployment_package.zip,
updates the agent runtime, waits for READY and prints the runtime ARN.

The deploy target is resolved CATALOG-FIRST. The backend proxy routes on the
platform DB catalog entry's runtime_arn (backend/phase0.db, table
agent_catalog) — not on any naming convention — so that ARN is the runtime the
live app actually serves. Several live runtimes were hand-created under names
the convention cannot derive (e.g. Planner-QIXryP8Qvh for
sdlc-planner-strands); deploying by convention updated or created a same-named
twin runtime the app never routes to, leaving the app on stale code. Per agent
this script therefore:

1. resolves the catalog entry (CATALOG_AGENT_IDS map first, then a row whose
   runtime_name matches the name-derived runtime) and updates THAT runtime,
   warning loudly when the convention would have picked a different one;
2. falls back to the old find-or-create by derived name ("-" -> "_") only when
   no catalog entry is reachable — the first deploy of a brand-new agent. The
   catalog auto-registers the new runtime on its next AgentCore sync.

Configuration is read from the .env file in this script's parent directory
(the repo root in the monorepo layout; the agents/ folder when this script
ships alongside the agents). The catalog DB is expected at backend/phase0.db
next to it; set CATALOG_DB_PATH in that .env when the backend's SQLite file
lives elsewhere. A non-SQLite catalog (Postgres DATABASE_URL) cannot be read
here — the name-derived fallback then applies, so verify the catalog ARN after
deploying. Runtime ARNs are never written back to .env: the catalog is their
only home (AGENTS.md invariant 2).
"""

import sqlite3
import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

PHASE0_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = PHASE0_DIR / ".env"
DEFAULT_CATALOG_DB = PHASE0_DIR / "backend" / "phase0.db"

# Agent directory -> platform catalog agent_id (agent_catalog.agent_id); also
# the allowlist of deployable agent names. The five original ids were picked by
# hand before the runtime naming convention existed, so they cannot be derived.
# A brand-new agent's auto-registered id is the slug of its runtime name, which
# equals the directory name — add it here as itself.
CATALOG_AGENT_IDS = {
    "sdlc-planner-strands": "planner",
    "release-readiness-langgraph": "release",
    "bug-report-strands": "bugreport",
    "a2ui-demo-strands": "a2uidemo",
    "press-release-strands": "pressrelease",
}

READY_TIMEOUT_SECONDS = 300
POLL_SECONDS = 5


def build_env_vars(env: dict, control, existing_runtime_id: str | None) -> dict:
    """Runtime environment variables for the agent: model id + optional gateway config.

    On UPDATE, start from the runtime's current environmentVariables. AgentCore's
    update_agent_runtime REPLACES the whole map, so without this merge a redeploy
    would silently strip values set out-of-band — most importantly the enterprise
    gateway config entered in the console, which the enterprise agents cannot
    start without.

    This script serves BOTH copies (AGENTS.md invariant 4), which is why the
    gateway variables are passed through rather than required: deploying a
    Phase0/agents/ (Bedrock-only) agent legitimately has none, while a
    cloud_deploy/agents/ (gateway-only) agent needs all of BEDROCK_ENDPOINT_URL,
    BEDROCK_API_KEY and BEDROCK_MODEL_ID. The agent itself enforces that — it
    raises at startup — so the check lives where it can tell the two apart. The
    cost is that a gateway agent deployed without them fails at runtime, not
    here, and the symptom is an unhelpful initialization timeout; the real error
    is in the runtime's [runtime-logs] CloudWatch stream.
    """
    merged: dict = {}
    if existing_runtime_id:
        try:
            detail = control.get_agent_runtime(agentRuntimeId=existing_runtime_id)
            merged.update(detail.get("environmentVariables") or {})
        except ClientError as error:
            print(f"WARN: could not read existing env vars, not merging: {error}")

    merged["BEDROCK_MODEL_ID"] = require(env, "BEDROCK_MODEL_ID")
    for key in ("BEDROCK_ENDPOINT_URL", "BEDROCK_API_KEY", "BEDROCK_STREAMING"):
        value = env.get(key, "").strip()
        if value:
            merged[key] = value
    return merged


def load_env() -> dict:
    if not ENV_PATH.exists():
        sys.exit(f"FAIL: {ENV_PATH} not found, copy .env.example to .env and fill it")
    values = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def require(env: dict, key: str) -> str:
    value = env.get(key, "")
    if not value:
        sys.exit(f"FAIL: {key} is empty in .env, fill it first ([Human] prerequisite)")
    return value


def ensure_bucket(s3, bucket: str, region: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
        return
    except ClientError as error:
        code = error.response["Error"]["Code"]
        if code not in ("404", "NoSuchBucket"):
            raise
    print(f"Bucket {bucket} not found, creating it")
    create_kwargs = {"Bucket": bucket}
    if region != "us-east-1":
        create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
    s3.create_bucket(**create_kwargs)


def runtime_name_for(agent_name: str) -> str:
    return agent_name.replace("-", "_")


def resolve_target(control, target: str):
    """Find the runtime an explicit --runtime flag names, by runtime name or ARN.

    --runtime is the escape hatch for updating a runtime whose name this script's
    naming convention could not derive — e.g. one created by hand in the AgentCore
    console under an arbitrary name (four of the five runtimes in the personal
    account are exactly this: Planner / Release_Readiness / Press_Release /
    A2UI_demo). The default path is the catalog-first resolution in main(); this
    only runs when --runtime is given, and exits if the name/ARN is not found.
    """
    wanted_arn = target if target.startswith("arn:") else ""
    wanted_name = "" if wanted_arn else target
    token = None
    while True:
        kwargs = {"maxResults": 100}
        if token:
            kwargs["nextToken"] = token
        page = control.list_agent_runtimes(**kwargs)
        for runtime in page.get("agentRuntimes", []):
            if wanted_arn and runtime.get("agentRuntimeArn") == wanted_arn:
                return runtime
            if wanted_name and runtime.get("agentRuntimeName") == wanted_name:
                return runtime
        token = page.get("nextToken")
        if not token:
            sys.exit(f"FAIL: --runtime={target} not found. Deploy without --runtime to create a new one.")


def find_existing_runtime(control, runtime_name: str):
    token = None
    while True:
        kwargs = {"maxResults": 100}
        if token:
            kwargs["nextToken"] = token
        page = control.list_agent_runtimes(**kwargs)
        for runtime in page.get("agentRuntimes", []):
            if runtime.get("agentRuntimeName") == runtime_name:
                return runtime
        token = page.get("nextToken")
        if not token:
            return None


def resolve_catalog_target(env: dict, agent_name: str, derived_name: str) -> dict | None:
    """Look up the deploy target in the platform catalog DB — the same table the
    backend proxy routes on. Returns None (after printing why) when no entry is
    reachable, which sends the caller down the name-derived fallback.

    Read-only, at deploy time only; no ARN ends up in env or config, so
    AGENTS.md invariant 2 stands. Matches the explicit CATALOG_AGENT_IDS map
    first, then a row whose runtime_name equals the name-derived runtime (an
    agent that only ever existed by convention). Also picks up a duplicate row
    pointing at the name-derived runtime so a stray auto-registration is called
    out instead of silently coexisting with the real entry.
    """
    configured = env.get("CATALOG_DB_PATH", "").strip()
    db_path = Path(configured).expanduser() if configured else DEFAULT_CATALOG_DB
    if not db_path.exists():
        print(f"Catalog DB not found at {db_path} — using the name-derived runtime")
        return None
    query = "SELECT agent_id, runtime_name, runtime_arn FROM agent_catalog WHERE {} = ?"
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.Error as error:
        print(f"WARN: cannot open catalog DB {db_path} ({error}) — using the name-derived runtime")
        return None
    try:
        conn.row_factory = sqlite3.Row
        row = conn.execute(query.format("agent_id"), (CATALOG_AGENT_IDS[agent_name],)).fetchone()
        if row is None:
            row = conn.execute(query.format("runtime_name"), (derived_name,)).fetchone()
        if row is None:
            print(f"No catalog entry for {agent_name} in {db_path} — using the name-derived runtime")
            return None
        duplicate = conn.execute(
            "SELECT agent_id, runtime_arn FROM agent_catalog WHERE runtime_name = ? AND agent_id != ?",
            (derived_name, row["agent_id"]),
        ).fetchone()
    except sqlite3.Error as error:
        print(f"WARN: catalog DB query failed ({error}) — using the name-derived runtime")
        return None
    finally:
        conn.close()
    return {
        "agent_id": row["agent_id"],
        "runtime_name": row["runtime_name"],
        "runtime_arn": row["runtime_arn"],
        "duplicate": dict(duplicate) if duplicate else None,
    }


def warn_catalog_divergence(control, catalog: dict, derived_name: str) -> None:
    """The failure mode this script guards against: the catalog routes the agent
    to a runtime the naming convention cannot reach, so a name-derived deploy
    would update (or create) a twin the app never serves. Make the divergence
    impossible to miss, and point at any twin that already exists."""
    bar = "!" * 78
    lines = [
        bar,
        "!! WARNING: the name-derived runtime and the catalog target DISAGREE.",
        f"!!   catalog '{catalog['agent_id']}' routes to : {catalog['runtime_arn']}",
        f"!!   the naming convention would pick : {derived_name}",
        "!! Deploying to the CATALOG runtime — the one the live app actually serves.",
    ]
    twin = find_existing_runtime(control, derived_name)
    if twin and twin.get("agentRuntimeArn") != catalog["runtime_arn"]:
        lines += [
            f"!! A separate runtime named {derived_name} also exists:",
            f"!!   {twin.get('agentRuntimeArn')}",
            "!! The app does not route this agent there (a twin from an old name-derived",
            "!! deploy). Until it is deleted, every catalog sync re-registers it as a",
            "!! duplicate agent entry.",
        ]
    if catalog["duplicate"]:
        dup = catalog["duplicate"]
        lines += [
            f"!! The catalog also holds a duplicate entry '{dup['agent_id']}' pointing at",
            f"!!   {dup['runtime_arn']}",
            "!! Disable or delete it on /admin — it is a stray auto-registration.",
        ]
    lines.append(bar)
    print("\n".join(lines))


def wait_until_ready(control, runtime_id: str) -> dict:
    deadline = time.time() + READY_TIMEOUT_SECONDS
    while time.time() < deadline:
        info = control.get_agent_runtime(agentRuntimeId=runtime_id)
        status = info["status"]
        print(f"  status: {status}")
        if status == "READY":
            return info
        if status in ("CREATE_FAILED", "UPDATE_FAILED"):
            sys.exit(f"FAIL: runtime entered {status}: {info.get('failureReason', 'no reason given')}")
        time.sleep(POLL_SECONDS)
    sys.exit(f"FAIL: runtime not READY within {READY_TIMEOUT_SECONDS} seconds")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    target = next((f.split("=", 1)[1] for f in flags if f.startswith("--runtime=")), "")
    if len(args) != 2 or any(not f.startswith("--runtime=") for f in flags):
        sys.exit(
            "usage: deploy_agent.py <agent-name> <zip-path> [--runtime=<name-or-arn>]\n"
            "  --runtime  update an EXISTING runtime whose name this script would not\n"
            "             guess — e.g. one created by hand in the AgentCore console."
        )
    agent_name, zip_arg = args
    if agent_name not in CATALOG_AGENT_IDS:
        sys.exit(
            f"FAIL: unknown agent name, expected one of {sorted(CATALOG_AGENT_IDS)} "
            "(add a brand-new agent to CATALOG_AGENT_IDS first)"
        )
    zip_path = Path(zip_arg).resolve()
    if not zip_path.exists():
        sys.exit(f"FAIL: zip not found: {zip_path}")

    env = load_env()
    region = require(env, "AWS_REGION")
    bucket = require(env, "DEPLOY_BUCKET")
    role_arn = require(env, "EXECUTION_ROLE_ARN")
    auth_mode = env.get("AUTH_MODE", "iam").lower()

    session = boto3.Session(region_name=region)
    s3 = session.client("s3")
    control = session.client("bedrock-agentcore-control")

    # Resolve the deploy target BEFORE touching S3: the catalog (what the proxy
    # routes on) wins; the naming convention is only the fallback for an agent
    # the catalog does not know yet.
    derived_name = runtime_name_for(agent_name)
    catalog = resolve_catalog_target(env, agent_name, derived_name)
    if catalog:
        runtime_id = catalog["runtime_arn"].rsplit("/", 1)[-1]
        print(f"Catalog: '{catalog['agent_id']}' routes to {catalog['runtime_arn']}")
        catalog_runtime_name = catalog["runtime_name"] or runtime_id.rsplit("-", 1)[0]
        if catalog_runtime_name != derived_name:
            warn_catalog_divergence(control, catalog, derived_name)
        try:
            control.get_agent_runtime(agentRuntimeId=runtime_id)
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "unknown")
            sys.exit(
                f"FAIL: the catalog routes '{catalog['agent_id']}' to {catalog['runtime_arn']} "
                f"but that runtime cannot be fetched ({code}). Fix the catalog entry (re-sync "
                "from AgentCore or edit it on /admin) and retry — deploying to a name-derived "
                "runtime instead would ship code the app never serves."
            )
        existing = {"agentRuntimeId": runtime_id}
    else:
        existing = find_existing_runtime(control, derived_name)

    ensure_bucket(s3, bucket, region)
    object_key = f"{agent_name}/deployment_package.zip"
    print(f"Uploading {zip_path.name} to s3://{bucket}/{object_key}")
    s3.upload_file(str(zip_path), bucket, object_key)

    # `existing` is already resolved above — catalog first, else the name-derived
    # runtime. An explicit --runtime overrides that with a runtime the naming
    # convention could not reach; resolve_target() exits if the name/ARN is
    # unknown, so a returned value is always a real runtime. Either way, an update
    # must merge onto the target runtime's existing env vars.
    if target:
        existing = resolve_target(control, target)
        print(f"Updating explicitly targeted runtime: {existing['agentRuntimeName']}")
    env_vars = build_env_vars(env, control, existing["agentRuntimeId"] if existing else None)
    if "BEDROCK_ENDPOINT_URL" in env_vars and "BEDROCK_API_KEY" in env_vars:
        print("Gateway config present: BEDROCK_ENDPOINT_URL + BEDROCK_API_KEY set on the runtime")
        print("  (only a cloud_deploy/agents/ build can use these; a Phase0/agents/ build ignores them)")

    runtime_config = {
        "agentRuntimeArtifact": {
            "codeConfiguration": {
                "code": {"s3": {"bucket": bucket, "prefix": object_key}},
                "runtime": "PYTHON_3_13",
                "entryPoint": ["agent.py"],
            }
        },
        "roleArn": role_arn,
        "networkConfiguration": {"networkMode": "PUBLIC"},
        "protocolConfiguration": {"serverProtocol": "AGUI"},
        "environmentVariables": env_vars,
    }
    if auth_mode == "entra":
        discovery_url = require(env, "ENTRA_DISCOVERY_URL")
        audience = require(env, "ENTRA_ALLOWED_AUDIENCE")
        runtime_config["authorizerConfiguration"] = {
            "customJWTAuthorizer": {
                "discoveryUrl": discovery_url,
                "allowedAudience": [audience],
            }
        }

    if existing:
        runtime_id = existing["agentRuntimeId"]
        print(f"Updating runtime {runtime_id}")
        control.update_agent_runtime(agentRuntimeId=runtime_id, **runtime_config)
    else:
        print(f"Creating runtime {derived_name} (name-derived — first deploy of a new agent)")
        created = control.create_agent_runtime(agentRuntimeName=derived_name, **runtime_config)
        runtime_id = created["agentRuntimeId"]

    info = wait_until_ready(control, runtime_id)
    runtime_arn = info["agentRuntimeArn"]
    print(f"OK: runtime READY, {runtime_arn}")
    if catalog:
        print(f"    the catalog routes '{catalog['agent_id']}' here — the live app serves this build")
    else:
        print("    resolved by NAME, not via the catalog — after the next AgentCore sync,")
        print(f"    verify on /admin that the catalog entry for {agent_name} routes to this ARN")


if __name__ == "__main__":
    main()
