"""Bounded, cycle-safe traversal of the knowledge graph.

The traversal lives here rather than in a store implementation on purpose: it
is the contract, and it must behave identically whatever engine holds the
edges. A store only has to answer two questions - what is this node, and which
edges touch these nodes - and it inherits this walk for free, together with the
tests that pin it down.

Three properties the walk guarantees:
  - bounded: depth is checked against MAX_DEPTH before a single edge is read,
    so a tool call cannot pull the whole graph back
  - cycle safe: a node is expanded once. A -> B -> C -> A terminates, and the
    edge that closes the cycle is still reported
  - deterministic: same seeds, same filter, same depth -> byte-identical
    result, because the frontier is walked in sorted order and the result is
    sorted before it is returned

Edges are followed in both directions. A case names its peril outbound, and
its documents point at it inbound; a subgraph that dropped the inbound half
would leave the agent without the documents it needs to cite.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from errors import InvalidDepth, InvalidRelation, ToolError, UnknownNode
from ingest.entities import RELATIONS, Edge, Node

MAX_DEPTH = 4


@dataclass(frozen=True)
class Subgraph:
    """The neighbourhood of a set of seeds, with every node's distance from them."""

    seeds: tuple[str, ...]
    depth: int
    nodes: tuple[Node, ...]  # sorted by (type, node_id)
    edges: tuple[Edge, ...]  # sorted by (src, rel, dst, source_doc)
    depth_of: Mapping[str, int]  # node_id -> hops from the nearest seed


class GraphReader(Protocol):
    """The two reads a graph engine must support for traverse() to work."""

    def get_node(self, node_id: str) -> Node | None: ...

    def neighbours(
        self, node_ids: Sequence[str], rel_types: Sequence[str] | None = None
    ) -> tuple[Edge, ...]: ...


def check_depth(depth: int) -> int:
    """Depth must be a whole number of hops the tools are willing to walk."""
    if depth < 0 or depth > MAX_DEPTH:
        raise InvalidDepth(f"depth {depth} is out of range - use 0 to {MAX_DEPTH}")
    return depth


def check_relations(rel_types: Sequence[str] | None) -> tuple[str, ...] | None:
    """Validate a relation filter against the published vocabulary.

    None means every relation. An empty filter would mean no relation at all,
    which is never what a caller wants, so it is treated as an error rather
    than silently returning the seeds back.
    """
    if rel_types is None:
        return None
    wanted = tuple(dict.fromkeys(rel_types))
    if not wanted:
        raise InvalidRelation("rel_types is empty - pass None for every relation")
    unknown = sorted(set(wanted) - RELATIONS)
    if unknown:
        known = " - ".join(sorted(RELATIONS))
        raise InvalidRelation(
            f"unknown relation(s) {' - '.join(unknown)} - the vocabulary defines: {known}"
        )
    return wanted


def traverse(
    store: GraphReader,
    seed_ids: Sequence[str],
    rel_types: Sequence[str] | None = None,
    depth: int = 2,
) -> Subgraph:
    """Walk out from the seeds and return everything reached within depth hops."""
    relations = check_relations(rel_types)
    hops = check_depth(depth)
    seeds = tuple(dict.fromkeys(seed_ids))
    if not seeds:
        raise ToolError("traverse needs at least one seed node id")

    found: dict[str, Node] = {}
    for seed in seeds:
        node = store.get_node(seed)
        if node is None:
            raise UnknownNode(f"unknown node '{seed}' - graph holds no node with that id")
        found[seed] = node

    # depth_of doubles as the visited set: a node in it is never queued again.
    depth_of = dict.fromkeys(seeds, 0)
    edges: dict[tuple[str, str, str, str], Edge] = {}
    frontier = sorted(seeds)

    for hop in range(1, hops + 1):
        if not frontier:
            break
        discovered: list[str] = []
        for edge in store.neighbours(frontier, relations):
            edges.setdefault((edge.src, edge.rel, edge.dst, edge.source_doc), edge)
            for end in (edge.src, edge.dst):
                if end in depth_of:
                    continue
                depth_of[end] = hop
                discovered.append(end)
        for node_id in sorted(discovered):
            node = store.get_node(node_id)
            if node is not None:
                found[node_id] = node
        frontier = sorted(discovered)

    kept = tuple(
        sorted(
            (edge for edge in edges.values() if edge.src in found and edge.dst in found),
            key=lambda edge: (edge.src, edge.rel, edge.dst, edge.source_doc),
        )
    )
    return Subgraph(
        seeds=seeds,
        depth=hops,
        nodes=tuple(sorted(found.values(), key=lambda node: (node.type, node.node_id))),
        edges=kept,
        depth_of={node_id: depth_of[node_id] for node_id in sorted(found)},
    )
