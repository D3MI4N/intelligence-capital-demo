from pathlib import Path

from ingest.entities import Edge, Graph
from ingest.graph import build_graph, read_graph, write_graph
from ingest.parse import parse_corpus

Roots = tuple[tuple[str, Path], ...]


def graph_of(corpus: Roots) -> Graph:
    documents, _ = parse_corpus(corpus)
    return build_graph(documents)


def has(graph: Graph, src: str, rel: str, dst: str) -> bool:
    return any(edge.src == src and edge.rel == rel and edge.dst == dst for edge in graph.edges)


def test_nodes_come_from_frontmatter(corpus: Roots) -> None:
    graph = graph_of(corpus)
    by_id = {node.node_id: node for node in graph.nodes}

    assert by_id["Case:CLM-9999-001"].attrs["status"] == "settled-closed"
    assert by_id["Insured:testco-logistics-bv"].label == "Testco Logistics BV"
    assert "RiskClass:cyber-logistics" in by_id
    assert "Peril:vendor-compromise" in by_id
    assert "Clause:CY-EX-04" in by_id


def test_case_relations_come_from_frontmatter_fields(corpus: Roots) -> None:
    graph = graph_of(corpus)

    assert has(graph, "Case:CLM-9999-001", "insured_by", "Insured:testco-logistics-bv")
    assert has(graph, "Case:CLM-9999-001", "in_class", "RiskClass:cyber-logistics")
    assert has(graph, "Case:CLM-9999-001", "involves_peril", "Peril:ransomware")
    assert has(graph, "Case:CLM-9999-001", "linked_submission", "Case:SUB-9999-001")
    assert has(graph, "Case:SUB-9999-001", "linked_claim", "Case:CLM-9999-001")


def test_documents_belong_to_their_case(corpus: Roots) -> None:
    graph = graph_of(corpus)

    assert has(
        graph,
        "Document:wiki/claims/CLM-9999-001/lessons.md",
        "belongs_to",
        "Case:CLM-9999-001",
    )


def test_a_source_note_belongs_to_the_case_directory_it_sits_in(corpus: Roots) -> None:
    graph = graph_of(corpus)

    # sources/note.md carries source_id, not case_id - the case comes from the path.
    assert has(
        graph,
        "Document:wiki/claims/CLM-9999-001/sources/note.md",
        "belongs_to",
        "Case:CLM-9999-001",
    )


def test_wikilinks_become_reference_edges(corpus: Roots) -> None:
    graph = graph_of(corpus)

    assert has(
        graph,
        "Document:wiki/claims/CLM-9999-001/index.md",
        "references",
        "Document:wiki/submissions/SUB-9999-001/index.md",
    )
    assert has(graph, "Case:CLM-9999-001", "related_case", "Case:SUB-9999-001")


def test_locator_lines_link_a_source_note_to_its_raw_document(corpus: Roots) -> None:
    graph = graph_of(corpus)

    assert has(
        graph,
        "Document:wiki/claims/CLM-9999-001/sources/note.md",
        "derived_from",
        "Document:raw/testco-survey.md",
    )


def test_raw_documents_name_their_case(corpus: Roots) -> None:
    graph = graph_of(corpus)

    assert has(graph, "Document:raw/testco-survey.md", "about_case", "Case:CLM-9999-001")


def test_identifiers_in_text_become_nodes_with_labels(corpus: Roots) -> None:
    graph = graph_of(corpus)
    by_id = {node.node_id: node for node in graph.nodes}

    assert by_id["Lesson:L-900"].label == "Vendor standing access is a distinct exposure path"
    assert by_id["Skill:SK-900"].label == "Precedent search"
    assert has(graph, "Case:CLM-9999-001", "has_lesson", "Lesson:L-900")
    assert has(graph, "Case:SUB-9999-001", "mentions_clause", "Clause:CY-EX-01")
    assert has(
        graph, "Document:wiki/platform-ic/skills/precedent.md", "defines_skill", "Skill:SK-900"
    )


def test_unresolved_link_targets_are_dropped(corpus: Roots) -> None:
    graph = graph_of(corpus)
    node_ids = {node.node_id for node in graph.nodes}

    assert all(edge.dst in node_ids and edge.src in node_ids for edge in graph.edges)


def test_no_self_loops(corpus: Roots) -> None:
    graph = graph_of(corpus)

    assert all(edge.src != edge.dst for edge in graph.edges)


def test_every_edge_names_the_document_it_came_from(corpus: Roots) -> None:
    graph = graph_of(corpus)
    documents, _ = parse_corpus(corpus)
    doc_ids = {document.doc_id for document in documents}

    assert all(edge.source_doc in doc_ids for edge in graph.edges)


def test_build_is_order_stable(corpus: Roots) -> None:
    assert graph_of(corpus) == graph_of(corpus)


def test_graph_round_trips_through_the_store(corpus: Roots, tmp_path: Path) -> None:
    graph = graph_of(corpus)
    db_path = tmp_path / "graph" / "graph.db"

    write_graph(graph, db_path)
    write_graph(graph, db_path)  # rewriting replaces, it does not accumulate

    assert read_graph(db_path) == graph


def test_the_store_is_traversable_over_two_hops(corpus: Roots, tmp_path: Path) -> None:
    import sqlite3

    db_path = tmp_path / "graph.db"
    write_graph(graph_of(corpus), db_path)
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            """
            with recursive reachable(node_id, hops) as (
                select ?, 0
                union
                select edges.dst, reachable.hops + 1
                from edges join reachable on edges.src = reachable.node_id
                where reachable.hops < 2
            )
            select distinct node_id from reachable order by node_id
            """,
            ("Case:SUB-9999-001",),
        ).fetchall()
    finally:
        connection.close()

    assert "Lesson:L-900" in {str(row[0]) for row in rows}


def test_edges_are_deduplicated_per_source_document(corpus: Roots) -> None:
    graph = graph_of(corpus)

    assert len(set(graph.edges)) == len(graph.edges)
    assert all(isinstance(edge, Edge) for edge in graph.edges)
