"""Entity and relation vocabulary for the knowledge graph.

Node types follow wiki/vocabulary/entity-types.md. Identifiers are readable on
purpose: an agent citing "Clause:CY-EX-04" is citing something a human can look
up. Extraction here is structural - frontmatter fields and identifier patterns,
never a model call.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

CASE = "Case"
CLAUSE = "Clause"
DOCUMENT = "Document"
INSURED = "Insured"
LESSON = "Lesson"
PERIL = "Peril"
RISK_CLASS = "RiskClass"
SKILL = "Skill"

CLAUSE_PATTERN = re.compile(r"\bCY-EX-\d{2,}\b")
LESSON_PATTERN = re.compile(r"\bL-\d{3}\b")
SKILL_PATTERN = re.compile(r"\bSK-\d{3}\b")
LOCATOR_PATTERN = re.compile(r"^\s*Locator:\s*(\S+)", re.MULTILINE)
_LABEL_HEADING = re.compile(
    r"^#{1,6}\s*(?P<id>[A-Z]{1,3}-\d{3})\s*-\s*(?P<label>.+?)\s*$", re.MULTILINE
)


@dataclass(frozen=True)
class Node:
    node_id: str
    type: str
    label: str
    attrs: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Edge:
    src: str
    rel: str
    dst: str
    source_doc: str


@dataclass(frozen=True)
class Graph:
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]


def node_id(node_type: str, key: str) -> str:
    """Identifier for a node. Codes stay as written, names are slugged."""
    return f"{node_type}:{key}"


def slug(value: str) -> str:
    """Lowercase, punctuation-free key for names that are not codes."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    return cleaned.strip("-")


def find_clauses(text: str) -> tuple[str, ...]:
    return _distinct(CLAUSE_PATTERN.findall(text))


def find_lessons(text: str) -> tuple[str, ...]:
    return _distinct(LESSON_PATTERN.findall(text))


def find_skills(text: str) -> tuple[str, ...]:
    return _distinct(SKILL_PATTERN.findall(text))


def find_locators(text: str) -> tuple[str, ...]:
    """Paths named on 'Locator:' lines in source notes."""
    return _distinct(match.rstrip(".,;") for match in LOCATOR_PATTERN.findall(text))


def find_labels(text: str) -> dict[str, str]:
    """Headings of the form '## L-001 - title' give identifiers their label."""
    return {match.group("id"): match.group("label") for match in _LABEL_HEADING.finditer(text)}


def _distinct(values: Iterable[str]) -> tuple[str, ...]:
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return tuple(seen)
