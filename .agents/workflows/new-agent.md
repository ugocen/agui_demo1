---
description: Scaffold a new Strands or LangGraph agent under Phase0/agents/
---

## Steps

Agents are fully generic from the platform's point of view: a new agent needs
no backend or frontend code (invariant 2) — it appears in the catalog once
deployed and synced from AgentCore.

### 1. Create the agent directory
- `Phase0/agents/<name>/` with:
  - `agent.py` — the agent entry point, using
    `model_factory.build_strands_model()` (Strands) or
    `model_factory.build_langchain_model()` (LangGraph) so the model provider
    stays env-driven (invariant 4). Serve the AgentCore contract: `POST
    /invocations` (SSE, `AGUI` protocol), `GET /ping`, `/ws`, port 8080.
  - `model_factory.py` — copy verbatim from a sibling agent (e.g.
    `agents/sdlc-planner-strands/model_factory.py`); every agent carries its
    own copy since each is packaged as an independent zip. Never hand-edit it
    to hardcode a provider.
  - `requirements.txt` — pin versions (see `Phase0/VERSIONS.md`); include
    `boto3` and `python-dotenv` (for local `.env` loading) plus the framework
    package (`strands-agents` + `ag-ui-strands`, or `langgraph` +
    `langchain-aws` + `ag-ui-langgraph`) and `bedrock-agentcore`.
  - `tools.py` (optional) — any backend tool definitions the agent emits.

### 2. Local standalone test (optional)
```bash
cd Phase0/agents/<name>
uv venv .venv -p 3.13 && uv pip install --python .venv/bin/python -r requirements.txt
BEDROCK_MODEL_ID=... AWS_REGION=... .venv/bin/python agent.py   # port 8080
```
- Or copy `Phase0/agents/.env.example` to `.env` in the agent directory for
  local model config (auto-loaded via `python-dotenv`).

### 3. Build and deploy
```bash
cd Phase0
./scripts/build_zip.sh agents/<name>
uv run scripts/deploy_agent.py <name> build/<name>.zip
```
- If deploying a brand-new agent name not yet in `deploy_agent.py`'s
  `ARN_ENV_KEYS`, add an entry there (it is only used to write the resulting
  ARN back to `Phase0/.env` for local reference — the catalog itself is
  populated by syncing AgentCore, not from this map).

### 4. Verify it appears in the catalog
- Restart the backend or use "Sync from AgentCore" on `/admin`. A new AG-UI
  runtime is auto-registered with `ui_mode='a2ui'`.

### 5. Report
- Report the files created, the zip build result, and the deploy result
  (runtime ARN + READY status).
