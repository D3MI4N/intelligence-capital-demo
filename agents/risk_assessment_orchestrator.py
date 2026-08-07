"""The Risk Assessment orchestrator: orient, dispatch, cross-validate, write back.

This is one functional orchestrator, not the Main Orchestrator. In the platform
architecture the Main Orchestrator owns the case end to end - it decides which
functional orchestrator runs, in what order, and when a human is asked. That is
out of scope in this module and in this session; intelligence_capital_demo.py
stands in for it when the run is wired up. What lives here is the single
function "assess the risk on this case", and it is deliberately readable top to
bottom:

    orient          the cascade read, direct, with the token cost on the record
    dispatch        the three specialists, each one tool call and one model call
    cross-validate  rule-based, no model, deterministic
    compose         one model call, the draft a human will read
    normalise       the draft into house style, with the count on the trace
    write back      through propose_wiki_kb_update, never a file write of its own

Two rules the module exists to keep. The orchestrator never touches a wiki file
directly - every write goes through the tool that has the guardrails on it. And
every step leaves a trace line: what it was given, what it produced, what it
cost in tokens, when. A run that cannot be reconstructed afterwards is not an
auditable run.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from agents import llm
from agents.context import Orientation, orient, strip_unverified
from agents.llm import CompleteFn
from agents.specialists import (
    APPETITE,
    EXPOSURE,
    POSITION,
    SEVERITY,
    SPECIALISTS,
    UNSTATED,
    Assessment,
    SpecialistFn,
)
from agents.text import normalise
from agents.validate import ValidationReport, cross_validate, grade
from errors import WriteRefused
from ingest import entities, layout
from mcp_server import tools, tracing, writes
from mcp_server.context import ToolContext, as_agent, default_context
from mcp_server.results import WriteResult
from mcp_server.tokens import TokenCounter

BRIEFING = "briefing.md"
DECISIONS = "decisions.md"
OPEN_QUESTIONS = "open-questions.md"

# The title a case file opens with, for the run that has to create one.
HEADINGS = {
    BRIEFING: "# Briefing",
    DECISIONS: "# Decisions",
    OPEN_QUESTIONS: "# Open questions",
}

COMPOSER = "risk_assessment_orchestrator"

DRAFTER = (
    "You are the drafting agent of a specialty insurance underwriting platform. "
    "You write the assessment a human underwriter reads first. You work only "
    "from the specialist findings below and the operating instructions of the "
    "case, and you cite the id given with every claim you carry over."
)

DRAFT_TASK = (
    "Draft the risk assessment for {case_id}. Three to six short paragraphs of "
    "markdown, no preamble, and no heading except the alert line described "
    "below. Carry the citation ids through in "
    "square brackets after the claim they support, and cite only ids that appear "
    "verbatim in the specialist findings below - nothing else, and never an id "
    "you completed or adapted. Prefix anything you concluded rather than read "
    "with 'Assessment:'."
)

# Always asked for, and answered from the findings or not at all. Whether the
# draft opens with an alert is the composer's reading of what it was handed -
# a heading written in by the caller, or matched out of the findings by a rule
# here, would be the demo announcing a conflict it already knew about. The
# shape is specified and the subject deliberately is not.
ALERT_TASK = (
    " If the findings conflict with each other or with the case record - a "
    "clause applied in one source and absent from another, a grading that "
    "cannot stand beside the position stated next to it, a precedent that "
    "contradicts the current reading - open the draft with a single "
    "third-level heading line naming that conflict and nothing above it, in "
    "the form '### <subject> Conflict Alert: <what is in dispute> in <where it "
    "applies>'. One line, and the sharpest conflict only. If the findings hold "
    "together, write no heading at all."
)

# Added only when there are open questions. Asking for a section that has no
# content invites the model to write "Open questions: none", which is a line
# the underwriter has to read before finding out it says nothing.
OPEN_QUESTIONS_TASK = " End with the open questions as they stand - do not resolve them."


@dataclass(frozen=True)
class RunResult:
    """Everything one assessment run produced, for the caller and for the demo."""

    case_id: str
    orientation: Orientation
    assessments: tuple[Assessment, ...]
    report: ValidationReport
    draft: str
    writes: tuple[WriteResult, ...]


def run_risk_assessment(
    case_path: str,
    context: ToolContext | None = None,
    complete: CompleteFn | None = None,
    stamp: str | None = None,
) -> RunResult:
    """Assess the risk on a case and write the draft back to the wiki."""
    wiring = context or default_context()
    meter = TokenMeter(complete or llm.complete, wiring.count_tokens)
    orientation = orient_step(wiring, case_path)
    assessments = tuple(
        specialist_step(wiring, orientation, meter, specialist) for specialist in SPECIALISTS
    )
    report = validate_step(wiring, assessments)
    return write_back_step(wiring, orientation, assessments, report, meter, stamp)


def orient_step(context: ToolContext, case_path: str) -> Orientation:
    """Beat one: read the rules, the index and the briefing, and say what it cost."""
    orientation = orient(case_path, context.wiki_dir, context.count_tokens)
    trace(
        context,
        "orient",
        {"case_path": case_path},
        {
            "case_id": orientation.case_id,
            "files": [file.path for file in orientation.files],
            "tokens_per_file": {file.path: file.tokens for file in orientation.files},
            "missing": list(orientation.missing),
            "model_calls": 0,
            "tokens": orientation.total_tokens,
        },
    )
    return orientation


def specialist_step(
    context: ToolContext,
    orientation: Orientation,
    meter: TokenMeter,
    specialist: SpecialistFn,
) -> Assessment:
    """Beat two, once per specialist. The tool calls trace themselves as well."""
    assessment = specialist(context, orientation, meter)
    spend = meter.take()
    trace(
        context,
        "specialist",
        {"agent": assessment.agent, "case_id": orientation.case_id},
        {
            "findings": len(assessment.findings),
            "citations": list(assessment.citations),
            "flags": list(assessment.flags),
            "model_calls": spend.calls,
            "orientation_tokens": spend.system_tokens,
            "context_tokens": spend.prompt_tokens,
            "answer_tokens": spend.answer_tokens,
            "tokens": spend.tokens,
        },
    )
    return assessment


def validate_step(context: ToolContext, assessments: Sequence[Assessment]) -> ValidationReport:
    """The rule-based pass. No model call, so no tokens to report."""
    report = cross_validate(assessments)
    trace(
        context,
        "cross_validate",
        {"agents": [assessment.agent for assessment in assessments]},
        {
            "ok": report.ok,
            "issues": [f"{issue.kind} - {issue.agent}" for issue in report.issues],
            "open_questions": len(report.open_questions),
            "model_calls": 0,
            "tokens": 0,
        },
    )
    return report


def write_back_step(
    context: ToolContext,
    orientation: Orientation,
    assessments: Sequence[Assessment],
    report: ValidationReport,
    meter: TokenMeter,
    stamp: str | None = None,
) -> RunResult:
    """Beat three: compose the draft once, then write it through the tool.

    stamp dates the records this run writes. It defaults to today and is passed
    in only by a replayed run, which writes the date it was recorded on - the
    same reason it answers from recorded completions rather than new ones.
    """
    allowed = frozenset(citation for assessment in assessments for citation in assessment.citations)
    system = f"{DRAFTER}\n\n{orientation.text}"
    task = DRAFT_TASK.format(case_id=orientation.case_id) + ALERT_TASK
    if report.open_questions:
        task += OPEN_QUESTIONS_TASK
    prompt = "\n\n".join((task, render(assessments, report)))
    composed = normalise(meter(system, prompt))
    draft = strip_unverified(composed.text, allowed)
    spend = meter.take()

    dated = stamp or datetime.now(UTC).date().isoformat()
    written = [
        propose(context, orientation, BRIEFING, briefing_section(draft, allowed, dated)),
        propose(
            context,
            orientation,
            DECISIONS,
            decisions_section(assessments, report, dated),
        ),
    ]
    if report.open_questions:
        written.append(
            propose(context, orientation, OPEN_QUESTIONS, open_questions_section(report, dated))
        )
    trace(
        context,
        "write_back",
        {"case_id": orientation.case_id, "citations": sorted(allowed)},
        {
            "paths": [result["path"] for result in written],
            "created": [result["path"] for result in written if result["created"]],
            "normalised": composed.replacements,
            "model_calls": spend.calls,
            "tokens": spend.tokens,
        },
    )
    return RunResult(
        case_id=orientation.case_id,
        orientation=orientation,
        assessments=tuple(assessments),
        report=report,
        draft=draft,
        writes=tuple(written),
    )


@dataclass(frozen=True)
class Spend:
    """What one step cost, split the way the demo has to show it.

    The three parts are three different things on screen: the system prompt is
    the orientation the agent was handed, the prompt is the retrieval merged
    into one context block plus its task, and the answer is what came back.
    """

    system_tokens: int
    prompt_tokens: int
    answer_tokens: int
    calls: int

    @property
    def tokens(self) -> int:
        return self.system_tokens + self.prompt_tokens + self.answer_tokens


class TokenMeter:
    """A completion function with a counter around it.

    The specialists take a completion function and know nothing else about it,
    which is what keeps them pure - so measuring what a step cost belongs on
    this side of the call, not in their return type.
    """

    def __init__(self, complete: CompleteFn, count: TokenCounter) -> None:
        self._complete = complete
        self._count = count
        self._spend = Spend(0, 0, 0, 0)

    def __call__(self, system: str, prompt: str) -> str:
        answer = self._complete(system, prompt)
        self._spend = Spend(
            system_tokens=self._spend.system_tokens + self._count(system),
            prompt_tokens=self._spend.prompt_tokens + self._count(prompt),
            answer_tokens=self._spend.answer_tokens + self._count(answer),
            calls=self._spend.calls + 1,
        )
        return answer

    def take(self) -> Spend:
        """What has been spent since the last take(), then reset."""
        spend = self._spend
        self._spend = Spend(0, 0, 0, 0)
        return spend


def render(assessments: Sequence[Assessment], report: ValidationReport) -> str:
    """The specialist findings and the validation result, as the drafter sees them.

    A clean cross-validation contributes no section at all. An empty heading is
    an invitation to fill it, and what comes back is a paragraph explaining that
    there is nothing to report.
    """
    blocks = []
    for assessment in assessments:
        lines = [f"### {assessment.agent} ({' - '.join(assessment.flags) or 'no flags'})"]
        lines.extend(
            f"- {finding.claim} [{' - '.join(finding.citations) or 'uncited'}]"
            for finding in assessment.findings
        )
        if not assessment.findings:
            lines.append("- nothing usable returned")
        blocks.append("\n".join(lines))
    if report.open_questions:
        questions = "\n".join(f"- {question}" for question in report.open_questions)
        blocks.append(f"### Cross-validation\n{questions}")
    return "\n\n".join(("## Specialist findings", *blocks))


def briefing_section(draft: str, allowed: frozenset[str], stamp: str) -> str:
    """The draft as it goes into briefing.md, with what it rests on underneath."""
    citations = " - ".join(evidence(citation) for citation in sorted(allowed)) or "none"
    return (
        f"## Risk assessment draft - {stamp}\n\n"
        f"{draft.strip()}\n\n"
        f"Evidence: {citations}\n"
        f"Drafted by the {COMPOSER}. Not a decision - a human confirms or rejects it."
    )


def evidence(citation: str) -> str:
    """One citation on the Evidence line: a link when it names a file.

    The link text is the id exactly as it was cited, so the footer still reads
    as provenance and a grep for a chunk id still finds it. The target is the
    file that id points at - vault-relative, and without the chunk anchor,
    because the anchor addresses a chunk of the index and no heading a reader
    could land on. Obsidian opens it; so does an editor with the repo open.

    This changes how the footer reads and nothing else. A markdown link is not
    a wikilink: ingest/wikilinks.py matches [[...]] and only that, so no edge
    is derived from any of this and the census is the same either side of the
    change. Entity ids that name no file - a case, a clause, a lesson, a risk
    class - stay plain text, because there is nothing to open.
    """
    target = _document_path(citation)
    return f"[{citation}]({target})" if target else citation


def _document_path(citation: str) -> str:
    """The file a citation points at, vault-relative, or "" if it names none."""
    path = citation.removeprefix(f"{entities.DOCUMENT}:").split("#", 1)[0]
    if not path.endswith(".md"):
        return ""
    return path.removeprefix(f"{layout.WIKI_DIR.name}/")


def decisions_section(
    assessments: Sequence[Assessment], report: ValidationReport, stamp: str
) -> str:
    """One append-only record of what the run concluded and on what evidence.

    The record is dated rather than numbered. Numbering it D-004 would mean
    counting the records already in the file, and the orchestrator cannot read
    the file - the write tool is the only door and it does not open outwards.
    The human who confirms the draft numbers it.
    """
    by_agent = {assessment.agent: assessment for assessment in assessments}
    exposure = by_agent.get(EXPOSURE)
    appetite = by_agent.get(APPETITE)
    severity = grade(exposure, SEVERITY) if exposure else UNSTATED
    position = grade(appetite, POSITION) if appetite else UNSTATED
    checked = "clean" if report.ok else f"{len(report.issues)} issue(s)"
    lines = [
        f"## D-{stamp} - Risk assessment draft recorded",
        "",
        f"Assessment: exposure graded {severity}, appetite position {position}.",
        "",
    ]
    lines.extend(
        (
            f"- {assessment.agent}: {len(assessment.findings)} finding(s), evidence "
            f"{' - '.join(assessment.citations) or 'none'}"
        )
        for assessment in assessments
    )
    lines.extend(
        (
            "",
            f"Cross-validation: {checked}, {len(report.open_questions)} open question(s).",
            f"Decided by: {COMPOSER} (draft) - awaiting a human decision.",
        )
    )
    return "\n".join(lines)


def open_questions_section(report: ValidationReport, stamp: str) -> str:
    """What the run could not settle, in the file a human works from."""
    questions = "\n".join(f"- {question}" for question in report.open_questions)
    return f"## Raised by the risk assessment run - {stamp}\n\n{questions}"


def propose(context: ToolContext, orientation: Orientation, name: str, content: str) -> WriteResult:
    """Append a section to a case file, creating the file if the case has none yet.

    A case takes its first decision before it has a decisions.md, and raises
    its first open question before it has an open-questions.md. Append is the
    intent either way; create_file is the fallback the tool leaves open when
    there is nothing to append to, and a file created that way opens with the
    frontmatter and title the rest of the wiki carries.

    decisions.md never takes that fallback: the write tool creates an
    append-only file from its first append, precisely so the first record of a
    case has somewhere to go. That file therefore opens with the record itself,
    which is the guarantee working as intended - the log only ever grows.
    """
    path = f"{orientation.case_dir}/{name}"
    caller = as_agent(context, COMPOSER)
    try:
        return tools.propose_wiki_kb_update(caller, path, writes.APPEND_SECTION, content)
    except WriteRefused:
        header = f"---\ncase_id: {orientation.case_id}\n---\n\n{HEADINGS[name]}\n\n"
        return tools.propose_wiki_kb_update(caller, path, writes.CREATE_FILE, f"{header}{content}")


def trace(
    context: ToolContext, step: str, args: Mapping[str, object], result: Mapping[str, object]
) -> None:
    """One line per agent step, in the same stream as the tool calls."""
    tracing.append(f"agent.{step}", args, result, tracing.OK, context.traces_dir)
