"""The human edit beat: a plain file write, picked up by the next read."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import hitl
from agents.risk_assessment_orchestrator import orient_step
from mcp_server.tracing import read
from tests.fakes import Sandbox

CASE = "SUB-2025-007"
CASE_DIR = "wiki/submissions/SUB-2025-007"


def traces(sandbox: Sandbox) -> list[dict[str, Any]]:
    files = sorted(sandbox.context.traces_dir.glob("*.jsonl"))
    return [line for path in files for line in read(path)]


def test_the_fixture_edit_is_added_to_the_briefing_the_human_already_wrote(
    sandbox: Sandbox,
) -> None:
    before = sandbox.written(CASE_DIR, "briefing.md")

    edit = hitl.apply_fixture(sandbox.context.wiki_dir, CASE_DIR, sandbox.context.traces_dir)

    after = sandbox.written(CASE_DIR, "briefing.md")
    assert after.startswith(before.rstrip())
    assert edit.section in after
    assert edit.scripted
    assert edit.path == f"{CASE_DIR}/briefing.md"


def test_the_scripted_edit_is_the_checked_in_fixture_and_nothing_else(sandbox: Sandbox) -> None:
    """Checked in, so the edit is the same one every rehearsal replays."""
    edit = hitl.apply_fixture(sandbox.context.wiki_dir, CASE_DIR, sandbox.context.traces_dir)

    assert edit.section == hitl.FIXTURE.read_text(encoding="utf-8").strip()


def test_the_edit_is_traced_as_the_demo_writing_by_hand(sandbox: Sandbox) -> None:
    """Not a tool call - the wiki rules say direct writes are for humans."""
    hitl.apply_fixture(sandbox.context.wiki_dir, CASE_DIR, sandbox.context.traces_dir)

    line = traces(sandbox)[-1]
    assert line["tool"] == "demo.human_edit"
    assert line["result"]["scripted"] is True
    assert line["args"]["path"] == f"{CASE_DIR}/briefing.md"
    assert "hitl-edit.md" in str(line["args"]["source"])


def test_the_next_orientation_picks_the_edit_up_with_nothing_re_indexed(
    sandbox: Sandbox,
) -> None:
    before = orient_step(sandbox.context, CASE)

    edit = hitl.apply_fixture(sandbox.context.wiki_dir, CASE_DIR, sandbox.context.traces_dir)
    after = orient_step(sandbox.context, CASE)

    assert after.total_tokens > before.total_tokens
    assert edit.section.splitlines()[0] in after.text


def test_a_typed_edit_reports_the_lines_the_human_added(sandbox: Sandbox) -> None:
    path = f"{CASE_DIR}/briefing.md"

    edit = hitl.typed_edit(
        path,
        "# Briefing\n\nintake\n",
        "# Briefing\n\nintake\n\n## Note\ntyped by hand\n",
        sandbox.context.traces_dir,
    )

    assert edit.section == "## Note\ntyped by hand"
    assert not edit.scripted
    assert traces(sandbox)[-1]["result"]["scripted"] is False


def test_reading_a_file_that_is_not_there_yet_is_empty_rather_than_an_error(
    tmp_path: Path,
) -> None:
    assert hitl.read(tmp_path / "nothing.md") == ""
