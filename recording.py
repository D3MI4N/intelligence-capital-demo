"""The blessed recording: the traces a replayed run answers from, kept in the repo.

traces/ is the live stream. It is gitignored, it accumulates every rehearsal on
the machine that ran them, and it is exactly the wrong thing to depend on when
the demo is presented from a laptop that never recorded anything. So a good
rehearsal gets blessed: its traces are compacted - newest entry per key wins,
everything it superseded dropped - and written to fixtures/recording/, which is
committed and travels with the repo.

Installing works the other way. reset --replay copies the recording
back into traces/ before the rebuild, so replay resolution stays exactly where
it was: agents/llm.py still reads one path, still takes the newest recording of
a key, and has learned nothing about any of this.

Three files carry a run:

    llm_calls.jsonl   the completions, keyed by model + system + prompt
    embeddings.jsonl  the vectors, keyed by model + text
    demo_runs.jsonl   the date the run wrote its records under

The daily trace file is not among them. That is the audit stream a run
produces, not something it consumes, and a replayed run writes its own.

Compaction keeps one entry per key and orders what survives by where its
newest entry appeared. That ordering is load-bearing for demo_runs.jsonl,
which resolve_stamp reads from the end: installing the recording over a
machine whose own live runs are more recent still has to leave the blessed
run last, or the replay would date its records to a run it is not replaying.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from agents import llm
from ingest import layout

RECORDING_DIR = layout.REPO_ROOT / "fixtures" / "recording"
RUNS_FILE = "demo_runs.jsonl"


@dataclass(frozen=True)
class Recorded:
    """One file of a recording, and the field that identifies an entry in it."""

    name: str
    key: str


FILES: tuple[Recorded, ...] = (
    Recorded(llm.CACHE_FILE, "key"),
    Recorded(llm.EMBED_CACHE_FILE, "key"),
    Recorded(RUNS_FILE, "stamp"),
)


@dataclass(frozen=True)
class Written:
    """What compacting one file produced."""

    name: str
    kept: int
    dropped: int


def bless(
    traces_dir: Path = layout.TRACES_DIR, recording_dir: Path = RECORDING_DIR
) -> list[Written]:
    """Make the current traces the recording, compacted. Returns what was written.

    Refuses on an empty or missing source file rather than blessing half a run:
    a recording with no embeddings replays until the first search and then
    stops, in front of the client.
    """
    empty = [file.name for file in FILES if not _read(traces_dir / file.name)]
    if empty:
        raise RuntimeError(
            f"nothing to bless: {', '.join(empty)} in {traces_dir} is empty or missing - "
            "run intelligence_capital_demo.py reset and then run, live, once - and bless that"
        )
    return [_compact_into(traces_dir / f.name, recording_dir / f.name, f, ()) for f in FILES]


def install(
    recording_dir: Path = RECORDING_DIR, traces_dir: Path = layout.TRACES_DIR
) -> list[Written]:
    """Copy the recording into the live traces, the recording winning every key.

    A merge rather than an overwrite: whatever this machine recorded for keys
    the recording does not cover survives, and the file stays compacted instead
    of growing by a whole run every reset.
    """
    missing = [file.name for file in FILES if not (recording_dir / file.name).is_file()]
    if missing:
        raise RuntimeError(
            f"no recording to install: {', '.join(missing)} is not in {recording_dir} - "
            "record a live run and bless it with intelligence_capital_demo.py bless"
        )
    return [
        _compact_into(traces_dir / f.name, traces_dir / f.name, f, _read(recording_dir / f.name))
        for f in FILES
    ]


def compact(lines: Sequence[Mapping[str, object]], key: str) -> list[dict[str, object]]:
    """One entry per key, the newest of each, in the order their newest appeared."""
    newest: dict[str, dict[str, object]] = {}
    for line in lines:
        identifier = str(line.get(key, ""))
        newest.pop(identifier, None)
        newest[identifier] = dict(line)
    return list(newest.values())


def _compact_into(
    source: Path, target: Path, file: Recorded, appended: Sequence[Mapping[str, object]]
) -> Written:
    """Compact one file, with anything appended taking precedence, and write it."""
    lines = [*_read(source), *appended]
    kept = compact(lines, file.key)
    target.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n" for line in kept)
    target.write_text(body, encoding="utf-8")
    return Written(name=file.name, kept=len(kept), dropped=len(lines) - len(kept))


def _read(path: Path) -> list[dict[str, object]]:
    """Every entry in one JSONL file, oldest first. A missing file is an empty one."""
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]
