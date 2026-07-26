"""Where the primary store lives and where the derived indexes are written."""

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


def source_roots() -> tuple[tuple[str, Path], ...]:
    """The markdown trees that get ingested, as (source label, directory)."""
    return (("wiki", WIKI_DIR), ("raw", RAW_DIR))
