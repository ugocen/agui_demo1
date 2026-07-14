---
description: Run the live end-to-end AG-UI smoke test against deployed agents
argument-hint: (optional notes)
---

Run the live end-to-end smoke test and report the result. Requires the
backend running and real AWS credentials against deployed AgentCore runtimes.

```bash
cd Phase0
uv run scripts/smoke_test.py
```

Respects `BACKEND_URL` (default `http://localhost:8000`). It exercises the
planner scenario (stories, estimation, ticket-approval HITL) and the release
scenario (readiness assessment, go/no-go HITL), plus Entra 401/403 checks
when `AUTH_MODE=entra` (export `SMOKE_BEARER_TOKEN` first). Prints a
`[PASS]`/`[FAIL]` line per check and a final `=== G0 REPORT ===`. If it fails,
show the failing lines and diagnose. $ARGUMENTS
