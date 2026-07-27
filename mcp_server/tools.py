"""The four tools. Everything an agent may do to the wiki is one of these.

Each is a plain function of its context and its arguments: no class to
instantiate, no session to keep, no state between calls. They are the only
route to storage - agents never open an index or a markdown file themselves -
and every call, refused or served, leaves a trace line behind.

  search_knowledge_base  ranked chunks, each carrying the id and path a claim
                         must cite
  traverse_graph         the entity neighbourhood around a seed, bounded
  read_case_context      the AGENTS.md cascade plus index and briefing, each
                         with what it costs to read
  propose_wiki_update    the only write path, guarded by mcp_server/writes.py
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from errors import ToolError
from ingest.entities import Edge, Node
from ingest.models import Chunk
from mcp_server import cases, tracing, writes
from mcp_server.context import ToolContext
from mcp_server.results import (
    CaseContext,
    CaseDocument,
    ChunkHit,
    GraphEdge,
    GraphNode,
    SubgraphResult,
    WriteResult,
)

SEARCH = "search_knowledge_base"
TRAVERSE = "traverse_graph"
READ_CASE = "read_case_context"
PROPOSE = "propose_wiki_update"


def search_knowledge_base(
    context: ToolContext,
    query: str,
    top_k: int = 5,
    path_prefix: str | None = None,
) -> list[ChunkHit]:
    """Rank chunks of the corpus against a query, best first.

    path_prefix narrows the search to part of the corpus by document path -
    "wiki/submissions/" for open submissions, "wiki/claims/" for closed
    claims, a single case directory for one case.
    """
    args: dict[str, object] = {"query": query, "top_k": top_k, "path_prefix": path_prefix}
    try:
        if not query.strip():
            raise ToolError("query is empty - say what to search for")
        vector = context.embed([query])[0]
        hits = [
            _hit(chunk, score)
            for chunk, score in context.vectors.search(vector, top_k, path_prefix)
        ]
    except (ToolError, ValueError) as error:
        _trace_error(context, SEARCH, args, error)
        raise
    _trace(
        context,
        SEARCH,
        args,
        {
            "hits": len(hits),
            "chunk_ids": [hit["chunk_id"] for hit in hits],
            # The ranking, not the payload: an audit of a retrieval wants to
            # know how close the chunk that got cited actually was.
            "scores": [hit["score"] for hit in hits],
        },
    )
    return hits


def traverse_graph(
    context: ToolContext,
    seed: str,
    rel_types: Sequence[str] | None = None,
    depth: int = 2,
) -> SubgraphResult:
    """Return the entity neighbourhood around a seed node.

    rel_types filters on the published vocabulary - an unknown relation is a
    refusal, not an empty result. depth is bounded; see stores/traversal.py.
    """
    args: dict[str, object] = {
        "seed": seed,
        "rel_types": list(rel_types) if rel_types is not None else None,
        "depth": depth,
    }
    try:
        subgraph = context.graph.traverse([seed], rel_types, depth)
    except (ToolError, ValueError) as error:
        _trace_error(context, TRAVERSE, args, error)
        raise
    result: SubgraphResult = {
        "seeds": list(subgraph.seeds),
        "depth": subgraph.depth,
        "rel_types": list(rel_types) if rel_types is not None else None,
        "nodes": [_node(node, subgraph.depth_of[node.node_id]) for node in subgraph.nodes],
        "edges": [_edge(edge) for edge in subgraph.edges],
    }
    _trace(
        context,
        TRAVERSE,
        args,
        {
            "nodes": len(result["nodes"]),
            "edges": len(result["edges"]),
            "node_ids": [node["id"] for node in result["nodes"]],
        },
    )
    return result


def read_case_context(context: ToolContext, case_id: str) -> CaseContext:
    """The orientation read for a case, in the order an agent should take it.

    The AGENTS.md cascade first - platform, then domain, then case - then
    index.md, then briefing.md. Each file carries its own token count, so the
    caller can show what the orientation cost before any retrieval happens.

    index.md defines the case and its absence means the case does not exist. A
    missing briefing.md is reported in "missing" rather than raised: a case
    part-way through its first run has not been briefed yet, and refusing to
    orient at all would be the wrong answer.
    """
    args: dict[str, object] = {"case_id": case_id}
    try:
        directory = cases.case_dir(case_id, context.wiki_dir)
        documents: list[CaseDocument] = []
        missing: list[str] = []
        for path in cases.context_files(directory, context.wiki_dir):
            if not path.is_file():
                missing.append(_relative(path, context.wiki_dir))
                continue
            text = path.read_text(encoding="utf-8")
            documents.append(
                {
                    "path": _relative(path, context.wiki_dir),
                    "role": cases.role_of(path),
                    "text": text,
                    "tokens": context.count_tokens(text),
                }
            )
    except (ToolError, OSError) as error:
        _trace_error(context, READ_CASE, args, error)
        raise
    result: CaseContext = {
        "case_id": case_id,
        "case_dir": _relative(directory, context.wiki_dir),
        "documents": documents,
        "missing": missing,
        "total_tokens": sum(document["tokens"] for document in documents),
    }
    _trace(
        context,
        READ_CASE,
        args,
        {
            "documents": len(documents),
            "paths": [document["path"] for document in documents],
            "missing": missing,
            "total_tokens": result["total_tokens"],
        },
    )
    return result


def propose_wiki_update(
    context: ToolContext,
    path: str,
    operation: str,
    content: str,
) -> WriteResult:
    """Write to the wiki, if the guardrails allow it.

    Operations: append_section, replace_section, create_file. What is refused,
    and why, is in mcp_server/writes.py - the refusal message says what would
    have been allowed instead.
    """
    args: dict[str, object] = {
        "path": path,
        "operation": operation,
        "content_chars": len(content),
    }
    try:
        outcome = writes.apply(path, operation, content, context.wiki_dir)
    except (ToolError, OSError) as error:
        _trace_error(context, PROPOSE, args, error)
        raise
    result: WriteResult = {
        "path": _relative(outcome.path, context.wiki_dir),
        "operation": outcome.operation,
        "section": outcome.section,
        "created": outcome.created,
        "bytes_written": outcome.bytes_written,
    }
    _trace(context, PROPOSE, args, dict(result) | {"content_chars": len(content)})
    return result


def _hit(chunk: Chunk, score: float) -> ChunkHit:
    return {
        "chunk_id": chunk.chunk_id,
        "doc": chunk.doc_id,
        "source": chunk.source,
        "heading_path": list(chunk.heading_path),
        "score": round(score, 6),
        "text": chunk.text,
    }


def _node(node: Node, depth: int) -> GraphNode:
    return {
        "id": node.node_id,
        "type": node.type,
        "label": node.label,
        "attrs": dict(node.attrs),
        "depth": depth,
    }


def _edge(edge: Edge) -> GraphEdge:
    return {"src": edge.src, "rel": edge.rel, "dst": edge.dst, "source_doc": edge.source_doc}


def _relative(path: Path, wiki_dir: Path) -> str:
    """A path in the form the rest of the platform cites.

    The same string a chunk carries as its doc_id - "wiki/claims/.../index.md"
    - so a path returned by one tool matches a path returned by another, and
    both resolve as wikilinks.
    """
    resolved = path.resolve()
    root = wiki_dir.resolve().parent
    return resolved.relative_to(root).as_posix() if resolved.is_relative_to(root) else str(resolved)


def _trace(
    context: ToolContext, tool: str, args: Mapping[str, object], result: Mapping[str, object]
) -> None:
    tracing.append(tool, args, result, tracing.OK, context.traces_dir)


def _trace_error(
    context: ToolContext, tool: str, args: Mapping[str, object], error: Exception
) -> None:
    tracing.append(
        tool,
        args,
        {"error": str(error), "type": type(error).__name__},
        tracing.ERROR,
        context.traces_dir,
    )
