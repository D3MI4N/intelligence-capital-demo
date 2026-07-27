"""The write guardrails, and what each operation does to a file."""

from __future__ import annotations

from pathlib import Path

import pytest

from errors import WriteRefused
from mcp_server import writes

BRIEFING = "claims/CLM-9999-001/briefing.md"
DECISIONS = "claims/CLM-9999-001/decisions.md"
NEW_DECISIONS = "submissions/SUB-9999-001/decisions.md"


def read(wiki: Path, relative: str) -> str:
    return (wiki / relative).read_text(encoding="utf-8")


def test_a_vault_path_a_repo_path_and_an_absolute_path_all_resolve(wiki: Path) -> None:
    expected = wiki / "claims" / "CLM-9999-001" / "briefing.md"

    assert writes.resolve(BRIEFING, wiki) == expected
    assert writes.resolve(f"wiki/{BRIEFING}", wiki) == expected
    assert writes.resolve(str(expected), wiki) == expected


def test_a_path_that_climbs_out_of_the_wiki_is_refused(wiki: Path) -> None:
    with pytest.raises(WriteRefused, match="outside the wiki"):
        writes.resolve("../escaped.md", wiki)

    with pytest.raises(WriteRefused, match="outside the wiki"):
        writes.resolve("claims/../../escaped.md", wiki)

    with pytest.raises(WriteRefused, match="outside the wiki"):
        writes.resolve("/etc/passwd.md", wiki)


