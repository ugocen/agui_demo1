# Start here

Before doing anything in this repository, read the root `AGENTS.md` — it is
the canonical guide: what the project is, the 7 architecture invariants, the
command cheatsheet, where to add things, and how to verify.

Phase 0 is the application: a local Next.js/CopilotKit frontend plus a local
FastAPI backend proxy, streaming AG-UI over SSE to Strands/LangGraph agents on
Amazon Bedrock AgentCore. It lives entirely under `Phase0/`.

`cloud_deploy/` is **not** a second application — it is an enterprise
configuration overlay (env files only) for the same `Phase0/` code. Never fork
or duplicate app code into `cloud_deploy/`.

Use the PR workflow for every change (see `50-collaboration.md`): pull main,
branch, commit, push, open a PR, merge, pull main again. Never commit directly
to `main`.
