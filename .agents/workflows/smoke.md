---
description: Run the live end-to-end AG-UI smoke test against deployed agents
---

## Steps

### 1. Prerequisites
- The backend must be running (`cd Phase0/backend && .venv/bin/uvicorn
  app.main:app --port 8000`).
- Real AWS credentials that can invoke the deployed AgentCore runtimes.
- `AUTH_MODE=entra`: export `SMOKE_BEARER_TOKEN` (and optionally
  `SMOKE_BEARER_TOKEN_NO_ROLE`) first.

### 2. Run
```bash
cd Phase0
uv run scripts/smoke_test.py
```
- Respects `BACKEND_URL` (default `http://localhost:8000`).
- Exercises the planner scenario (story generation, estimation, ticket
  approval HITL) and the release scenario (readiness assessment, go/no-go
  HITL), plus Entra 401/403 checks when `AUTH_MODE=entra`.

### 3. Interpret
- Prints a `[PASS]`/`[FAIL]` line per check and a final `=== G0 REPORT ===`.
  Exit code is non-zero if anything failed.
- On failure, show the failing lines and diagnose the root cause (agent
  runtime not READY, stale catalog ARN — re-sync via `/admin`, or auth
  misconfiguration).
