"""Token estimation for chunk sizing.

Deliberately a heuristic and not a provider tokenizer: chunk sizing needs a
stable, offline, dependency-free number so that a rebuild produces identical
chunks on any machine and the test suite never reaches the network. Four
characters per token is the usual approximation for English prose.
"""

from __future__ import annotations

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Approximate token count of text. Empty text is zero tokens."""
    stripped = text.strip()
    if not stripped:
        return 0
    return max(1, -(-len(stripped) // CHARS_PER_TOKEN))
