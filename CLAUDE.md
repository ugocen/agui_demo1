# CLAUDE.md

Project guidance is canonical in @AGENTS.md — read it first (the 7
architecture invariants, the command cheatsheet, where things live, and how
to verify). This file only adds the Claude Code specifics so the two never
drift.

## Collaboration protocol — PR-based, no exceptions

`git pull` on `main` first → create a new branch off `main` → commit → push
the branch → open a PR → merge the PR → `git pull` `main`. Never commit
directly to `main`; never force-push `main`. On push rejection,
`git pull --rebase`. Full rule: `.agents/rules/50-collaboration.md`.

**Always `gh pr create --base main`.** The repo's GitHub *default branch* is the
stale `phase0` (~39 commits behind `main`), so a PR opened without `--base`
silently targets it and merges into a dead branch while `main` never receives the
change — `gh pr merge` still reports success. After merging, confirm with
`git log --oneline -1 origin/main`.

## Agents live in two copies — edit both

Per AGENTS.md invariant 4, `Phase0/agents/` is Bedrock-only and
`cloud_deploy/agents/` is gateway-only; only `model_factory.py` may differ. After
touching any agent, run `./cloud_deploy/scripts/sync_agents.sh` then
`./cloud_deploy/scripts/check_agent_sync.sh` — the gate fails on drift and on
either side growing the other's provider.

## Claude Code specifics

- **Subagents** (`.claude/agents/`): `phase0-verifier` (read-only health
  check — ruff + frontend build/lint), `a2ui-component-builder` (add a
  component to `richCatalog.tsx` end to end), `agentcore-agent-builder`
  (scaffold + build + deploy a new Strands/LangGraph AgentCore agent).
- **Commands** (`.claude/commands/`): `/check`, `/run`, `/build`, `/verify`,
  `/smoke`, `/deploy`, `/add-a2ui-component`, `/new-agent`,
  `/aws-bootstrap`.
- **Permissions**: `.claude/settings.json` allowlists common dev commands;
  `.claude/settings.local.json` is personal and untouched by this scaffold.

After changes, prefer `/verify` (or the `phase0-verifier` subagent) to
confirm the repo is still healthy.
