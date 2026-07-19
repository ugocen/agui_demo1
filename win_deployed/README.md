# win_deployed/ — enterprise delivery staging area

**Internal document. Our side only. This file is not shipped.**

This directory is the **versioned staging area** for what we hand to the
enterprise environment (Windows 11 + WSL2 Ubuntu, no git access, no internet
git). It is **not** shipped as-is: only the three payload folders —
`backend/`, `frontend/`, `agents/` — are zipped and sent. Everything else here
(`scripts/`, `MANIFEST.sha256`, `VERSION`, `CHANGELOG.md`, this README) is our
tooling and stays behind.

The enterprise operator never sees this file. They get three zips, each of
which expands into a self-contained project directory with its own README
written for Windows 11 + WSL2.

---

## The rule: `Phase0/` is the single source of truth

Code under `win_deployed/` is a **copy**, produced mechanically by
`scripts/build_packages.sh`. Backend and frontend come from `Phase0/` and are not
forked. **Agents come from `cloud_deploy/agents/`** — the one deliberate fork
(AGENTS.md invariant 4), whose `model_factory.py` is gateway-only because this
account has no Bedrock access. Everything else about the agents is kept identical
to `Phase0/agents/` by `cloud_deploy/scripts/check_agent_sync.sh`.

> **Never hand-edit code under `win_deployed/`.** Fix it at its source — `Phase0/`
> for backend/frontend/agent code, `cloud_deploy/agents/` for the gateway-only
> `model_factory.py` — then re-run `scripts/build_packages.sh`. A hand-edit here is silently reverted by
> the next sync and shows up as drift in `scripts/check_sync.sh`.

The **only** files owned by `win_deployed/` — hand-written, enterprise-specific,
with no `Phase0/` counterpart — are:

| File | Owned by | Why it exists |
| --- | --- | --- |
| `backend/README.md`, `frontend/README.md`, `agents/README.md` | win_deployed | Operator docs for Windows 11 + WSL2. `Phase0/README.md` is a dev-environment doc and never ships. |
| `backend/.gitignore`, `frontend/.gitignore`, `agents/.gitignore` | win_deployed | Each folder becomes its own Bitbucket repo, so each needs its own ignore rules. The repo-root `.gitignore` does not travel. |
| `backend/.gitattributes`, `frontend/.gitattributes`, `agents/.gitattributes` | win_deployed | Enforce LF (`* text=auto eol=lf`, `*.sh text eol=lf`) so shell scripts committed from Windows do not get CRLF and fail with `bad interpreter`. |
| `backend/.env.example`, `agents/.env.example`, `frontend/.env.local.example` | win_deployed | Config templates with blanks. Real `.env` files never ship. |

`scripts/_payload.sh` encodes this split: the sync copies code only and never
touches the files in the table above.

---

## Layout

```
win_deployed/
├── README.md              # this file — internal index (not shipped)
├── CHANGELOG.md           # what changed per package version (not shipped)
├── VERSION                # package version of what we send (this file is the source of truth)
├── MANIFEST.sha256        # sha256 of every shipped file (78 files) — the record of what a version contained
├── scripts/               # our tooling (not shipped)
│   ├── _payload.sh        # THE definition of what ships; sourced by the two scripts below
│   ├── build_packages.sh  # re-sync payload from Phase0/ + rewrite MANIFEST.sha256
│   ├── check_sync.sh      # read-only drift check: has Phase0/ moved on?
│   ├── make_zips.sh       # produce the 3 SOURCE zips dist/agui-*-<VERSION>.zip
│   └── make_agentcore_zips.sh  # produce the 5 DEPLOYABLE dist/agentcore/<agent>-<VERSION>.zip
├── dist/                  # generated zips (TRACKED)
│   └── agentcore/         # the packages you upload to AgentCore (~151 MB)
│
├── backend/               # PAYLOAD 1 -> own Bitbucket repo (21 files)
│   ├── app/               # verbatim from Phase0/backend/app/
│   ├── alembic/           # verbatim from Phase0/backend/alembic/
│   ├── alembic.ini        # verbatim
│   ├── requirements.txt   # verbatim (pinned)
│   └── (README.md, .gitignore, .gitattributes, .env.example)   # ours
│
├── frontend/              # PAYLOAD 2 -> own Bitbucket repo (34 files)
│   ├── src/               # verbatim from Phase0/frontend/src/
│   ├── public/            # verbatim
│   ├── package.json, package-lock.json, tsconfig.json,
│   │   next.config.ts, eslint.config.mjs                       # verbatim
│   └── (README.md, .gitignore, .gitattributes, .env.local.example)  # ours
│
└── agents/                # PAYLOAD 3 -> own folder/repo (23 files)
    ├── sdlc-planner-strands/        # verbatim
    ├── release-readiness-langgraph/ # verbatim
    ├── bug-report-strands/          # verbatim
    ├── a2ui-demo-strands/           # verbatim
    ├── press-release-strands/       # verbatim
    ├── scripts/
    │   ├── build_zip.sh             # verbatim from Phase0/scripts/ (chmod +x by the sync)
    │   └── deploy_agent.py          # verbatim from Phase0/scripts/
    └── (README.md, .gitignore, .gitattributes, .env.example)   # ours
```

