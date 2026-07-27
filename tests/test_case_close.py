"""Closing the case, and the one thing the whole demo is for: the corpus grew.

Everything here runs over a copy of the real wiki - the cases the deck talks
about, the vocabulary they are written in - because the claim being tested is
about that wiki: close SUB-2025-007, promote what it learned, rebuild, and the
precedent query the specialists ran comes back with one more result.
"""

from __future__ import annotations

from typing import Any

import case_close
from case_close import VENDOR_ACCESS
from mcp_server.tracing import read
from tests.fakes import Sandbox

CASE = "SUB-2025-007"
CASE_DIR = "wiki/submissions/SUB-2025-007"
RISK_CLASS = "cyber-logistics"
STAMP = "2025-04-01"
PLATFORM_PATH = "wiki/platform-ic/engagement-lessons/vendor-access-cyber-logistics.md"


def traces(sandbox: Sandbox) -> list[dict[str, Any]]:
    files = sorted(sandbox.context.traces_dir.glob("*.jsonl"))
    return [line for path in files for line in read(path)]


def close(sandbox: Sandbox) -> case_close.Promotion:
    return case_close.close_case(sandbox.context, CASE, CASE_DIR, RISK_CLASS, STAMP)


def test_the_case_records_its_lesson_and_says_where_it_was_promoted(sandbox: Sandbox) -> None:
    close(sandbox)

    lessons = sandbox.written(CASE_DIR, "lessons.md")
    assert f"case_id: {CASE}" in lessons
    assert "status: promoted" in lessons
    assert f"promoted_to: {VENDOR_ACCESS.vault_path()}" in lessons
    assert f"## {VENDOR_ACCESS.lesson_id} - {VENDOR_ACCESS.title}" in lessons


def test_the_lesson_lands_in_the_platform_layer_where_every_case_retrieves_it(
    sandbox: Sandbox,
) -> None:
    promotion = close(sandbox)

    assert promotion.lesson.platform_path() == PLATFORM_PATH
    assert sandbox.exists(PLATFORM_PATH)
    platform = (sandbox.context.wiki_dir.parent / PLATFORM_PATH).read_text(encoding="utf-8")
    assert f"domain: {RISK_CLASS}" in platform
    assert f"promoted: {STAMP}" in platform
    assert VENDOR_ACCESS.lesson_id in platform


def test_the_promotion_goes_through_the_write_tool_like_any_other_write(
    sandbox: Sandbox,
) -> None:
    """The ceremony is a human act, and it still uses the agents' door."""
    promotion = close(sandbox)

    writes = [line for line in traces(sandbox) if line["tool"] == "propose_wiki_update"]
    assert [line["args"]["operation"] for line in writes] == ["create_file", "create_file"]
    assert [line["result"]["path"] for line in writes] == [
        f"{CASE_DIR}/lessons.md",
        PLATFORM_PATH,
    ]
    assert all(result["created"] for result in promotion.written)


def test_closing_a_case_twice_says_the_same_thing_rather_than_failing(
    sandbox: Sandbox,
) -> None:
    """A rehearsal nobody reset should not blow up on the last beat."""
    close(sandbox)
    close(sandbox)

    lessons = sandbox.written(CASE_DIR, "lessons.md")
    assert lessons.count(f"## {VENDOR_ACCESS.lesson_id}") == 1


def test_the_date_never_reaches_the_text_that_gets_embedded(sandbox: Sandbox) -> None:
    """Frontmatter dates the promotion; the body is what a rebuild embeds."""
    close(sandbox)

    platform = (sandbox.context.wiki_dir.parent / PLATFORM_PATH).read_text(encoding="utf-8")
    _, body = platform.split("---\n", 2)[1:]
    assert STAMP not in body


def test_the_same_precedent_query_returns_one_more_result_after_the_case_closes(
    sandbox: Sandbox,
) -> None:
    before = case_close.precedent_query(sandbox.context, RISK_CLASS)

    close(sandbox)
    sandbox.rebuild()
    after = case_close.precedent_query(sandbox.context, RISK_CLASS)

    assert after.results == before.results + 1
    gained = set(after.entity_ids) - set(before.entity_ids)
    assert gained == {f"Lesson:{VENDOR_ACCESS.lesson_id}"}


def test_the_promoted_lesson_hangs_off_the_risk_class_the_query_walks(
    sandbox: Sandbox,
) -> None:
    """Nobody points the next case at the file - the graph does."""
    close(sandbox)
    sandbox.rebuild()

    after = case_close.precedent_query(sandbox.context, RISK_CLASS)
    assert f"Case:{CASE}" in after.entity_ids
    assert f"Lesson:{VENDOR_ACCESS.lesson_id}" in after.entity_ids


def test_the_query_is_the_one_the_precedent_finder_runs(sandbox: Sandbox) -> None:
    """Same strings, or the comparison in beat five means nothing."""
    case_close.precedent_query(sandbox.context, RISK_CLASS)

    search, traverse = traces(sandbox)[-2:]
    assert search["args"]["query"] == (
        "cyber-logistics precedent - prior claims, coverage outcome, lessons"
    )
    assert search["args"]["top_k"] == 5
    assert traverse["args"]["seed"] == "RiskClass:cyber-logistics"
    assert traverse["args"]["rel_types"] == ["in_class", "has_lesson"]
    assert traverse["args"]["depth"] == 2
