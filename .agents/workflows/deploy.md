---
description: Deploy an agent zip to Bedrock AgentCore Runtime
---

## Steps

### 1. Build the zip
```bash
cd Phase0
./scripts/build_zip.sh agents/<agent-dir>
```

### 2. Deploy
```bash
cd Phase0
uv run scripts/deploy_agent.py <agent-name> <zip-path>

# runtime config only — no zip, no build, no upload; keeps the running code
uv run scripts/deploy_agent.py <agent-name> --config-only
```
- `--config-only` is for what lives on the runtime rather than in the package:
  the request-header allowlist, the inbound authorizer, environment variables.
  Skip step 1 entirely for those. It requires the runtime to exist already.
- Reads `AWS_REGION`, `DEPLOY_BUCKET`, `EXECUTION_ROLE_ARN`, `BEDROCK_MODEL_ID`
  from `Phase0/.env` (never from `backend/.env` — the running backend never
  reads deploy config).
- Resolves the target runtime **catalog-first**: the platform DB
  (`backend/phase0.db`, table `agent_catalog`; override the path with
  `CATALOG_DB_PATH` in `Phase0/.env`) holds the runtime ARN the backend proxy
  routes on, so that runtime is the one updated. The name-derived runtime
  (`-` → `_`) is only the find-or-create fallback when no catalog entry exists
  — e.g. the first deploy of a brand-new agent. A loud warning is printed when
  the catalog target and the name-derived runtime disagree (several live
  runtimes are hand-created, e.g. `Planner-…` vs `sdlc_planner_strands`).
- Uploads the zip to
  `s3://$DEPLOY_BUCKET/<agent-name>/deployment_package.zip`, updates the
  AgentCore runtime with protocol `AGUI`, and waits for `READY`. Runtime ARNs
  are never written back into `.env` — the catalog is their only home
  (invariant 2).

### 3. Verify the catalog picks it up
- Restart the backend (or hit "Sync from AgentCore" on `/admin`) — the new or
  updated runtime should appear in `GET /api/agentcore/runtimes` and, once
  registered, in `GET /api/agents`. No frontend or backend code changes are
  needed for a new agent to appear — the catalog is fully generic (invariant
  2).

### 4. Report
- Report the runtime name, ARN, and READY status, or the exact failure
  (`CREATE_FAILED`/`UPDATE_FAILED` reason from the AgentCore API).
