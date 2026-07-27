"""Exact token counts for text an agent is about to read.

ingest/tokens.py is a different job: it estimates tokens to size chunks, and
it is a four-characters-per-token heuristic on purpose, so a rebuild produces
identical chunks on any machine with no dependency to install. This module
answers the other question - how much context did that read actually cost -
and the demo puts the number on screen, so an estimate will not do. It runs
the text through a real byte-pair tokenizer.

The encoding name is the one vendor-specific detail in the module, and the
reason the module exists rather than the counting being inlined: swapping
tokenizers is a one-line change here and nothing else moves.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

import tiktoken

ENCODING = "cl100k_base"

TokenCounter = Callable[[str], int]


@lru_cache(maxsize=1)
def encoder() -> tiktoken.Encoding:
    """The tokenizer, built once. The first call may fetch and cache its table."""
    return tiktoken.get_encoding(ENCODING)


def count_tokens(text: str) -> int:
    """Number of tokens in text."""
    return len(encoder().encode(text))
