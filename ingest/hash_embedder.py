"""Deterministic offline embeddings.

A stand-in for the provider embedder: a hash of the chunk text scaled to
[-1, 1]. The same text gives the same vector on any machine with no network, so
the pipeline can be rebuilt and tested without credentials.

These vectors carry no meaning - two chunks about the same peril are no closer
than two unrelated ones. This backend exercises the wiring, never the retrieval
quality.
"""

from __future__ import annotations

import hashlib

DIMENSION = 16


def hash_embed(texts: list[str]) -> list[list[float]]:
    """One deterministic pseudo-embedding per text, in input order."""
    vectors: list[list[float]] = []
    for text in texts:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vectors.append([(digest[index] - 128) / 128.0 for index in range(DIMENSION)])
    return vectors
