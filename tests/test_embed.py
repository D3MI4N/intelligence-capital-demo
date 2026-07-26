from pathlib import Path

import pytest

from ingest.embed import build_vector_index, connect, search
from ingest.hash_embedder import DIMENSION, hash_embed
from ingest.models import Chunk
from ingest.parse import parse_corpus

Roots = tuple[tuple[str, Path], ...]


def build(corpus: Roots, tmp_path: Path) -> tuple[list[Chunk], Path]:
    _, chunks = parse_corpus(corpus)
    db_path = tmp_path / "vectors" / "chunks.db"
    build_vector_index(chunks, hash_embed, db_path)
    return chunks, db_path


def test_every_chunk_is_indexed_with_its_provenance(corpus: Roots, tmp_path: Path) -> None:
    chunks, db_path = build(corpus, tmp_path)

    connection = connect(db_path)
    try:
        rows = connection.execute(
            "select chunk_id, doc_id from chunks order by chunk_id"
        ).fetchall()
        dimension = connection.execute("select value from meta where key = 'dimension'").fetchone()
    finally:
        connection.close()

    assert [str(row[0]) for row in rows] == sorted(chunk.chunk_id for chunk in chunks)
    assert all(str(row[0]).startswith(str(row[1])) for row in rows)
    assert int(str(dimension[0])) == DIMENSION


def test_search_returns_the_nearest_chunk_and_its_text(corpus: Roots, tmp_path: Path) -> None:
    chunks, db_path = build(corpus, tmp_path)
    target = chunks[0]

    results = search(hash_embed([target.text])[0], k=3, db_path=db_path)

    assert len(results) == 3
    best, score = results[0]
    assert best.chunk_id == target.chunk_id
    assert best.text == target.text
    assert best.frontmatter == target.frontmatter
    assert best.references == target.references
    assert score == pytest.approx(1.0, abs=1e-5)


def test_results_are_ranked_best_first(corpus: Roots, tmp_path: Path) -> None:
    chunks, db_path = build(corpus, tmp_path)

    results = search(hash_embed([chunks[0].text])[0], k=5, db_path=db_path)
    scores = [score for _, score in results]

    assert scores == sorted(scores, reverse=True)


def test_rebuilding_replaces_the_index_rather_than_appending(corpus: Roots, tmp_path: Path) -> None:
    chunks, db_path = build(corpus, tmp_path)
    build_vector_index(chunks, hash_embed, db_path)

    connection = connect(db_path)
    try:
        count = connection.execute("select count(*) from chunks").fetchone()
    finally:
        connection.close()

    assert int(str(count[0])) == len(chunks)


def test_an_empty_corpus_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        build_vector_index([], hash_embed, tmp_path / "chunks.db")


def test_ragged_embeddings_are_an_error(corpus: Roots, tmp_path: Path) -> None:
    _, chunks = parse_corpus(corpus)

    def ragged(texts: list[str]) -> list[list[float]]:
        return [[0.0] * (index + 1) for index, _ in enumerate(texts)]

    with pytest.raises(ValueError):
        build_vector_index(chunks, ragged, tmp_path / "chunks.db")


def test_a_short_embedding_batch_is_an_error(corpus: Roots, tmp_path: Path) -> None:
    _, chunks = parse_corpus(corpus)

    def short(texts: list[str]) -> list[list[float]]:
        return hash_embed(texts)[:-1]

    with pytest.raises(ValueError):
        build_vector_index(chunks, short, tmp_path / "chunks.db")


def test_batching_does_not_change_the_index(corpus: Roots, tmp_path: Path) -> None:
    _, chunks = parse_corpus(corpus)
    one = tmp_path / "one.db"
    many = tmp_path / "many.db"

    build_vector_index(chunks, hash_embed, one, batch_size=1000)
    build_vector_index(chunks, hash_embed, many, batch_size=2)

    assert _vectors(one) == _vectors(many)


def _vectors(db_path: Path) -> list[tuple[object, ...]]:
    connection = connect(db_path)
    try:
        return connection.execute(
            "select chunk_id, embedding from chunk_vectors order by chunk_id"
        ).fetchall()
    finally:
        connection.close()
