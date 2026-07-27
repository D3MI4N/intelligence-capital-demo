"""The exact token counter behind the demo's live counter.

The tokenizer keeps its table in a local cache, filled on first use. If this
machine has neither the cache nor a way to fill it, these tests skip rather
than reach out: the suite stays offline, and nothing else in it depends on
this module - tests/conftest.py counts words instead.
"""

from __future__ import annotations

import pytest

from ingest.tokens import estimate_tokens
from mcp_server import tokens

SAMPLE = """# Briefing - at close

Ransomware through the vendor's remote access channel. Settled at EUR 2.1M
after CY-EX-04 was held not to apply.
"""


@pytest.fixture(autouse=True)
def tokenizer() -> None:
    try:
        tokens.encoder()
    except (OSError, ValueError) as error:  # no cached table and no way to fetch one
        pytest.skip(f"tokenizer table unavailable offline: {error}")


def test_empty_text_costs_nothing() -> None:
    assert tokens.count_tokens("") == 0


def test_the_count_is_the_length_of_the_encoded_text() -> None:
    assert tokens.count_tokens(SAMPLE) == len(tokens.encoder().encode(SAMPLE))


def test_counting_the_same_text_twice_gives_the_same_number() -> None:
    assert tokens.count_tokens(SAMPLE) == tokens.count_tokens(SAMPLE)


def test_more_text_costs_more() -> None:
    assert tokens.count_tokens(SAMPLE * 2) > tokens.count_tokens(SAMPLE)


def test_it_is_the_real_count_and_not_the_chunking_estimate() -> None:
    """ingest/tokens.py is a heuristic for sizing chunks. This is not that."""
    exact = tokens.count_tokens(SAMPLE)

    assert exact != estimate_tokens(SAMPLE)
    assert abs(exact - estimate_tokens(SAMPLE)) < exact
