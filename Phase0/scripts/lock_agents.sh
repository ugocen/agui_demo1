#!/usr/bin/env bash
# Regenerate requirements.lock for every agent — the full, pinned dependency set
# that build_zip.sh installs.
#
# Usage:  Phase0/scripts/lock_agents.sh [agent-dir ...]
#         (no args = all agents under Phase0/agents/)
#
# Run this whenever you change an agent's requirements.txt, then review the diff:
# it is the only place a dependency change becomes visible before it ships.
#
# WHY THIS EXISTS
# requirements.txt pins only DIRECT dependencies — 6 of the 54 packages that end
# up in a zip. The other 48 are transitive and were resolved fresh against live
# PyPI on every build, so a rebuild changed the delivered bytes on its own. That
# is not hypothetical: langsmith 0.10.4 -> 0.10.5 moved one package on 2026-07-15,
# and botocore 1.43.48 -> 1.43.49 moved all five on 2026-07-16 — both discovered
# by comparing zips after the fact, neither reviewed by anyone.
#
# The point is less determinism than VISIBILITY: with a lock, those bumps are a
# one-line diff you approve, instead of a surprise found later.
#
# The resolution is platform-specific and must match build_zip.sh exactly
# (linux/arm64, Python 3.13, wheels only) — AgentCore runs ARM64 and does not
# pip install at deploy time. Resolving for this machine instead would produce a
# lock that installs the wrong wheels.
#
# The lock is a BUILD input, not a runtime file: build_zip.sh copies only *.py
# into the package, so it never ships inside a deployment zip. It does travel in
# the agents source payload, so the enterprise side can rebuild identically.
#
# Agents live in two copies (AGENTS.md invariant 4). requirements.lock is not a
# forked file, so after running this here, propagate it:
#   cloud_deploy/scripts/sync_agents.sh && cloud_deploy/scripts/check_agent_sync.sh

set -euo pipefail

PHASE0_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_VERSION=3.13
PLATFORM=aarch64-manylinux2014

if [ $# -gt 0 ]; then
  AGENT_DIRS=("$@")
else
  AGENT_DIRS=()
  for dir in "$PHASE0_DIR"/agents/*/; do
    [ -f "$dir/requirements.txt" ] || continue
    AGENT_DIRS+=("$dir")
  done
fi

[ "${#AGENT_DIRS[@]}" -gt 0 ] || { echo "FAIL: no agents with a requirements.txt found" >&2; exit 1; }

for dir in "${AGENT_DIRS[@]}"; do
  agent_dir="$(cd "$dir" && pwd)"
  name="$(basename "$agent_dir")"
  [ -f "$agent_dir/requirements.txt" ] || { echo "FAIL: $name has no requirements.txt" >&2; exit 1; }

  # --no-header: the header embeds the exact command line, which differs between
  # the two agent copies (different paths) and would read as drift in the gate.
  # --only-binary=:all: is not optional: build_zip.sh installs with it, so the
  # resolution must obey it too. Without it, compile is free to pick a version
  # that only ships an sdist (it assumes it could build from source) and the
  # install then fails with "no usable wheels" — which is exactly what
  # numpy==2.5.1 did here. The lock must be resolved under the SAME constraints
  # the build installs under, or it is a lock for a build that does not exist.
  uv pip compile "$agent_dir/requirements.txt" \
    --python-platform "$PLATFORM" \
    --python-version "$PYTHON_VERSION" \
    --only-binary=:all: \
    --no-header \
    --quiet \
    -o "$agent_dir/requirements.lock"

  direct=$(grep -c '==' "$agent_dir/requirements.txt" || true)
  total=$(grep -c '^[a-zA-Z0-9]' "$agent_dir/requirements.lock" || true)
  printf '  %-32s %s direct -> %s pinned\n' "$name" "$direct" "$total"
done

echo
echo "OK: locks regenerated for ${#AGENT_DIRS[@]} agent(s)"
echo "    review : git diff -- '*/requirements.lock'   <-- this is the dependency change"
echo "    then   : cloud_deploy/scripts/sync_agents.sh && cloud_deploy/scripts/check_agent_sync.sh"
