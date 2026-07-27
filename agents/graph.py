"""The orchestration shell, and the only file in the repo that imports the graph framework.

What is here: a state schema, one node per step, and the edges between them.
What is not here: any decision about the case. Every node is a one-line call
into agents/risk_assessment_orchestrator.py, so the logic a client engineer
reads is plain typed Python and the framework is confined to the wiring it is
good at - fanning the three specialists out in parallel and joining them back.

The fan-out is the reason a graph framework is here at all. The three
specialists are independent: they retrieve different things, they never read
each other's output, and running them one after another only makes the demo
slower. START -> orient -> {three specialists} -> cross_validate -> write_back
-> END, with the specialists' assessments accumulated into one list by the
reducer on the state field.

The context and the completion function are captured when the graph is built
rather than carried in the state: they are wiring, not data, and keeping them
out of the state keeps the state something you can print during the demo.

If the framework's types and mypy disagree, the accommodation stays in this
file. Nothing else in the repo should ever have to know this file exists.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.context import Orientation
from agents.llm import CompleteFn
from agents.risk_assessment_orchestrator import (
    RunResult,
    TokenMeter,
    orient_step,
    specialist_step,
    validate_step,
    write_back_step,
)
from agents.specialists import (
    APPETITE,
    EXPOSURE,
    PRECEDENT,
    Assessment,
    SpecialistFn,
    appetite_checker,
    exposure_analyst,
    precedent_finder,
)
from agents.validate import ValidationReport
from mcp_server.context import ToolContext

ORIENT = "orient"
VALIDATE = "cross_validate"
WRITE_BACK = "write_back"

SPECIALIST_NODES: dict[str, SpecialistFn] = {
    EXPOSURE: exposure_analyst,
    APPETITE: appetite_checker,
    PRECEDENT: precedent_finder,
}


class RunState(TypedDict, total=False):
    """What flows between the nodes.

    assessments carries a reducer because three nodes write it at once: the
    framework merges concurrent updates with it instead of the last one home
    overwriting the other two.
    """

    case_path: str
    orientation: Orientation
    assessments: Annotated[list[Assessment], operator.add]
    report: ValidationReport
    result: RunResult


def build(context: ToolContext, complete: CompleteFn) -> Any:
    """Compile the risk assessment graph over one tool context and one model."""
    writer = TokenMeter(complete, context.count_tokens)
    graph = StateGraph(RunState)

    def orient_node(state: RunState) -> RunState:
        return {"orientation": orient_step(context, state["case_path"])}

    def specialist_node(state: RunState, specialist: SpecialistFn, meter: TokenMeter) -> RunState:
        assessment = specialist_step(context, state["orientation"], meter, specialist)
        return {"assessments": [assessment]}

    def validate_node(state: RunState) -> RunState:
        return {"report": validate_step(context, state["assessments"])}

    def write_back_node(state: RunState) -> RunState:
        return {
            "result": write_back_step(
                context,
                state["orientation"],
                state["assessments"],
                state["report"],
                writer,
            )
        }

    graph.add_node(ORIENT, orient_node)
    for name, specialist in SPECIALIST_NODES.items():
        # One meter per specialist: the three run in the same superstep, and a
        # shared counter would report one specialist's tokens against another.
        graph.add_node(
            name, _bind(specialist_node, specialist, TokenMeter(complete, context.count_tokens))
        )
    graph.add_node(VALIDATE, validate_node)
    graph.add_node(WRITE_BACK, write_back_node)

    graph.add_edge(START, ORIENT)
    for name in SPECIALIST_NODES:
        graph.add_edge(ORIENT, name)
        graph.add_edge(name, VALIDATE)
    graph.add_edge(VALIDATE, WRITE_BACK)
    graph.add_edge(WRITE_BACK, END)

    return graph.compile()


def run(context: ToolContext, complete: CompleteFn, case_path: str) -> RunResult:
    """Run the compiled graph over one case and return what the run produced."""
    final: RunState = build(context, complete).invoke({"case_path": case_path})
    return final["result"]


def _bind(node: Any, specialist: SpecialistFn, meter: TokenMeter) -> Any:
    """One node per specialist, each closed over the function it dispatches."""
    return lambda state: node(state, specialist, meter)
