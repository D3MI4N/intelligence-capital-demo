"""Store protocols for the derived indexes, and the implementations behind them.

The wiki markdown is the primary store. The vector index and the knowledge
graph are derived from it, disposable, and reached only through the two
protocols declared here: VectorStore and GraphStore. Both layers above -
the ingest pipeline that writes the indexes and the MCP tools that read them -
are written against the protocols, so moving the graph onto a native graph
database means adding one implementation and running the existing tests
against it. Nothing outside this package knows, or can find out, which engine
is in use.

The engine the demo ships with is SQLite: one file per index under .index/,
the vector extension loaded for nearest-neighbour search, nodes and edges as
two ordinary tables. It is embedded rather than a service, so an index is
deleted and rebuilt by one command, and at this corpus size its brute-force
KNN is exact, which keeps rebuilds deterministic. The chunk text and its
provenance live beside the vector, so a retrieval carries its own citation.

This is the only module in the repo that opens those files or imports the
database driver, which is why the ingest writers call in here rather than
writing SQL of their own. tests/test_layering.py enforces that.
"""

from __future__ import annotations

import json
import sqlite3
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import sqlite_vec

from errors import IndexMissing
from ingest import layout
from ingest.entities import Edge, Graph, Node
from ingest.models import Chunk
from stores.traversal import GraphReader, Subgraph, traverse

# A retrieved chunk and its similarity score, 1.0 being identical.
Hit = tuple[Chunk, float]


class VectorStore(Protocol):
    """Nearest-neighbour retrieval over the chunks of the wiki."""

    def search(
        self, query_vector: Sequence[float], k: int = 5, path_prefix: str | None = None
    ) -> list[Hit]: ...


class GraphStore(GraphReader, Protocol):
    """Node lookup, one-hop neighbours, and the bounded walk built on them."""

    def traverse(
        self, seed_ids: Sequence[str], rel_types: Sequence[str] | None = None, depth: int = 2
    ) -> Subgraph: ...


@dataclass(frozen=True)
class SqliteVectorStore:
    """VectorStore over the embedded vector index."""

    db_path: Path = layout.VECTOR_DB_PATH

    def search(
        self, query_vector: Sequence[float], k: int = 5, path_prefix: str | None = None
    ) -> list[Hit]:
        """The k nearest chunks with a cosine similarity score, best first.

        A path prefix filters on doc_id. The filter is applied after the
        nearest-neighbour scan rather than inside it, so the scan is widened to
        the whole index first and k still comes back full whenever the corpus
        can fill it. That is affordable because the index is one small file.
        """
        if k <= 0:
            raise ValueError(f"k must be positive, got {k}")
        connection = _read_connection(self.db_path)
        try:
            wanted = k if path_prefix is None else max(k, _chunk_count(connection))
            rows = connection.execute(
                """
                select c.chunk_id, c.doc_id, c.source, c.ordinal, c.heading_path,
                       c.text, c.tokens, c.frontmatter, c.refs, v.distance
                from chunk_vectors v
                join chunks c on c.chunk_id = v.chunk_id
                where v.embedding match ? and k = ?
                order by v.distance, c.chunk_id
                """,
                (pack_vector(query_vector), wanted),
            ).fetchall()
        finally:
            connection.close()

        hits = [(_row_to_chunk(row), 1.0 - float(row[9])) for row in rows]
        if path_prefix is not None:
            hits = [hit for hit in hits if hit[0].doc_id.startswith(path_prefix)]
        return hits[:k]


