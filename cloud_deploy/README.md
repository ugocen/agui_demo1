# cloud_deploy — the enterprise side

This directory carries the **enterprise-specific configuration** for the J&J
account, plus the one part of the application that is deliberately forked: the
**agents**. The backend and frontend are not forked — they live once in
[`../Phase0`](../Phase0) and run unchanged here.

## The one real difference: the LLM provider

| | Personal / dev (`Phase0/`) | Enterprise (here) |
|---|---|---|
| Model calls | Amazon Bedrock via AgentCore, **SigV4** | **J&J GenAI API gateway**, `x-api-key` |
| Default model | Claude Haiku 4.5 | Claude Sonnet 4.5 |
| AWS account | personal | enterprise (different account) |
| Runtime | **AgentCore** (identical) | **AgentCore** (identical) |
| Backend / frontend | `Phase0/*` | **the same `Phase0/*`** |
| Agents | `Phase0/agents/*` (Bedrock-only) | `cloud_deploy/agents/*` (gateway-only) |

Each environment has exactly **one** LLM provider, so the provider is not
selected at runtime — it is selected by *which copy you are in*:

* [`Phase0/agents/<a>/model_factory.py`](../Phase0/agents) — Bedrock only. It has
  no gateway code; setting `BEDROCK_ENDPOINT_URL` there does nothing.
* [`agents/<a>/model_factory.py`](agents) — gateway only. It has no Bedrock code,
  requires the endpoint and key, and refuses to build without them.

**Why not one env-driven file?** That is what this used to be, and it meant a
single missing or mistyped variable silently sent enterprise traffic to Amazon
Bedrock — an account that has no Bedrock model access, on data that must not go
there. A fallback that must never fire is better deleted than configured: now the
code path does not exist, so no environment can reach it.

**The cost, and how it is paid:** two copies can drift. `model_factory.py` is the
**only** file allowed to differ; everything else (prompt, tools, graph,
requirements) must land in both. That is enforced, not documented:

```bash
./scripts/sync_agents.sh        # propagate a Phase0 agent change into this copy
./scripts/check_agent_sync.sh   # gate: no drift, and no provider bleed either way
```

The gate fails if an agent differs anywhere but `model_factory.py`, if the
enterprise factory stops requiring the gateway (i.e. grows a Bedrock fallback),
or if the Phase0 factory grows a gateway path.

## What's here

```
env/
  agents.env.example          # J&J gateway URL + api-key + Sonnet model  (the important one)
  backend.env.example         # backend config for the per-component layout
  frontend.env.local.example  # enterprise Entra SPA client id + tenant
```

These are `*.example` templates. Copy each to the real (gitignored) location and
fill secrets:

* `env/agents.env.example`   → set as the **AgentCore runtime env vars** when you
  create each runtime (or, for local standalone agent tests, copy to
  `Phase0/agents/.env`).
* `env/backend.env.example`  → `Phase0/backend/.env` (component-local; the backend
  loads `backend/.env` in preference to the repo-root `Phase0/.env`).
* `env/frontend.env.local.example` → `Phase0/frontend/.env.local`.

## Deploying to the enterprise account

Enterprise Bedrock/AgentCore-Bedrock is unavailable, and there is no scripted
deploy path here — deployment is **manual via the AgentCore Console**.

1. **Build** each agent zip from the single source with the ARM64 packager:
   ```bash
   Phase0/scripts/build_zip.sh Phase0/agents/<agent-dir>
   ```
   (Output: `Phase0/build/<agent>.zip`.)
2. **Create the runtime** in the enterprise AgentCore Console (protocol `AGUI`),
   uploading the zip, and set the runtime **environment variables** from
   `env/agents.env.example` — critically `BEDROCK_ENDPOINT_URL`,
   `BEDROCK_API_KEY`, and `BEDROCK_MODEL_ID`. Setting these flips the agent to
   gateway mode automatically.
3. **Backend + frontend** run the Phase 0 code with the enterprise env files
   above.

## Note on leftover local files

Earlier this directory held full copies of `agents/`, `backend/`, `frontend/`
and prebuilt `aguidemo_v*.zip` bundles. Those duplicated `Phase0/` and have been
removed from version control. Any `agents/`, `backend/`, `frontend/`, `build/`
or `*.zip` still on your disk here are **untracked local artifacts** (including a
possible local `agents/.env` with a real gateway key) — safe to delete once
you've copied any secrets you need into the Phase 0 locations above.
