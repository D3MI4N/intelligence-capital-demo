"""The wiring: three specialists in parallel, everything else in a line."""

from __future__ import annotations

from agents import graph
from agents.specialists import APPETITE, EXPOSURE, PRECEDENT
from tests.fakes import FakeLLM, Sandbox

CASE = "SUB-2025-007"
CASE_DIR = "wiki/submissions/SUB-2025-007"


def edges(sandbox: Sandbox, fake_llm: FakeLLM) -> set[tuple[str, str]]:
    drawn = graph.build(sandbox.context, fake_llm).get_graph()
    return {(edge.source, edge.target) for edge in drawn.edges}


def test_the_three_specialists_fan_out_from_orientation_and_join_before_validation(
    sandbox: Sandbox, fake_llm: FakeLLM
) -> None:
    wiring = edges(sandbox, fake_llm)

    for name in (EXPOSURE, APPETITE, PRECEDENT):
        assert (graph.ORIENT, name) in wiring
        assert (name, graph.VALIDATE) in wiring


def test_the_rest_of_the_run_is_a_straight_line(sandbox: Sandbox, fake_llm: FakeLLM) -> None:
    wiring = edges(sandbox, fake_llm)

    assert ("__start__", graph.ORIENT) in wiring
    assert (graph.VALIDATE, graph.WRITE_BACK) in wiring
    assert (graph.WRITE_BACK, "__end__") in wiring


def test_running_the_graph_produces_the_same_run_as_the_orchestrator(
    sandbox: Sandbox, fake_llm: FakeLLM
) -> None:
    result = graph.run(sandbox.context, fake_llm, CASE)

    assert result.case_id == CASE
    assert {assessment.agent for assessment in result.assessments} == {
        EXPOSURE,
        APPETITE,
        PRECEDENT,
    }
    assert len(fake_llm.calls) == 4
    assert "## Risk assessment draft" in sandbox.written(CASE_DIR, "briefing.md")