@dataclass(frozen=True)
class SqliteGraphStore:
    """GraphStore over the embedded knowledge graph."""

    db_path: Path = layout.GRAPH_DB_PATH

    def get_node(self, node_id: str) -> Node | None:
        connection = _read_connection(self.db_path)
        try:
            row = connection.execute(
                "select node_id, type, label, attrs from nodes where node_id = ?", (node_id,)
            ).fetchone()
        finally:
            connection.close()
        return None if row is None else _row_to_node(row)

    def neighbours(
        self, node_ids: Sequence[str], rel_types: Sequence[str] | None = None
    ) -> tuple[Edge, ...]:
        """Every edge with either end in node_ids, in a stable order."""
        wanted = tuple(dict.fromkeys(node_ids))
        if not wanted:
            return ()
        ends = ", ".join("?" * len(wanted))
        clause = f"(src in ({ends}) or dst in ({ends}))"
        parameters: list[str] = [*wanted, *wanted]
        if rel_types is not None:
            relations = tuple(dict.fromkeys(rel_types))
            clause += f" and rel in ({', '.join('?' * len(relations))})"
            parameters.extend(relations)
        connection = _read_connection(self.db_path)
        try:
            rows = connection.execute(
                f"select src, rel, dst, source_doc from edges where {clause} "
                "order by src, rel, dst, source_doc",
                parameters,
            ).fetchall()
        finally:
            connection.close()
        return tuple(_row_to_edge(row) for row in rows)

    def traverse(
        self, seed_ids: Sequence[str], rel_types: Sequence[str] | None = None, depth: int = 2
    ) -> Subgraph:
        return traverse(self, seed_ids, rel_types, depth)


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a connection with the vector extension loaded."""
    connection = sqlite3.connect(db_path)
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)
    return connection


def write_vector_index(
    chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]], db_path: Path
) -> None:
    """Persist chunks and their vectors, replacing whatever was there."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    connection = connect(db_path)
    try:
        _create_vector_schema(connection, len(vectors[0]))
        _insert_vectors(connection, chunks, vectors)
        connection.commit()
    finally:
        connection.close()


def write_graph(graph: Graph, db_path: Path = layout.GRAPH_DB_PATH) -> None:
    """Persist the graph, replacing whatever was there."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    connection = sqlite3.connect(db_path)
    try:
        _create_graph_schema(connection)
        connection.executemany(
            "insert into nodes values (?, ?, ?, ?)",
            [
                (node.node_id, node.type, node.label, json.dumps(node.attrs, sort_keys=True))
                for node in graph.nodes
            ],
        )
        connection.executemany(
            "insert into edges values (?, ?, ?, ?)",
            [(edge.src, edge.rel, edge.dst, edge.source_doc) for edge in graph.edges],
        )
        connection.commit()
    finally:
        connection.close()


def read_graph(db_path: Path = layout.GRAPH_DB_PATH) -> Graph:
    """Read the whole graph back, in the order it was written."""
    connection = _read_connection(db_path)
    try:
        nodes = tuple(
            _row_to_node(row)
            for row in connection.execute(
                "select node_id, type, label, attrs from nodes order by type, node_id"
            )
        )
        edges = tuple(
            _row_to_edge(row)
            for row in connection.execute(
                "select src, rel, dst, source_doc from edges order by src, rel, dst, source_doc"
            )
        )
    finally:
        connection.close()
    return Graph(nodes=nodes, edges=edges)


def pack_vector(vector: Sequence[float]) -> bytes:
    """Serialise a vector to the float32 blob the vector table expects."""
    return struct.pack(f"{len(vector)}f", *vector)


def _read_connection(db_path: Path) -> sqlite3.Connection:
    """Open an index that must already exist - an absent file is an error.

    Without this the driver would create an empty database and every query
    would fail on a missing table instead of saying the index is not built.
    """
    if not db_path.is_file():
        raise IndexMissing(f"no index at {db_path} - run ingest/rebuild.sh")
    return connect(db_path)


def _chunk_count(connection: sqlite3.Connection) -> int:
    row = connection.execute("select value from meta where key = 'chunk_count'").fetchone()
    return 0 if row is None else int(str(row[0]))


def _create_vector_schema(connection: sqlite3.Connection, dimension: int) -> None:
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


def _create_graph_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        create table nodes (
            node_id text primary key,
            type    text not null,
            label   text not null,
            attrs   text not null
        )
        """
    )
    connection.execute(
        """
        create table edges (
            src        text not null,
            rel        text not null,
            dst        text not null,
            source_doc text not null,
            primary key (src, rel, dst, source_doc)
        )
        """
    )
    connection.execute("create index nodes_type on nodes(type)")
    connection.execute("create index edges_src on edges(src)")
    connection.execute("create index edges_dst on edges(dst)")


def _insert_vectors(
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


def _row_to_node(row: tuple[object, ...]) -> Node:
    return Node(
        node_id=str(row[0]), type=str(row[1]), label=str(row[2]), attrs=json.loads(str(row[3]))
    )


def _row_to_edge(row: tuple[object, ...]) -> Edge:
    return Edge(src=str(row[0]), rel=str(row[1]), dst=str(row[2]), source_doc=str(row[3]))
