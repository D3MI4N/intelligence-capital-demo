"""One run end to end over the demo wiki, with a deterministic model.

The run writes: this is the beat where a draft lands in briefing.md and a
record lands in decisions.md. Everything asserted here is what a client should
be able to check on screen - the citations resolve, the trace accounts for
every step, and nothing was written except through the tool.
"""

from __future__ import annotations

from typing import Any

import pytest

from agents import risk_assessment_orchestrator as orchestrator
from agents.context import UNVERIFIED, cited_ids
from agents.specialists import APPETITE, EXPOSURE, PRECEDENT
from errors import UnknownCase
from mcp_server.tracing import read
from tests.fakes import FakeLLM, Sandbox

CASE = "SUB-2025-007"
CASE_DIR = "wiki/submissions/SUB-2025-007"


@pytest.fixture
def run(sandbox: Sandbox, fake_llm: FakeLLM) -> orchestrator.RunResult:
    return orchestrator.run_risk_assessment(CASE, sandbox.context, fake_llm)


def traces(sandbox: Sandbox) -> list[dict[str, Any]]:
    files = sorted(sandbox.context.traces_dir.glob("*.jsonl"))
    return [line for path in files for line in read(path)]


def test_the_run_orients_dispatches_three_specialists_and_validates(
    run: orchestrator.RunResult,
) -> None:
    assert run.case_id == CASE
    assert run.orientation.risk_class == "cyber-logistics"
    assert [assessment.agent for assessment in run.assessments] == [EXPOSURE, APPETITE, PRECEDENT]
    assert run.report.issues


def test_the_run_asks_the_model_once_per_specialist_and_once_for_the_draft(
    sandbox: Sandbox, fake_llm: FakeLLM
) -> None:
    orchestrator.run_risk_assessment(CASE, sandbox.context, fake_llm)

    assert len(fake_llm.calls) == 4


def test_the_draft_lands_in_the_briefing_with_its_evidence(
    run: orchestrator.RunResult, sandbox: Sandbox
) -> None:
    briefing = sandbox.written(CASE_DIR, "briefing.md")

    assert "# Briefing - intake" in briefing  # the human's text is still there
    assert "## Risk assessment draft" in briefing
    assert run.draft.strip().splitlines()[0] in briefing
    assert "Evidence:" in briefing
    assert "Not a decision" in briefing


def test_a_decision_record_is_appended_for_the_case(sandbox: Sandbox) -> None:
    """The case has taken no decision yet, so this run creates the file by appending."""
    orchestrator.run_risk_assessment(CASE, sandbox.context, FakeLLM())

    decisions = sandbox.written(CASE_DIR, "decisions.md")
    assert decisions.startswith("## D-")
    assert "Risk assessment draft recorded" in decisions
    assert f"{EXPOSURE}:" in decisions
    assert "awaiting a human decision" in decisions


def test_a_second_run_adds_to_the_decision_log_rather_than_replacing_it(
    sandbox: Sandbox,
) -> None:
    orchestrator.run_risk_assessment(CASE, sandbox.context, FakeLLM())
    orchestrator.run_risk_assessment(CASE, sandbox.context, FakeLLM())

    assert sandbox.written(CASE_DIR, "decisions.md").count("Risk assessment draft recorded") == 2


def test_every_id_written_to_the_wiki_exists_in_the_index(
    run: orchestrator.RunResult, sandbox: Sandbox
) -> None:
    written = "\n".join(
        sandbox.written(CASE_DIR, name)
        for name in ("briefing.md", "decisions.md", "open-questions.md")
    )

    ids = cited_ids(written)
    assert ids
    assert set(ids) <= sandbox.ids


def test_the_id_the_model_invented_never_reaches_the_wiki(
    run: orchestrator.RunResult, sandbox: Sandbox
) -> None:
    briefing = sandbox.written(CASE_DIR, "briefing.md")

    assert FakeLLM.INVENTED not in briefing
    assert UNVERIFIED in briefing


def test_unresolved_items_go_to_open_questions(
    run: orchestrator.RunResult, sandbox: Sandbox
) -> None:
    questions = sandbox.written(CASE_DIR, "open-questions.md")

    assert "# Open questions" in questions
    assert questions.count("- ") >= len(run.report.open_questions)
    assert all(question in questions for question in run.report.open_questions)


def test_the_drafter_is_told_to_cite_only_what_the_specialists_gave_it(
    sandbox: Sandbox, fake_llm: FakeLLM
) -> None:
    orchestrator.run_risk_assessment(CASE, sandbox.context, fake_llm)

    _, prompt = fake_llm.calls[-1]
    assert "cite only ids that appear verbatim in the specialist findings below" in prompt
    assert "never an id you completed or adapted" in prompt