Both `build_zip.sh` and `deploy_agent.py` resolve `PHASE0_DIR` as
`<script-dir>/..`, so in the standalone layout they operate on `agents/` itself:
zips land in `agents/build/<name>.zip` and `deploy_agent.py` reads — and writes
the resulting runtime ARN back to — `agents/.env`. This is why the agents
payload works without a parent directory.

---

## The three workflows

### 1. Re-sync after `Phase0/` changes

```bash
win_deployed/scripts/build_packages.sh
```

Copies code from `Phase0/` into the three payload trees (`rsync -a` with the
exclude list in `_payload.sh`), then rewrites `MANIFEST.sha256` by hashing every
file under `backend/ frontend/ agents/`. Safe to re-run; idempotent. It never
overwrites the hand-written enterprise files. Prints the file count and reminds
you to review `git diff win_deployed/`.

### 2. Check drift (requirement 7)

```bash
win_deployed/scripts/check_sync.sh
```

Read-only. It re-materializes the payload from `Phase0/` into a temp dir using
the same `_payload.sh` definition, then `diff -qr`s that against the committed
`win_deployed/` trees, filtering the hand-written enterprise files (which have
no `Phase0/` counterpart and would otherwise read as spurious differences).

- **exit 0** — `win_deployed/` payloads match `Phase0/`.
- **exit 1** — drift; the diff is printed per tree, followed by the recovery
  steps (re-sync → bump VERSION + CHANGELOG → rebuild zips).

Run this before any delivery, and any time you touch `Phase0/`.

### 3. Produce the deliverables

```bash
win_deployed/scripts/make_zips.sh
```

Rewrites the three source payload zips, named from `VERSION` (it leaves
`dist/agentcore/` alone):

```
dist/agui-backend-<VERSION>.zip
dist/agui-frontend-<VERSION>.zip
dist/agui-agents-<VERSION>.zip
dist/SHA256SUMS.txt
```

Each archive is rooted at its folder name, so it expands to `backend/`,
`frontend/`, `agents/`. `SHA256SUMS.txt` lets the enterprise side verify the
transfer (`shasum -a 256 -c SHA256SUMS.txt` in WSL).

### Built AgentCore packages (`dist/agentcore/`)

`make_zips.sh` produces the **source** delivery zips. The **deployable** AgentCore
packages are a separate artifact with its own script:

```bash
win_deployed/scripts/make_agentcore_zips.sh
# -> dist/agentcore/<agent>-<VERSION>.zip  (+ SHA256SUMS.txt)
```

It packages `win_deployed/agents/` — the enterprise fork, synced from
`cloud_deploy/agents/` — so run `build_packages.sh` first if the sources moved.
The version is in the filename so a package on disk, or already uploaded to a
runtime, can be identified without unzipping it.

Staging these used to be a hand-run `build_zip.sh` + `cp` + `shasum` sequence with
nothing enforcing it, while `make_zips.sh` deleted `dist/agentcore/` on every run.
The omission was invisible — `dist/` still looked populated. `make_zips.sh` now
removes only its own `agui-*.zip`, and this script owns `dist/agentcore/`.

They are ~27–42 MB each (~151 MB total) because every dependency is vendored as
a **linux/arm64** wheel — AgentCore runs on ARM64 and does not `pip install` at
deploy time. The 36 KB source zip is **not** deployable; it carries no
dependencies.

They are **tracked in git** — see "Why `dist/` is committed" below, including the
caveat that reproducibility is bounded by transitive-dependency drift.

### Why `dist/` is committed

Unusually for build output, the zips **are tracked in git** (the root
`.gitignore` negates `dist/` and `*.zip` for this folder only). Rationale:

- **They are the delivery record.** The enterprise side has no git. Tracking the
  exact bytes we handed over is the only way to answer *"which build is running
  over there?"* and to diff against what they unzipped — the whole point of this
  staging area.
