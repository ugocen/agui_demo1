#!/usr/bin/env bash
# Shared definition of the Phase0 -> cloud_deploy agent fork: which agents exist,
# and which files are ALLOWED to differ between the two copies. Sourced by
# sync_agents.sh and check_agent_sync.sh so both agree on one definition.
#
# Why a fork at all (see AGENTS.md invariant 4): each environment has exactly one
# LLM provider. Phase0 runs in our account and only ever talks to Amazon Bedrock;
# the enterprise runs in its own account, has no Bedrock model access, and only
# ever talks to the GenAI marketplace gateway. Keeping the provider selectable at
# runtime meant a single missing env var silently sent enterprise traffic to
# Bedrock. Splitting the provider into two purpose-built files removes the switch,
# so that failure mode cannot exist.
#
# Why only ONE file may differ: everything else about an agent — its prompt,
# tools, graph, deps — is identical in both environments. Letting the copies drift
# anywhere else would fork the product, not just the provider. check_agent_sync.sh
# enforces that.

set -euo pipefail

AGENT_DIRS=(
  sdlc-planner-strands
  release-readiness-langgraph
  bug-report-strands
  a2ui-demo-strands
  press-release-strands
  jira-story-strands
)

# The ONLY files that may differ between Phase0/agents/<a>/ and
# cloud_deploy/agents/<a>/. Phase0's model_factory.py is Bedrock-only;
# cloud_deploy's is gateway-only. Neither carries the other's provider.
FORKED_FILES=(
  model_factory.py
)

# Never copied or compared.
EXCLUDES=(
  --exclude '__pycache__'
  --exclude '*.pyc'
  --exclude '.DS_Store'
  --exclude '.venv'
  --exclude '.env'
  --exclude '.env.*'
  --exclude 'build'
)

# Materialize the enterprise agent tree from Phase0 into $2, leaving the forked
# files in place (they are owned by the destination, never by the sync).
agents_sync() {
  local src="$1" out="$2"
  local fork_excludes=()
  local f
  for f in "${FORKED_FILES[@]}"; do
    fork_excludes+=(--exclude "$f")
  done

  local a
  for a in "${AGENT_DIRS[@]}"; do
    mkdir -p "$out/agents/$a"
    # --delete so a file removed from Phase0 is removed here too. rsync never
    # deletes an --exclude'd path, so the forked model_factory.py survives.
    rsync -a --delete "${EXCLUDES[@]}" "${fork_excludes[@]}" \
      "$src/agents/$a/" "$out/agents/$a/"
  done
}
