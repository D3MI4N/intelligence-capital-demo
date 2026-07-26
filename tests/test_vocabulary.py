"""The graph may only speak the vocabulary the wiki publishes."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ingest import layout
from ingest.entities import RELATIONS, Edge
from ingest.graph import build_graph
from ingest.parse import parse_corpus

Roots = tuple[tuple[str, Path], ...]

_TABLE_ROW = re.compile(r"^\|\s*([a-z_]+)\s*\|")


def documented_relations() -> set[str]:
    """The first column of the edge-type table in the vocabulary file."""
    text = (layout.WIKI_DIR / "vocabulary" / "entity-types.md").read_text(encoding="utf-8")
    heading = "# Edge types"
    assert heading in text, "the vocabulary file has lost its edge-type table"
    rows = text.split(heading, 1)[1].splitlines()
    found = {match.group(1) for line in rows if (match := _TABLE_ROW.match(line))}
    return found - {"relation"}  # the table header


def test_the_constants_match_the_published_table() -> None:
    assert RELATIONS == documented_relations()


def test_a_known_relation_is_accepted() -> None:
    edge = Edge(src="Case:CLM-1", rel="has_lesson", dst="Lesson:L-001", source_doc="wiki/a.md")

    assert edge.rel in RELATIONS


def test_an_unknown_relation_is_rejected() -> None:
    with pytest.raises(ValueError, match="caused_by"):
        Edge(src="Case:CLM-1", rel="caused_by", dst="Peril:ransomware", source_doc="wiki/a.md")


def test_the_error_says_where_to_add_a_new_relation() -> None:
    with pytest.raises(ValueError, match="entity-types.md"):
        Edge(src="a", rel="invented", dst="b", source_doc="wiki/a.md")


def test_a_built_graph_only_uses_known_relations(corpus: Roots) -> None:
    documents, _ = parse_corpus(corpus)

    graph = build_graph(documents)

    assert {edge.rel for edge in graph.edges} <= RELATIONS


def test_the_real_wiki_exercises_most_of_the_vocabulary() -> None:
    documents, _ = parse_corpus()

    used = {edge.rel for edge in build_graph(documents).edges}

    assert used <= RELATIONS
    assert used  # the demo wiki should not build an edgeless graph
