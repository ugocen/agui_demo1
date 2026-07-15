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
agents/                       # THE ENTERPRISE AGENT FORK — tracked, not scratch space
  <agent>/model_factory.py    #   gateway-only provider (the one file that may differ)
  <agent>/agent.py, ...       #   kept byte-identical to Phase0/agents/ by the sync
  .env                        #   real gateway config (gitignored; never commit)
scripts/
  _agents.sh                  # single definition: which agents, which files may differ
  sync_agents.sh              # propagate a Phase0 agent change into the fork
  check_agent_sync.sh         # gate: no drift, no provider bleed either way
env/
  agents.env.example          # J&J gateway URL + api-key + Sonnet model  (the important one)
  backend.env.example         # backend config for the per-component layout
  frontend.env.local.example  # enterprise Entra SPA client id + tenant
```

`agents/` is **version-controlled source**, not a local artifact. It is what
`win_deployed/` packages and what the enterprise runs.

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

> **Package the enterprise copy, never `Phase0/agents/`.** `Phase0/agents/` is
> Bedrock-only (invariant 4) and would be dead on arrival in an account with no
> Bedrock model access. The zip must come from `cloud_deploy/agents/`.

1. **Get the zip.** The built, gateway-only packages are already committed and
   verified — prefer them over rebuilding:
   ```
   win_deployed/dist/agentcore/<agent>.zip
   ```
   To rebuild from source instead, point the ARM64 packager at the **enterprise**
   copy (output still lands in `Phase0/build/<agent>.zip`):
   ```bash
   Phase0/scripts/build_zip.sh cloud_deploy/agents/<agent-dir>
   ```
2. **Create the runtime** in the enterprise AgentCore Console: protocol `AGUI`,
   runtime `PYTHON_3_13`, entrypoint `agent.py`, upload the zip.
3. **Set the runtime environment variables.** The console is the only place these
   are supplied — they are not in the zip. All three are **mandatory**; the agent
   raises `RuntimeError` at startup without them and has no Bedrock fallback:

   | Variable | Value |
   |---|---|
   | `BEDROCK_ENDPOINT_URL` | Gateway **base** URL, e.g. `https://genaiapigwna.jnj.com`. No `/model/...` or `/converse` path — botocore appends it. |
   | `BEDROCK_API_KEY` | The gateway key. Sent as the `x-api-key` header. |
   | `BEDROCK_MODEL_ID` | e.g. `global.anthropic.claude-sonnet-4-5-20250929-v1:0`. There is no default. |
   | `BEDROCK_STREAMING` | Optional, defaults on. Set `false` if the gateway does not proxy `converse-stream`. |

   Forgetting one produces the *same* symptom as a wrong port — the runtime never
   goes healthy and the invoke fails with an initialization timeout. The real
   error is in the `[runtime-logs]` stream of the runtime's log group; see
   "Reading the logs" below.
4. **Backend + frontend** run the Phase 0 code with the enterprise env files
   above.

### Reading the logs

One log group per runtime endpoint, created by AgentCore on first invocation:

```
/aws/bedrock-agentcore/runtimes/<runtimeId>-DEFAULT
  ├─ [runtime-logs] <UUID>   ← stdout/stderr: tracebacks, the RuntimeError above
  └─ otel-rt-logs            ← ADOT structured logs + spans
```

The runtime id is `<agent-name with - replaced by _>-<suffix AgentCore generates>`,
so `a2ui-demo-strands` becomes e.g. `a2ui_demo_strands-XjHRIuAVCG`. List them with
`aws bedrock-agentcore-control list-agent-runtimes`, then
`aws logs tail /aws/bedrock-agentcore/runtimes/<id>-DEFAULT --since 1d`.

Spans and traces (GenAI Observability) additionally need **CloudWatch Transaction
Search** enabled once per account+region.

## Note on leftover local files

> **`agents/` is NOT a leftover.** An earlier revision of this note called any
> `agents/` here a deletable local artifact. That was true for about a day, and is
> now dangerously wrong: `agents/` is the tracked enterprise fork (invariant 4).
> Deleting it deletes the gateway-only build that the enterprise runs.

Earlier this directory held full copies of `backend/` and `frontend/` and prebuilt
`aguidemo_v*.zip` bundles. Those duplicated `Phase0/` and have been removed from
version control. Any `backend/`, `frontend/`, `build/` or `*.zip` still on your
disk here are **untracked local artifacts** — safe to delete.

`agents/.env` is also untracked, but it holds the real gateway key: do not delete
it without keeping the key somewhere, and never commit it.
