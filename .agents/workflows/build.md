---
description: Build an AgentCore deployment zip for one agent
---

## Steps

### 1. Build the zip
```bash
cd Phase0
./scripts/build_zip.sh agents/<agent-dir>
```
- Installs linux/arm64 wheels for the agent's `requirements.txt`, copies its
  sources to the package root, verifies every native binary is ARM64, and
  zips from inside the package folder. Fails loudly on size (250 MB zipped /
  750 MB unzipped) or architecture violations.
- Output: `Phase0/build/<agent>.zip`.

### 2. Frontend production build (pre-flight for frontend changes)
```bash
cd Phase0/frontend
npm run build
```

### 3. Report
- Report the zip path and size, or the frontend build result. If a build
  fails, show the exact error and diagnose before retrying.
