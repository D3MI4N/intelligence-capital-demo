"""Each specialist retrieves, asks once, and keeps only what it can cite."""

from __future__ import annotations

import json

import pytest

from agents import specialists
from agents.context import UNVERIFIED, Orientation, orient
from mcp_server.context import ToolContext
from tests.fakes import FakeLLM, count_words

CASE = "CLM-9999-001"


@pytest.fixture
def oriented(tool_context: ToolContext) -> Orientation:
    return orient(CASE, tool_context.wiki_dir, count_words)


@pytest.mark.parametrize(
    ("specialist", "agent"),
    [
        (specialists.exposure_analyst, specialists.EXPOSURE),
        (specialists.appetite_checker, specialists.APPETITE),
        (specialists.precedent_finder, specialists.PRECEDENT),
    ],
)
def test_a_specialist_asks_the_model_once_and_names_itself(
    tool_context: ToolContext,
    oriented: Orientation,
    fake_llm: FakeLLM,
    specialist: specialists.SpecialistFn,
    agent: str,
) -> None:
    assessment = specialist(tool_context, oriented, fake_llm)

    assert assessment.agent == agent
    assert len(fake_llm.calls) == 1
    assert assessment.findings


def test_a_specialist_is_given_the_case_rules_and_the_retrieved_context(
    tool_context: ToolContext, oriented: Orientation, fake_llm: FakeLLM
) -> None:
    specialists.exposure_analyst(tool_context, oriented, fake_llm)

    system, prompt = fake_llm.calls[0]
    assert "wiki/AGENTS.md" in system
    assert "Cite a source for every claim." in system
    assert "## Retrieved chunks" in prompt


def test_the_exposure_analyst_grades_severity_from_the_published_values(
    tool_context: ToolContext, oriented: Orientation
) -> None:
    assessment = specialists.exposure_analyst(tool_context, oriented, FakeLLM(severity="medium"))

    assert assessment.flags == ("severity:medium",)


def test_the_appetite_checker_walks_the_class_and_states_a_position(
    tool_context: ToolContext, oriented: Orientation
) -> None:
    assessment = specialists.appetite_checker(tool_context, oriented, FakeLLM(position="refer"))

    assert assessment.flags == ("position:refer",)
    assert any(citation.startswith("RiskClass:") for citation in assessment.citations)


def test_a_grade_outside_the_published_values_is_recorded_as_unstated(
    tool_context: ToolContext, oriented: Orientation
) -> None:
    assessment = specialists.exposure_analyst(tool_context, oriented, FakeLLM(severity="colossal"))

    assert assessment.flags == (f"{specialists.SEVERITY}:{specialists.UNSTATED}",)


def test_the_precedent_finder_merges_both_tools_into_one_context_block(
    tool_context: ToolContext, oriented: Orientation, fake_llm: FakeLLM
) -> None:
    assessment = specialists.precedent_finder(tool_context, oriented, fake_llm)

    _, prompt = fake_llm.calls[0]
    assert "## Retrieved chunks" in prompt
    assert "## Entity subgraph" in prompt
    assert prompt.index("## Retrieved chunks") < prompt.index("## Entity subgraph")
    assert assessment.flags == ()


def test_an_id_the_retrieval_never_returned_is_stripped_from_the_citations(
    tool_context: ToolContext, oriented: Orientation, fake_llm: FakeLLM
) -> None:
    assessment = specialists.exposure_analyst(tool_context, oriented, fake_llm)

    assert assessment.citations
    assert FakeLLM.INVENTED not in assessment.citations
    assert all(citation in _retrieved(fake_llm) for citation in assessment.citations)


def test_a_claim_left_with_no_citation_keeps_the_claim_and_loses_the_id(
    tool_context: ToolContext, oriented: Orientation, fake_llm: FakeLLM
) -> None:
    assessment = specialists.exposure_analyst(tool_context, oriented, fake_llm)

    unsupported = [finding for finding in assessment.findings if not finding.citations]
    assert len(unsupported) == 1
    assert FakeLLM.INVENTED not in unsupported[0].claim
    assert UNVERIFIED in unsupported[0].claim


def test_the_assessment_citations_are_the_findings_citations_deduplicated(
    tool_context: ToolContext, oriented: Orientation, fake_llm: FakeLLM
) -> None:
    assessment = specialists.precedent_finder(tool_context, oriented, fake_llm)

    from_findings = [citation for finding in assessment.findings for citation in finding.citations]
    assert set(assessment.citations) == set(from_findings)
    assert len(assessment.citations) == len(set(assessment.citations))


def test_a_fenced_answer_parses(tool_context: ToolContext, oriented: Orientation) -> None:
    fenced = "```json\n" + json.dumps({"findings": [{"claim": "A.", "citations": []}]}) + "\n```"

    findings, flags = specialists.parse_response(fenced)

    assert [finding.claim for finding in findings] == ["A."]
    assert flags == ()


def test_an_answer_that_is_not_json_yields_no_findings_and_says_so() -> None:
    findings, flags = specialists.parse_response("I could not do that.", specialists.SEVERITY)

    assert findings == ()
    assert flags == (specialists.UNPARSED,)


def test_a_finding_without_a_claim_is_not_a_finding() -> None:
    payload = json.dumps(
        {"findings": [{"citations": ["a#c001"]}, {"claim": "  ", "citations": []}, "nonsense"]}
    )

    findings, _ = specialists.parse_response(payload)

    assert findings == ()


def _retrieved(fake: FakeLLM) -> str:
    """The context block the specialist actually handed over."""
    return fake.calls[0][1]
