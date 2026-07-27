"""What the tools need in order to run, passed in rather than reached for.

Every tool in tools.py takes a ToolContext as its first argument and touches
nothing else: no module-level store, no ambient configuration, no import-time
side effect. That is what makes the tools plain functions to test - a test
builds a context over a temporary wiki and a temporary index - and it is what
lets the demo point the same tools at a rehearsal copy.

default_context() is the one place the demo's real choices are wired up, and
server.py is its only caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ingest import layout
from ingest.embed import EmbedFn, select_embedder
from mcp_server.tokens import TokenCounter, count_tokens
from stores import GraphStore, SqliteGraphStore, SqliteVectorStore, VectorStore


@dataclass(frozen=True)
class ToolContext:
    """The stores, the embedder, the tokenizer and the two directories."""

    vectors: VectorStore
    graph: GraphStore
    embed: EmbedFn
    count_tokens: TokenCounter
    wiki_dir: Path
    traces_dir: Path


def default_context() -> ToolContext:
    """The demo wiring: the indexes under .index/, the wiki, traces/."""
    return ToolContext(
        vectors=SqliteVectorStore(layout.VECTOR_DB_PATH),
        graph=SqliteGraphStore(layout.GRAPH_DB_PATH),
        embed=select_embedder(),
        count_tokens=count_tokens,
        wiki_dir=layout.WIKI_DIR,
        traces_dir=layout.TRACES_DIR,
    )
