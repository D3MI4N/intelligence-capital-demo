"""The driver: five beats in order, a reset that really resets, a dated replay.

The beats run here exactly as they run on the night, with two substitutions the
demo already allows for: a deterministic model instead of the provider, and the
sandbox's own rebuild instead of shelling out to ingest/rebuild.sh. Nothing
reaches the network and nothing touches the repo's wiki.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

import demo
from agents import llm
from case_close import VENDOR_ACCESS
from stage import Stage
from tests.fakes import FakeLLM, Sandbox

CASE = "SUB-2025-007"
CASE_DIR = "wiki/submissions/SUB-2025-007"
STAMP = "2025-04-01"
PLATFORM_PATH = "wiki/platform-ic/engagement-lessons/vendor-access-cyber-logistics.md"


@pytest.fixture
def screen() -> StringIO:
    """Everything the room would have seen."""
    return StringIO()


@pytest.fixture
def stage(screen: StringIO) -> Stage:
    return Stage(console=Console(file=screen, width=240, highlight=False), paused=False)


@pytest.fixture
def five_beats(stage: Stage, sandbox: Sandbox, fake_llm: FakeLLM) -> str:
    """Run all five beats over the sandbox wiki and return what was printed."""
    demo.beats(
        stage,
        sandbox.context,
        fake_llm,
        CASE,
        STAMP,
        replay=True,
        rebuild=lambda _: sandbox.rebuild(),
    )
    file = stage.console.file
    assert isinstance(file, StringIO)
    return file.getvalue()


def test_the_five_beats_run_in_order(five_beats: str) -> None:
    positions = [
        five_beats.index(f"BEAT {number} - {name}")
        for number, name in (
            (1, "ORIENT"),
            (2, "RETRIEVE"),
            (3, "WRITE BACK"),
            (4, "HITL"),
            (5, "COMPOUND"),
        )
    ]

    assert positions == sorted(positions)


def test_beat_one_shows_the_cascade_with_a_running_token_count(five_beats: str) -> None:
    for path in (
        "wiki/AGENTS.md",
        "wiki/submissions/AGENTS.md",
        f"{CASE_DIR}/AGENTS.md",
        f"{CASE_DIR}/index.md",
        f"{CASE_DIR}/briefing.md",
    ):
        assert path in five_beats
    assert "Running" in five_beats
    assert "no model call yet" in five_beats


def test_beat_two_echoes_every_tool_call_with_the_arguments_it_was_made_with(
    five_beats: str,
) -> None:
    """The deck shows these strings. They have to be these strings."""
    assert (
        'search_knowledge_base(query="cyber-logistics exposure - loss drivers, '
        'business interruption, dependencies", top_k=5, path_prefix=None)'
    ) in five_beats
    assert (
        'search_knowledge_base(query="cyber-logistics precedent - prior claims, '
        'coverage outcome, lessons", top_k=5, path_prefix=None)'
    ) in five_beats
    assert (
        'traverse_graph(seed="RiskClass:cyber-logistics", '
        'rel_types=["in_class", "applies_to_class"], depth=2)'
    ) in five_beats
    assert (
        'traverse_graph(seed="RiskClass:cyber-logistics", '
        'rel_types=["in_class", "has_lesson"], depth=2)'
    ) in five_beats


def test_beat_two_reports_what_came_back_and_what_it_cost(five_beats: str) -> None:
    assert "exposure_analyst" in five_beats
    assert "appetite_checker" in five_beats
    assert "precedent_finder" in five_beats
    assert "entities" in five_beats
    assert "merged GraphRAG block" in five_beats


def test_beat_three_writes_through_the_tool_and_shows_the_diff(
    five_beats: str, sandbox: Sandbox
) -> None:
    assert f'propose_wiki_update(path="{CASE_DIR}/briefing.md"' in five_beats
    assert f"diff - {CASE_DIR}/briefing.md" in five_beats
    assert "composed draft" in five_beats
    assert "## Risk assessment draft" in sandbox.written(CASE_DIR, "briefing.md")
    assert "Risk assessment draft recorded" in sandbox.written(CASE_DIR, "decisions.md")


def test_beat_three_says_when_it_normalised_the_model_output(five_beats: str) -> None:
    """The fake writes a non-breaking hyphen and an em dash. Both get reported."""
    assert "normalised into house style" in five_beats
    assert "\u2011" not in five_beats.split("BEAT 4")[0].split("composed draft")[1]


def test_beat_four_applies_the_scripted_edit_and_says_so(five_beats: str, sandbox: Sandbox) -> None:
    assert "scripted edit from fixtures/hitl-edit.md" in five_beats
    assert "Underwriter note" in sandbox.written(CASE_DIR, "briefing.md")
    assert "orientation tokens" in five_beats


def test_beat_five_closes_the_case_and_the_query_returns_one_more_result(
    five_beats: str, sandbox: Sandbox
) -> None:
    assert sandbox.exists(PLATFORM_PATH)
    assert f"new: Lesson:{VENDOR_ACCESS.lesson_id}" in five_beats
    assert "results: " in five_beats


def test_the_run_asks_the_model_four_times_and_no_more(five_beats: str, fake_llm: FakeLLM) -> None:
    """Three specialists and one draft. The rest of the demo is deterministic."""
    assert len(fake_llm.calls) == 4


def test_a_reset_puts_back_what_a_run_changed_and_removes_what_it_created(
    stage: Stage, tmp_path: Path
) -> None:
    """The clean matters: decisions.md is created by its first append."""
    root = _repository(tmp_path)
    (root / "wiki" / "briefing.md").write_text("# Briefing\n\nedited by a run\n", encoding="utf-8")
    (root / "wiki" / "decisions.md").write_text("## D-2025-04-01\n", encoding="utf-8")

    demo.restore_wiki(stage, root)

    assert (root / "wiki" / "briefing.md").read_text(encoding="utf-8") == "# Briefing\n\nintake\n"
    assert not (root / "wiki" / "decisions.md").exists()


def test_a_live_run_records_the_date_it_wrote_under(tmp_path: Path) -> None:
    stamp = demo.resolve_stamp(tmp_path, llm.LIVE, CASE)

    assert stamp == datetime.now(UTC).date().isoformat()
    assert (tmp_path / demo.RUNS_FILE).is_file()


def test_a_replayed_run_writes_the_date_of_the_run_it_replays(tmp_path: Path) -> None:
    """Otherwise beat five rebuilds a corpus the recorded embeddings never saw."""
    demo.resolve_stamp(tmp_path, llm.LIVE, CASE)
    (tmp_path / demo.RUNS_FILE).write_text(
        '{"ts": "2025-04-01T09:00:00+00:00", "stamp": "2025-04-01", "case": "SUB-2025-007"}\n',
        encoding="utf-8",
    )

    assert demo.resolve_stamp(tmp_path, llm.REPLAY, CASE) == "2025-04-01"


def test_replaying_with_nothing_recorded_says_what_to_do(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="nothing to replay"):
        demo.resolve_stamp(tmp_path, llm.REPLAY, CASE)


def _repository(tmp_path: Path) -> Path:
    """A git repository with a committed wiki, to reset against."""
    root = tmp_path / "repo"
    (root / "wiki").mkdir(parents=True)
    (root / "wiki" / "briefing.md").write_text("# Briefing\n\nintake\n", encoding="utf-8")
    for command in (
        ["git", "init", "--quiet"],
        ["git", "config", "user.email", "demo@example.com"],
        ["git", "config", "user.name", "demo"],
        ["git", "add", "wiki"],
        ["git", "commit", "--quiet", "-m", "wiki"],
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)
    return root


def test_the_closing_summary_counts_this_run_and_not_the_rehearsal_before_it(
    five_beats: str,
) -> None:
    """One trace file per day - an hour-old rehearsal is not this run."""
    summary = five_beats.split("BEAT 0 - DONE")[1]

    assert "model calls" in summary
    assert " 4" in summary.split("model calls")[1].splitlines()[0]
