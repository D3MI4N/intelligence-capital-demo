"""Cross-validation of what the specialists came back with. No model involved.

Three specialists reading the same case will sometimes agree for the wrong
reason and sometimes disagree without noticing. This is the pass that says so,
and it is deliberately rule-based: a check that asked a model whether the
model's own answers hold up would be marking its own homework, and it would
not give the same answer twice.

The rules, in the order they are reported:

  uncited-finding   a claim with no surviving citation. Anything the agent
                    could not support, or supported with an id it invented and
                    lost in the strip, ends up here
  no-findings       a specialist that returned nothing usable at all
  contradiction     the exposure grade and the appetite position disagree.
                    High exposure declared in appetite, or low exposure
                    declined, is not a conclusion to publish quietly - the
                    platform rules say record both positions and escalate

Output is deterministic: issues sorted, open questions derived from them in
the same order, every run over the same assessments identical.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from agents.specialists import APPETITE, EXPOSURE, POSITION, SEVERITY, Assessment

UNCITED = "uncited-finding"
NO_FINDINGS = "no-findings"
CONTRADICTION = "contradiction"

# Grade pairs that cannot both be right. Read as (severity, position).
DISAGREEMENTS = (("high", "in-appetite"), ("low", "decline"))


@dataclass(frozen=True)
class Issue:
    """One thing wrong with the assessments, and who it belongs to."""

    kind: str
    agent: str
    detail: str


@dataclass(frozen=True)
class ValidationReport:
    """What survived the checks, and what a human has to look at."""

    issues: tuple[Issue, ...]
    open_questions: tuple[str, ...]
    ok: bool


def cross_validate(assessments: Sequence[Assessment]) -> ValidationReport:
    """Check the assessments against each other and against the citation rule."""
    issues = [*_citation_issues(assessments), *_contradiction_issues(assessments)]
    ordered = tuple(sorted(issues, key=lambda issue: (issue.kind, issue.agent, issue.detail)))
    return ValidationReport(
        issues=ordered,
        open_questions=tuple(f"{issue.detail} - raised by {issue.agent}" for issue in ordered),
        ok=not ordered,
    )


def grade(assessment: Assessment, label: str) -> str:
    """The value of a graded label on an assessment, or "" if it states none."""
    prefix = f"{label}:"
    for flag in assessment.flags:
        if flag.startswith(prefix):
            return flag[len(prefix) :]
    return ""


def _citation_issues(assessments: Sequence[Assessment]) -> list[Issue]:
    issues: list[Issue] = []
    for assessment in assessments:
        if not assessment.findings:
            issues.append(
                Issue(
                    kind=NO_FINDINGS,
                    agent=assessment.agent,
                    detail="returned no usable findings",
                )
            )
            continue
        issues.extend(
            Issue(
                kind=UNCITED,
                agent=assessment.agent,
                detail=f"claim carries no citation the retrieval supports: {finding.claim}",
            )
            for finding in assessment.findings
            if not finding.citations
        )
    return issues


def _contradiction_issues(assessments: Sequence[Assessment]) -> list[Issue]:
    by_agent = {assessment.agent: assessment for assessment in assessments}
    exposure, appetite = by_agent.get(EXPOSURE), by_agent.get(APPETITE)
    if exposure is None or appetite is None:
        return []
    severity, position = grade(exposure, SEVERITY), grade(appetite, POSITION)
    if (severity, position) not in DISAGREEMENTS:
        return []
    return [
        Issue(
            kind=CONTRADICTION,
            agent=f"{EXPOSURE} - {APPETITE}",
            detail=(
                f"exposure graded {severity} but appetite position is {position} - "
                "both positions stand until a human resolves them"
            ),
        )
    ]
