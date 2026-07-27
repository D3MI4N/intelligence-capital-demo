"""The orientation read, the GraphRAG merge, and the citation rule over both."""

from __future__ import annotations

from pathlib import Path

import pytest

from agents import context as agent_context
from errors import UnknownCase
from mcp_server.results import ChunkHit, GraphEdge, GraphNode, SubgraphResult
from tests.fakes import count_words

CASE = "CLM-9999-001"


def hit(chunk_id: str, score: float, doc: str = "wiki/a.md") -> ChunkHit:
    return {
        "chunk_id": chunk_id,
        "doc": doc,
        "source": "wiki",
        "heading_path": ["Section"],
        "score": score,
        "text": f"text of {chunk_id}",
    }


def node(node_id: str, node_type: str = "Case", depth: int = 0) -> GraphNode:
    return {"id": node_id, "type": node_type, "label": node_id, "attrs": {}, "depth": depth}


def edge(src: str, rel: str, dst: str) -> GraphEdge:
    return {"src": src, "rel": rel, "dst": dst, "source_doc": "wiki/a.md"}


def subgraph(nodes: list[GraphNode], edges: list[GraphEdge]) -> SubgraphResult:
    return {"seeds": ["Case:A"], "depth": 2, "rel_types": None, "nodes": nodes, "edges": edges}


def test_orientation_reads_the_cascade_then_the_index_then_the_briefing(wiki: Path) -> None:
    oriented = agent_context.orient(CASE, wiki, count_words)

    assert [file.role for file in oriented.files] == [
        "rules",
        "rules",
        "rules",
        "index",
        "briefing",
    ]
    assert [file.path for file in oriented.files] == [
        "wiki/AGENTS.md",
        "wiki/claims/AGENTS.md",
        "wiki/claims/CLM-9999-001/AGENTS.md",
        "wiki/claims/CLM-9999-001/index.md",
        "wiki/claims/CLM-9999-001/briefing.md",
    ]
    assert oriented.case_dir == "wiki/claims/CLM-9999-001"
    assert oriented.missing == ()


def test_a_case_path_orients_the_same_case_as_a_case_id(wiki: Path) -> None:
    by_id = agent_context.orient(CASE, wiki, count_words)
    by_path = agent_context.orient(f"wiki/claims/{CASE}", wiki, count_words)

    assert by_path.files == by_id.files


def test_every_file_is_counted_and_the_counts_sum_to_the_total(wiki: Path) -> None:
    oriented = agent_context.orient(CASE, wiki, count_words)

    assert all(file.tokens == count_words(file.text) for file in oriented.files)
    assert oriented.total_tokens == sum(file.tokens for file in oriented.files)
    assert oriented.total_tokens > 0


def test_the_assembled_context_carries_every_file_and_what_it_cost(wiki: Path) -> None:
    oriented = agent_context.orient(CASE, wiki, count_words)

    for file in oriented.files:
        assert file.path in oriented.text
        assert f"{file.tokens} tokens" in oriented.text
        assert file.text.strip().splitlines()[0] in oriented.text


def test_orientation_picks_up_the_case_facts_the_specialists_query_on(wiki: Path) -> None:
    oriented = agent_context.orient(CASE, wiki, count_words)

    assert oriented.case_id == CASE
    assert oriented.risk_class == "cyber-logistics"
    assert oriented.insured == "Testco Logistics BV"


def test_a_case_with_no_briefing_yet_still_orients(wiki: Path) -> None:
    oriented = agent_context.orient("SUB-9999-001", wiki, count_words)

    assert [file.role for file in oriented.files] == ["rules", "index"]
    assert oriented.missing == ("wiki/submissions/SUB-9999-001/briefing.md",)


def test_orientation_refuses_a_case_that_does_not_exist(wiki: Path) -> None:
    with pytest.raises(UnknownCase, match="CLM-0000-000"):
        agent_context.orient("CLM-0000-000", wiki, count_words)


def test_the_merge_ranks_chunks_by_score_then_by_id() -> None:
    block = agent_context.merge_retrieval([hit("b#c001", 0.4), hit("a#c002", 0.9)])

    assert block.index("a#c002") < block.index("b#c001")
    assert "1. [a#c002]" in block


def test_the_merge_breaks_score_ties_on_the_chunk_id() -> None:
    block = agent_context.merge_retrieval([hit("b#c001", 0.5), hit("a#c001", 0.5)])

    assert block.index("a#c001") < block.index("b#c001")


def test_the_merge_is_byte_identical_for_the_same_retrieval() -> None:
    chunks = [hit("b#c001", 0.4), hit("a#c002", 0.9)]
    graph = subgraph([node("Case:B"), node("Case:A")], [edge("Case:A", "related_case", "Case:B")])

    assert agent_context.merge_retrieval(chunks, graph) == agent_context.merge_retrieval(
        list(reversed(chunks)), graph
    )


def test_the_merge_orders_entities_by_type_then_id_and_relations_after_them() -> None:
    graph = subgraph(
        [node("Peril:z", "Peril", 1), node("Case:B"), node("Case:A")],
        [edge("Case:B", "involves_peril", "Peril:z"), edge("Case:A", "related_case", "Case:B")],
    )

    block = agent_context.merge_retrieval([], graph)

    assert block.index("Case:A -") < block.index("Case:B -") < block.index("Peril:z -")
    assert block.index("Entities:") < block.index("Relations:")
    assert "Case:A -related_case-> Case:B" in block


def test_the_merge_says_so_when_half_of_it_is_empty() -> None:
    block = agent_context.merge_retrieval([])

    assert "## Retrieved chunks\nnone" in block
    assert "## Entity subgraph\nnone" in block


def test_what_may_be_cited_is_what_retrieval_returned() -> None:
    graph = subgraph([node("Case:A")], [edge("Case:A", "related_case", "Case:B")])

    assert agent_context.available_ids([hit("a#c001", 0.5)], graph) == {
        "a#c001",
        "Case:A",
        "Case:B",
    }


def test_citations_that_were_never_retrieved_are_dropped() -> None:
    kept = agent_context.keep_known(
        ["a#c001", "Case:INVENTED-000", " a#c001 ", "Case:A"], frozenset({"a#c001", "Case:A"})
    )

    assert kept == ("a#c001", "Case:A")


def test_an_invented_id_in_prose_is_replaced_and_a_real_one_is_kept() -> None:
    text = "Held under Clause:CY-EX-04 [wiki/a.md#c001] but not Case:INVENTED-000."

    scrubbed = agent_context.strip_unverified(text, frozenset({"wiki/a.md#c001"}))

    assert "wiki/a.md#c001" in scrubbed
    assert "Case:INVENTED-000" not in scrubbed
    assert "Clause:CY-EX-04" not in scrubbed
    assert scrubbed.count(agent_context.UNVERIFIED) == 2


def test_the_marker_left_behind_cannot_become_a_wikilink() -> None:
    """An id is usually cited inside [...]. A [marker] there would read as a link."""
    scrubbed = agent_context.strip_unverified("as recorded [Case:INVENTED-000]", frozenset())

    assert "[[" not in scrubbed
    assert agent_context.UNVERIFIED in scrubbed


def test_the_platform_convention_for_marking_inference_is_not_an_entity_id() -> None:
    """AGENTS.md asks for 'Assessment:' prefixes - the strip must leave them alone."""
    text = "Assessment: the exposure is concentrated."

    assert agent_context.strip_unverified(text, frozenset()) == text
    assert agent_context.cited_ids(text) == ()
