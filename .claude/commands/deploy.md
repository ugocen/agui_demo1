---
description: Deploy an agent zip to Bedrock AgentCore Runtime
argument-hint: <agent-name> <zip-path, e.g. build/sdlc-planner-strands.zip>
---

Deploy an agent to AgentCore: $ARGUMENTS

```bash
cd Phase0
uv run scripts/deploy_agent.py $ARGUMENTS
```

Reads `AWS_REGION`, `DEPLOY_BUCKET`, `EXECUTION_ROLE_ARN`, `BEDROCK_MODEL_ID`
from `Phase0/.env` (never `backend/.env`). Resolves the target runtime
catalog-first: the platform DB (`backend/phase0.db`, table `agent_catalog`)
holds the ARN the backend proxy routes on, so that runtime is the one updated;
the name-derived runtime (`-` → `_`) is only the find-or-create fallback when
no catalog entry exists. Prints a loud warning when the two disagree. Uploads
the zip to S3, updates the runtime with protocol `AGUI`, and waits for
`READY`. Runtime ARNs are never written to `.env`.

No frontend or backend code changes are needed for the new/updated agent to
appear — the catalog is fully generic and picks it up on the next AgentCore
sync (backend restart, or "Sync from AgentCore" on `/admin`). Report the
runtime name, ARN, and READY status, or the exact failure reason.
