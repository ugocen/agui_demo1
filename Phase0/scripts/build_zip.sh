#!/usr/bin/env bash
# Build an AgentCore direct-code-deployment zip for one agent.
# Usage: build_zip.sh <agent-dir>
# Installs dependencies as linux/arm64 wheels, copies the agent sources to
# the package root, normalizes permissions, zips from inside the package
# folder, and fails loudly on size or architecture violations.
#
# The zip is REPRODUCIBLE. Two things are needed for that and this script has both:
#
#  1. Deterministic packaging — no embedded timestamps, fixed entry order, no
#     machine-specific attributes (see "Making the package reproducible" below).
#  2. A pinned resolution — dependencies are installed from requirements.lock,
#     which pins all 54 packages, not from requirements.txt, which pins only the 6
#     direct ones. Without this a rebuild silently shipped different bytes: langsmith
#     0.10.4 -> 0.10.5 (2026-07-15) and botocore 1.43.48 -> 1.43.49 (2026-07-16),
#     neither reviewed by anyone.
#
# So a rebuild from unchanged sources produces byte-identical output, and two
# machines can compare checksums to prove they built the same package. Regenerate
# the lock with Phase0/scripts/lock_agents.sh after changing requirements.txt.

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "usage: $0 <agent-dir>" >&2
  exit 1
fi

AGENT_DIR="$(cd "$1" && pwd)"
AGENT_NAME="$(basename "$AGENT_DIR")"
PHASE0_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PHASE0_DIR/build/$AGENT_NAME"
PACKAGE_DIR="$BUILD_DIR/package"
ZIP_PATH="$PHASE0_DIR/build/$AGENT_NAME.zip"
LOCK_PATH="$AGENT_DIR/requirements.lock"

MAX_ZIP_MB=250
MAX_UNZIPPED_MB=750
PYTHON_VERSION=3.13
# Fixed timestamp stamped on every packaged file. The zip format stores an mtime
# per entry, so without pinning it every build differs. Must be >= 1980 (the zip
# epoch). The value is arbitrary; only its stability matters.
SOURCE_DATE=202001010000

if [ ! -f "$AGENT_DIR/requirements.txt" ]; then
  echo "FAIL: $AGENT_DIR/requirements.txt not found" >&2
  exit 1
fi

# The lock is mandatory, with no fall back to requirements.txt. requirements.txt
# pins only direct dependencies (6 of the 54 packages in a zip), so installing
# from it resolves the other 48 against live PyPI and silently changes what ships.
# Falling back "just this once" is exactly how the bytes drifted twice.
if [ ! -f "$LOCK_PATH" ]; then
  echo "FAIL: $LOCK_PATH not found — generate it first:" >&2
  echo "      Phase0/scripts/lock_agents.sh $AGENT_DIR" >&2
  exit 1
fi
# Is the lock current? Compare CONTENT, not mtime.
#
# This was `requirements.txt -nt requirements.lock`, which is wrong for both ways
# these files actually arrive. Git does not preserve mtimes, so a fresh clone or a
# branch switch orders the pair arbitrarily; and unzipping the delivered agents
# payload restores whatever ordering the packaging machine happened to have. Every
# agent read as stale after a `git pull` here, and the enterprise side would have
# hit the same failure on a first build straight out of the zip. The only way past
# it was to touch a file — which trains you to bypass the check that catches the
# real case.
#
# What matters is whether every pin in requirements.txt is resolved at that exact
# version in the lock. Bump a pin, add a package or swap one out without
# re-locking and the lock no longer carries that line. Reorder, reformat or
# re-comment requirements.txt and nothing trips, correctly.
stale_pins=""
while IFS= read -r req_line || [ -n "$req_line" ]; do
  req_line="$(printf '%s' "${req_line%%#*}" | tr -d '[:space:]')"
  [ -n "$req_line" ] || continue
  case "$req_line" in *==*) ;; *) continue ;; esac
  pin_name="${req_line%%==*}"
  pin_version="${req_line#*==}"
  # pyjwt[crypto] -> pyjwt. The extra's own dependencies are separate lock lines.
  pin_name="${pin_name%%[*}"
  # The lock is written PEP 503-normalized (lowercase, hyphens); match that.
  pin_name="$(printf '%s' "$pin_name" | tr '[:upper:]' '[:lower:]' | tr '_.' '--')"
  grep -qxF "$pin_name==$pin_version" "$LOCK_PATH" || stale_pins="$stale_pins        $req_line
"
done < "$AGENT_DIR/requirements.txt"

if [ -n "$stale_pins" ]; then
  echo "FAIL: requirements.lock does not resolve these requirements.txt pins:" >&2
  printf '%s' "$stale_pins" >&2
  echo "      The lock is stale. Regenerate it and review the diff:" >&2
  echo "      Phase0/scripts/lock_agents.sh $AGENT_DIR" >&2
  exit 1
