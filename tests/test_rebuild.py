"""The rebuild contract: wipe the derived indexes, regenerate, get the same thing.

Same steps as ingest/rebuild.sh, run with EMBED_BACKEND=hash so nothing goes
out to the network.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ingest.embed import build_vector_index, connect
from ingest.entities import Graph
from ingest.graph import build_graph, read_graph, write_graph
from ingest.hash_embedder import hash_embed
from ingest.parse import parse_corpus, read_documents, write_records

Roots = tuple[tuple[str, Path], ...]


def rebuild(corpus: Roots, index_dir: Path) -> None:
    """What rebuild.sh does: wipe, parse, embed, graph."""
    shutil.rmtree(index_dir, ignore_errors=True)
    documents, chunks = parse_corpus(corpus)
    write_records(documents, chunks, index_dir / "documents.json", index_dir / "chunks.json")
    build_vector_index(chunks, hash_embed, index_dir / "vectors" / "chunks.db")
    write_graph(
        build_graph(read_documents(index_dir / "documents.json")),
        index_dir / "graph" / "graph.db",
    )


def graph_of(index_dir: Path) -> Graph:
    return read_graph(index_dir / "graph" / "graph.db")


def vectors_of(index_dir: Path) -> list[tuple[object, ...]]:
    connection = connect(index_dir / "vectors" / "chunks.db")
    try:
        return connection.execute(
            "select chunk_id, embedding from chunk_vectors order by chunk_id"
        ).fetchall()
    finally:
        connection.close()


def test_two_rebuilds_produce_identical_indexes(corpus: Roots, tmp_path: Path) -> None:
    first = tmp_path / "index-one"
    second = tmp_path / "index-two"

    rebuild(corpus, first)
    rebuild(corpus, second)

    assert (first / "documents.json").read_bytes() == (second / "documents.json").read_bytes()
    assert (first / "chunks.json").read_bytes() == (second / "chunks.json").read_bytes()
    assert graph_of(first) == graph_of(second)
    assert vectors_of(first) == vectors_of(second)


def test_rebuilding_in_place_is_idempotent(corpus: Roots, tmp_path: Path) -> None:
    index_dir = tmp_path / "index"

    rebuild(corpus, index_dir)
    before = (graph_of(index_dir), vectors_of(index_dir))
    rebuild(corpus, index_dir)

    assert (graph_of(index_dir), vectors_of(index_dir)) == before


def test_a_human_edit_is_picked_up_on_the_next_rebuild(corpus: Roots, tmp_path: Path) -> None:
    index_dir = tmp_path / "index"
    rebuild(corpus, index_dir)
    before = graph_of(index_dir)

    wiki_root = corpus[0][1]
    edited = wiki_root / "claims" / "CLM-9999-001" / "coverage.md"
    edited.write_text(
        "---\ncase_id: CLM-9999-001\n---\n\n# Coverage\n\nExclusion CY-EX-07 was raised.\n",
        encoding="utf-8",
    )
    rebuild(corpus, index_dir)
    after = graph_of(index_dir)

    added = {node.node_id for node in after.nodes} - {node.node_id for node in before.nodes}
    assert "Clause:CY-EX-07" in added
    assert "Document:wiki/claims/CLM-9999-001/coverage.md" in added


def test_wiping_the_index_directory_loses_nothing_the_wiki_holds(
    corpus: Roots, tmp_path: Path
) -> None:
    index_dir = tmp_path / "index"
    rebuild(corpus, index_dir)
    expected = graph_of(index_dir)

    shutil.rmtree(index_dir)
    rebuild(corpus, index_dir)

    assert graph_of(index_dir) == expected
