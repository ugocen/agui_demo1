#!/usr/bin/env bash
# Gate for the Phase0 <-> cloud_deploy agent fork. Read-only: changes nothing.
#
# Usage:  cloud_deploy/scripts/check_agent_sync.sh
# Exit 0 = both copies are one product with two providers. Exit 1 = something drifted.
#
# Two independent things are proven here, because the fork has two ways to rot:
#
#   1. DRIFT — an agent changed on one side only. The copies must be byte-identical
#      everywhere except model_factory.py, or we have forked the product instead of
#      the provider.
#   2. PROVIDER PURITY — the whole point of the fork (AGENTS.md invariant 4) is that
#      no environment variable can make an enterprise agent reach Amazon Bedrock,
#      because the code path does not exist. That guarantee is only real while the
#      enterprise factory has no Bedrock fallback and the Phase0 factory has no
#      gateway code. Grep is enough: the gateway is unreachable without an endpoint
#      and a key, so if both are unconditionally required there is no other path.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_agents.sh
source "$HERE/_agents.sh"

REPO_ROOT="$(cd "$HERE/../.." && pwd)"
SRC="$REPO_ROOT/Phase0"
OUT="$REPO_ROOT/cloud_deploy"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail=0

# ---------------------------------------------------------------- 1. drift
# Re-materialize the enterprise tree from Phase0 into a temp dir and diff. The
# forked files are seeded from the cloud_deploy side so they never read as drift.
mkdir -p "$TMP/agents"
agents_sync "$SRC" "$TMP"
for a in "${AGENT_DIRS[@]}"; do
  for f in "${FORKED_FILES[@]}"; do
    [ -f "$OUT/agents/$a/$f" ] && cp "$OUT/agents/$a/$f" "$TMP/agents/$a/$f"
  done
done

DIFF_FILTER=()
for name in __pycache__ .venv build .DS_Store '*.pyc' .env; do
  DIFF_FILTER+=(--exclude="$name")
done

for a in "${AGENT_DIRS[@]}"; do
  if ! diff -qr "${DIFF_FILTER[@]}" "$TMP/agents/$a" "$OUT/agents/$a" > "$TMP/d.$a" 2>&1; then
    echo "DRIFT in agents/$a/:"
    sed 's/^/    /' "$TMP/d.$a"
    fail=1
  fi
done

# ------------------------------------------------- 2. one factory per side
# Every agent is a flat, independent zip, so each carries its own copy of the
# factory. Within a side they must all be the same file.
for side in "$SRC" "$OUT"; do
  n=$(for a in "${AGENT_DIRS[@]}"; do
        [ -f "$side/agents/$a/model_factory.py" ] && shasum -a 256 < "$side/agents/$a/model_factory.py"
      done | sort -u | wc -l | tr -d ' ')
  if [ "$n" != "1" ]; then
    echo "DRIFT: model_factory.py copies differ inside $(basename "$side")/agents/ ($n distinct versions)"
    fail=1
  fi
done

# --------------------------------------------------- 3. provider purity
PHASE0_MF="$SRC/agents/${AGENT_DIRS[0]}/model_factory.py"
ENTER_MF="$OUT/agents/${AGENT_DIRS[0]}/model_factory.py"

# Phase0 is Bedrock-only: it must not know the gateway exists.
for marker in BEDROCK_ENDPOINT_URL BEDROCK_API_KEY x-api-key; do
  if grep -q -- "$marker" "$PHASE0_MF" 2>/dev/null; then
    echo "PURITY: Phase0 model_factory.py references '$marker' — it must have no gateway path."
    fail=1
  fi
done

# Enterprise is gateway-only: endpoint + key must be unconditionally required, so
# there is no reachable code path that builds a plain Amazon Bedrock client.
for marker in '_require("BEDROCK_ENDPOINT_URL")' '_require("BEDROCK_API_KEY")' 'x-api-key'; do
  if ! grep -qF -- "$marker" "$ENTER_MF" 2>/dev/null; then
    echo "PURITY: enterprise model_factory.py is missing '$marker' — the gateway must be mandatory."
    fail=1
  fi
done
# A fallback would have to be conditional on the gateway being absent.
if grep -qE 'use_gateway|if not .*(endpoint|api_key)' "$ENTER_MF" 2>/dev/null; then
  echo "PURITY: enterprise model_factory.py looks like it has a provider switch — there must be no fallback."
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "OK: cloud_deploy/agents match Phase0/agents (only ${FORKED_FILES[*]} differs)"
  echo "    Phase0 = Bedrock-only, cloud_deploy = gateway-only, no fallback either way"
  exit 0
fi

echo
echo "To adopt Phase0 agent changes into the enterprise fork:"
echo "  1. cloud_deploy/scripts/sync_agents.sh    # copies everything except ${FORKED_FILES[*]}"
echo "  2. re-run this check"
echo "  3. win_deployed/scripts/build_packages.sh # re-package the enterprise delivery"
exit 1
