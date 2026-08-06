"""The driver: five beats in order, a reset that really resets, a dated replay.

The beats run here exactly as they run on the night, with two substitutions the
demo already allows for: a deterministic model instead of the provider, and the
sandbox's own rebuild instead of shelling out to ingest/rebuild.sh. Nothing
reaches the network and nothing touches the repo's wiki.

"beat" survives in the names of these tests and nowhere the room can see it -
what the panels say is asserted here as the strings they have to be.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

import hitl
import intelligence_capital_demo as demo
import recording
from agents import llm
from case_close import VENDOR_ACCESS
from ingest.entities import Edge, Graph, Node
from ingest.graph import build_graph
from ingest.parse import parse_corpus
from stage import Stage
from tests.fakes import FakeLLM, Sandbox

CASE = "SUB-2025-007"
CASE_DIR = "wiki/submissions/SUB-2025-007"
STAMP = "2025-04-01"
PLATFORM_PATH = "wiki/platform-ic/engagement-lessons/vendor-access-cyber-logistics.md"
COMPOUND = "COMPOUND - the case closes"
DRAFTED = "Price the concentration"  # a line only the drafted lesson carries


@pytest.fixture
def screen() -> StringIO:
    """Everything the room would have seen."""
    return StringIO()


@pytest.fixture
def stage(screen: StringIO) -> Stage:
    return Stage(console=Console(file=screen, width=240, highlight=False), paused=False)


@pytest.fixture
def paused_stage(screen: StringIO) -> Stage:
    """The stage as the presenter drives it: a keypress between the beats."""
    return Stage(console=Console(file=screen, width=240, highlight=False), paused=True)


@pytest.fixture
def keypresses(monkeypatch: pytest.MonkeyPatch, screen: StringIO) -> list[tuple[str, str]]:
    """Every pause the presenter had to clear, with what was on screen at the time.

    Patching the console's input rather than overriding Stage.pause keeps the
    --no-pause branch under test: a stage that is not paused never gets here.
    """
    pressed: list[tuple[str, str]] = []

    def press(_console: Console, prompt: object = "", **_: object) -> str:
        pressed.append((str(prompt), screen.getvalue()))
        return ""

    monkeypatch.setattr(Console, "input", press)
    return pressed


def _beats(stage: Stage, sandbox: Sandbox, fake_llm: FakeLLM) -> str:
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


@pytest.fixture
def five_beats(stage: Stage, sandbox: Sandbox, fake_llm: FakeLLM) -> str:
    return _beats(stage, sandbox, fake_llm)


def test_the_five_beats_run_in_order(five_beats: str) -> None:
    """The panels are named for what they do and where they sit in the flow."""
    positions = [
        five_beats.index(heading)
        for heading in (
            "ORIENT - step 2 of the swarm flow",
            "RETRIEVE - steps 3-5",
            "WRITE BACK - steps 6-8",
            "HUMAN IN THE LOOP - step 9",
            COMPOUND,
        )
    ]

    assert positions == sorted(positions)


def test_nothing_on_screen_calls_a_phase_a_beat(five_beats: str) -> None:
    """The word is retired in front of a client - it means nothing to them."""
    assert "beat" not in five_beats.lower()


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


def test_every_echoed_call_is_prefixed_with_the_agent_the_trace_recorded(five_beats: str) -> None:
    """Read off the trace line, never guessed: the three specialists interleave."""
    assert "exposure_analyst -> search_knowledge_base(" in five_beats
    assert "appetite_checker -> traverse_graph(" in five_beats
    assert "precedent_finder -> search_knowledge_base(" in five_beats
    assert "precedent_finder -> traverse_graph(" in five_beats
    assert "risk_assessment_orchestrator -> propose_wiki_update(" in five_beats
    assert "case_close -> propose_wiki_update(" in five_beats


def test_a_trace_line_that_names_no_agent_is_echoed_under_the_step_it_came_from(
    stage: Stage, screen: StringIO
) -> None:
    """A blessed trace recorded before the field still has to read as something."""
    older: dict[str, Any] = {
        "tool": "search_knowledge_base",
        "status": "ok",
        "args": {"query": "cyber", "top_k": 5, "path_prefix": None},
        "result": {"chunk_ids": ["wiki/a.md#0"], "scores": [0.5]},
    }

    demo.echo(stage, [older], demo.SPECIALIST)

    assert "specialist -> search_knowledge_base(" in screen.getvalue()


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
    assert "\u2011" not in five_beats.split("HUMAN IN THE LOOP")[0].split("composed draft")[1]


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


def test_beat_five_shows_the_drafted_lesson_before_it_writes_anything(five_beats: str) -> None:
    """The gate opens after the reading, so the reading has to come first."""
    beat = five_beats.split(COMPOUND)[1]

    assert beat.index(DRAFTED) < beat.index("propose_wiki_update")
    assert "nothing written yet" in beat
    assert "strictest gate" in beat


def test_the_promotion_gate_waits_for_approval_with_the_lesson_on_screen(
    keypresses: list[tuple[str, str]], paused_stage: Stage, sandbox: Sandbox, fake_llm: FakeLLM
) -> None:
    _beats(paused_stage, sandbox, fake_llm)

    gates = [press for press in keypresses if VENDOR_ACCESS.lesson_id in press[0]]
    assert len(gates) == 1
    prompt, seen = gates[0]
    assert "approve" in prompt
    approved = seen.split(COMPOUND)[1]
    assert DRAFTED in approved
    assert "propose_wiki_update" not in approved


def test_no_pause_runs_the_gate_unattended(
    keypresses: list[tuple[str, str]], five_beats: str, sandbox: Sandbox
) -> None:
    """--no-pause is for rehearsing alone: nothing waits, the promotion still happens."""
    assert keypresses == []
    assert DRAFTED in five_beats.split(COMPOUND)[1]
    assert sandbox.exists(PLATFORM_PATH)


def test_the_run_asks_the_model_four_times_and_no_more(five_beats: str, fake_llm: FakeLLM) -> None:
    """Three specialists and one draft. The rest of the demo is deterministic."""
    assert len(fake_llm.calls) == 4


def test_a_pasted_note_that_matches_the_fixture_draws_no_re_recording_warning(
    monkeypatch: pytest.MonkeyPatch,
    screen: StringIO,
    paused_stage: Stage,
    sandbox: Sandbox,
    fake_llm: FakeLLM,
) -> None:
    """The live option: paste the note into Obsidian, and it is the scripted edit."""
    briefing = sandbox.path(CASE_DIR, "briefing.md")
    pasted = hitl.FIXTURE.read_text(encoding="utf-8").strip()

    def press(_console: Console, prompt: object = "", **_: object) -> str:
        if "edit applied" in str(prompt):
            # Trailing whitespace on every line, the way a paste arrives.
            note = "\n".join(f"{line}  " for line in pasted.splitlines())
            briefing.write_text(
                f"{briefing.read_text(encoding='utf-8').rstrip()}\n\n{note}\n", encoding="utf-8"
            )
        return ""

    monkeypatch.setattr(Console, "input", press)
    demo.beats(
        paused_stage,
        sandbox.context,
        fake_llm,
        CASE,
        STAMP,
        replay=False,
        rebuild=lambda _: sandbox.rebuild(),
    )

    shown = screen.getvalue()
    assert "the scripted edit" in shown
    assert "re-record" not in shown


def test_a_note_the_recordings_have_never_seen_still_warns(
    monkeypatch: pytest.MonkeyPatch,
    screen: StringIO,
    paused_stage: Stage,
    sandbox: Sandbox,
    fake_llm: FakeLLM,
) -> None:
    """One character away from the fixture is a sentence no recording covers."""
    briefing = sandbox.path(CASE_DIR, "briefing.md")
    typed = f"{hitl.FIXTURE.read_text(encoding='utf-8').strip()[:-1]}X"

    def press(_console: Console, prompt: object = "", **_: object) -> str:
        if "edit applied" in str(prompt):
            briefing.write_text(
                f"{briefing.read_text(encoding='utf-8').rstrip()}\n\n{typed}\n", encoding="utf-8"
            )
        return ""

    monkeypatch.setattr(Console, "input", press)
    demo.beats(
        paused_stage,
        sandbox.context,
        fake_llm,
        CASE,
        STAMP,
        replay=False,
        rebuild=lambda _: sandbox.rebuild(),
    )

    assert "re-record" in screen.getvalue()


def test_the_graph_census_puts_every_edge_in_exactly_one_kind() -> None:
    """Three kinds, told apart by what sits at each end of the edge."""
    nodes = (
        Node("Document:wiki/a.md", "Document", "a"),
        Node("Document:wiki/b.md", "Document", "b"),
        Node("Case:SUB-1", "Case", "SUB-1"),
        Node("RiskClass:cyber-logistics", "RiskClass", "cyber-logistics"),
    )
    edges = (
        Edge("Document:wiki/a.md", "references", "Document:wiki/b.md", "wiki/a.md"),
        Edge("Document:wiki/a.md", "belongs_to", "Case:SUB-1", "wiki/a.md"),
        Edge("Case:SUB-1", "in_class", "RiskClass:cyber-logistics", "wiki/a.md"),
    )

    assert demo.edge_kinds(Graph(nodes=nodes, edges=edges)) == [
        (demo.TYPED_RELATIONS, 1),
        (demo.DOCUMENT_REFERENCES, 1),
        (demo.FILE_LINKS, 1),
    ]


def test_the_graph_census_breakdown_sums_to_the_edges_it_breaks_down(
    corpus: tuple[tuple[str, Path], ...],
) -> None:
    """Computed off the store, so it is still right after the rebuild at the close."""
    documents, _ = parse_corpus(corpus)
    knowledge_graph = build_graph(documents)

    counted = demo.edge_kinds(knowledge_graph)

    assert sum(count for _, count in counted) == len(knowledge_graph.edges)
    assert len(knowledge_graph.edges) > 0


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
    assert (tmp_path / recording.RUNS_FILE).is_file()


def test_a_replayed_run_writes_the_date_of_the_run_it_replays(tmp_path: Path) -> None:
    """Otherwise beat five rebuilds a corpus the recorded embeddings never saw."""
    demo.resolve_stamp(tmp_path, llm.LIVE, CASE)
    (tmp_path / recording.RUNS_FILE).write_text(
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
    summary = five_beats.split(" DONE ")[1]

    assert "model calls" in summary
    assert " 4" in summary.split("model calls")[1].splitlines()[0]
