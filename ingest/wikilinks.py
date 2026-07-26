"""Obsidian wikilink parsing: [[vault/root/path|label]].

The label is text and goes to the vector index, the path is a reference and
goes to the knowledge graph. Both halves are extracted here so parse.py and
graph.py agree on what a link is.
"""

from __future__ import annotations

import re

from ingest.models import WikiLink

# [[target]] | [[target|label]] | [[target#anchor|label]]
_PATTERN = re.compile(r"\[\[([^\[\]|#]+?)(?:#([^\[\]|]*))?(?:\|([^\[\]]*))?\]\]")


def find_wikilinks(text: str) -> tuple[WikiLink, ...]:
    """Every wikilink in text, in document order, duplicates kept."""
    links: list[WikiLink] = []
    for match in _PATTERN.finditer(text):
        target = _normalise_target(match.group(1))
        if not target:
            continue
        label = (match.group(3) or "").strip() or target
        links.append(WikiLink(target=target, label=label))
    return tuple(links)


def render_labels(text: str) -> str:
    """Replace every wikilink with its label, leaving readable prose behind."""
    return _PATTERN.sub(_label_of, text)


def targets(text: str) -> tuple[str, ...]:
    """Distinct link targets in text, first-seen order."""
    seen: dict[str, None] = {}
    for link in find_wikilinks(text):
        seen.setdefault(link.target, None)
    return tuple(seen)


def _label_of(match: re.Match[str]) -> str:
    label = (match.group(3) or "").strip()
    if label:
        return label
    target = _normalise_target(match.group(1))
    return target.rsplit("/", 1)[-1] if target else match.group(0)


def _normalise_target(raw: str) -> str:
    target = raw.strip().strip("/")
    target = target.removeprefix("./")
    return target
