"""The recording that travels with the repo: blessing it, installing it, replaying it.

The claim under test is that the machine which presents the demo does not have
to be the machine that recorded it. So the last test here is the acceptance
one: record a run, bless it, delete traces/ the way a fresh clone has no
traces/ at all, install, and then resolve every completion, every embedding and
the run date with no credentials and no provider reachable.

Nothing here calls out. The recording is written through the same llm.record
and llm.record_embedding a live run uses, so the format under test is the real
one rather than a hand-rolled imitation of it.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import demo
import recording
from agents import llm
from ingest import layout
from stage import Stage

CASE = "SUB-2025-007"
SYSTEM = "you are an exposure analyst"
PROMPT = "assess Northbound Freight"
ANSWER = "Assessment: matches the pattern already on file [Chunk:0001]."
TEXT = "vendor standing access is a distinct exposure path"
VECTOR = [0.5, 0.25, 0.125]


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Model names and nothing else - no .env, and no key to reach a provider with."""
    monkeypatch.setattr(llm, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("EMBED_MODEL", "test-embed-model")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.delenv("LLM_MODE", raising=False)


@pytest.fixture
def recorded(tmp_path: Path) -> Path:
    """A live run's traces: one completion, one embedding, one dated run."""
    traces = tmp_path / "traces"
    llm.record(
        llm.call_key("test-model", SYSTEM, PROMPT),
        "test-model",
        SYSTEM,
        PROMPT,
        ANSWER,
        llm.cache_file(traces),
    )
    llm.record_embedding(
        llm.embed_key("test-embed-model", TEXT),
        "test-embed-model",
        TEXT,
        VECTOR,
        llm.embed_cache_file(traces),
    )
    demo.resolve_stamp(traces, llm.LIVE, CASE)
    return traces


def read(path: Path) -> list[dict[str, object]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_compaction_keeps_the_newest_entry_of_each_key() -> None:
    lines = [
        {"key": "a", "response": "first"},
        {"key": "b", "response": "only"},
        {"key": "a", "response": "second"},
    ]

    assert recording.compact(lines, "key") == [
        {"key": "b", "response": "only"},
        {"key": "a", "response": "second"},
    ]


def test_compaction_orders_by_the_newest_entry_so_the_last_line_is_the_newest() -> None:
    """resolve_stamp reads the run file from the end. The blessed run has to be there."""
    lines = [{"stamp": "2025-04-01"}, {"stamp": "2025-04-02"}, {"stamp": "2025-04-01"}]

    assert recording.compact(lines, "stamp")[-1] == {"stamp": "2025-04-01"}


def test_blessing_writes_the_recording_with_one_entry_per_key(
    recorded: Path, tmp_path: Path
) -> None:
    llm.record(
        llm.call_key("test-model", SYSTEM, PROMPT),
        "test-model",
        SYSTEM,
        PROMPT,
        "a better answer, recorded later",
        llm.cache_file(recorded),
    )
    blessed = tmp_path / "recording"

    written = recording.bless(recorded, blessed)

    calls = read(blessed / llm.CACHE_FILE)
    assert len(calls) == 1
    assert calls[0]["response"] == "a better answer, recorded later"
    assert [file.dropped for file in written if file.name == llm.CACHE_FILE] == [1]
    assert {file.name for file in written} == {file.name for file in recording.FILES}


def test_blessing_an_incomplete_run_refuses_and_says_what_is_missing(tmp_path: Path) -> None:
    """A recording with no embeddings replays until the first search, in front of the client."""
    traces = tmp_path / "traces"
    demo.resolve_stamp(traces, llm.LIVE, CASE)

    with pytest.raises(RuntimeError, match=llm.EMBED_CACHE_FILE):
        recording.bless(traces, tmp_path / "recording")


def test_installing_puts_the_recording_where_replay_already_looks(
    recorded: Path, tmp_path: Path
) -> None:
    blessed = tmp_path / "recording"
    recording.bless(recorded, blessed)
    fresh = tmp_path / "fresh-traces"

    recording.install(blessed, fresh)

    assert read(fresh / llm.CACHE_FILE)[0]["response"] == ANSWER
    assert read(fresh / llm.EMBED_CACHE_FILE)[0]["vector"] == VECTOR


def test_installing_keeps_what_this_machine_recorded_for_keys_the_recording_misses(
    recorded: Path, tmp_path: Path
) -> None:
    blessed = tmp_path / "recording"
    recording.bless(recorded, blessed)
    llm.record(
        llm.call_key("test-model", SYSTEM, "a prompt only this machine has seen"),
        "test-model",
        SYSTEM,
        "a prompt only this machine has seen",
        "local answer",
        llm.cache_file(recorded),
    )

    recording.install(blessed, recorded)

    responses = {line["response"] for line in read(llm.cache_file(recorded))}
    assert responses == {ANSWER, "local answer"}


def test_installing_leaves_the_blessed_run_last_even_after_a_newer_local_run(
    recorded: Path, tmp_path: Path
) -> None:
    """Otherwise the replay dates its records to a run it is not replaying."""
    blessed = tmp_path / "recording"
    recording.bless(recorded, blessed)
    stamp = str(read(blessed / recording.RUNS_FILE)[-1]["stamp"])
    later = (stamp, "2099-01-01")
    (recorded / recording.RUNS_FILE).write_text(
        "".join(json.dumps({"stamp": value, "case": CASE}) + "\n" for value in later),
        encoding="utf-8",
    )

    recording.install(blessed, recorded)

    assert demo.resolve_stamp(recorded, llm.REPLAY, CASE) == stamp


def test_installing_without_a_recording_says_how_to_make_one(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="demo.py bless"):
        recording.install(tmp_path / "recording", tmp_path / "traces")


def test_a_machine_that_has_never_recorded_anything_replays_the_committed_recording(
    recorded: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The acceptance flow: bless here, delete traces/, install there, replay it all."""
    blessed = tmp_path / "recording"
    recording.bless(recorded, blessed)
    stamp = str(read(blessed / recording.RUNS_FILE)[-1]["stamp"])
    shutil.rmtree(recorded)
    monkeypatch.setenv("LLM_MODE", llm.REPLAY)
    monkeypatch.setattr(
        llm, "_client", lambda: pytest.fail("a replayed run reached for the provider")
    )

    recording.install(blessed, recorded)

    assert llm.complete(SYSTEM, PROMPT, recorded) == ANSWER
    assert llm.embed([TEXT], recorded) == [VECTOR]
    assert demo.resolve_stamp(recorded, llm.REPLAY, CASE) == stamp


def test_the_reset_that_prepares_a_replay_installs_the_recording(
    recorded: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """reset --replay, with the wiki restore and the rebuild stubbed out around it."""
    blessed = tmp_path / "recording"
    recording.bless(recorded, blessed)
    fresh = tmp_path / "fresh-traces"
    monkeypatch.setattr(recording, "RECORDING_DIR", blessed)
    monkeypatch.setattr(layout, "TRACES_DIR", fresh)
    monkeypatch.setattr(demo, "restore_wiki", lambda stage: None)
    monkeypatch.setattr(demo, "rebuild_indexes", lambda stage: None)

    assert demo.reset(Stage(paused=False), replay=True) == 0
    assert read(fresh / llm.CACHE_FILE)[0]["response"] == ANSWER


def test_a_live_reset_leaves_the_traces_alone(
    recorded: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Live is how a recording gets made. Installing over it would overwrite the new one."""
    blessed = tmp_path / "recording"
    recording.bless(recorded, blessed)
    monkeypatch.setattr(recording, "RECORDING_DIR", blessed)
    monkeypatch.setattr(layout, "TRACES_DIR", tmp_path / "fresh-traces")
    monkeypatch.setattr(demo, "restore_wiki", lambda stage: None)
    monkeypatch.setattr(demo, "rebuild_indexes", lambda stage: None)

    assert demo.reset(Stage(paused=False), replay=False) == 0
    assert not (tmp_path / "fresh-traces").exists()
