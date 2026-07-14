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
