---
description: Verify the repo end to end (ruff clean, frontend build + lint green)
---

Verify Phase 0 is healthy. Prefer launching the `phase0-verifier` subagent so
the checks run and report in one place. It should run
`ruff check agents backend/app --exclude '**/.venv/**'` from `Phase0/`, and
`npm run build && npm run lint` from `Phase0/frontend/` (running `npm
install` first if `node_modules` is missing).

Report a compact pass/fail table and an overall verdict. Note that the live
`scripts/smoke_test.py`, the CopilotKit browser runtime, and Entra login
cannot be verified headlessly. Do not change code as part of verifying —
surface failures instead.
