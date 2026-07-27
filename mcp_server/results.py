"""The shapes the four tools return.

TypedDicts rather than dataclasses: these values cross the MCP boundary as
JSON, and this way the JSON shape and the type checked inside the process are
the same declaration. Every field is something an agent can cite - a chunk id,
a document path, an entity id - because a result no one can cite is a result
the platform rules will not let an agent use.
"""

from __future__ import annotations

from typing import TypedDict


class ChunkHit(TypedDict):
    """One retrieved chunk with its provenance and score."""

    chunk_id: str
    doc: str
    source: str
    heading_path: list[str]
    score: float
    text: str


class GraphNode(TypedDict):
    """One entity in a returned subgraph, with its distance from the seed."""

    id: str
    type: str
    label: str
    attrs: dict[str, object]
    depth: int


class GraphEdge(TypedDict):
    """One relation in a returned subgraph, and the document it came from."""

    src: str
    rel: str
    dst: str
    source_doc: str


class SubgraphResult(TypedDict):
    seeds: list[str]
    depth: int
    rel_types: list[str] | None
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class CaseDocument(TypedDict):
    """One file of case context, and what reading it costs."""

    path: str
    role: str  # rules - index - briefing
    text: str
    tokens: int


class CaseContext(TypedDict):
    case_id: str
    case_dir: str
    documents: list[CaseDocument]
    missing: list[str]
    total_tokens: int


class WriteResult(TypedDict):
    path: str
    operation: str
    section: str | None
    created: bool
    bytes_written: int
