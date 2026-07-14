# /// script
# requires-python = ">=3.11"
# dependencies = ["boto3==1.43.46", "botocore[crt]==1.43.46"]
# ///
"""Deploy one agent zip to Bedrock AgentCore Runtime via direct code deployment.

Usage: uv run scripts/deploy_agent.py <agent-name> <zip-path>

Uploads the zip to s3://$DEPLOY_BUCKET/<agent-name>/deployment_package.zip,
creates or updates the agent runtime with the AGUI protocol, waits for READY,
prints the runtime ARN and writes it back into .env.

Configuration is read from the .env file in this script's parent directory
(the repo root in the monorepo layout; the agents/ folder when this script ships
alongside the agents). Creating the runtime by hand in the AgentCore console,
with the same settings, produces an identical runtime.
"""

import sys
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

PHASE0_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = PHASE0_DIR / ".env"

ARN_ENV_KEYS = {
    "sdlc-planner-strands": "PLANNER_RUNTIME_ARN",
    "release-readiness-langgraph": "RELEASE_RUNTIME_ARN",
    "bug-report-strands": "BUGREPORT_RUNTIME_ARN",
    "a2ui-demo-strands": "A2UIDEMO_RUNTIME_ARN",
    "press-release-strands": "PRESSRELEASE_RUNTIME_ARN",
}

READY_TIMEOUT_SECONDS = 300
POLL_SECONDS = 5


def build_env_vars(env: dict, control, existing_runtime_id: str | None) -> dict:
    """Runtime environment variables for the agent: model id + optional gateway config.

    On UPDATE, start from the runtime's current environmentVariables. AgentCore's
    update_agent_runtime REPLACES the whole map, so without this merge a redeploy
    would silently strip values set out-of-band — most importantly the enterprise
    gateway config entered in the console, which would drop the agent back to
    Bedrock/SigV4 (and fail in an account with no Bedrock access).

    Gateway mode (model_factory.use_gateway) needs BOTH BEDROCK_ENDPOINT_URL and
    BEDROCK_API_KEY; they are passed through only when present in .env.
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


def save_env_value(key: str, value: str) -> None:
    lines = ENV_PATH.read_text().splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if line.split("=", 1)[0].strip() == key:
            lines[index] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n")


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
    if len(sys.argv) != 3:
        sys.exit("usage: deploy_agent.py <agent-name> <zip-path>")
    agent_name, zip_arg = sys.argv[1], sys.argv[2]
    if agent_name not in ARN_ENV_KEYS:
        sys.exit(f"FAIL: unknown agent name, expected one of {sorted(ARN_ENV_KEYS)}")
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

    ensure_bucket(s3, bucket, region)
    object_key = f"{agent_name}/deployment_package.zip"
    print(f"Uploading {zip_path.name} to s3://{bucket}/{object_key}")
    s3.upload_file(str(zip_path), bucket, object_key)

    # Resolve the runtime first: an update must merge onto its existing env vars.
    runtime_name = runtime_name_for(agent_name)
    existing = find_existing_runtime(control, runtime_name)
    env_vars = build_env_vars(env, control, existing["agentRuntimeId"] if existing else None)
    if "BEDROCK_ENDPOINT_URL" in env_vars and "BEDROCK_API_KEY" in env_vars:
        print("Gateway mode: BEDROCK_ENDPOINT_URL + BEDROCK_API_KEY set on the runtime")

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
        print(f"Updating existing runtime {runtime_name} ({runtime_id})")
        control.update_agent_runtime(agentRuntimeId=runtime_id, **runtime_config)
    else:
        print(f"Creating runtime {runtime_name}")
        created = control.create_agent_runtime(agentRuntimeName=runtime_name, **runtime_config)
        runtime_id = created["agentRuntimeId"]

    info = wait_until_ready(control, runtime_id)
    runtime_arn = info["agentRuntimeArn"]
    env_key = ARN_ENV_KEYS[agent_name]
    save_env_value(env_key, runtime_arn)
    print(f"OK: runtime READY, {env_key}={runtime_arn} written to .env")


if __name__ == "__main__":
    main()