- **The zips are reproducible given the same resolved dependencies**, so tracking
  them is cheap. `make_zips.sh` packs the source zips with `zip -qrX`;
  `build_zip.sh` (v1.0.1+) pins timestamps (`touch -h -t`), sorts entry order and
  passes `-X` for the built packages. Two builds minutes apart from unchanged
  sources are byte-for-byte identical — verified by building all five agents
  twice and comparing checksums.

  Dependencies are installed from each agent's `requirements.lock` (the full
  pinned resolution, 54 packages), not from `requirements.txt` (6 direct pins), so
  the resolution cannot drift between builds. Before the lock it did, twice:
  `langsmith` 0.10.4 → 0.10.5 (1.2.0) and `botocore` 1.43.48 → 1.43.49 across all
  five packages (1.4.0). Regenerate a lock with `Phase0/scripts/lock_agents.sh`
  and review the diff — that is where a dependency change is meant to be seen.
- **Reproducibility is a verification tool.** The enterprise side can run
  `build_zip.sh` and compare its checksum to `agentcore/SHA256SUMS.txt`; a match
  proves both machines built the same artifact, and since 1.5.0 a mismatch means
  something — the inputs are pinned, so it is no longer explained away by a
  transitive dependency having moved.
- **They are safe.** Payloads contain no secrets — only `*.example` templates.
  `BEDROCK_API_KEY` ships blank by design.

So a real diff on `dist/` always means *the payload actually changed* — treat it
as a signal, and make sure `VERSION` and `CHANGELOG.md` were bumped to match.

---

## Versioning policy

- `VERSION` is the **package version of what we send** — it versions the
  delivery, not the app. Read it with `cat win_deployed/VERSION`; do not restate
  it in prose here, or this README goes stale the next time it is bumped.
- **Whenever the payload changes, bump `VERSION` and add a `CHANGELOG.md`
  entry.** Semantic-ish: patch for doc/config fixes, minor for new code or
  agents, major for a layout or migration-requiring change.
- `MANIFEST.sha256` records the sha256 of every shipped file. This is how we
  **prove and compare exactly what a given version contained** — when the
  enterprise side reports a problem, ask which zip version they unzipped, check
  out that tag, and diff their file hashes against the manifest of that version.
  Without it we have no way to tell what is actually running over there.
- Order of operations for a delivery: `check_sync.sh` → `build_packages.sh` (if
  drifted) → bump `VERSION` → `CHANGELOG.md` entry → commit → `make_zips.sh`.

---

## What is deliberately excluded, and why

| Excluded | Why |
| --- | --- |
| `.claude/`, `.agents/`, `CLAUDE.md`, `AGENTS.md` | Our dev/agent tooling. Requirement 6: nothing about our dev environment ships. Enforced in `_payload.sh` (`EXCLUDES`) and again in `make_zips.sh`. |
| `Phase0/README.md`, `ARCHITECTURE.md`, `PRESENTATION-AGUI-A2UI.md`, `VERSIONS.md`, `docs/`, audit and plan docs | Internal docs. The payload READMEs are written fresh in English. |
| `.env` and any real secret | Only `*.example` templates with blanks ship. Never put a real key in this tree. |
| `node_modules/`, `.venv/`, `.next/`, `build/`, `*.zip`, `*.pyc`, `*.tsbuildinfo` | Build artifacts — the operator installs from `package-lock.json` / `requirements.txt`. Also keeps the zips small. |
| `*.db`, `*.sqlite3` | Local dev databases. The backend creates its own SQLite file on first run. |
| Git history / `.git/` | Zip delivery; the enterprise side starts fresh repos in Bitbucket. |
| `cloud_deploy/`, `a2a-poc/`, `aws-setup/` | Not needed to deploy and run. The enterprise config lives in the `.env` templates. |
| `.DS_Store` | macOS cruft. |

---

## Delivery instructions (what to tell the enterprise side)

1. Send the three zips from `win_deployed/dist/` plus `SHA256SUMS.txt`.
2. **Unzip inside WSL, on the Linux filesystem** (e.g. `~/apps/`), **not** under
   `/mnt/c/...`. `/mnt/c` is slow and breaks Next.js file-watching/hot-reload.
3. After unzipping, shell scripts may have lost their exec bit (the zips are
   produced on macOS):
   ```bash
   chmod +x agents/scripts/build_zip.sh
   ```
