#!/usr/bin/env bash
# Report drift between the committed win_deployed/ payload trees and the archives
# in dist/ — i.e. "were the zips rebuilt after the last payload change?"
#
# check_sync.sh answers a different question: whether the payload trees still
# match Phase0/ + cloud_deploy/. It never opens an archive. So a change that was
# synced with build_packages.sh but never packaged with make_zips.sh leaves
# check_sync.sh green while the delivered archives are stale — and the zips are
# what actually ships, to a side that has no git to notice. This closes that gap.
#
# Usage:  win_deployed/scripts/check_zips.sh
# Exit 0 = archives match the payload. Exit 1 = drift (details printed).
# Read-only: extracts to a temp dir and changes nothing.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_payload.sh
source "$HERE/_payload.sh"

OUT="$(cd "$HERE/.." && pwd)"
DIST="$OUT/dist"
VERSION="$(tr -d '[:space:]' < "$OUT/VERSION")"

[ -n "$VERSION" ] || { echo "FAIL: win_deployed/VERSION is empty" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

drift=0

# 1. Source zips vs the payload trees. The -x list mirrors make_zips.sh: without
# it every artifact the zip deliberately omits reads as a false "only in tree".
DIFF_EXCLUDE=(-x node_modules -x .next -x __pycache__ -x .venv -x build
              -x '*.pyc' -x '*.zip' -x .DS_Store -x .env -x .env.local
              -x '*.db' -x '*.sqlite3' -x CLAUDE.md -x AGENTS.md -x '*.tsbuildinfo')

for tree in backend frontend agents; do
  zip_path="$DIST/agui-$tree-$VERSION.zip"
  if [ ! -f "$zip_path" ]; then
    echo "MISSING: dist/$(basename "$zip_path") — run make_zips.sh"
    drift=1
    continue
  fi
  rm -rf "${TMP:?}/x"
  mkdir -p "$TMP/x"
  unzip -q "$zip_path" -d "$TMP/x"
  if ! diff -r "${DIFF_EXCLUDE[@]}" "$TMP/x/$tree" "$OUT/$tree" > "$TMP/diff.$tree" 2>&1; then
    echo "DRIFT: agui-$tree-$VERSION.zip does not match win_deployed/$tree/"
    sed 's/^/    /' "$TMP/diff.$tree"
    drift=1
  fi
done

# 2. Deployable AgentCore packages vs the agent sources. These also carry every
# dependency as a vendored wheel, so only the agent's own modules are compared.
# requirements.txt/.lock are inputs to build_zip.sh, not runtime files, and are
# deliberately absent from the package.
for agent in "${AGENT_DIRS[@]}"; do
  zip_path="$DIST/agentcore/$agent-$VERSION.zip"
  if [ ! -f "$zip_path" ]; then
    echo "MISSING: dist/agentcore/$agent-$VERSION.zip — run make_agentcore_zips.sh"
    drift=1
    continue
  fi
  for src in "$OUT/agents/$agent"/*.py; do
    [ -e "$src" ] || continue
    name="$(basename "$src")"
    if ! unzip -p "$zip_path" "$name" > "$TMP/entry" 2>/dev/null; then
      echo "DRIFT: $agent-$VERSION.zip does not contain $name"
      drift=1
      continue
    fi
    if ! diff -q "$TMP/entry" "$src" >/dev/null 2>&1; then
      echo "DRIFT: $agent-$VERSION.zip carries a stale $name"
      drift=1
    fi
  done
done

# 3. The checksum records have to describe the archives actually sitting there —
# they are what the enterprise side verifies the transfer against.
for sums in "$DIST/SHA256SUMS.txt" "$DIST/agentcore/SHA256SUMS.txt"; do
  rel="${sums#"$OUT"/}"
  if [ ! -f "$sums" ]; then
    echo "MISSING: $rel"
    drift=1
    continue
  fi
  if ! ( cd "$(dirname "$sums")" && shasum -a 256 -c "$(basename "$sums")" >/dev/null 2>&1 ); then
    echo "DRIFT: $rel does not match the archives next to it"
    ( cd "$(dirname "$sums")" && shasum -a 256 -c "$(basename "$sums")" 2>&1 |
        grep -v ': OK$' | sed 's/^/    /' ) || true
    drift=1
  fi
done

if [ "$drift" -eq 0 ]; then
  echo "OK: dist/ archives match the win_deployed/ payload (version $VERSION) —" \
       "3 source zips, ${#AGENT_DIRS[@]} AgentCore packages, both SHA256SUMS files"
  exit 0
fi

echo
echo "The archives are behind the payload. Rebuild what drifted:"
echo "  win_deployed/scripts/make_zips.sh            # the three source zips"
echo "  win_deployed/scripts/make_agentcore_zips.sh  # the deployable AgentCore packages"
exit 1
