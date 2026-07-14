"""Model factory — selects the LLM provider from the environment.

A single agent codebase runs unchanged in both deployment targets:

* Default (personal / AgentCore)  — Amazon Bedrock with the host's default
  credential chain (SigV4). Used whenever gateway mode is not configured.
* Enterprise gateway              — a Bedrock-Runtime-compatible API gateway
  that authenticates with an ``x-api-key`` header instead of SigV4 (e.g. an
  internal GenAI marketplace gateway). Activated ONLY when both
  ``BEDROCK_ENDPOINT_URL`` and ``BEDROCK_API_KEY`` are set.

Environment variables:
  BEDROCK_MODEL_ID      model id (default: Claude Haiku 4.5 global profile)
  BEDROCK_ENDPOINT_URL  gateway base URL — set with BEDROCK_API_KEY to enable gateway mode
  BEDROCK_API_KEY       gateway key, injected as the ``x-api-key`` header
  AWS_REGION            region (gateway: only the ignored SigV4 scope; default us-east-1)
  BEDROCK_STREAMING     "false"/"0"/"no"/"off" to disable ConverseStream (default: stream)

This file is intentionally self-contained and duplicated into each agent
directory: every agent is packaged as an independent AgentCore zip (its own
requirements.txt + sources at the zip root), so it must carry its own copy.
Keep the copies identical; if you edit one, mirror the change to the others.
"""

import os

DEFAULT_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"


def _endpoint() -> str:
    return os.environ.get("BEDROCK_ENDPOINT_URL", "").strip()


def _api_key() -> str:
    return os.environ.get("BEDROCK_API_KEY", "").strip()


def use_gateway() -> bool:
    """Gateway mode is on only when both the endpoint and the key are set."""
    return bool(_endpoint() and _api_key())


def _model_id() -> str:
    return os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID)


def _region() -> str:
    return os.environ.get("AWS_REGION", "us-east-1")


def _streaming() -> bool:
    return os.environ.get("BEDROCK_STREAMING", "true").strip().lower() not in ("0", "false", "no", "off")


def build_strands_model():
    """Build a Strands ``BedrockModel`` for the active provider."""
    from strands.models import BedrockModel

    if not use_gateway():
        return BedrockModel(model_id=_model_id())

    import boto3

    api_key = _api_key()
    session = boto3.Session(
        aws_access_key_id="dummy",
        aws_secret_access_key="dummy",
        region_name=_region(),
    )
    model = BedrockModel(
        model_id=_model_id(),
        boto_session=session,
        endpoint_url=_endpoint(),
        streaming=_streaming(),
    )

    def _add_api_key(model, params, request_signer, **kwargs):  # noqa: ARG001
        params["headers"]["x-api-key"] = api_key

    events = model.client.meta.events
    for op in ("Converse", "ConverseStream", "CountTokens"):
        events.register(f"before-call.bedrock-runtime.{op}", _add_api_key)
    return model


def build_langchain_model():
    """Build a langchain-aws ``ChatBedrockConverse`` for the active provider."""
    from langchain_aws import ChatBedrockConverse

    if not use_gateway():
        return ChatBedrockConverse(model_id=_model_id())

    import boto3

    api_key = _api_key()
    session = boto3.Session(aws_access_key_id="dummy", aws_secret_access_key="dummy")
    client = session.client(
        "bedrock-runtime",
        endpoint_url=_endpoint(),
        region_name=_region(),
    )

    def _add_api_key(model, params, request_signer, **kwargs):  # noqa: ARG001
        params["headers"]["x-api-key"] = api_key

    for op in ("Converse", "ConverseStream", "CountTokens"):
        client.meta.events.register(f"before-call.bedrock-runtime.{op}", _add_api_key)
    # ChatBedrockConverse also builds a `bedrock` control-plane client during
    # validation; with dummy static creds it constructs cleanly and is never
    # called at runtime (our model id is not an inference profile).
    return ChatBedrockConverse(
        model=_model_id(),
        client=client,
        region_name=_region(),
        aws_access_key_id="dummy",
        aws_secret_access_key="dummy",
        disable_streaming=not _streaming(),
    )
