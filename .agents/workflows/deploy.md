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
```
- Reads `AWS_REGION`, `DEPLOY_BUCKET`, `EXECUTION_ROLE_ARN`, `BEDROCK_MODEL_ID`
  from `Phase0/.env` (never from `backend/.env` — the running backend never
  reads deploy config).
- Uploads the zip to
  `s3://$DEPLOY_BUCKET/<agent-name>/deployment_package.zip`, creates or
  updates the AgentCore runtime with protocol `AGUI`, waits for `READY`, and
  writes the resulting runtime ARN back into `Phase0/.env` (for local
  reference only — the backend catalog gets the ARN by syncing AgentCore, not
  from this file).

### 3. Verify the catalog picks it up
- Restart the backend (or hit "Sync from AgentCore" on `/admin`) — the new or
  updated runtime should appear in `GET /api/agentcore/runtimes` and, once
  registered, in `GET /api/agents`. No frontend or backend code changes are
  needed for a new agent to appear — the catalog is fully generic (invariant
  2).

### 4. Report
- Report the runtime name, ARN, and READY status, or the exact failure
  (`CREATE_FAILED`/`UPDATE_FAILED` reason from the AgentCore API).
