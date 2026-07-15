# Start here

Before doing anything in this repository, read the root `AGENTS.md` — it is
the canonical guide: what the project is, the 7 architecture invariants, the
command cheatsheet, where to add things, and how to verify.

Phase 0 is the application: a local Next.js/CopilotKit frontend plus a local
FastAPI backend proxy, streaming AG-UI over SSE to Strands/LangGraph agents on
Amazon Bedrock AgentCore. It lives entirely under `Phase0/`.

`cloud_deploy/` is the enterprise side: the enterprise env files, **plus one
deliberate fork — the agents**. `cloud_deploy/agents/` is a permanent second copy
whose `model_factory.py` is gateway-only; `Phase0/agents/` is Bedrock-only. That
fork is the point, not an accident: do not "unify" it back (see
`10-invariants.md` 4 and 7). The backend and frontend are *not* forked — they
live once, in `Phase0/`, and `cloud_deploy/` only supplies their env.

After changing any agent, run `cloud_deploy/scripts/sync_agents.sh` then
`cloud_deploy/scripts/check_agent_sync.sh` — everything except `model_factory.py`
must stay identical across the two copies, and the gate enforces it.

Use the PR workflow for every change (see `50-collaboration.md`): pull main,
branch, commit, push, open a PR, merge, pull main again. Never commit directly
to `main`.
