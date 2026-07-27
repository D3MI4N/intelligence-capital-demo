"""The store contract: retrieval, one-hop reads, and the bounded walk.

Everything here goes through VectorStore and GraphStore rather than through
the engine underneath, so a second implementation is expected to pass this
file unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from errors import IndexMissing, InvalidDepth, InvalidRelation, UnknownNode
from ingest.embed import build_vector_index
from ingest.entities import Edge, Graph, Node
from ingest.graph import build_graph
from ingest.hash_embedder import hash_embed
from ingest.parse import parse_corpus
from stores import MAX_DEPTH, SqliteGraphStore, SqliteVectorStore, write_graph

Roots = tuple[tuple[str, Path], ...]

CASE = "Case:CLM-9999-001"


@pytest.fixture
def vectors(corpus: Roots, tmp_path: Path) -> SqliteVectorStore:
    _, chunks = parse_corpus(corpus)
    db_path = tmp_path / "vectors" / "chunks.db"
    build_vector_index(chunks, hash_embed, db_path)
    return SqliteVectorStore(db_path)


@pytest.fixture
def graph(corpus: Roots, tmp_path: Path) -> SqliteGraphStore:
    documents, _ = parse_corpus(corpus)
    db_path = tmp_path / "graph" / "graph.db"
    write_graph(build_graph(documents), db_path)
    return SqliteGraphStore(db_path)


@pytest.fixture
def cyclic(tmp_path: Path) -> SqliteGraphStore:
    """Three cases pointing at each other in a ring: A -> B -> C -> A.

    Nothing in the wiki produces this today, and something eventually will -
    two cases that each link the other is enough. The walk has to come back.
    """
    ring = ("Case:A", "Case:B", "Case:C")
    nodes = tuple(Node(node_id=node, type="Case", label=node) for node in ring)
    edges = tuple(
        Edge(src=src, rel="related_case", dst=ring[(index + 1) % len(ring)], source_doc="wiki/a.md")
        for index, src in enumerate(ring)
    )
    db_path = tmp_path / "cyclic" / "graph.db"
    write_graph(Graph(nodes=nodes, edges=edges), db_path)
    return SqliteGraphStore(db_path)


def test_search_ranks_the_matching_chunk_first(vectors: SqliteVectorStore, corpus: Roots) -> None:
    _, chunks = parse_corpus(corpus)
    target = chunks[0]

    hits = vectors.search(hash_embed([target.text])[0], k=3)

    best, _ = hits[0]
    assert best.chunk_id == target.chunk_id
    assert [score for _, score in hits] == sorted((score for _, score in hits), reverse=True)


def test_a_path_prefix_keeps_only_that_part_of_the_corpus(
    vectors: SqliteVectorStore, corpus: Roots
) -> None:
    _, chunks = parse_corpus(corpus)

    hits = vectors.search(hash_embed([chunks[0].text])[0], k=5, path_prefix="wiki/claims/")

    assert hits
    assert all(chunk.doc_id.startswith("wiki/claims/") for chunk, _ in hits)


def test_a_path_prefix_still_returns_a_full_page_of_hits(
    vectors: SqliteVectorStore, corpus: Roots
) -> None:
    """The filter must not eat the top k - the scan widens before it narrows."""
    _, chunks = parse_corpus(corpus)
    claims = {chunk.chunk_id for chunk in chunks if chunk.doc_id.startswith("wiki/claims/")}

    hits = vectors.search(hash_embed(["anything at all"])[0], k=5, path_prefix="wiki/claims/")

    assert len(hits) == min(5, len(claims))


def test_a_prefix_that_matches_nothing_returns_nothing(
    vectors: SqliteVectorStore, corpus: Roots
) -> None:
    _, chunks = parse_corpus(corpus)

    assert vectors.search(hash_embed([chunks[0].text])[0], k=5, path_prefix="wiki/nowhere/") == []


def test_asking_for_no_results_is_an_error(vectors: SqliteVectorStore) -> None:
    with pytest.raises(ValueError, match="positive"):
        vectors.search(hash_embed(["query"])[0], k=0)


def test_an_index_that_was_never_built_says_so(tmp_path: Path) -> None:
    with pytest.raises(IndexMissing, match="rebuild.sh"):
        SqliteVectorStore(tmp_path / "absent.db").search(hash_embed(["query"])[0])

    with pytest.raises(IndexMissing, match="rebuild.sh"):
        SqliteGraphStore(tmp_path / "absent.db").get_node(CASE)


def test_get_node_returns_the_node_and_its_attributes(graph: SqliteGraphStore) -> None:
    node = graph.get_node(CASE)

    assert node is not None
    assert node.type == "Case"
    assert node.attrs["status"] == "settled-closed"


def test_get_node_returns_nothing_for_an_id_the_graph_does_not_hold(
    graph: SqliteGraphStore,
) -> None:
    assert graph.get_node("Case:NOPE") is None


def test_neighbours_come_back_from_both_directions(graph: SqliteGraphStore) -> None:
    edges = graph.neighbours([CASE])

    assert any(edge.src == CASE and edge.rel == "insured_by" for edge in edges)
    assert any(edge.dst == CASE and edge.rel == "belongs_to" for edge in edges)


def test_neighbours_can_be_filtered_to_named_relations(graph: SqliteGraphStore) -> None:
    edges = graph.neighbours([CASE], ["involves_peril"])

    assert edges
    assert {edge.rel for edge in edges} == {"involves_peril"}


def test_neighbours_of_nothing_is_nothing(graph: SqliteGraphStore) -> None:
    assert graph.neighbours([]) == ()


def test_depth_zero_returns_the_seed_alone(graph: SqliteGraphStore) -> None:
    subgraph = graph.traverse([CASE], depth=0)

    assert [node.node_id for node in subgraph.nodes] == [CASE]
    assert subgraph.edges == ()


def test_one_hop_reaches_the_directly_related_entities(graph: SqliteGraphStore) -> None:
    reached = {node.node_id for node in graph.traverse([CASE], depth=1).nodes}

    assert "Insured:testco-logistics-bv" in reached
    assert "Peril:ransomware" in reached
    assert "Case:SUB-9999-001" in reached


def test_two_hops_reach_what_the_neighbours_reach(graph: SqliteGraphStore) -> None:
    one = {node.node_id for node in graph.traverse([CASE], depth=1).nodes}
    two = {node.node_id for node in graph.traverse([CASE], depth=2).nodes}

    assert one < two
    assert "Clause:CY-EX-01" in two


def test_every_node_carries_its_distance_from_the_seed(graph: SqliteGraphStore) -> None:
    subgraph = graph.traverse([CASE], depth=2)

    assert subgraph.depth_of[CASE] == 0
    assert subgraph.depth_of["Insured:testco-logistics-bv"] == 1
    assert set(subgraph.depth_of.values()) <= {0, 1, 2}
    assert set(subgraph.depth_of) == {node.node_id for node in subgraph.nodes}


def test_a_relation_filter_limits_the_walk(graph: SqliteGraphStore) -> None:
    subgraph = graph.traverse([CASE], ["involves_peril"], depth=2)

    assert {edge.rel for edge in subgraph.edges} == {"involves_peril"}
    assert {node.type for node in subgraph.nodes} == {"Case", "Peril"}


def test_an_unknown_relation_is_refused_and_names_the_known_ones(
    graph: SqliteGraphStore,
) -> None:
    with pytest.raises(InvalidRelation, match="caused_by"):
        graph.traverse([CASE], ["caused_by"], depth=1)


def test_an_empty_relation_filter_is_refused(graph: SqliteGraphStore) -> None:
    with pytest.raises(InvalidRelation, match="empty"):
        graph.traverse([CASE], [], depth=1)


def test_depth_beyond_the_bound_is_refused(graph: SqliteGraphStore) -> None:
    with pytest.raises(InvalidDepth, match=str(MAX_DEPTH)):
        graph.traverse([CASE], depth=MAX_DEPTH + 1)

    with pytest.raises(InvalidDepth):
        graph.traverse([CASE], depth=-1)


def test_an_unknown_seed_is_refused(graph: SqliteGraphStore) -> None:
    with pytest.raises(UnknownNode, match="Case:NOPE"):
        graph.traverse(["Case:NOPE"], depth=1)


def test_the_result_is_internally_consistent(graph: SqliteGraphStore) -> None:
    subgraph = graph.traverse([CASE], depth=2)
    node_ids = {node.node_id for node in subgraph.nodes}

    assert all(edge.src in node_ids and edge.dst in node_ids for edge in subgraph.edges)


def test_the_result_is_sorted_and_repeatable(graph: SqliteGraphStore) -> None:
    first = graph.traverse([CASE], depth=2)
    second = graph.traverse([CASE], depth=2)

    assert first == second
    assert list(first.nodes) == sorted(first.nodes, key=lambda node: (node.type, node.node_id))
    assert list(first.edges) == sorted(
        first.edges, key=lambda edge: (edge.src, edge.rel, edge.dst, edge.source_doc)
    )


def test_a_cycle_terminates_and_reports_the_edge_that_closes_it(
    cyclic: SqliteGraphStore,
) -> None:
    subgraph = cyclic.traverse(["Case:A"], depth=MAX_DEPTH)

    assert [node.node_id for node in subgraph.nodes] == ["Case:A", "Case:B", "Case:C"]
    assert len(subgraph.edges) == 3
    assert subgraph.depth_of == {"Case:A": 0, "Case:B": 1, "Case:C": 1}


def test_a_cycle_is_walked_the_same_way_however_deep_the_request(
    cyclic: SqliteGraphStore,
) -> None:
    shallow = cyclic.traverse(["Case:A"], depth=2)
    deep = cyclic.traverse(["Case:A"], depth=MAX_DEPTH)

    assert shallow.nodes == deep.nodes
    assert shallow.edges == deep.edges
