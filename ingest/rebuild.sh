#!/usr/bin/env bash
# Rebuild every derived index from the markdown files.
#
# The wiki is the primary store; .index/ is disposable. This script wipes it and
# regenerates parsed records, the vector index and the knowledge graph, in that
# order. Running it twice on an unchanged wiki produces the same indexes.
#
# Usage: ./ingest/rebuild.sh [--verbose]
#   --verbose  also list every file ingest skipped, and why
#
# Environment (.env):
#   OPENAI_API_KEY, EMBED_MODEL  needed by the default embedding backend
#   EMBED_BACKEND=hash           rebuild offline, with no network calls

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

verbose=""
for argument in "$@"; do
  case "$argument" in
    --verbose) verbose="--verbose" ;;
    *) echo "unknown option: $argument" >&2; exit 2 ;;
  esac
done

echo "wiping .index/"
rm -rf .index

uv run python -m ingest.parse $verbose
uv run python -m ingest.embed
uv run python -m ingest.graph

echo "rebuild complete -> .index/"