4. Each folder becomes **its own Bitbucket repo** — `backend/` and `frontend/`
   at minimum; `agents/` is the third folder and can be its own repo too. Each
   already carries its own `.gitignore` and `.gitattributes` (LF enforced).
   Advise `git config core.autocrlf false` in WSL.
5. Each folder has its own `README.md` with the full Windows 11 + WSL2 setup,
   config, and run instructions — including the AgentCore deploy process and the
   GenAI marketplace API gateway settings. Point the operator there; do not
   re-explain it in email.
6. Order of standup: **agents** (deploy to AgentCore) → **backend** (discovers
   the deployed runtimes automatically) → **frontend**.

---

## Requirement → how this package satisfies it

| # | Stakeholder requirement | How this package satisfies it | Honest status |
| --- | --- | --- | --- |
| 1 | Only what is needed ships: a backend, a frontend, the agents | Exactly three payload trees, 78 files (66 code synced from `Phase0/` + 12 hand-written enterprise files), defined once in `scripts/_payload.sh`. Nothing else is copied. | **Met** |
| 2 | No Turkish text anywhere; everything in English | Internal docs (`PRESENTATION-AGUI-A2UI.md`, `docs/`) are never copied; all shipped READMEs and templates are written fresh in English. | **Met** — but it is a review discipline, not a mechanical check. There is no automated Turkish-text linter; re-read new docs before shipping. |
| 3 | Agents ready for the GenAI marketplace API gateway, under one `agents/` folder; AgentCore deploy explained | All five agents in one `agents/` folder with `scripts/build_zip.sh` + `scripts/deploy_agent.py`. The agents are **gateway-only** — no Amazon Bedrock code path exists in this build, and `BEDROCK_ENDPOINT_URL` + `BEDROCK_API_KEY` + `BEDROCK_MODEL_ID` are all mandatory (identical `model_factory.py` in all five). `agents/README.md` documents the deploy process end to end. | **Met** — caveat: the gateway itself has not been exercised from here; `BEDROCK_API_KEY` is blank in the template and the operator fills it. If the gateway does not proxy `converse-stream`, set `BEDROCK_STREAMING=false`. |
| 4 | No git on the enterprise side — zip delivery, separate folders | `make_zips.sh` produces three independent zips; no git metadata, no cross-folder references. | **Met** |
| 5 | `backend/` and `frontend/` each get their own `.gitignore` and `README.md`, for Windows 11 + WSL2 | Present in both (plus `agents/`), hand-written and owned by `win_deployed/`, protected from the sync. `.gitattributes` added on top for LF enforcement. | **Met** |
| 6 | Nothing about our dev environment ships | `.claude/`, `.agents/`, `CLAUDE.md`, `AGENTS.md` excluded twice — in `_payload.sh` `EXCLUDES` and again in `make_zips.sh` `-x` patterns. | **Met** |
| 7 | `win_deployed/` is versioned and diffable against `Phase0/` | `VERSION` + `CHANGELOG.md` + `MANIFEST.sha256`; `check_sync.sh` gives a machine-checkable in-sync/drift verdict. | **Met, with the caveats below.** |

### Known caveats (requirement 7)

These are real and worth knowing before you trust a green check:

1. **The hand-written enterprise files are not drift-checked.** `check_sync.sh`
   compares code only — the files in `ENTERPRISE_OWNED` (`_payload.sh`) are
   filtered out of the diff by design, because they have no `Phase0/`
   counterpart. If `Phase0/` gains or renames an env var, the READMEs and `.env`
   templates do **not** fail any check — they silently go stale. Re-read them by
   hand whenever the config surface changes.
2. **`dist/` and its zips ARE tracked** — the root `.gitignore` negates them for
   this folder only, because they are the delivery record and the enterprise side
   has no git. See "Why `dist/` is committed" above, including the caveat that
   reproducibility is bounded by transitive-dependency drift.
3. **`win_deployed/` tooling runs on macOS** (`rsync`, `shasum`, `zip`). It is
   our-side only and is not expected to run in WSL.

Two caveats reported during authoring have since been **fixed** and are no longer
open: `check_sync.sh` falsely reporting drift on `.gitattributes` (the diff filter
now derives from `ENTERPRISE_OWNED` in `_payload.sh`), and
`frontend/.env.local.example` being swallowed by the repo-root `.gitignore` (a
`!.env.local.example` negation was added). Both are covered by regression checks:
`check_sync.sh` exits 0 in sync and 1 on a real code change, and
`git check-ignore` confirms every template is tracked while every real `.env`
stays ignored.
