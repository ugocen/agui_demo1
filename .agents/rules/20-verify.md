# Always verify after changes

After any code change, verify before considering the work done (or run the
`/verify` workflow):

- **Python:** `cd Phase0 && ruff check agents backend/app --exclude
  '**/.venv/**'` — must be clean.
- **Frontend:** `cd Phase0/frontend && npm run build && npm run lint` — must
  be green. Run `npm install` first if `node_modules` is missing.

The live end-to-end smoke, `cd Phase0 && uv run scripts/smoke_test.py`, needs
a **running backend** and **real AWS credentials** against deployed AgentCore
runtimes — it cannot run headless as part of routine verification. Run it
manually when you need to confirm end-to-end behavior, and note in your report
that it was not run if it wasn't.

Do not report a change complete while any runnable check fails.
