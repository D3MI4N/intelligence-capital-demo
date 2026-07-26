"""Build the vector index from parsed chunks.

Store choice: SQLite with the sqlite-vec extension. It is an embedded library,
not a service - the whole index is one file under .index/ that can be deleted
and rebuilt. It keeps chunk text, provenance and vectors in the same file, so
a retrieval returns its citation without a second lookup, and at this corpus
size its brute-force KNN is exact, which keeps rebuilds deterministic. The
graph uses the same engine, so the demo carries one embedded dependency.
"""

from __future__ import annotations

import json
import os
import sqlite3
import struct
from collections.abc import Callable, Sequence
from pathlib import Path

import sqlite_vec
from dotenv import load_dotenv

from ingest import layout, parse
from ingest.hash_embedder import hash_embed
from ingest.models import Chunk

BATCH_SIZE = 64

# EMBED_BACKEND chooses where vectors come from:
#   openai  the model provider, through agents/llm.py - the default, and what a
#           real rebuild uses. Needs credentials and makes network calls.
#   hash    deterministic offline vectors from ingest/hash_embedder.py. No
#           network and no credentials, so the pipeline can be rebuilt and
#           tested anywhere. Retrieval results are meaningless - wiring only.
DEFAULT_BACKEND = "openai"

EmbedFn = Callable[[list[str]], list[list[float]]]


def backend_name(backend: str | None = None) -> str:
    """The backend that will be used: the argument, EMBED_BACKEND, or the default."""
    load_dotenv()
    return (backend or os.environ.get("EMBED_BACKEND") or DEFAULT_BACKEND).strip().lower()


def select_embedder(backend: str | None = None) -> EmbedFn:
    """Resolve the embedding backend, from the argument or EMBED_BACKEND."""
    name = backend_name(backend)
    if name == "hash":
        return hash_embed
    if name == DEFAULT_BACKEND:
        from agents.llm import embed

        return embed
    raise ValueError(f"unknown EMBED_BACKEND '{name}' - use openai or hash")


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with the vector extension loaded."""
    connection = sqlite3.connect(db_path)
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)
    return connection


def build_vector_index(
    chunks: Sequence[Chunk],
    embed_fn: EmbedFn,
    db_path: Path = layout.VECTOR_DB_PATH,
    batch_size: int = BATCH_SIZE,
) -> int:
    """Embed chunks and write the index. Returns the vector dimension."""
    if not chunks:
        raise ValueError("no chunks to index - run ingest.parse first")

    vectors = _embed_all(chunks, embed_fn, batch_size)
    dimension = len(vectors[0])
    if any(len(vector) != dimension for vector in vectors):
        raise ValueError("embedding dimensions are not uniform")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    connection = connect(db_path)
    try:
        _create_schema(connection, dimension)
        _insert(connection, chunks, vectors)
        connection.commit()
    finally:
        connection.close()
    return dimension


def search(
    query_vector: Sequence[float],
    k: int = 5,
    db_path: Path = layout.VECTOR_DB_PATH,
) -> list[tuple[Chunk, float]]:
    """Return the k nearest chunks with a cosine similarity score, best first."""
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            select c.chunk_id, c.doc_id, c.source, c.ordinal, c.heading_path,
                   c.text, c.tokens, c.frontmatter, c.refs, v.distance
            from chunk_vectors v
            join chunks c on c.chunk_id = v.chunk_id
            where v.embedding match ? and k = ?
            order by v.distance
            """,
            (pack_vector(query_vector), k),
        ).fetchall()
    finally:
        connection.close()
    return [(_row_to_chunk(row), 1.0 - float(row[9])) for row in rows]


def pack_vector(vector: Sequence[float]) -> bytes:
    """Serialise a vector to the float32 blob the vector table expects."""
    return struct.pack(f"{len(vector)}f", *vector)


def _embed_all(chunks: Sequence[Chunk], embed_fn: EmbedFn, batch_size: int) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(chunks), batch_size):
        batch = [chunk.text for chunk in chunks[start : start + batch_size]]
        result = embed_fn(batch)
        if len(result) != len(batch):
            raise ValueError("embedding count does not match batch size")
        vectors.extend(result)
    return vectors


def _create_schema(connection: sqlite3.Connection, dimension: int) -> None:
    connection.execute(
        """
        create table chunks (
            chunk_id     text primary key,
            doc_id       text not null,
            source       text not null,
            ordinal      integer not null,
            heading_path text not null,
            text         text not null,
            tokens       integer not null,
            frontmatter  text not null,
            refs         text not null
        )
        """
    )
    connection.execute("create index chunks_doc on chunks(doc_id)")
    connection.execute("create table meta (key text primary key, value text not null)")
    connection.execute(
        "create virtual table chunk_vectors using vec0("
        "chunk_id text primary key, "
        f"embedding float[{dimension}] distance_metric=cosine)"
    )


def _insert(
    connection: sqlite3.Connection,
    chunks: Sequence[Chunk],
    vectors: Sequence[Sequence[float]],
) -> None:
    connection.executemany(
        "insert into chunks values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                chunk.chunk_id,
                chunk.doc_id,
                chunk.source,
                chunk.ordinal,
                json.dumps(list(chunk.heading_path)),
                chunk.text,
                chunk.tokens,
                json.dumps(chunk.frontmatter, sort_keys=True),
                json.dumps(list(chunk.references)),
            )
            for chunk in chunks
        ],
    )
    connection.executemany(
        "insert into chunk_vectors(chunk_id, embedding) values (?, ?)",
        [(chunk.chunk_id, pack_vector(vector)) for chunk, vector in zip(chunks, vectors)],
    )
    connection.executemany(
        "insert into meta values (?, ?)",
        [("dimension", str(len(vectors[0]))), ("chunk_count", str(len(chunks)))],
    )


def _row_to_chunk(row: tuple[object, ...]) -> Chunk:
    return Chunk(
        chunk_id=str(row[0]),
        doc_id=str(row[1]),
        source=str(row[2]),
        ordinal=int(str(row[3])),
        heading_path=tuple(json.loads(str(row[4]))),
        text=str(row[5]),
        tokens=int(str(row[6])),
        frontmatter=dict(json.loads(str(row[7]))),
        references=tuple(json.loads(str(row[8]))),
    )


def main() -> None:
    chunks = parse.read_chunks()
    dimension = build_vector_index(chunks, select_embedder())
    print(f"embed: vectors={len(chunks)} dimension={dimension} backend={backend_name()}")


if __name__ == "__main__":
    main()