fi

rm -rf "$BUILD_DIR" "$ZIP_PATH"
mkdir -p "$PACKAGE_DIR"

echo "==> Installing linux/arm64 dependencies for $AGENT_NAME (from requirements.lock)"
uv pip install \
  --python-platform aarch64-manylinux2014 \
  --python-version "$PYTHON_VERSION" \
  --only-binary=:all: \
  -r "$LOCK_PATH" \
  --target "$PACKAGE_DIR"

echo "==> Copying agent sources to the package root"
cp "$AGENT_DIR"/*.py "$PACKAGE_DIR/"

echo "==> Normalizing permissions (644 files, 755 dirs and console scripts)"
find "$PACKAGE_DIR" -type d -exec chmod 755 {} +
find "$PACKAGE_DIR" -type f -exec chmod 644 {} +
# bin/ holds the console scripts that came with the dependencies, and the runtime
# entry point IS one of them: ["opentelemetry-instrument", "agent.py"]. AgentCore
# needs 755 on executables, so the blanket 644 above has to be undone here — left
# at 644 the runtime never goes healthy and reports an initialization timeout,
# with nothing in the logs pointing at a permission bit.
if [ -d "$PACKAGE_DIR/bin" ]; then
  find "$PACKAGE_DIR/bin" -type f -exec chmod 755 {} +
fi

echo "==> Verifying every native binary is ARM64"
bad=0
while IFS= read -r so_file; do
  info="$(file -b "$so_file")"
  case "$info" in
    *aarch64*) ;;
    *ARM64*) ;;
    *) echo "NOT ARM64: $so_file -> $info" >&2; bad=1 ;;
  esac
done < <(find "$PACKAGE_DIR" -type f -name "*.so*")
if [ "$bad" -ne 0 ]; then
  echo "FAIL: non-ARM64 native binaries found, rebuild with the uv flags in this script" >&2
  exit 1
fi

unzipped_mb=$(du -sm "$PACKAGE_DIR" | cut -f1)
if [ "$unzipped_mb" -gt "$MAX_UNZIPPED_MB" ]; then
  echo "FAIL: unzipped package is ${unzipped_mb} MB, limit is ${MAX_UNZIPPED_MB} MB" >&2
  exit 1
fi

echo "==> Making the package reproducible"
# Bytecode caches are build-time noise: they embed source paths/timestamps and
# would differ per build. Python regenerates them at runtime.
find "$PACKAGE_DIR" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$PACKAGE_DIR" -type f -name '*.pyc' -delete 2>/dev/null || true
# Pin every mtime (zip stores one per entry). -h so a symlink's own timestamp is
# set instead of its target's.
find "$PACKAGE_DIR" -exec touch -h -t "$SOURCE_DATE" {} +

echo "==> Zipping from inside the package folder (reproducible)"
# -X drops extra attributes (uid/gid, atime, Finder metadata) that vary by
# machine. The sorted file list pins entry ORDER, which plain `zip -r` would
# otherwise take from filesystem traversal order.
( cd "$PACKAGE_DIR" && find . -mindepth 1 | LC_ALL=C sort | zip -qX "$ZIP_PATH" -@ )

zip_mb=$(du -m "$ZIP_PATH" | cut -f1)
if [ "$zip_mb" -gt "$MAX_ZIP_MB" ]; then
  echo "FAIL: zip is ${zip_mb} MB, limit is ${MAX_ZIP_MB} MB" >&2
  exit 1
fi

root_entry_count="$(unzip -l "$ZIP_PATH" | awk '{print $4}' | grep -cx "agent.py" || true)"
if [ "$root_entry_count" -eq 0 ]; then
  echo "FAIL: agent.py is not at the zip root" >&2
  exit 1
fi

# The deployed entry point is ["opentelemetry-instrument", "agent.py"]
# (scripts/deploy_agent.py), so a zip without a runnable opentelemetry-instrument
# is a zip that cannot start. Both failure modes — dependency dropped from
# requirements.txt, or the 644 pass above reaching bin/ — surface at deploy time
# as an initialization timeout, hours later and far from the cause. Check here.
otel_entry="$(unzip -Z "$ZIP_PATH" 'bin/opentelemetry-instrument' 2>/dev/null | head -1)"
case "$otel_entry" in
  -rwxr-xr-x*) ;;
  "")
    echo "FAIL: bin/opentelemetry-instrument is missing from the zip." >&2
    echo "      aws-opentelemetry-distro must stay in $AGENT_NAME/requirements.txt" >&2
    echo "      (and in requirements.lock — rerun scripts/lock_agents.sh)." >&2
    exit 1
    ;;
  *)
    echo "FAIL: bin/opentelemetry-instrument is not executable ($otel_entry)" >&2
    exit 1
    ;;
esac

echo "OK: $ZIP_PATH (${zip_mb} MB zipped, ${unzipped_mb} MB unzipped)"
