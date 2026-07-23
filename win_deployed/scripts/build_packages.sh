#!/usr/bin/env bash
# Regenerate the enterprise payloads under win_deployed/ from the Phase0 source,
# then rewrite MANIFEST.sha256.
#
# Usage:  win_deployed/scripts/build_packages.sh
#
# Safe to re-run. It copies CODE from Phase0/ and leaves every hand-written
# enterprise file (README.md, .gitignore, .env*.example) untouched, so local
# documentation is never clobbered by a sync.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_payload.sh
source "$HERE/_payload.sh"

REPO_ROOT="$(cd "$HERE/../.." && pwd)"
SRC="$REPO_ROOT/Phase0"
OUT="$REPO_ROOT/win_deployed"

[ -d "$SRC" ] || { echo "FAIL: source not found: $SRC" >&2; exit 1; }

echo "==> Syncing code from Phase0/ into win_deployed/"
payload_sync "$SRC" "$OUT"

echo "==> Writing MANIFEST.sha256"
(
  cd "$OUT"
  # Hash every shipped file (every payload tree), excluding our own tooling
  # and generated artifacts, so drift in either code or docs is visible.
  find "${PAYLOAD_TREES[@]}" -type f \
    ! -name '.DS_Store' ! -path '*/node_modules/*' ! -path '*/.next/*' \
    ! -path '*/__pycache__/*' ! -path '*/build/*' ! -name '*.zip' \
    | LC_ALL=C sort \
    | xargs shasum -a 256 > MANIFEST.sha256
)

count=$(wc -l < "$OUT/MANIFEST.sha256" | tr -d ' ')
echo "OK: $count file(s) in the enterprise payloads"
echo "    version : $(cat "$OUT/VERSION" 2>/dev/null || echo '(no VERSION file)')"
echo "    next    : review 'git diff win_deployed/', then win_deployed/scripts/make_zips.sh"
