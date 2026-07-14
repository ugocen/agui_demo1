#!/usr/bin/env bash
# Produce the zips to hand to the enterprise environment (which has no git access).
#
# Usage:  win_deployed/scripts/make_zips.sh
# Output: win_deployed/dist/<name>-<version>.zip  (three zips + a checksum file)
#
# Each zip expands into a SELF-CONTAINED project directory that becomes its own
# Bitbucket repository on the enterprise side (see win_deployed/README.md).
# Excluded by construction: git metadata, agent/dev tooling (.claude, .agents,
# CLAUDE.md, AGENTS.md), secrets (.env), and build artifacts.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="$(cd "$HERE/.." && pwd)"
DIST="$OUT/dist"
VERSION="$(tr -d '[:space:]' < "$OUT/VERSION")"

[ -n "$VERSION" ] || { echo "FAIL: win_deployed/VERSION is empty" >&2; exit 1; }

rm -rf "$DIST"
mkdir -p "$DIST"

for tree in backend frontend agents; do
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

( cd "$DIST" && shasum -a 256 ./*.zip > SHA256SUMS.txt )

echo
echo "OK: zips ready in win_deployed/dist/ (version $VERSION)"
ls -lh "$DIST" | sed 's/^/    /'
echo
echo "Send these three zips. On the enterprise machine each unzips to a folder that"
echo "is initialised as its own Bitbucket repo — see win_deployed/README.md."
