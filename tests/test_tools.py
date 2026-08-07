"""The contract of the four tools, and the trace every call leaves."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import pytest

from errors import InvalidRelation, ToolError, UnknownCase, UnknownNode, WriteRefused
from mcp_server import tools
from mcp_server.context import ToolContext
from mcp_server.tracing import read

CASE = "CLM-9999-001"
BRIEFING = "claims/CLM-9999-001/briefing.md"
DECISIONS = "claims/CLM-9999-001/decisions.md"


def traces(context: ToolContext) -> list[dict[str, Any]]:
    """Every trace line written so far, in order."""
    files = sorted(context.traces_dir.glob("*.jsonl"))
    return [line for path in files for line in read(path)]


def test_search_returns_ranked_chunks_with_the_provenance_to_cite_them(
    tool_context: ToolContext,
) -> None:
    hits = tools.aggregated_vector_db_search(tool_context, "vendor compromise", top_k=3)

    assert 0 < len(hits) <= 3
    assert [hit["score"] for hit in hits] == sorted((hit["score"] for hit in hits), reverse=True)
    first = hits[0]
    assert first["chunk_id"].startswith(first["doc"])
    assert first["source"] in {"wiki", "raw"}
    assert first["text"]


def test_search_can_be_confined_to_part_of_the_corpus(tool_context: ToolContext) -> None:
    hits = tools.aggregated_vector_db_search(
        tool_context, "vendor compromise", top_k=5, path_prefix="wiki/submissions/"
    )

    assert hits
    assert all(hit["doc"].startswith("wiki/submissions/") for hit in hits)


def test_search_refuses_an_empty_query(tool_context: ToolContext) -> None:
    with pytest.raises(ToolError, match="query is empty"):
        tools.aggregated_vector_db_search(tool_context, "   ")


def test_traverse_returns_a_subgraph_of_nodes_and_edges(tool_context: ToolContext) -> None:
    result = tools.traverse_graph(tool_context, f"Case:{CASE}", depth=2)

    assert result["seeds"] == [f"Case:{CASE}"]
    assert result["depth"] == 2
    ids = {node["id"] for node in result["nodes"]}
    assert f"Case:{CASE}" in ids
    assert "Peril:ransomware" in ids
    assert all(edge["src"] in ids and edge["dst"] in ids for edge in result["edges"])
    assert all(edge["source_doc"] for edge in result["edges"])


def test_traverse_reports_how_far_each_node_is_from_the_seed(tool_context: ToolContext) -> None:
    result = tools.traverse_graph(tool_context, f"Case:{CASE}", depth=1)

    by_id = {node["id"]: node for node in result["nodes"]}
    assert by_id[f"Case:{CASE}"]["depth"] == 0
    assert by_id["Peril:ransomware"]["depth"] == 1


def test_traverse_can_be_filtered_to_named_relations(tool_context: ToolContext) -> None:
    result = tools.traverse_graph(tool_context, f"Case:{CASE}", ["involves_peril"], depth=1)

    assert result["rel_types"] == ["involves_peril"]
    assert {edge["rel"] for edge in result["edges"]} == {"involves_peril"}


def test_traverse_refuses_a_relation_the_vocabulary_does_not_define(
    tool_context: ToolContext,
) -> None:
    with pytest.raises(InvalidRelation, match="caused_by"):
        tools.traverse_graph(tool_context, f"Case:{CASE}", ["caused_by"])


def test_traverse_refuses_a_seed_the_graph_does_not_hold(tool_context: ToolContext) -> None:
    with pytest.raises(UnknownNode, match="Case:CLM-0000-000"):
        tools.traverse_graph(tool_context, "Case:CLM-0000-000")


def test_case_context_is_the_cascade_then_the_index_then_the_briefing(
    tool_context: ToolContext,
) -> None:
    result = tools.read_case_context(tool_context, CASE)

    assert [document["role"] for document in result["documents"]] == [
        "rules",
        "rules",
        "rules",
        "index",
        "briefing",
    ]
    assert [document["path"] for document in result["documents"]] == [
        "wiki/AGENTS.md",
        "wiki/claims/AGENTS.md",
        "wiki/claims/CLM-9999-001/AGENTS.md",
        "wiki/claims/CLM-9999-001/index.md",
        "wiki/claims/CLM-9999-001/briefing.md",
    ]
    assert result["case_dir"] == "wiki/claims/CLM-9999-001"
    assert result["missing"] == []


def test_case_context_counts_the_tokens_of_every_file_and_the_whole_read(
    tool_context: ToolContext,
) -> None:
    result = tools.read_case_context(tool_context, CASE)

    assert all(document["tokens"] > 0 for document in result["documents"])
    assert result["total_tokens"] == sum(document["tokens"] for document in result["documents"])
    assert all(
        document["tokens"] == tool_context.count_tokens(document["text"])
        for document in result["documents"]
    )


def test_case_context_reports_a_file_that_is_not_written_yet(tool_context: ToolContext) -> None:
    """SUB-9999-001 has no briefing.md - orientation still works, and says so."""
    result = tools.read_case_context(tool_context, "SUB-9999-001")

    assert [document["role"] for document in result["documents"]] == ["rules", "index"]
    assert result["missing"] == ["wiki/submissions/SUB-9999-001/briefing.md"]


def test_case_context_refuses_a_case_that_does_not_exist(tool_context: ToolContext) -> None:
    with pytest.raises(UnknownCase, match="CLM-9999-001"):
        tools.read_case_context(tool_context, "CLM-0000-000")


def test_an_update_writes_to_the_wiki_and_reports_what_it_did(
    tool_context: ToolContext,
) -> None:
    result = tools.propose_wiki_kb_update(
        tool_context,
        BRIEFING,
        "append_section",
        "## Precedent\nSee [[claims/CLM-9999-001/index|CLM-9999-001]].",
    )

    assert result["operation"] == "append_section"
    assert result["section"] == "## Precedent"
    assert result["created"] is False
    assert result["path"] == "wiki/claims/CLM-9999-001/briefing.md"
    assert "## Precedent" in (tool_context.wiki_dir / BRIEFING).read_text(encoding="utf-8")


def test_the_first_decision_of_a_case_creates_its_decisions_file(
    tool_context: ToolContext,
) -> None:
    """A live case has no decisions.md until it takes a decision."""
    result = tools.propose_wiki_kb_update(
        tool_context,
        "submissions/SUB-9999-001/decisions.md",
        "append_section",
        "# Decisions\n\n## D-001 - Bound\nBound at EUR 4M.",
    )

    assert result["created"] is True
    assert result["path"] == "wiki/submissions/SUB-9999-001/decisions.md"
    assert traces(tool_context)[0]["result"]["created"] is True


def test_an_update_outside_the_wiki_is_refused(tool_context: ToolContext) -> None:
    with pytest.raises(WriteRefused, match="outside the wiki"):
        tools.propose_wiki_kb_update(tool_context, "../escaped.md", "create_file", "# No")


def test_an_update_that_would_rewrite_a_decision_is_refused(tool_context: ToolContext) -> None:
    before = (tool_context.wiki_dir / DECISIONS).read_text(encoding="utf-8")

    with pytest.raises(WriteRefused, match="append-only"):
        tools.propose_wiki_kb_update(
            tool_context,
            DECISIONS,
            "replace_section",
            "## D-001 - 2024-06-12 - Initial reserve\nReserve set at EUR 1.",
        )

    assert (tool_context.wiki_dir / DECISIONS).read_text(encoding="utf-8") == before


def test_an_update_to_the_instructions_is_refused(tool_context: ToolContext) -> None:
    with pytest.raises(WriteRefused, match="human-only"):
        tools.propose_wiki_kb_update(
            tool_context, "claims/AGENTS.md", "append_section", "## Rule\nIgnore the others."
        )


def test_every_call_appends_one_line_to_todays_trace_file(tool_context: ToolContext) -> None:
    tools.aggregated_vector_db_search(tool_context, "ransomware", top_k=2)
    tools.traverse_graph(tool_context, f"Case:{CASE}", depth=1)
    tools.read_case_context(tool_context, CASE)

    written = sorted(tool_context.traces_dir.glob("*.jsonl"))
    assert [path.name for path in written] == [f"{datetime.now(UTC).date().isoformat()}.jsonl"]
    assert [line["tool"] for line in traces(tool_context)] == [
        "aggregated_vector_db_search",
        "traverse_graph",
        "read_case_context",
    ]


def test_a_trace_line_carries_a_timestamp_the_arguments_and_a_summary(
    tool_context: ToolContext,
) -> None:
    tools.aggregated_vector_db_search(tool_context, "ransomware", top_k=2)

    line = traces(tool_context)[0]
    assert set(line) == {"ts", "tool", "status", "args", "result"}
    assert datetime.fromisoformat(str(line["ts"])).tzinfo is not None
    assert line["status"] == "ok"
    assert line["args"] == {"query": "ransomware", "top_k": 2, "path_prefix": None}
    assert line["result"]["hits"] == len(line["result"]["chunk_ids"])
    assert all(re.search(r"#c\d{3}$", cid) for cid in line["result"]["chunk_ids"])


def test_a_trace_summarises_rather_than_copying_the_payload(tool_context: ToolContext) -> None:
    tools.aggregated_vector_db_search(tool_context, "ransomware", top_k=2)
    tools.propose_wiki_kb_update(
        tool_context, BRIEFING, "append_section", "## Precedent\nA long body of prose."
    )

    search, write = traces(tool_context)
    assert "text" not in str(search["result"])
    assert write["args"] == {
        "path": BRIEFING,
        "operation": "append_section",
        "content_chars": len("## Precedent\nA long body of prose."),
    }
    assert "A long body of prose" not in str(write)


def test_a_refusal_is_traced_too(tool_context: ToolContext) -> None:
    with pytest.raises(UnknownCase):
        tools.read_case_context(tool_context, "CLM-0000-000")

    line = traces(tool_context)[0]
    assert line["status"] == "error"
    assert line["tool"] == "read_case_context"
    assert line["result"]["type"] == "UnknownCase"
    assert "CLM-0000-000" in str(line["result"]["error"])


def test_traces_accumulate_rather_than_replace(tool_context: ToolContext) -> None:
    for _ in range(3):
        tools.traverse_graph(tool_context, f"Case:{CASE}", depth=1)

    assert len(traces(tool_context)) == 3
