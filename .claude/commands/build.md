---
description: Build an AgentCore deployment zip for one agent
argument-hint: <agent-dir under Phase0/agents/, e.g. sdlc-planner-strands>
---

Build the AgentCore direct-code-deployment zip for: $ARGUMENTS

```bash
cd Phase0
./scripts/build_zip.sh agents/$ARGUMENTS
```

This installs linux/arm64 wheels, copies the agent sources to the package
root, verifies every native binary is ARM64, and zips from inside the package
folder — failing loudly on size or architecture violations. Output:
`Phase0/build/$ARGUMENTS.zip`.

For a frontend-only pre-flight build, run `cd Phase0/frontend && npm run
build` instead. Report the zip path and size, or the exact build failure.
