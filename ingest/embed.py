"""Build the vector index from parsed chunks.

This module picks the embedding backend, batches the text through it, and
hands chunks plus vectors to the store. Where those end up, and in what, is
the store's business - see stores/stores.py. Retrieval is the store's
business too: nothing reads the index back from here.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from pathlib import Path

from dotenv import load_dotenv

from ingest import layout, parse
from ingest.hash_embedder import hash_embed
from ingest.models import Chunk
from stores import write_vector_index

BATCH_SIZE = 64

# EMBED_BACKEND chooses where vectors come from:
#   llm   the model provider, through agents/llm.py - the default, and what a
#         real rebuild uses. Needs credentials and makes network calls. Which
#         provider that is stays llm.py's business, not this module's.
#   hash  deterministic offline vectors from ingest/hash_embedder.py. No
#         network and no credentials, so the pipeline can be rebuilt and tested
#         anywhere. Retrieval results are meaningless - wiring only.
DEFAULT_BACKEND = "llm"

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
    raise ValueError(f"unknown EMBED_BACKEND '{name}' - use llm or hash")


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

    write_vector_index(chunks, vectors, db_path)
    return dimension


def _embed_all(chunks: Sequence[Chunk], embed_fn: EmbedFn, batch_size: int) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(chunks), batch_size):
        batch = [chunk.text for chunk in chunks[start : start + batch_size]]
        result = embed_fn(batch)
        if len(result) != len(batch):
            raise ValueError("embedding count does not match batch size")
        vectors.extend(result)
    return vectors


def main() -> None:
    chunks = parse.read_chunks()
    dimension = build_vector_index(chunks, select_embedder())
    print(f"embed: vectors={len(chunks)} dimension={dimension} backend={backend_name()}")


if __name__ == "__main__":
    main()
