---
description: Verify the repo end to end (ruff clean, frontend build + lint green)
---

## Steps

### 1. Python
```bash
cd Phase0
ruff check agents backend/app --exclude '**/.venv/**'
```
- Must be clean.

### 2. Frontend
```bash
cd Phase0/frontend
npm run build && npm run lint
```
- Run `npm install` first if `node_modules` is missing. Both must be green.

### 3. What this does not cover
- `scripts/smoke_test.py` needs a running backend and real AWS credentials
  against live AgentCore runtimes — it cannot run headless here. Run it
  manually (see `smoke.md`) when you need end-to-end confirmation.
- The CopilotKit browser runtime and Entra login also need a real browser and
  cannot be verified from this workflow.

### 4. Report
- Report a compact pass/fail table with the exact error lines for any
  failure. Do not change code as part of verifying — surface failures
  instead. Do not report a change complete while any runnable check fails.
