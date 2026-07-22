"""Model factory — Amazon Bedrock (SigV4).

Phase0 runs in our own AWS account, where Amazon Bedrock is the only LLM
provider, so this file has no enterprise-gateway code path: no environment
variable can make a Phase0 agent talk to the marketplace gateway.

The enterprise counterpart at cloud_deploy/agents/<agent>/model_factory.py is the
mirror image — gateway-only, with no Bedrock path. They are the ONLY files that
may differ between the two copies; cloud_deploy/scripts/check_agent_sync.sh keeps
everything else identical and proves neither side grew the other's provider.
See AGENTS.md invariant 4.

Environment variables:
  BEDROCK_MODEL_ID  model id (default: Claude Haiku 4.5 global profile)
  AWS_REGION        resolved by the standard AWS credential/config chain

This file is intentionally self-contained and duplicated into each agent
directory: every agent is packaged as an independent AgentCore zip (its own
requirements.txt + sources at the zip root), so it must carry its own copy.
Keep the copies identical; if you edit one, mirror the change to the others.
"""

import os

DEFAULT_MODEL_ID = "global.anthropic.claude-haiku-4-5-20251001-v1:0"


def _model_id() -> str:
    return os.environ.get("BEDROCK_MODEL_ID", DEFAULT_MODEL_ID)


def build_strands_model():
    """Build a Strands ``BedrockModel`` on Amazon Bedrock."""
    from strands.models import BedrockModel

    return BedrockModel(model_id=_model_id())


def build_langchain_model():
    """Build a langchain-aws ``ChatBedrockConverse`` on Amazon Bedrock."""
    from langchain_aws import ChatBedrockConverse

    return ChatBedrockConverse(model_id=_model_id())
