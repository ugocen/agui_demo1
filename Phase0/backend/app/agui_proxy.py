"""AG-UI proxy.

POST /api/agui/{agent_id} forwards the AG-UI request to the agent's
AgentCore runtime invocation endpoint and pipes the SSE stream back
unchanged. entra mode forwards the caller's bearer token, iam mode signs
the upstream request with SigV4. httpx streaming, no buffering.

Local development escape hatch: setting LOCAL_AGENT_URL_<AGENT_ID>
(for example LOCAL_AGENT_URL_RELEASE=http://127.0.0.1:8080/invocations)
proxies that agent to a locally running process instead of AgentCore.
Unset in normal operation.
"""

import json
import os
import urllib.parse

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents_catalog import get_agent
from app.auth import require_platform_access
from app.db import get_session
from app.logging_setup import get_logger

router = APIRouter()
log = get_logger("proxy")

SESSION_HEADER = "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"
MIN_SESSION_ID_LENGTH = 33


def invocation_url(runtime_arn: str, region: str) -> str:
    escaped_arn = urllib.parse.quote(runtime_arn, safe="")
    return (
        f"https://bedrock-agentcore.{region}.amazonaws.com"
        f"/runtimes/{escaped_arn}/invocations?qualifier=DEFAULT"
    )


def session_id_from_thread(body: bytes) -> str:
    try:
        thread_id = str(json.loads(body).get("threadId") or "")
    except (ValueError, AttributeError):
        thread_id = ""
    session_id = thread_id or "phase0-session"
    if len(session_id) < MIN_SESSION_ID_LENGTH:
        session_id = session_id + "-" + "0" * MIN_SESSION_ID_LENGTH
    return session_id[:100]


def sigv4_headers(url: str, body: bytes, region: str, base_headers: dict) -> dict:
    credentials = boto3.Session().get_credentials()
    if credentials is None:
        raise HTTPException(status_code=500, detail="no AWS credentials available for SigV4")
    aws_request = AWSRequest(method="POST", url=url, data=body, headers=base_headers)
    SigV4Auth(credentials.get_frozen_credentials(), "bedrock-agentcore", region).add_auth(aws_request)
    return dict(aws_request.headers)


@router.post("/api/agui/{agent_id}")
async def proxy_agui(
    agent_id: str,
    request: Request,
    user: dict = Depends(require_platform_access),
    db: AsyncSession = Depends(get_session),
):
    agent = await get_agent(db, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"unknown agent {agent_id}")

    body = await request.body()
    session_id = session_id_from_thread(body)
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        SESSION_HEADER: session_id,
    }
    log.debug(
        "proxy %s: auth_mode=%s user=%s session=%s body=%dB",
        agent_id,
        user.get("mode"),
        user.get("user", "-"),
        session_id[:16],
        len(body),
    )

    local_url = os.environ.get(f"LOCAL_AGENT_URL_{agent_id.upper()}", "")
    if local_url:
        url = local_url
        log.debug("proxy %s -> LOCAL override %s", agent_id, url)
    else:
        runtime_arn = agent["runtime_arn"]
        if not runtime_arn:
            raise HTTPException(
                status_code=503,
                detail=f"runtime ARN for {agent_id} is not set in .env, deploy the agent first",
            )
        region = os.environ.get("AWS_REGION", "")
        if not region:
            raise HTTPException(status_code=500, detail="AWS_REGION is not set in .env")
        url = invocation_url(runtime_arn, region)
        # The Phase 0 runtimes are deployed with IAM auth, so the AgentCore
        # call is always SigV4-signed regardless of the app-level auth mode.
        # In entra mode the backend has already validated the user's Entra ID
        # token (SSO at the platform boundary) and now acts as the trusted
        # caller — the "backend exchanges the token and calls AgentCore with
        # SigV4" pattern from doc 05. The user's identity stays in the request
        # context (user["user"]) but is not forwarded upstream.
        headers = sigv4_headers(url, body, region, headers)
        log.debug("proxy %s -> AgentCore (SigV4) %s", agent_id, url.split("?")[0])

    client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=None, write=30, pool=10))
    upstream_request = client.build_request("POST", url, content=body, headers=headers)
    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.HTTPError as error:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"upstream connection failed: {error}")

    if upstream.status_code != 200:
        detail = (await upstream.aread()).decode(errors="replace")
        await upstream.aclose()
        await client.aclose()
        log.warning("proxy %s upstream returned %s: %s", agent_id, upstream.status_code, detail[:200])
        raise HTTPException(status_code=upstream.status_code, detail=detail[:1000])

    log.debug("proxy %s upstream 200, streaming SSE back", agent_id)

    async def pipe():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    media_type = upstream.headers.get("content-type", "text/event-stream")
    return StreamingResponse(pipe(), media_type=media_type)
