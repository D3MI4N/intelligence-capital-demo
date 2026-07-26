"""YAML frontmatter splitting.

Frontmatter is the structured half of the wiki: it carries case_id, insured,
class, perils and links, and the graph is built from it. Values are normalised
to JSON-safe types so a parsed document survives a round trip through disk.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, cast

import yaml

from ingest.models import Frontmatter

DELIMITER = "---"


def split_frontmatter(text: str) -> tuple[Frontmatter, str]:
    """Return (frontmatter mapping, body). No frontmatter -> ({}, text)."""
    if not text.startswith(DELIMITER):
        return {}, text

    lines = text.splitlines(keepends=True)
    if lines[0].strip() != DELIMITER:
        return {}, text

    for position, line in enumerate(lines[1:], start=1):
        if line.strip() == DELIMITER:
            block = "".join(lines[1:position])
            body = "".join(lines[position + 1 :])
            return _parse_block(block), body.lstrip("\n")

    # Unterminated frontmatter: treat the whole file as body rather than guess.
    return {}, text


def _parse_block(block: str) -> Frontmatter:
    try:
        loaded = yaml.safe_load(block)
    except yaml.YAMLError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    return cast(Frontmatter, _normalise(loaded))


def _normalise(value: Any) -> Any:
    """Convert YAML scalars into JSON-safe values, dates included."""
    if isinstance(value, dict):
        return {str(key): _normalise(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalise(item) for item in value]
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
