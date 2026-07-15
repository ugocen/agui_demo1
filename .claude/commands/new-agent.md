---
description: Scaffold a new Strands or LangGraph AgentCore agent
argument-hint: <agent name, framework (strands|langgraph), and purpose>
---

Create a new AgentCore agent: $ARGUMENTS

Launch the `agentcore-agent-builder` subagent to scaffold it under
`Phase0/agents/<name>/` (its own `agent.py` using
`model_factory.build_strands_model()` or `build_langchain_model()` rather than
constructing a model directly, `requirements.txt` including `boto3` +
`python-dotenv`, and `model_factory.py` copied verbatim from a sibling
agent), then build the zip and deploy it. No frontend or backend code is
needed — the catalog is fully generic and picks up the new agent on the next
AgentCore sync. Have it verify with `./scripts/build_zip.sh` and
`uv run scripts/deploy_agent.py`, then summarize. Do not commit unless I ask.
