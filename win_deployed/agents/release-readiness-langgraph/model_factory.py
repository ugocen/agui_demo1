"""Model factory — enterprise GenAI API marketplace gateway (x-api-key).

The enterprise runs in its own AWS account, which has no Bedrock model access;
the marketplace gateway is the only LLM provider. This file therefore has **no
Amazon Bedrock code path at all** — there is no environment variable, and no
misconfiguration, that can make an enterprise agent call Bedrock. That is the
whole point of the fork (AGENTS.md invariant 4): the guarantee is structural, not
configuration-dependent. The predecessor selected the provider from the
environment, which meant one missing variable silently sent enterprise traffic to
Amazon Bedrock.

The Phase0 counterpart at Phase0/agents/<agent>/model_factory.py is the mirror
image — Bedrock-only, with no gateway path. They are the ONLY files that may
differ between the two copies; cloud_deploy/scripts/check_agent_sync.sh keeps
everything else identical and proves neither side grew the other's provider.

Required environment (cloud_deploy/agents/.env; injected onto the AgentCore
runtime by scripts/deploy_agent.py). All are mandatory — there is nothing to fall
back to:
  BEDROCK_ENDPOINT_URL  gateway base URL
  BEDROCK_API_KEY       gateway key, sent as the ``x-api-key`` header
  BEDROCK_MODEL_ID      model id
  BEDROCK_STREAMING     "false"/"0"/"no"/"off" to disable ConverseStream

This file is intentionally self-contained and duplicated into each agent
directory: every agent is packaged as an independent AgentCore zip (its own
requirements.txt + sources at the zip root), so it must carry its own copy.
Keep the copies identical; if you edit one, mirror the change to the others.
"""

import os

# The gateway authenticates with x-api-key and ignores the SigV4 scope, so the
# region is a placeholder — the marketplace's own code samples pass "dummy" too.
# Pinning it is a safety property, not cosmetics: a non-routable region leaves
# botocore unable to resolve a real AWS endpoint, so anything that escaped the
# gateway would fail closed rather than reach Amazon Bedrock. It is also what
# keeps langchain's control-plane client (built during validation, and not given
# our endpoint) off a live bedrock.<region>.amazonaws.com.
GATEWAY_REGION = "dummy"

# Only the operations our agents actually issue: Strands and langchain both use
# the Converse family, and Strands issues CountTokens when it measures context.
SIGNED_OPS = ("Converse", "ConverseStream", "CountTokens")


def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"{name} is not set. Enterprise agents have no Amazon Bedrock "
            "fallback by design — the GenAI marketplace gateway must be fully "
            "configured (see cloud_deploy/agents/.env)."
        )
    return value


def _model_id() -> str:
    return _require("BEDROCK_MODEL_ID")


def _streaming() -> bool:
    return os.environ.get("BEDROCK_STREAMING", "true").strip().lower() not in ("0", "false", "no", "off")


def _sign_with_api_key(client) -> None:
    """Attach the gateway key to every operation we issue."""
    api_key = _require("BEDROCK_API_KEY")

    def _add_api_key(model, params, request_signer, **kwargs):  # noqa: ARG001
        params["headers"]["x-api-key"] = api_key

    for op in SIGNED_OPS:
        client.meta.events.register(f"before-call.bedrock-runtime.{op}", _add_api_key)


def _dummy_session():
    """A session with placeholder credentials — nothing here is ever SigV4-verified."""
    import boto3

    return boto3.Session(
        aws_access_key_id="dummy",
        aws_secret_access_key="dummy",
        region_name=GATEWAY_REGION,
    )


def build_strands_model():
    """Build a Strands ``BedrockModel`` bound to the gateway."""
    from strands.models import BedrockModel

    model = BedrockModel(
        model_id=_model_id(),
        boto_session=_dummy_session(),
        endpoint_url=_require("BEDROCK_ENDPOINT_URL"),
        streaming=_streaming(),
    )
    _sign_with_api_key(model.client)
    return model


def build_langchain_model():
    """Build a langchain-aws ``ChatBedrockConverse`` bound to the gateway."""
    from langchain_aws import ChatBedrockConverse

    client = _dummy_session().client(
        "bedrock-runtime",
        endpoint_url=_require("BEDROCK_ENDPOINT_URL"),
        region_name=GATEWAY_REGION,
    )
    _sign_with_api_key(client)
    # ChatBedrockConverse also builds a `bedrock` control-plane client during
    # validation. The dummy static credentials let it construct without an AWS
    # credential chain, and GATEWAY_REGION keeps that client pointed at a
    # non-routable host. It is never called for our model ids anyway (that path
    # only triggers for an application-inference-profile id).
    return ChatBedrockConverse(
        model=_model_id(),
        client=client,
        region_name=GATEWAY_REGION,
        aws_access_key_id="dummy",
        aws_secret_access_key="dummy",
        disable_streaming=not _streaming(),
    )
