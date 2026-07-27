"""Finding a case, and assembling the AGENTS.md cascade over it."""

from __future__ import annotations

from pathlib import Path

import pytest

from errors import UnknownCase
from mcp_server import cases


def test_a_case_is_found_by_the_directory_named_after_it(wiki: Path) -> None:
    assert cases.case_dir("CLM-9999-001", wiki) == wiki / "claims" / "CLM-9999-001"
    assert cases.case_dir("SUB-9999-001", wiki) == wiki / "submissions" / "SUB-9999-001"


def test_every_case_in_the_wiki_is_listed(wiki: Path) -> None:
    assert cases.known_cases(wiki) == ("CLM-9999-001", "SUB-9999-001")


def test_an_unknown_case_names_the_ones_that_exist(wiki: Path) -> None:
    with pytest.raises(UnknownCase, match="CLM-9999-001"):
        cases.case_dir("CLM-0000-000", wiki)


def test_a_case_id_that_is_really_a_path_is_refused(wiki: Path) -> None:
    with pytest.raises(UnknownCase, match="not a case id"):
        cases.case_dir("../../etc", wiki)

    with pytest.raises(UnknownCase, match="not a case id"):
        cases.case_dir("claims/CLM-9999-001", wiki)


def test_the_cascade_runs_platform_then_domain_then_case(wiki: Path) -> None:
    found = cases.cascade(wiki / "claims" / "CLM-9999-001", wiki)

    assert [path.relative_to(wiki).as_posix() for path in found] == [
        "AGENTS.md",
        "claims/AGENTS.md",
        "claims/CLM-9999-001/AGENTS.md",
    ]


def test_the_cascade_holds_only_the_levels_that_wrote_rules(wiki: Path) -> None:
    """submissions/ has no AGENTS.md in this wiki - the platform one still applies."""
    found = cases.cascade(wiki / "submissions" / "SUB-9999-001", wiki)

    assert [path.relative_to(wiki).as_posix() for path in found] == ["AGENTS.md"]


def test_context_files_end_with_the_index_and_the_briefing(wiki: Path) -> None:
    found = cases.context_files(wiki / "claims" / "CLM-9999-001", wiki)

    assert [path.name for path in found[-2:]] == ["index.md", "briefing.md"]
    assert [cases.role_of(path) for path in found] == [
        "rules",
        "rules",
        "rules",
        "index",
        "briefing",
    ]
