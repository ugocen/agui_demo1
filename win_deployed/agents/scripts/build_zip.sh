#!/usr/bin/env bash
# Build an AgentCore direct-code-deployment zip for one agent.
# Usage: build_zip.sh <agent-dir>
# Installs dependencies as linux/arm64 wheels, copies the agent sources to
# the package root, normalizes permissions, zips from inside the package
# folder, and fails loudly on size or architecture violations.

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

MAX_ZIP_MB=250
MAX_UNZIPPED_MB=750
PYTHON_VERSION=3.13

if [ ! -f "$AGENT_DIR/requirements.txt" ]; then
  echo "FAIL: $AGENT_DIR/requirements.txt not found" >&2
  exit 1
fi

rm -rf "$BUILD_DIR" "$ZIP_PATH"
mkdir -p "$PACKAGE_DIR"

echo "==> Installing linux/arm64 dependencies for $AGENT_NAME"
uv pip install \
  --python-platform aarch64-manylinux2014 \
  --python-version "$PYTHON_VERSION" \
  --only-binary=:all: \
  -r "$AGENT_DIR/requirements.txt" \
  --target "$PACKAGE_DIR"

echo "==> Copying agent sources to the package root"
cp "$AGENT_DIR"/*.py "$PACKAGE_DIR/"

echo "==> Normalizing permissions (644 files, 755 dirs)"
find "$PACKAGE_DIR" -type d -exec chmod 755 {} +
find "$PACKAGE_DIR" -type f -exec chmod 644 {} +

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

echo "==> Zipping from inside the package folder"
(cd "$PACKAGE_DIR" && zip -qr "$ZIP_PATH" .)

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

echo "OK: $ZIP_PATH (${zip_mb} MB zipped, ${unzipped_mb} MB unzipped)"