def test_a_symlink_out_of_the_wiki_is_refused(wiki: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (wiki / "escape").symlink_to(outside)

    with pytest.raises(WriteRefused, match="outside the wiki"):
        writes.resolve("escape/note.md", wiki)


def test_only_markdown_is_writable(wiki: Path) -> None:
    with pytest.raises(WriteRefused, match="not markdown"):
        writes.resolve("claims/CLM-9999-001/notes.txt", wiki)


def test_agents_files_are_human_only(wiki: Path) -> None:
    for path in ("AGENTS.md", "claims/AGENTS.md", "claims/CLM-9999-001/AGENTS.md"):
        with pytest.raises(WriteRefused, match="human-only"):
            writes.apply(path, writes.APPEND_SECTION, "## New rule\nDo it.", wiki)


def test_the_vocabulary_is_human_only(wiki: Path) -> None:
    with pytest.raises(WriteRefused, match="human-only"):
        writes.apply("vocabulary/perils.md", writes.APPEND_SECTION, "## New peril", wiki)

    with pytest.raises(WriteRefused, match="human-only"):
        writes.apply("vocabulary/new-terms.md", writes.CREATE_FILE, "# Terms", wiki)


def test_decisions_accept_an_append(wiki: Path) -> None:
    outcome = writes.apply(
        DECISIONS,
        writes.APPEND_SECTION,
        "## D-002 - 2024-09-15 - Coverage position\nCY-EX-04 held not to apply.",
        wiki,
    )

    text = read(wiki, DECISIONS)
    assert outcome.section == "## D-002 - 2024-09-15 - Coverage position"
    assert "## D-001 - 2024-06-12 - Initial reserve" in text
    assert text.rstrip().endswith("CY-EX-04 held not to apply.")


def test_the_first_append_creates_a_decisions_file_that_is_not_there_yet(wiki: Path) -> None:
    """SUB-9999-001 has taken no decisions, so it has no decisions.md."""
    outcome = writes.apply(
        NEW_DECISIONS, writes.APPEND_SECTION, "# Decisions\n\n## D-001 - Bound", wiki
    )

    assert outcome.created is True
    assert read(wiki, NEW_DECISIONS) == "# Decisions\n\n## D-001 - Bound\n"


def test_the_second_append_adds_to_the_file_the_first_one_created(wiki: Path) -> None:
    writes.apply(NEW_DECISIONS, writes.APPEND_SECTION, "# Decisions\n\n## D-001 - Bound", wiki)

    outcome = writes.apply(NEW_DECISIONS, writes.APPEND_SECTION, "## D-002 - Renewed", wiki)

    assert outcome.created is False
    assert read(wiki, NEW_DECISIONS) == "# Decisions\n\n## D-001 - Bound\n\n## D-002 - Renewed\n"


def test_a_created_decisions_file_is_still_append_only(wiki: Path) -> None:
    writes.apply(NEW_DECISIONS, writes.APPEND_SECTION, "# Decisions\n\n## D-001 - Bound", wiki)
    before = read(wiki, NEW_DECISIONS)

    with pytest.raises(WriteRefused, match="append-only"):
        writes.apply(NEW_DECISIONS, writes.REPLACE_SECTION, "## D-001 - Declined", wiki)
    with pytest.raises(WriteRefused, match="append-only"):
        writes.apply(NEW_DECISIONS, writes.CREATE_FILE, "# Decisions", wiki)

    assert read(wiki, NEW_DECISIONS) == before


def test_decisions_refuse_anything_that_would_rewrite_a_record(wiki: Path) -> None:
    before = read(wiki, DECISIONS)

    with pytest.raises(WriteRefused, match="append-only"):
        writes.apply(
            DECISIONS,
            writes.REPLACE_SECTION,
            "## D-001 - 2024-06-12 - Initial reserve\nReserve set at EUR 1.",
            wiki,
        )
    with pytest.raises(WriteRefused, match="append-only"):
        writes.apply(DECISIONS, writes.CREATE_FILE, "# Decisions", wiki)

    assert read(wiki, DECISIONS) == before


def test_an_unknown_operation_names_the_ones_that_exist(wiki: Path) -> None:
    with pytest.raises(WriteRefused, match="append_section"):
        writes.apply(BRIEFING, "delete_file", "## Gone", wiki)


def test_empty_content_is_refused(wiki: Path) -> None:
    with pytest.raises(WriteRefused, match="empty"):
        writes.apply(BRIEFING, writes.APPEND_SECTION, "   \n\n", wiki)


def test_append_adds_a_section_and_leaves_the_rest_alone(wiki: Path) -> None:
    before = read(wiki, BRIEFING)

    writes.apply(BRIEFING, writes.APPEND_SECTION, "## Precedent\nSee CLM-9999-001.", wiki)

    after = read(wiki, BRIEFING)
    assert after.startswith(before.rstrip())
    assert after.endswith("## Precedent\nSee CLM-9999-001.\n")


def test_replace_swaps_one_section_and_keeps_its_neighbours(wiki: Path) -> None:
    outcome = writes.apply(
        BRIEFING,
        writes.REPLACE_SECTION,
        "## Assessment\nVendor access is a distinct exposure path [[chunk]].",
        wiki,
    )

    text = read(wiki, BRIEFING)
    assert outcome.section == "## Assessment"
    assert "Vendor access is a distinct exposure path" in text
    assert "not treated as a distinct exposure path" not in text
    assert "# Briefing - at close" in text
    assert text.rstrip().endswith("## Open points\nNone at close.")


def test_replace_needs_a_section_that_is_there(wiki: Path) -> None:
    with pytest.raises(WriteRefused, match="has no section"):
        writes.apply(BRIEFING, writes.REPLACE_SECTION, "## Reserve\nEUR 2.5M.", wiki)


def test_replace_needs_content_that_starts_with_a_heading(wiki: Path) -> None:
    with pytest.raises(WriteRefused, match="starts with the heading"):
        writes.apply(BRIEFING, writes.REPLACE_SECTION, "Just a paragraph.", wiki)


def test_create_writes_a_new_file_and_its_parents(wiki: Path) -> None:
    outcome = writes.apply(
        "claims/CLM-9999-001/sources/new-note.md",
        writes.CREATE_FILE,
        "# Source note\n\nLocator: raw/testco-survey.md",
        wiki,
    )

    assert outcome.created is True
    assert read(wiki, "claims/CLM-9999-001/sources/new-note.md").endswith("survey.md\n")


def test_create_never_overwrites(wiki: Path) -> None:
    before = read(wiki, BRIEFING)

    with pytest.raises(WriteRefused, match="already exists"):
        writes.apply(BRIEFING, writes.CREATE_FILE, "# Briefing", wiki)

    assert read(wiki, BRIEFING) == before


def test_appending_to_any_other_file_that_is_not_there_says_to_create_it(wiki: Path) -> None:
    """Only append-only files are created by appending - elsewhere it is a typo guard."""
    with pytest.raises(WriteRefused, match="create_file"):
        writes.apply("claims/CLM-9999-001/absent.md", writes.APPEND_SECTION, "## New", wiki)

    assert not (wiki / "claims" / "CLM-9999-001" / "absent.md").exists()


def test_every_write_leaves_one_trailing_newline(wiki: Path) -> None:
    writes.apply(BRIEFING, writes.APPEND_SECTION, "## Precedent\nSee CLM-9999-001.\n\n\n", wiki)

    text = read(wiki, BRIEFING)
    assert text.endswith("\n")
    assert not text.endswith("\n\n")
