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
from `Phase0/.env` (never `backend/.env`). Uploads the zip to S3, creates or
updates the AgentCore runtime with protocol `AGUI`, waits for `READY`, and
writes the runtime ARN back into `Phase0/.env`.

No frontend or backend code changes are needed for the new/updated agent to
appear — the catalog is fully generic and picks it up on the next AgentCore
sync (backend restart, or "Sync from AgentCore" on `/admin`). Report the
runtime name, ARN, and READY status, or the exact failure reason.
