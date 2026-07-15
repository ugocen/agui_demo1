#!/usr/bin/env bash
# Report drift between the sources and the enterprise payloads shipped from
# win_deployed/ — i.e. "have the sources moved on since we last packaged?"
#
# Sources are split: backend/ and frontend/ come from Phase0/, agents/ come from
# the enterprise fork in cloud_deploy/ (AGENTS.md invariant 4). _payload.sh owns
# that mapping; this script just diffs whatever it produces.
#
# Usage:  win_deployed/scripts/check_sync.sh
# Exit 0 = in sync. Exit 1 = drift (details printed). Read-only: changes nothing.
#
# How: re-materialize the payload into a temp dir straight from Phase0/, then diff
# it against the committed win_deployed/ trees. Only CODE is compared — the
# hand-written enterprise files (README.md, .gitignore, .env*.example) intentionally
# have no Phase0 counterpart and are excluded from the comparison.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_payload.sh
source "$HERE/_payload.sh"

REPO_ROOT="$(cd "$HERE/../.." && pwd)"
SRC="$REPO_ROOT/Phase0"
OUT="$REPO_ROOT/win_deployed"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

payload_sync "$SRC" "$TMP"

# Compare only what the sync owns. The hand-written enterprise files
# (ENTERPRISE_OWNED, from _payload.sh) exist only on the win_deployed side and
# would always read as false drift, so they are filtered out — as are local
# build artifacts that legitimately differ between the temp tree and ours.
DIFF_FILTER=()
for name in "${ENTERPRISE_OWNED[@]}"; do
  DIFF_FILTER+=(--exclude="$name")
done
for name in node_modules .next __pycache__ build dist .venv .DS_Store '*.pyc'; do
  DIFF_FILTER+=(--exclude="$name")
done

drift=0
for tree in backend frontend agents; do
  if ! diff -qr "${DIFF_FILTER[@]}" \
      "$TMP/$tree" "$OUT/$tree" > "$TMP/diff.$tree" 2>&1; then
    echo "DRIFT in $tree/:"
    sed 's/^/    /' "$TMP/diff.$tree"
    drift=1
  fi
done

if [ "$drift" -eq 0 ]; then
  echo "OK: win_deployed/ payloads match their sources — backend+frontend from Phase0/, agents from cloud_deploy/ (version $(cat "$OUT/VERSION" 2>/dev/null || echo '?'))"
  exit 0
fi

echo
echo "The sources have moved on. To adopt the changes into the enterprise package:"
echo "  0. cloud_deploy/scripts/sync_agents.sh    # if an AGENT changed in Phase0/"
echo "  1. win_deployed/scripts/build_packages.sh   # re-sync + rewrite MANIFEST"
echo "  2. bump win_deployed/VERSION and add a CHANGELOG.md entry"
echo "  3. win_deployed/scripts/make_zips.sh        # rebuild the zips to send"
exit 1
