#!/usr/bin/env bash
# Shared payload definition: WHAT gets copied from Phase0/ into the enterprise
# packages. Sourced by build_packages.sh and check_sync.sh so both agree on the
# file set — there is exactly one definition of "what ships".
#
# Rules encoded here:
#  * backend/ and frontend/ are copied verbatim from Phase0/ (single source; no fork).
#  * agents/ ship from the ENTERPRISE fork at cloud_deploy/agents/, NOT from
#    Phase0/agents/. The delivered package must carry the gateway-only provider:
#    the enterprise account has no Bedrock model access, and an agent that could
#    fall back to Amazon Bedrock is exactly what we removed (AGENTS.md invariant
#    4). The two agent copies are identical apart from model_factory.py, and
#    cloud_deploy/scripts/check_agent_sync.sh is the gate that proves it.
#  * Agent/dev tooling never ships: .claude/, .agents/, CLAUDE.md, AGENTS.md.
#  * Secrets never ship: only *.example templates (hand-written, see below).
#  * Hand-written enterprise files (README.md, .gitignore, .env*.example) are
#    OWNED by win_deployed/ and are never overwritten by the sync.

set -euo pipefail

AGENT_DIRS=(
  sdlc-planner-strands
  release-readiness-langgraph
  bug-report-strands
  a2ui-demo-strands
  press-release-strands
)

# Files copied verbatim into win_deployed/frontend/
FRONTEND_FILES=(
  package.json
  package-lock.json
  tsconfig.json
  next.config.ts
  eslint.config.mjs
)

# Files copied verbatim into win_deployed/backend/
BACKEND_FILES=(
  alembic.ini
  requirements.txt
)

# Hand-written enterprise files: OWNED by win_deployed/, with no Phase0/
# counterpart. The sync never writes them and the drift check never compares
# them (they would otherwise always read as "only in win_deployed" = false drift).
# Keep this list as the single definition — check_sync.sh derives its filter from it.
ENTERPRISE_OWNED=(
  README.md
  .gitignore
  .gitattributes
  .env.example
  .env.local.example
)

# Never copy these, anywhere.
EXCLUDES=(
  --exclude '__pycache__'
  --exclude '*.pyc'
  --exclude '.DS_Store'
  --exclude '.venv'
  --exclude 'node_modules'
  --exclude '.next'
  --exclude '*.db'
  --exclude '*.sqlite3'
  --exclude '*.zip'
  --exclude 'build'
  --exclude '.env'
  --exclude '.env.*'
  --exclude 'CLAUDE.md'
  --exclude 'AGENTS.md'
  --exclude '*.tsbuildinfo'
  --exclude 'next-env.d.ts'
)

# Materialize the three payload trees into $1 (a directory).
# Copies CODE ONLY — never the hand-written docs/.gitignore/.env examples.
payload_sync() {
  local src="$1" out="$2"

  # ---- backend ----
  mkdir -p "$out/backend"
  rm -rf "$out/backend/app" "$out/backend/alembic"
  rsync -a "${EXCLUDES[@]}" "$src/backend/app/"     "$out/backend/app/"
  rsync -a "${EXCLUDES[@]}" "$src/backend/alembic/" "$out/backend/alembic/"
  local f
  for f in "${BACKEND_FILES[@]}"; do
    cp "$src/backend/$f" "$out/backend/$f"
  done

  # ---- frontend ----
  mkdir -p "$out/frontend"
  rm -rf "$out/frontend/src" "$out/frontend/public"
  rsync -a "${EXCLUDES[@]}" "$src/frontend/src/"    "$out/frontend/src/"
  rsync -a "${EXCLUDES[@]}" "$src/frontend/public/" "$out/frontend/public/"
  for f in "${FRONTEND_FILES[@]}"; do
    cp "$src/frontend/$f" "$out/frontend/$f"
  done

  # ---- agents (from the enterprise fork, see header) ----
  local agents_src
  agents_src="$(cd "$src/.." && pwd)/cloud_deploy"
  [ -d "$agents_src/agents" ] || {
    echo "FAIL: enterprise agent fork not found: $agents_src/agents" >&2
    return 1
  }
  mkdir -p "$out/agents"
  local a
  for a in "${AGENT_DIRS[@]}"; do
    rm -rf "${out:?}/agents/$a"
    mkdir -p "$out/agents/$a"
    rsync -a "${EXCLUDES[@]}" "$agents_src/agents/$a/" "$out/agents/$a/"
  done
  # Packaging + deployment tooling the enterprise side needs for AgentCore.
  mkdir -p "$out/agents/scripts"
  cp "$src/scripts/build_zip.sh"    "$out/agents/scripts/build_zip.sh"
  cp "$src/scripts/deploy_agent.py" "$out/agents/scripts/deploy_agent.py"
  chmod +x "$out/agents/scripts/build_zip.sh"
}
