# Cleanup log — dead code, AI traces, win_deployed zips (pass 2)

Second pass of the `cleanup/dead-code-and-ai-traces` workflow, run 2026-07-19 on
branch `cleanup/dead-code-and-ai-traces-2`. The original branch name from PR #37
already exists and is preserved — branches are never deleted in this repo, so
this pass uses a suffixed name, and it merges without `--delete-branch`.

PR #37 ran this same workflow earlier today: its dead-code pass found nothing,
and its language pass translated two Turkish markdown files
(`DURUM-RAPORU-…` → `STATUS-REPORT-2026-07-18.md`,
`SUNUM-AGUI-A2UI.md` → `Phase0/PRESENTATION-AGUI-A2UI.md`). This pass
re-verifies everything from scratch.

Entry format:

    ## [pass name] file/path.ext
    * What / Why / Confidence (definite | likely | needs verification) / Result

---

## Dead code pass (project-wide)

* What: Scanned all Python (`Phase0/agents`, `Phase0/backend/app`,
  `Phase0/scripts`, `cloud_deploy/agents`) and all TypeScript
  (`Phase0/frontend/src`) for unused imports/variables/parameters, unreachable
  code, unused exports, commented-out code blocks, banner/divider comments, and
  stale feature flags. Tools: `ruff` (Python), `eslint` (TS), plus targeted
  regex for commented-out code and dividers. Spot-read the core logic files
  (`agui_proxy.py`, `main.py`, `press-release-strands/agent.py`) to judge dead
  exports and impossible branches that linters do not catch.
* Why: n/a — nothing found.
* Confidence: definite
* Result: skipped (nothing removed). `ruff` and `eslint` both report zero
  findings; no commented-out code, no divider banners, no reachable-but-dead
  branches, no unused exports. The comments that exist are all real "why"
  notes (e.g. the SigV4/no-buffer rationale in `agui_proxy.py`, the `LOCAL_DEV`
  OTEL workaround in each agent) and were kept.

## AI traces and language pass (project-wide)

* What: Scanned for emoji, "Note:/Important:/Here's how" filler comments,
  placeholder stubs ("your code here", "rest of impl"), decorative separators,
  verbose docstrings on trivial functions, and any Turkish text (in code,
  comments, strings, identifiers, docstrings, and file names).
* Why: n/a — nothing found that qualifies.
* Confidence: definite
* Result: skipped (nothing rewritten). Details:
  - **Turkish:** zero. No Turkish-specific letters (ğ ş ı İ Ğ Ş) in any tracked
    file; the two files PR #37 translated are in place under English names; no
    Turkish-named files remain. (`ç/ö/ü` matches were all curly quotes and
    emoji bytes in English UI strings, not Turkish.)
  - **Emoji:** the only emoji in source are UI status glyphs in JSX —
    `✓`/`⏳` (tool state, `AgentChat.tsx`), `✅`/`⚠️`/`❌` (`ChecklistCard.tsx`),
    `⚙` (`WorkspaceShell.tsx`). Zero emoji in comments. These are user-visible
    content, not AI traces, and were kept.
  - **Filler comments / placeholders / banners:** none found.

## win_deployed zips

**How the zips are produced (inspected before touching anything).** The archives
are generated from source by committed scripts under `win_deployed/scripts/`;
they are never hand-edited:

* `_payload.sh` — the single definition of *what* ships. `backend/` and
  `frontend/` are copied verbatim from `Phase0/`; `agents/` are copied from the
  enterprise fork `cloud_deploy/agents/` (gateway-only provider, AGENTS.md
  invariant 4); the AgentCore tooling scripts (`build_zip.sh`, `deploy_agent.py`,
  `smoke_test.py`, `invoke_agentcore.py`) come from `Phase0/scripts/`.
  Hand-written enterprise files (`README.md`, `.gitignore`, `.env*.example`) are
  owned by `win_deployed/` and never overwritten.
* `build_packages.sh` — re-syncs the three payload trees from source and rewrites
  `MANIFEST.sha256`.
* `make_zips.sh` — packs `backend/`, `frontend/`, `agents/` into the source zips
  `dist/agui-<tree>-<VERSION>.zip` + `dist/SHA256SUMS.txt`.
* `make_agentcore_zips.sh` — builds the deployable AgentCore packages
  (vendored linux/arm64 wheels) into `dist/agentcore/`.
* `check_sync.sh` — read-only drift gate: re-materializes the payload from source
  and diffs it against the committed `win_deployed/` trees.

**Because this pass changed no source, the zips did not need regeneration.**
Verified rather than rebuilt:

* `check_sync.sh` → **OK** (payloads match sources, version 1.8.0).
* Extracted `dist/agui-agents-1.8.0.zip`: **0** files with Turkish letters, **0**
  files with conflict markers.
* Confidence: definite. Result: skipped (no repackage needed).

## Summary

* Files touched: **1** (`CLEANUP_LOG.md` only — no source changed)
* Lines removed: **0**
* Zips rebuilt: **0** (source unchanged; `check_sync.sh` green, zip contents
  verified clean)
* Tests / build status: **green** — `ruff` (agents + backend + scripts +
  cloud_deploy) clean, `eslint` clean, `npm run build` succeeded, `check_sync.sh`
  OK.

The codebase was already clean (PR #37 did the substantive work earlier today).
This pass is a from-scratch re-verification and found nothing to remove,
rewrite, translate, or repackage.
