"""Entity and relation vocabulary for the knowledge graph.

Node and edge types follow the tables in wiki/vocabulary/entity-types.md, and
this module is where that vocabulary is enforced: an edge with a relation the
wiki does not define is an error, not a new relation. Identifiers are readable
on purpose - an agent citing "Clause:CY-EX-04" is citing something a human can
look up. Extraction is structural - frontmatter fields and identifier patterns,
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

# Edge relations, one per row of the edge-type table in entity-types.md.
BELONGS_TO = "belongs_to"
ABOUT_CASE = "about_case"
INSURED_BY = "insured_by"
MENTIONS_INSURED = "mentions_insured"
IN_CLASS = "in_class"
APPLIES_TO_CLASS = "applies_to_class"
INVOLVES_PERIL = "involves_peril"
LINKED_CLAIM = "linked_claim"
LINKED_SUBMISSION = "linked_submission"
RELATED_CASE = "related_case"
REFERENCES = "references"
DERIVED_FROM = "derived_from"
MENTIONS_CLAUSE = "mentions_clause"
RECORDS_LESSON = "records_lesson"
HAS_LESSON = "has_lesson"
DEFINES_SKILL = "defines_skill"
MENTIONS_SKILL = "mentions_skill"

RELATIONS = frozenset(
    {
        BELONGS_TO,
        ABOUT_CASE,
        INSURED_BY,
        MENTIONS_INSURED,
        IN_CLASS,
        APPLIES_TO_CLASS,
        INVOLVES_PERIL,
        LINKED_CLAIM,
        LINKED_SUBMISSION,
        RELATED_CASE,
        REFERENCES,
        DERIVED_FROM,
        MENTIONS_CLAUSE,
        RECORDS_LESSON,
        HAS_LESSON,
        DEFINES_SKILL,
        MENTIONS_SKILL,
    }
)

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
    """A relation between two nodes, and the document it was derived from.

    rel must come from RELATIONS. Inventing one silently would let the graph
    drift away from the vocabulary the wiki publishes and agents traverse by.
    """

    src: str
    rel: str
    dst: str
    source_doc: str

    def __post_init__(self) -> None:
        if self.rel not in RELATIONS:
            known = " - ".join(sorted(RELATIONS))
            raise ValueError(
                f"unknown relation '{self.rel}' - add it to wiki/vocabulary/"
                f"entity-types.md and to RELATIONS. Known: {known}"
            )


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
