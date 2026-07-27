"""Three specialists, one question each, and no framework anywhere near them.

Each is a plain function of (tool context, orientation, completion function) -
call a tool, render what came back, ask the model once, return an Assessment.
No class to build, no state between calls, no scheduler: what runs them in
parallel is agents/graph.py, and swapping that out changes nothing here.

  exposure_analyst   what drives loss on this class of risk -> search
  appetite_checker   where the class sits against appetite -> graph traversal
  precedent_finder   what comparable cases already taught us -> both, merged

The relation filter the appetite check walks - in_class and applies_to_class -
is the published vocabulary in wiki/vocabulary/entity-types.md. A traversal
naming a relation the wiki does not define is refused by the tool, which is
the point: agents reason in the language the wiki publishes, not their own.

The last step of every specialist is the same, and it is the one that matters:
any cited id that was not in what retrieval returned is dropped. An agent may
cite only what it was given.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from agents.context import (
    Orientation,
    available_ids,
    keep_known,
    merge_retrieval,
    strip_unverified,
)
from agents.llm import CompleteFn
from ingest import entities
from mcp_server import tools
from mcp_server.context import ToolContext
from mcp_server.results import ChunkHit, SubgraphResult

EXPOSURE = "exposure_analyst"
APPETITE = "appetite_checker"
PRECEDENT = "precedent_finder"

# The graded labels a specialist states, and the only values that count. A
# value outside the list is recorded as unstated rather than passed on, so
# cross-validation compares two known vocabularies and never free text.
SEVERITY = "severity"
POSITION = "position"
SEVERITIES = ("low", "medium", "high")
POSITIONS = ("in-appetite", "refer", "decline")
UNSTATED = "unstated"
VALUES: dict[str, tuple[str, ...]] = {SEVERITY: SEVERITIES, POSITION: POSITIONS}

UNPARSED = "output:unparsed"

TOP_K = 5
DEPTH = 2

EXPOSURE_QUERY = "{risk_class} exposure - loss drivers, business interruption, dependencies"
PRECEDENT_QUERY = "{risk_class} precedent - prior claims, coverage outcome, lessons"


@dataclass(frozen=True)
class Finding:
    """One claim and the ids that support it. No ids, no support."""

    claim: str
    citations: tuple[str, ...]


@dataclass(frozen=True)
class Assessment:
    """What one specialist concluded, and everything it may be held to."""

    agent: str
    findings: tuple[Finding, ...]
    citations: tuple[str, ...]  # every id cited across the findings, deduplicated
    flags: tuple[str, ...]  # graded labels: severity:high, position:refer


SpecialistFn = Callable[[ToolContext, Orientation, CompleteFn], Assessment]

ROLE = (
    "You are the {agent} on a specialty insurance underwriting platform. "
    "You work only from the retrieved context below and the operating "
    "instructions of the case. You do not use outside knowledge."
)

FORMAT = (
    "Answer with one JSON object and nothing else:\n"
    '{{"findings": [{{"claim": "one sentence", "citations": ["<id>"]}}], '
    '"{label}": "{options}"}}\n'
    "Every citation is a chunk id or an entity id copied exactly from the "
    "retrieved context. A claim you cannot cite does not go in."
)


def exposure_analyst(
    context: ToolContext, orientation: Orientation, complete: CompleteFn
) -> Assessment:
    """What drives loss on this risk, from the corpus."""
    hits = tools.search_knowledge_base(
        context, EXPOSURE_QUERY.format(risk_class=orientation.risk_class), top_k=TOP_K
    )
    task = (
        f"Assess the exposure on {orientation.insured or 'this insured'}, risk class "
        f"{orientation.risk_class or 'unstated'}. Name the loss drivers the retrieved "
        "context evidences, and grade the overall exposure severity."
    )
    return _run(EXPOSURE, orientation, complete, task, hits, None, SEVERITY)


def appetite_checker(
    context: ToolContext, orientation: Orientation, complete: CompleteFn
) -> Assessment:
    """Where this risk class sits against appetite, from the entity graph."""
    seed = entities.node_id(entities.RISK_CLASS, orientation.risk_class)
    subgraph = tools.traverse_graph(
        context, seed, [entities.IN_CLASS, entities.APPLIES_TO_CLASS], depth=DEPTH
    )
    task = (
        f"State the appetite position for risk class {orientation.risk_class or 'unstated'}. "
        "Use the cases, clauses and documents attached to the class in the subgraph. "
        "Say which exclusions the class already carries."
    )
    return _run(APPETITE, orientation, complete, task, [], subgraph, POSITION)


def precedent_finder(
    context: ToolContext, orientation: Orientation, complete: CompleteFn
) -> Assessment:
    """What comparable cases already taught us, from both indexes merged."""
    hits = tools.search_knowledge_base(
        context, PRECEDENT_QUERY.format(risk_class=orientation.risk_class), top_k=TOP_K
    )
    seed = entities.node_id(entities.RISK_CLASS, orientation.risk_class)
    subgraph = tools.traverse_graph(
        context, seed, [entities.IN_CLASS, entities.HAS_LESSON], depth=DEPTH
    )
    task = (
        f"Find the precedent that bears on {orientation.case_id}. Name the comparable "
        "cases and the lessons already recorded on this class, and say what each one "
        "implies for this submission."
    )
    return _run(PRECEDENT, orientation, complete, task, hits, subgraph, None)


SPECIALISTS: tuple[SpecialistFn, ...] = (exposure_analyst, appetite_checker, precedent_finder)


def parse_response(
    text: str, label: str | None = None
) -> tuple[tuple[Finding, ...], tuple[str, ...]]:
    """Read findings and the graded label out of a model answer.

    An answer that will not parse yields no findings and the unparsed flag,
    rather than an exception: a specialist that returned nothing usable is a
    fact about the run, and cross-validation is where it gets reported.
    """
    payload = _payload(text)
    if payload is None:
        return (), (UNPARSED,)
    findings = tuple(
        Finding(claim=claim, citations=tuple(citations))
        for claim, citations in _findings(payload.get("findings"))
    )
    if label is None:
        return findings, ()
    return findings, (_graded(label, payload.get(label)),)


def _run(
    agent: str,
    orientation: Orientation,
    complete: CompleteFn,
    task: str,
    hits: Sequence[ChunkHit],
    subgraph: SubgraphResult | None,
    label: str | None,
) -> Assessment:
    """The shape every specialist shares: retrieve, ask once, keep what is cited."""
    allowed = available_ids(hits, subgraph)
    system = f"{ROLE.format(agent=agent)}\n\n{orientation.text}"
    prompt = "\n\n".join((task, merge_retrieval(hits, subgraph), _format(label)))
    findings, flags = parse_response(complete(system, prompt), label)
    kept = tuple(
        Finding(
            claim=strip_unverified(finding.claim, allowed),
            citations=keep_known(finding.citations, allowed),
        )
        for finding in findings
    )
    return Assessment(
        agent=agent,
        findings=kept,
        citations=keep_known(
            (citation for finding in kept for citation in finding.citations), allowed
        ),
        flags=flags,
    )


def _format(label: str | None) -> str:
    if label is None:
        return FORMAT.format(label="summary", options="one sentence")
    return FORMAT.format(label=label, options="|".join(VALUES[label]))


def _graded(label: str, value: object) -> str:
    """A graded label, held to the published values."""
    if isinstance(value, str) and value.strip().lower() in VALUES[label]:
        return f"{label}:{value.strip().lower()}"
    return f"{label}:{UNSTATED}"


def _payload(text: str) -> dict[str, object] | None:
    """The JSON object in a model answer, fenced or not."""
    body = text.strip()
    if body.startswith("```"):
        body = body.split("```")[1] if "```" in body[3:] else body[3:]
        body = body.removeprefix("json").strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        loaded = json.loads(body[start : end + 1])
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None


def _findings(value: object) -> list[tuple[str, list[str]]]:
    """Claims and their citations, skipping anything that is not both."""
    if not isinstance(value, list):
        return []
    found: list[tuple[str, list[str]]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        claim = item.get("claim")
        if not isinstance(claim, str) or not claim.strip():
            continue
        raw = item.get("citations")
        citations = [cite for cite in raw if isinstance(cite, str)] if isinstance(raw, list) else []
        found.append((claim.strip(), citations))
    return found
