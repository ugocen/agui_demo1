# cloud_deploy — enterprise overlay

This directory is **not a separate application.** The application (backend,
frontend, agents) lives once in [`../Phase0`](../Phase0) and is the single
source of truth. `cloud_deploy/` only carries the **enterprise-specific
configuration** needed to run that same code on the enterprise (J&J) account.

## The one real difference: the LLM provider

| | Personal / dev (Phase 0 default) | Enterprise (this overlay) |
|---|---|---|
| Model calls | Amazon Bedrock via AgentCore, **SigV4** (host credential chain) | **J&J GenAI API gateway**, `x-api-key` header |
| Default model | Claude Haiku 4.5 | Claude Sonnet 4.5 |
| AWS account | personal | enterprise (different account) |
| Runtime | **AgentCore** (identical) | **AgentCore** (identical) |
| Backend / frontend / agent code | `Phase0/*` | **the same `Phase0/*`** |

Everything except the model provider is byte-for-byte the same code. The
provider is chosen **purely from the environment** by
[`Phase0/agents/model_factory.py`](../Phase0/agents/model_factory.py):

* Leave `BEDROCK_ENDPOINT_URL` / `BEDROCK_API_KEY` empty → **Bedrock** (personal).
* Set **both** → **gateway** (enterprise). No code change either way.

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
