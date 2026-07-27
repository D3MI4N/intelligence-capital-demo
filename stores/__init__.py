"""The storage layer: protocols for the derived indexes and one implementation.

Storage is its own layer, below both the ingest pipeline that writes the
indexes and the MCP tools that read them. Neither of those knows which engine
is underneath - they know VectorStore, GraphStore, and the bounded walk in
traversal.py.

This module is the package's public surface. Import from here rather than from
stores.stores or stores.traversal, so a rearrangement inside the package is
not a change to everyone who uses it.
"""

from __future__ import annotations

from stores.stores import (
    GraphStore,
    Hit,
    SqliteGraphStore,
    SqliteVectorStore,
    VectorStore,
    connect,
    pack_vector,
    read_graph,
    write_graph,
    write_vector_index,
)
from stores.traversal import (
    MAX_DEPTH,
    GraphReader,
    Subgraph,
    check_depth,
    check_relations,
    traverse,
)

__all__ = [
    "MAX_DEPTH",
    "GraphReader",
    "GraphStore",
    "Hit",
    "SqliteGraphStore",
    "SqliteVectorStore",
    "Subgraph",
    "VectorStore",
    "check_depth",
    "check_relations",
    "connect",
    "pack_vector",
    "read_graph",
    "traverse",
    "write_graph",
    "write_vector_index",
]
