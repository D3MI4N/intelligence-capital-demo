"""Where the primary store lives, and where everything derived from it goes.

The wiki and raw trees are the inputs. Everything else named here is output -
disposable, gitignored, and rebuilt or re-accumulated from scratch.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

WIKI_DIR = REPO_ROOT / "wiki"
RAW_DIR = REPO_ROOT / "raw"

INDEX_DIR = REPO_ROOT / ".index"
DOCUMENTS_PATH = INDEX_DIR / "documents.json"
CHUNKS_PATH = INDEX_DIR / "chunks.json"
VECTOR_DB_PATH = INDEX_DIR / "vectors" / "chunks.db"
GRAPH_DB_PATH = INDEX_DIR / "graph" / "graph.db"

TRACES_DIR = REPO_ROOT / "traces"


def source_roots() -> tuple[tuple[str, Path], ...]:
    """The markdown trees that get ingested, as (source label, directory)."""
    return (("wiki", WIKI_DIR), ("raw", RAW_DIR))
