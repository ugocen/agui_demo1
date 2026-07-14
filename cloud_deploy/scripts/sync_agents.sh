#!/usr/bin/env bash
# Propagate agent changes from Phase0/ into the enterprise fork at
# cloud_deploy/agents/, leaving each side's model_factory.py alone.
#
# Usage:  cloud_deploy/scripts/sync_agents.sh
#
# Run this after ANY change to an agent (prompt, tools, graph, requirements) —
# the two copies are one product with two LLM providers, and only the provider is
# allowed to differ. check_agent_sync.sh is the gate that proves it.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_agents.sh
source "$HERE/_agents.sh"

REPO_ROOT="$(cd "$HERE/../.." && pwd)"
SRC="$REPO_ROOT/Phase0"
OUT="$REPO_ROOT/cloud_deploy"

[ -d "$SRC/agents" ] || { echo "FAIL: source not found: $SRC/agents" >&2; exit 1; }

echo "==> Syncing agent code from Phase0/ into cloud_deploy/ (model_factory.py kept per side)"
agents_sync "$SRC" "$OUT"

echo "OK: ${#AGENT_DIRS[@]} agent(s) synced"
echo "    forked (not synced): ${FORKED_FILES[*]}"
echo "    next  : cloud_deploy/scripts/check_agent_sync.sh, then win_deployed/scripts/build_packages.sh"