def test_exotic_punctuation_is_normalised_before_the_draft_is_written(
    run: orchestrator.RunResult, sandbox: Sandbox
) -> None:
    """The model writes a non-breaking hyphen; the wiki gets a hyphen."""
    briefing = sandbox.written(CASE_DIR, "briefing.md")

    assert "vendor-operated systems - the loss path" in briefing
    assert FakeLLM.EXOTIC not in briefing
    assert "\u2011" not in run.draft


def test_the_normalisation_is_counted_on_the_trace(
    run: orchestrator.RunResult, sandbox: Sandbox
) -> None:
    """A cleanup nobody can see is a cleanup nobody can audit."""
    written = [line for line in traces(sandbox) if line["tool"] == "agent.write_back"]

    assert written[0]["result"]["normalised"] == 2


def test_a_clean_run_raises_no_open_questions_and_writes_no_file_for_them(
    sandbox: Sandbox,
) -> None:
    """An empty section is a heading the underwriter reads for nothing."""
    clean = FakeLLM(severity="medium", position="in-appetite", invents=False)

    result = orchestrator.run_risk_assessment(CASE, sandbox.context, clean)

    assert result.report.ok
    assert result.report.open_questions == ()
    assert not sandbox.path(CASE_DIR, "open-questions.md").exists()
    assert [write["path"] for write in result.writes] == [
        f"{CASE_DIR}/briefing.md",
        f"{CASE_DIR}/decisions.md",
    ]


def test_a_clean_run_does_not_ask_the_drafter_for_open_questions(sandbox: Sandbox) -> None:
    clean = FakeLLM(severity="medium", position="in-appetite", invents=False)

    orchestrator.run_risk_assessment(CASE, sandbox.context, clean)

    _, prompt = clean.calls[-1]
    assert "### Cross-validation" not in prompt
    assert "End with the open questions" not in prompt


def test_a_run_with_open_questions_still_asks_for_them(sandbox: Sandbox, fake_llm: FakeLLM) -> None:
    orchestrator.run_risk_assessment(CASE, sandbox.context, fake_llm)

    _, prompt = fake_llm.calls[-1]
    assert "### Cross-validation" in prompt
    assert "End with the open questions" in prompt


def test_the_run_writes_nothing_the_write_tool_did_not_write(
    run: orchestrator.RunResult, sandbox: Sandbox
) -> None:
    writes = [line for line in traces(sandbox) if line["tool"] == "propose_wiki_kb_update"]
    written = {line["result"]["path"] for line in writes if line["status"] == "ok"}

    assert written == {result["path"] for result in run.writes}
    assert written == {
        f"{CASE_DIR}/briefing.md",
        f"{CASE_DIR}/decisions.md",
        f"{CASE_DIR}/open-questions.md",
    }


def test_the_refusal_on_the_way_to_a_file_that_does_not_exist_is_traced_too(
    run: orchestrator.RunResult, sandbox: Sandbox
) -> None:
    """The case has no open-questions.md, so the append is refused before the create."""
    refused = [line for line in traces(sandbox) if line["status"] == "error"]

    assert [line["args"]["operation"] for line in refused] == ["append_section"]
    assert refused[0]["args"]["path"].endswith("open-questions.md")
    assert refused[0]["result"]["type"] == "WriteRefused"


def test_every_agent_step_leaves_a_trace_line_with_a_timestamp_and_a_cost(
    run: orchestrator.RunResult, sandbox: Sandbox
) -> None:
    steps = [line for line in traces(sandbox) if str(line["tool"]).startswith("agent.")]

    assert [line["tool"] for line in steps] == [
        "agent.orient",
        "agent.specialist",
        "agent.specialist",
        "agent.specialist",
        "agent.cross_validate",
        "agent.write_back",
    ]
    assert all(line["ts"] for line in steps)
    assert all("tokens" in line["result"] for line in steps)
    assert steps[0]["result"]["tokens"] == sum(
        int(value) for value in dict(steps[0]["result"]["tokens_per_file"]).values()
    )
    assert all(
        int(line["result"]["tokens"]) > 0
        for line in steps
        if line["tool"] != "agent.cross_validate"
    )
    assert [line["result"]["model_calls"] for line in steps] == [0, 1, 1, 1, 0, 1]


def test_the_agent_steps_and_the_tool_calls_share_one_stream(
    run: orchestrator.RunResult, sandbox: Sandbox
) -> None:
    tools_used = {line["tool"] for line in traces(sandbox)}

    assert "aggregated_vector_db_search" in tools_used
    assert "traverse_graph" in tools_used
    assert "agent.orient" in tools_used


def test_a_case_that_does_not_exist_is_refused_before_anything_is_written(
    sandbox: Sandbox, fake_llm: FakeLLM
) -> None:
    with pytest.raises(UnknownCase):
        orchestrator.run_risk_assessment("SUB-0000-000", sandbox.context, fake_llm)

    assert fake_llm.calls == []
