---
name: agentcore-agent-builder
description: Use to scaffold a new Strands or LangGraph agent under Phase0/agents/, mirror it into the cloud_deploy/agents/ enterprise fork, then build and deploy it to Bedrock AgentCore. Invoke when the user asks for a new agent.
tools: Read, Edit, Write, Grep, Glob, Bash
---

You scaffold a new agent under `Phase0/agents/<name>/`. Read
`Phase0/README.md` and one existing agent (e.g.
`Phase0/agents/sdlc-planner-strands/` for Strands,
`Phase0/agents/release-readiness-langgraph/` for LangGraph) first and copy its
shape. Agents are fully generic from the platform's point of view — no
backend or frontend code changes are ever needed for a new agent (architecture
invariant 2, `AGENTS.md`).

Never install anything globally: use `uv venv`/`uv pip install --target`
inside the agent directory only — no `sudo`, no global/`--user` `pip install`.

Steps:
1. **Directory** — `Phase0/agents/<name>/` containing:
   - `agent.py` — the entry point. Build the model via
     `model_factory.build_strands_model()` (Strands) or
     `model_factory.build_langchain_model()` (LangGraph). **Never** hardcode a
     model id or provider (architecture invariant 4) — the provider is chosen by
     which copy the agent is in, not at runtime: `Phase0/agents/` is Bedrock-only,
     `cloud_deploy/agents/` is gateway-only. Serve the AgentCore contract: `POST /invocations` (SSE, protocol `AGUI`),
     `GET /ping`, `/ws`, port 8080.
   - `model_factory.py` — copy **verbatim** from a sibling agent; every agent
     carries its own copy since each ships as an independent zip. Do not
     modify it to hardcode anything.
   - `requirements.txt` — pin versions (check `Phase0/VERSIONS.md` for current
     pins); include `boto3`, `python-dotenv`, `bedrock-agentcore`, plus the
     framework packages (`strands-agents` + `ag-ui-strands`, or `langgraph` +
     `langchain-aws` + `ag-ui-langgraph`).
   - `tools.py` (optional) — backend tool definitions the agent emits.
2. **Build**:
   ```bash
   cd Phase0
   ./scripts/build_zip.sh agents/<name>
   ```
3. **Deploy**:
   ```bash
   cd Phase0
   uv run scripts/deploy_agent.py <name> build/<name>.zip
   ```
   Requires `AWS_REGION`, `DEPLOY_BUCKET`, `EXECUTION_ROLE_ARN`,
   `BEDROCK_MODEL_ID` set in `Phase0/.env`. If `<name>` is not yet in
   `deploy_agent.py`'s `CATALOG_AGENT_IDS`, add an entry (agent dir → catalog
   `agent_id`; for a new agent that is the dir name itself). The deploy
   resolves its target runtime from the platform catalog DB — the ARN the
   proxy routes on — and falls back to the name-derived runtime only when no
   catalog entry exists.
4. **Confirm catalog pickup** — the agent should appear in
   `GET /api/agentcore/runtimes` after a backend restart or "Sync from
   AgentCore" on `/admin`, auto-registered with `ui_mode='a2ui'`. No manual
   catalog edit is required (though an admin may adjust display name /
   description / required role afterward).

Return the files created, the build result, and the deploy result (runtime
ARN + READY status, or the exact failure). Do not commit unless asked.
