"""The rules cross-validation applies, and the same answer every time."""

from __future__ import annotations

from agents import validate
from agents.specialists import APPETITE, EXPOSURE, PRECEDENT, Assessment, Finding


def assessment(
    agent: str, claims: list[tuple[str, list[str]]], flags: tuple[str, ...] = ()
) -> Assessment:
    findings = tuple(Finding(claim=claim, citations=tuple(cites)) for claim, cites in claims)
    return Assessment(
        agent=agent,
        findings=findings,
        citations=tuple({cite for _, cites in claims for cite in cites}),
        flags=flags,
    )


def exposure(severity: str, claims: list[tuple[str, list[str]]] | None = None) -> Assessment:
    return assessment(EXPOSURE, claims or [("Cited.", ["a#c001"])], (f"severity:{severity}",))


def appetite(position: str, claims: list[tuple[str, list[str]]] | None = None) -> Assessment:
    return assessment(APPETITE, claims or [("Cited.", ["Case:A"])], (f"position:{position}",))


def test_a_clean_set_of_assessments_passes() -> None:
    report = validate.cross_validate([exposure("medium"), appetite("refer")])

    assert report.ok
    assert report.issues == ()
    assert report.open_questions == ()


def test_a_finding_with_no_citation_is_reported_against_its_agent() -> None:
    report = validate.cross_validate(
        [exposure("medium", [("Cited.", ["a#c001"]), ("Bare assertion.", [])])]
    )

    assert not report.ok
    assert [issue.kind for issue in report.issues] == [validate.UNCITED]
    assert report.issues[0].agent == EXPOSURE
    assert "Bare assertion." in report.issues[0].detail


def test_a_specialist_that_returned_nothing_is_reported_once() -> None:
    report = validate.cross_validate([assessment(PRECEDENT, [])])

    assert [issue.kind for issue in report.issues] == [validate.NO_FINDINGS]
    assert report.issues[0].agent == PRECEDENT


def test_high_exposure_declared_in_appetite_is_a_contradiction() -> None:
    report = validate.cross_validate([exposure("high"), appetite("in-appetite")])

    assert [issue.kind for issue in report.issues] == [validate.CONTRADICTION]
    assert "exposure graded high" in report.issues[0].detail
    assert "in-appetite" in report.issues[0].detail
    assert report.issues[0].agent == f"{EXPOSURE} - {APPETITE}"


def test_low_exposure_declined_is_a_contradiction_too() -> None:
    report = validate.cross_validate([exposure("low"), appetite("decline")])

    assert [issue.kind for issue in report.issues] == [validate.CONTRADICTION]


def test_grades_that_merely_differ_are_not_a_contradiction() -> None:
    report = validate.cross_validate([exposure("high"), appetite("refer")])

    assert report.ok


def test_a_contradiction_needs_both_sides_to_have_reported() -> None:
    report = validate.cross_validate([exposure("high")])

    assert report.ok


def test_an_unstated_grade_is_not_read_as_agreement() -> None:
    report = validate.cross_validate([exposure("unstated"), appetite("in-appetite")])

    assert report.ok


def test_every_issue_becomes_an_open_question_naming_its_agent() -> None:
    report = validate.cross_validate([exposure("high"), appetite("in-appetite", [("A.", [])])])

    assert len(report.open_questions) == len(report.issues) == 2
    assert all(" - raised by " in question for question in report.open_questions)


def test_the_same_assessments_validate_the_same_way_every_time() -> None:
    assessments = [exposure("high", [("A.", []), ("B.", ["a#c001"])]), appetite("in-appetite")]

    assert validate.cross_validate(assessments) == validate.cross_validate(assessments)
    assert validate.cross_validate(assessments) == validate.cross_validate(
        list(reversed(assessments))
    )


def test_the_graded_labels_are_read_back_off_the_flags() -> None:
    assert validate.grade(exposure("high"), "severity") == "high"
    assert validate.grade(exposure("high"), "position") == ""
