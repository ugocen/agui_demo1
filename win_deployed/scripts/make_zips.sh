#!/usr/bin/env bash
# Produce the zips to hand to the enterprise environment (which has no git access).
#
# Usage:  win_deployed/scripts/make_zips.sh
# Output: win_deployed/dist/agui-<name>-<version>.zip  (one per payload tree,
#         plus a checksum file)
#
# These are the SOURCE payloads. The deployable AgentCore packages are a separate
# artifact under dist/agentcore/ — run make_agentcore_zips.sh for those. This
# script leaves that directory alone.
#
# Each zip expands into a SELF-CONTAINED project directory that becomes its own
# Bitbucket repository on the enterprise side (see win_deployed/README.md).
# Excluded by construction: git metadata, agent/dev tooling (.claude, .agents,
# CLAUDE.md, AGENTS.md), secrets (.env), and build artifacts.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_payload.sh
source "$HERE/_payload.sh"   # PAYLOAD_TREES — the one definition of what ships

OUT="$(cd "$HERE/.." && pwd)"
DIST="$OUT/dist"
VERSION="$(tr -d '[:space:]' < "$OUT/VERSION")"

[ -n "$VERSION" ] || { echo "FAIL: win_deployed/VERSION is empty" >&2; exit 1; }

# Clear only what this script owns. dist/agentcore/ belongs to
# make_agentcore_zips.sh and must survive: a plain `rm -rf "$DIST"` here silently
# deleted ~151 MB of committed, deployable packages and left dist/ looking
# complete, because the source zips below reappear immediately.
mkdir -p "$DIST"
rm -f "$DIST"/agui-*.zip "$DIST/SHA256SUMS.txt"

for tree in "${PAYLOAD_TREES[@]}"; do
  [ -d "$OUT/$tree" ] || { echo "FAIL: missing $OUT/$tree — run build_packages.sh first" >&2; exit 1; }
  zip_path="$DIST/agui-$tree-$VERSION.zip"
  echo "==> Packing $tree -> $(basename "$zip_path")"
  (
    cd "$OUT"
    # -X strips extra file attributes; the excludes are belt-and-braces on top of
    # what build_packages.sh already refuses to copy.
    zip -qrX "$zip_path" "$tree" \
      -x '*/node_modules/*' '*/.next/*' '*/__pycache__/*' '*/.venv/*' \
         '*/build/*' '*.pyc' '*.zip' '*/.DS_Store' '*/.env' '*/.env.local' \
         '*.db' '*.sqlite3' '*/CLAUDE.md' '*/AGENTS.md' '*.tsbuildinfo'
  )
done

# Only the source zips live at the top level; agentcore/ has its own sums file.
( cd "$DIST" && shasum -a 256 ./agui-*.zip > SHA256SUMS.txt )

echo
echo "OK: zips ready in win_deployed/dist/ (version $VERSION)"
ls -lh "$DIST" | sed 's/^/    /'
echo
echo "Send these ${#PAYLOAD_TREES[@]} zips. On the enterprise machine each unzips to a folder that"
echo "is initialised as its own Bitbucket repo — see win_deployed/README.md."
