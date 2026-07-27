"""Expose the four tools over MCP.

Package choice: `mcp`, the official Python SDK of the Model Context Protocol,
maintained by the protocol's own project. It is the reference implementation,
so the wire format the client sees is the specification rather than one
library's reading of it, and its FastMCP server derives each tool's schema
from the function signature and docstring already written in tools.py. No
other package is needed: transport, schema and session handling all come from
this one, and it brings no agent framework with it.

The wrapper is deliberately thin. Every function here does one thing - hand
its arguments to the matching function in tools.py - so the behaviour under
test and the behaviour over the wire cannot drift. The tests never start a
server; they call tools.py directly, which is the whole point of keeping this
file empty of logic.

Run it with: uv run python -m mcp_server.server
"""

from __future__ import annotations

from functools import lru_cache

from mcp.server.fastmcp import FastMCP

from mcp_server import tools
from mcp_server.context import ToolContext, default_context
from mcp_server.results import CaseContext, ChunkHit, SubgraphResult, WriteResult

server = FastMCP("intelligence-capital-wiki")


@lru_cache(maxsize=1)
def context() -> ToolContext:
    """The wiring, built on the first call and reused for the process lifetime."""
    return default_context()


@server.tool()
def search_knowledge_base(
    query: str, top_k: int = 5, path_prefix: str | None = None
) -> list[ChunkHit]:
    """Search the wiki for chunks matching a query.

    Returns ranked chunks, best first, each with the chunk id and document
    path a claim must cite. path_prefix narrows the search to part of the
    corpus, for example "wiki/claims/".
    """
    return tools.search_knowledge_base(context(), query, top_k, path_prefix)


@server.tool()
def traverse_graph(seed: str, rel_types: list[str] | None = None, depth: int = 2) -> SubgraphResult:
    """Return the entity neighbourhood around a seed node of the knowledge graph.

    seed is an entity id such as "Case:CLM-2024-042" or "Clause:CY-EX-04".
    rel_types filters the walk to named relations from the wiki vocabulary.
    """
    return tools.traverse_graph(context(), seed, rel_types, depth)


@server.tool()
def read_case_context(case_id: str) -> CaseContext:
    """Read a case's operating instructions, index and briefing, with token counts.

    Returns the AGENTS.md cascade outermost first - platform, domain, case -
    then index.md, then briefing.md.
    """
    return tools.read_case_context(context(), case_id)


@server.tool()
def propose_wiki_update(path: str, operation: str, content: str) -> WriteResult:
    """Write to the wiki. Operations: append_section, replace_section, create_file.

    path is a wiki path such as "wiki/claims/CLM-2024-042/briefing.md".
    Writes outside the wiki, to AGENTS.md, to vocabulary/, or over an existing
    decision record are refused.
    """
    return tools.propose_wiki_update(context(), path, operation, content)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
