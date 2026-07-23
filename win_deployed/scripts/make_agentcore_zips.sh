#!/usr/bin/env bash
# Build the DEPLOYABLE AgentCore packages and stage them in dist/agentcore/.
#
# Usage:  win_deployed/scripts/make_agentcore_zips.sh
# Output: win_deployed/dist/agentcore/<agent>-<version>.zip  (+ SHA256SUMS.txt)
#
# These are what actually gets uploaded to an AgentCore runtime: every dependency
# vendored as a linux/arm64 wheel, ~27-42 MB each. They are NOT the same thing as
# make_zips.sh's `agui-agents-<version>.zip`, which is ~39 KB of source and is not
# deployable — uploading that one to AgentCore is the easiest mistake to make here,
# and it fails at import with no obvious cause.
#
# Why this exists at all: staging these was a manual `build_zip.sh` + `cp` +
# `shasum` sequence documented in README.md, and nothing enforced it. That gap
# cost real time — make_zips.sh would delete dist/agentcore/ and the omission was
# invisible, because dist/ still looked populated.
#
# The version is in the filename so a package on disk, or already uploaded to a
# runtime, can be identified without unzipping it. Renames are cheap in git: an
# unchanged package keeps its content hash, so a version bump costs a tree entry,
# not another 151 MB of blobs.
#
# Packages the ENTERPRISE payload (win_deployed/agents/), which build_packages.sh
# syncs from cloud_deploy/agents/ — the gateway-only fork (AGENTS.md invariant 4).
# Run build_packages.sh first if Phase0/ or cloud_deploy/ has moved.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=_payload.sh
source "$HERE/_payload.sh"

OUT="$(cd "$HERE/.." && pwd)"
DIST="$OUT/dist/agentcore"
BUILD="$OUT/agents/build"
VERSION="$(tr -d '[:space:]' < "$OUT/VERSION")"

[ -n "$VERSION" ] || { echo "FAIL: win_deployed/VERSION is empty" >&2; exit 1; }
[ -x "$OUT/agents/scripts/build_zip.sh" ] || chmod +x "$OUT/agents/scripts/build_zip.sh"

echo "==> Building ${#AGENT_DIRS[@]} AgentCore package(s) at version $VERSION"

rm -rf "$DIST" "$BUILD"
mkdir -p "$DIST"

for agent in "${AGENT_DIRS[@]}"; do
  [ -d "$OUT/agents/$agent" ] || {
    echo "FAIL: missing $OUT/agents/$agent — run build_packages.sh first" >&2
    exit 1
  }
  ( cd "$OUT/agents" && ./scripts/build_zip.sh "./$agent" >/dev/null )
  mv "$BUILD/$agent.zip" "$DIST/$agent-$VERSION.zip"
  echo "    $agent-$VERSION.zip"
done

( cd "$DIST" && shasum -a 256 ./*.zip > SHA256SUMS.txt )

# Cleanup last, and never fatal. This used to run before the checksums, under
# `set -e`, and `rm -rf` on the per-agent package folders intermittently fails
# with "Directory not empty" on macOS — so the script died after building all
# seven packages and never wrote SHA256SUMS.txt. Every artifact was correct and
# the delivery still failed check_zips.sh, with the exit code the only clue.
# The leftovers are gitignored build scratch; a stale one costs nothing.
if ! rm -rf "$BUILD" 2>/dev/null; then
  echo "WARN: could not fully remove $BUILD — safe to delete by hand" >&2
fi

echo
echo "OK: deployable packages in win_deployed/dist/agentcore/ (version $VERSION)"
ls -lh "$DIST"/*.zip | awk '{printf "    %-44s %s\n", $NF, $5}'
echo
echo "Upload THESE to AgentCore. dist/agui-agents-$VERSION.zip is source only."
echo "Next: review 'git diff --stat win_deployed/dist/' — an agent you did not"
echo "touch should show no change; if it does, a transitive dependency moved."
