"""The presenter's entry point: five beats, one keypress apart.

intelligence_capital_demo.py stands in for the Main Orchestrator. It takes the task ("assess this
submission"), hands it to the Risk Assessment orchestrator, and stays out of
the way while that runs - then performs the two things the platform reserves
for a human: accepting an edit, and closing a case.

    intelligence_capital_demo.py run [--case SUB-2025-007] [--replay] [--no-pause]
    intelligence_capital_demo.py reset [--replay]
    intelligence_capital_demo.py bless

The five beats, in order:

    1 ORIENT      the cascade read, with the token cost of every file
    2 RETRIEVE    three specialists in parallel, every tool call echoed
    3 WRITE BACK  validate, compose, write through the tool, show the diff
    4 HITL        a human edit, picked up by the next read
    5 COMPOUND    read the lesson, approve the promotion, rebuild, ask again

--replay answers every completion and every embedding from traces/ and makes
no network call, so a rehearsal cannot be sunk by a client's guest wifi. It
also writes the date the run was recorded on rather than today's, because a
replayed run that dated its own records differently would rebuild to a
different corpus and miss the recordings it was replaying.

Those recordings do not have to have been made here. intelligence_capital_demo.py bless compacts a
good rehearsal into fixtures/recording/, which is committed, and reset --replay
installs it into traces/ - so the machine that presents the demo and the
machine that recorded it need not be the same machine. See recording.py.

What the demo does not do is touch storage on an agent's behalf. Everything
written here goes through propose_wiki_update, exactly as an agent's write
would, and lands on the same trace.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from inspect import signature
from pathlib import Path
from typing import Any

import case_close
import hitl
import recording
from agents import graph, llm
from agents.context import Orientation
from agents.llm import CompleteFn
from agents.risk_assessment_orchestrator import RunResult, orient_step
from ingest import layout, parse
from mcp_server import tools
from mcp_server.context import ToolContext, default_context
from stage import Stage
from stores import read_graph

DEFAULT_CASE = "SUB-2025-007"
TRACE_FILE = re.compile(r"^\d{4}-\d{2}-\d{2}\.jsonl$")

BRIEFING = "briefing.md"
DECISIONS = "decisions.md"

# What "reset" means, in the order it has to happen.
RESTORE = (["git", "checkout", "--", "wiki/"], ["git", "clean", "-fd", "wiki/"])

# How beat five regenerates the indexes. Passed in so a test can rebuild a
# sandbox corpus offline instead of shelling out to the real one.
RebuildFn = Callable[["Stage"], None]

CLAIMS = {
    1: (
        "ORIENT",
        (
            "The orchestrator reads the rules before it reads the case: every AGENTS.md "
            "from the wiki root down to the case, then index.md, then briefing.md. Direct "
            "file reads - orientation is handed to an agent, not retrieved by it - and "
            "every read costs tokens the room can see."
        ),
    ),
    2: (
        "RETRIEVE",
        (
            "Three specialists, dispatched in parallel, one MCP tool call and one model "
            "call each. Search returns ranked chunks carrying the id a claim has to cite; "
            "the traversal returns the entity subgraph. GraphRAG merges the two into one "
            "context block per specialist."
        ),
    ),
    3: (
        "WRITE BACK",
        (
            "Cross-validation is rule-based, so it says the same thing every rehearsal. "
            "The draft is composed once, normalised into house style, and written through "
            "propose_wiki_update - the only door into the wiki, guardrails and all."
        ),
    ),
    4: (
        "HITL",
        (
            "A human edits the markdown. There is nothing to import and nothing to "
            "re-index: the file is the store, so the next read simply has it."
        ),
    ),
    5: (
        "COMPOUND",
        (
            "The case closes. A write into platform-ic changes what every future case in "
            "the class retrieves, which makes it the strictest human gate in the "
            "architecture: the lesson goes on screen first and is approved after it has "
            "been read, never before. Once approved, the indexes are rebuilt from the "
            "markdown with one command, and the precedent query from beat two comes back "
            "with one more result than it did."
        ),
    ),
}


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the command line and run what it asked for."""
    parser = argparse.ArgumentParser(
        prog="intelligence_capital_demo.py", description="Run the living wiki demo."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    running = commands.add_parser("run", help="run the five beats")
    running.add_argument("--case", default=DEFAULT_CASE, help="case id to assess")
    running.add_argument("--replay", action="store_true", help="no network, recorded run")
    running.add_argument("--no-pause", action="store_true", help="do not wait between beats")
    resetting = commands.add_parser("reset", help="restore the wiki and rebuild the indexes")
    resetting.add_argument("--replay", action="store_true", help="rebuild from recorded vectors")
    commands.add_parser("bless", help="make the current traces the committed recording")

    arguments = parser.parse_args(argv)
    if arguments.command == "bless":
        return bless(Stage(paused=False))
    if arguments.command == "reset":
        return reset(Stage(paused=False), replay=bool(arguments.replay))
    return run(
        Stage(paused=not arguments.no_pause),
        case=str(arguments.case),
        replay=bool(arguments.replay),
    )


def run(stage: Stage, case: str, replay: bool) -> int:
    """Wire the demo up against the real wiki and run the beats over it."""
    mode = llm.REPLAY if replay else llm.LIVE
    os.environ["LLM_MODE"] = mode
    context = default_context()
    stamp = resolve_stamp(context.traces_dir, mode, case)

    stage.title(
        f"Intelligence Capital - living wiki - {case}",
        f" {mode} mode - model {llm.required_env('LLM_MODEL')} - records dated {stamp} ",
    )
    if replay:
        stage.note("replay: every completion and embedding comes from traces/, no network call")
    if dirty_wiki():
        stage.warn(
            "wiki has uncommitted changes - intelligence_capital_demo.py reset gives a clean rehearsal"
        )

    beats(stage, context, llm.complete, case, stamp, replay, rebuild_indexes)
    return 0


def beats(
    stage: Stage,
    context: ToolContext,
    complete: CompleteFn,
    case: str,
    stamp: str,
    replay: bool,
    rebuild: RebuildFn,
) -> RunResult:
    """The five beats, in order, pausing between them.

    Everything the beats need is passed in - the tools, the model, the command
    that rebuilds the indexes - so the sequence can be run over a sandbox wiki
    with a deterministic model and no network, which is what the tests do.
    """
    tail = TraceTail(context.traces_dir)
    whole_run = TraceTail(context.traces_dir)
    updates = graph.stream(context, complete, case, stamp)

    orientation = beat_orient(stage, updates, tail)
    stage.pause("beat 2 - retrieve")

    beat_retrieve(stage, updates, tail)
    stage.pause("beat 3 - write back")

    result = beat_write_back(stage, updates, tail, context, orientation)
    stage.pause("beat 4 - human in the loop")

    beat_hitl(stage, context, orientation, replay)
    stage.pause("beat 5 - compound")

    beat_compound(stage, context, orientation, stamp, tail, rebuild)
    closing(stage, context, result, whole_run.take())
    return result


def beat_orient(stage: Stage, updates: Iterator[tuple[str, Any]], tail: TraceTail) -> Orientation:
    """Beat one: the cascade read, with a running token count."""
    stage.beat(1, *CLAIMS[1])
    orientation: Orientation = collect(updates, graph.ORIENT)["orientation"]

    running = 0
    rows: list[list[str]] = []
    for file in orientation.files:
        running += file.tokens
        rows.append([file.path, file.role, f"{file.tokens:,}", f"{running:,}"])
    stage.table(["file", "role", "Tokens", "Running"], rows)
    stage.note(
        f"{len(orientation.files)} files, {orientation.total_tokens:,} tokens, no model call yet"
    )
    for missing in orientation.missing:
        stage.warn(f"not written yet: {missing}")
    stage.step(f"case {orientation.case_id} - {orientation.insured} - {orientation.risk_class}")
    stage.note("read directly from the wiki - no tool call, no retrieval, no model")
    tail.take()
    return orientation


def beat_retrieve(stage: Stage, updates: Iterator[tuple[str, Any]], tail: TraceTail) -> None:
    """Beat two: the three specialists, and everything they asked for."""
    stage.beat(2, *CLAIMS[2])
    collect(updates, graph.VALIDATE)
    lines = tail.take()
    echo(stage, lines)

    rows = [
        [
            str(line["args"]["agent"]),
            str(line["result"]["findings"]),
            " - ".join(str(flag) for flag in line["result"]["flags"]) or "-",
            f"{len(line['result']['citations'])}",
            f"{int(line['result']['context_tokens']):,}",
            f"{int(line['result']['tokens']):,}",
        ]
        for line in lines
        if line["tool"] == "agent.specialist"
    ]
    stage.step("specialists")
    stage.table(
        ["agent", "Findings", "flags", "Cited", "Context", "Tokens"],
        rows,
    )
    stage.note("context = the merged GraphRAG block and its task, as the model received it")

    for line in lines:
        if line["tool"] != "agent.cross_validate":
            continue
        issues = [str(issue) for issue in line["result"]["issues"]]
        stage.step(f"cross-validation: {'clean' if line['result']['ok'] else 'issues found'}")
        for issue in issues:
            stage.returned(issue)


def beat_write_back(
    stage: Stage,
    updates: Iterator[tuple[str, Any]],
    tail: TraceTail,
    context: ToolContext,
    orientation: Orientation,
) -> RunResult:
    """Beat three: compose, write through the tool, show what changed on disk."""
    stage.beat(3, *CLAIMS[3])
    briefing = hitl.target(context.wiki_dir, orientation.case_dir, BRIEFING)
    decisions = hitl.target(context.wiki_dir, orientation.case_dir, DECISIONS)
    briefed, decided = hitl.read(briefing), hitl.read(decisions)

    result: RunResult = collect(updates, graph.WRITE_BACK)["result"]
    lines = tail.take()
    echo(stage, lines)

    for line in lines:
        if line["tool"] == "agent.write_back" and int(line["result"]["normalised"]):
            stage.warn(
                f"{line['result']['normalised']} character(s) normalised into house style "
                "before the write"
            )
    stage.markdown(result.draft, title="composed draft")
    stage.diff(briefed, hitl.read(briefing), f"{orientation.case_dir}/{BRIEFING}")
    stage.markdown(added(decided, hitl.read(decisions)), title=f"new record in {DECISIONS}")
    return result


def beat_hitl(stage: Stage, context: ToolContext, orientation: Orientation, replay: bool) -> None:
    """Beat four: a human edit, and the read that picks it up.

    The comparison is taken from a fresh orientation rather than beat one's, so
    the numbers on screen are the cost of the human's edit and not of the draft
    the run itself wrote in between.
    """
    stage.beat(4, *CLAIMS[4])
    path = hitl.target(context.wiki_dir, orientation.case_dir)
    relative = f"{orientation.case_dir}/{BRIEFING}"
    before = hitl.read(path)
    current = orient_step(context, orientation.case_id)

    if replay:
        stage.human(f"scripted edit from {hitl.FIXTURE.relative_to(layout.REPO_ROOT)}")
        stage.note("replay applies the fixture so the rebuild in beat 5 finds its recordings")
        edit = hitl.apply_fixture(context.wiki_dir, orientation.case_dir, context.traces_dir)
    else:
        stage.human(f"open {relative} in Obsidian, add a note, save")
        stage.pause("edit applied")
        after = hitl.read(path)
        if after == before:
            stage.note("no edit typed - applying the scripted one instead")
            edit = hitl.apply_fixture(context.wiki_dir, orientation.case_dir, context.traces_dir)
        else:
            edit = hitl.typed_edit(relative, before, after, context.traces_dir)
            stage.warn("typed edit - re-record the traces before rehearsing this run in replay")

    stage.markdown(edit.section, title=f"human edit - {edit.path}")
    stage.step("the next read is a plain file read - nothing was imported or re-indexed")
    reread = orient_step(context, orientation.case_id)
    stage.compare(
        f"{relative} tokens",
        tokens_of(current, relative),
        tokens_of(reread, relative),
        [],
    )
    stage.compare("orientation tokens", current.total_tokens, reread.total_tokens, [])
    stage.note(f"beat 1 read this case at {orientation.total_tokens:,} tokens, before the draft")


def beat_compound(
    stage: Stage,
    context: ToolContext,
    orientation: Orientation,
    stamp: str,
    tail: TraceTail,
    rebuild: RebuildFn,
    lesson: case_close.Lesson = case_close.VENDOR_ACCESS,
) -> None:
    """Beat five: read the lesson, approve the promotion, rebuild, ask again.

    The order is the point. The draft is on screen before anything is written,
    the approval is a keypress the presenter has to make, and only then does the
    ceremony run - a gate that opens before the room has read what it is
    approving is not a gate.
    """
    stage.beat(5, *CLAIMS[5])
    stage.step("the beat 2 precedent query, before the case closes")
    tail.take()
    before = case_close.precedent_query(context, orientation.risk_class)
    echo(stage, tail.take())

    stage.step(f"drafted lesson {lesson.lesson_id} - nothing written yet")
    stage.markdown(lesson.platform_body, title=lesson.platform_path())
    stage.human(
        "platform-ic is the strictest gate in the architecture: this write changes what "
        f"every future {orientation.risk_class} case retrieves"
    )
    stage.note("approve or stop - there is no edit here, the wiki is where a human writes")
    stage.pause(f"approve {lesson.lesson_id} and promote")

    stage.step("case close - the human act, through the same write tool an agent uses")
    promotion = case_close.close_case(
        context,
        orientation.case_id,
        orientation.case_dir,
        orientation.risk_class,
        stamp,
        lesson,
    )
    echo(stage, tail.take())
    stage.note(f"promoted {promotion.lesson.lesson_id} -> {promotion.lesson.platform_path()}")

    rebuild(stage)

    stage.step("the same precedent query, argument for argument")
    tail.take()
    after = case_close.precedent_query(context, orientation.risk_class)
    echo(stage, tail.take())

    stage.compare(
        "results",
        before.results,
        after.results,
        sorted(set(after.chunk_ids + after.entity_ids) - set(before.chunk_ids + before.entity_ids)),
    )
    stage.note(
        f"chunks {len(before.chunk_ids)} -> {len(after.chunk_ids)}, "
        f"entities {len(before.entity_ids)} -> {len(after.entity_ids)}"
    )


def closing(
    stage: Stage, context: ToolContext, result: RunResult, lines: Sequence[Mapping[str, Any]]
) -> None:
    """What this run cost and where the record of it is.

    Counted from the lines this run added rather than the whole file: the trace
    is one file per day, and a rehearsal that ran an hour ago is not this run.
    """
    calls = [line for line in lines if not str(line["tool"]).startswith(("agent.", "demo."))]
    tokens = sum(int(line["result"].get("tokens", 0)) for line in lines if "result" in line)
    models = sum(int(line["result"].get("model_calls", 0)) for line in lines if "result" in line)
    stage.beat(0, "DONE", "Everything on screen is in the wiki and on the trace.")
    stage.table(
        ["what", "Count"],
        [
            ["MCP tool calls", str(len(calls))],
            ["model calls", str(models)],
            ["tokens through the agents", f"{tokens:,}"],
            [
                "wiki writes",
                str(len([line for line in calls if line["tool"] == "propose_wiki_update"])),
            ],
            ["case", result.case_id],
        ],
    )
    stage.note(f"trace: {context.traces_dir}")


def reset(stage: Stage, replay: bool = False) -> int:
    """Put the wiki back the way it is committed and rebuild every index.

    --replay installs the committed recording into traces/ and rebuilds from
    its embeddings rather than from the provider, so the index a replayed
    rehearsal retrieves from is the index its recordings were made against,
    vector for vector - on any machine, including one that has never recorded
    anything.
    """
    mode = llm.REPLAY if replay else llm.LIVE
    os.environ["LLM_MODE"] = mode
    stage.title("Reset", f" restore wiki/ from git, then rebuild the indexes - {mode} ")
    restore_wiki(stage)
    if replay:
        install_recording(stage)
    rebuild_indexes(stage)
    return 0


def bless(stage: Stage) -> int:
    """Make the traces of the rehearsal that just ran the recording the demo ships.

    Run this after a live run that went the way it should. What lands in
    fixtures/recording/ is committed, so the presenting machine needs nothing
    but the repo.
    """
    stage.title("Bless", " compact traces/ into the committed recording ")
    for written in recording.bless(layout.TRACES_DIR, recording.RECORDING_DIR):
        stage.step(f"{written.name} - {written.kept:,} kept, {written.dropped:,} superseded")
    stage.note(f"commit {_relative(recording.RECORDING_DIR)} - the recording travels with the repo")
    return 0


def install_recording(stage: Stage) -> None:
    """Put the committed recording into traces/, where replay already looks."""
    stage.step(f"install {_relative(recording.RECORDING_DIR)} -> {_relative(layout.TRACES_DIR)}")
    for written in recording.install(recording.RECORDING_DIR, layout.TRACES_DIR):
        stage.note(f"{written.kept:,} entries in {written.name}")


def restore_wiki(stage: Stage, root: Path = layout.REPO_ROOT) -> None:
    """Undo everything a run wrote: the edits, and the files it created.

    Both commands matter. checkout puts the tracked files back the way they are
    committed; clean removes what the run created, and a case's decisions.md is
    created by its first append, so a checkout on its own would leave the last
    rehearsal's decision record sitting in a "clean" wiki.
    """
    for command in RESTORE:
        stage.step(" ".join(command))
        for line in shell(command, root):
            stage.note(line)


def rebuild_indexes(stage: Stage) -> None:
    """Run the one command that regenerates every derived index, and count what came out."""
    stage.step("bash ingest/rebuild.sh")
    for line in shell(["bash", "ingest/rebuild.sh"]):
        stage.note(line)
    graph_counts = read_graph()
    stage.table(
        ["index", "Count"],
        [
            ["documents", f"{len(parse.read_documents()):,}"],
            ["chunks", f"{len(parse.read_chunks()):,}"],
            ["graph nodes", f"{len(graph_counts.nodes):,}"],
            ["graph edges", f"{len(graph_counts.edges):,}"],
        ],
    )


class TraceTail:
    """Whatever the tools have written since the last time the demo looked.

    The demo echoes calls from the trace rather than from inside the agents:
    the trace is what an auditor would read afterwards, so a demo that shows
    the same thing is showing something the client can check.
    """

    def __init__(self, traces_dir: Path) -> None:
        self._dir = traces_dir
        self._seen = len(self.all())

    def all(self) -> list[dict[str, Any]]:
        """Every trace line written today, in order. Payload caches are not traces."""
        paths = sorted(path for path in self._dir.glob("*.jsonl") if TRACE_FILE.match(path.name))
        return [line for path in paths for line in _read_json_lines(path)]

    def take(self) -> list[dict[str, Any]]:
        """The lines written since the last take()."""
        lines = self.all()
        fresh = lines[self._seen :]
        self._seen = len(lines)
        return fresh


def echo(stage: Stage, lines: Sequence[Mapping[str, Any]]) -> None:
    """Print each traced tool call the way it was made, and what came back.

    Agent steps are on the same trace and are not echoed here: they are the
    orchestrator accounting for itself, and the beats report them as what they
    are - findings, flags, token costs - rather than as calls.
    """
    for line in lines:
        tool = str(line["tool"])
        if tool.startswith("agent."):
            continue
        args = in_signature_order(tool, dict(line["args"]))
        stage.call(tool, args)
        if line["status"] != "ok":
            stage.refused(str(line["result"]["error"]))
            continue
        for summary in _summary(tool, dict(line["result"])):
            stage.returned(summary)


def in_signature_order(tool: str, args: Mapping[str, Any]) -> dict[str, Any]:
    """Traced arguments, back in the order the tool declares them.

    A trace line is JSON with sorted keys, and an echo that read
    "search_knowledge_base(path_prefix=None, query=...)" would not be the call
    anyone wrote. The order comes from the tool's own signature rather than a
    list kept here, so it cannot drift from the contract.
    """
    function = getattr(tools, tool, None)
    declared = [name for name in signature(function).parameters if name in args] if function else []
    return {name: args[name] for name in (*declared, *(set(args) - set(declared)))}


def collect(updates: Iterator[tuple[str, Any]], until: str) -> dict[str, Any]:
    """Pull graph updates until the named node has produced its result."""
    produced: dict[str, Any] = {}
    for node, update in updates:
        produced.update(update)
        if node == until:
            return produced
    raise RuntimeError(f"the run ended before {until} produced anything")


def resolve_stamp(traces_dir: Path, mode: str, case: str) -> str:
    """The date this run writes its records under.

    A live run uses today and records it. A replayed run uses the date of the
    run it is replaying: the wiki it rebuilds in beat five has to match the
    corpus the embeddings were recorded from, down to the dates in the headings.
    """
    path = traces_dir / recording.RUNS_FILE
    if mode == llm.REPLAY:
        recorded = _read_json_lines(path)
        if not recorded:
            raise RuntimeError(
                f"nothing to replay: {path} holds no recorded run - "
                "run intelligence_capital_demo.py run live once to record one"
            )
        return str(recorded[-1]["stamp"])
    stamp = datetime.now(UTC).date().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        line = {"ts": datetime.now(UTC).isoformat(), "stamp": stamp, "case": case, "mode": mode}
        handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
    return stamp


def added(before: str, after: str) -> str:
    """The text a write appended to a file."""
    return after[len(before) :].strip() if after.startswith(before) else after.strip()


def tokens_of(orientation: Orientation, path: str) -> int:
    """What one file of an orientation cost, or 0 if it was not there."""
    return next((file.tokens for file in orientation.files if file.path == path), 0)


def _relative(path: Path) -> str:
    """A repo path the way someone would type it. Anything else, in full."""
    if not path.is_relative_to(layout.REPO_ROOT):
        return str(path)
    return path.relative_to(layout.REPO_ROOT).as_posix()


def dirty_wiki() -> bool:
    """True when wiki/ carries changes an earlier run left behind."""
    return any(shell(["git", "status", "--porcelain", "wiki/"]))


def shell(command: Sequence[str], cwd: Path = layout.REPO_ROOT) -> list[str]:
    """Run a command in the repo and return its output, or raise with its error."""
    finished = subprocess.run(
        list(command),
        cwd=cwd,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
        check=False,
    )
    if finished.returncode:
        raise RuntimeError(f"{' '.join(command)} failed: {finished.stderr.strip()}")
    return [line for line in finished.stdout.splitlines() if line.strip()]


def _summary(tool: str, result: Mapping[str, Any]) -> list[str]:
    """What a tool returned, in the shortest form that is still checkable."""
    if tool == "search_knowledge_base":
        pairs = zip(result["chunk_ids"], result.get("scores", []))
        return [f"{len(result['chunk_ids'])} chunks"] + [
            f"  {chunk_id}  {float(score):.3f}" for chunk_id, score in pairs
        ]
    if tool == "traverse_graph":
        return [
            f"{result['nodes']} entities, {result['edges']} relations",
            "  " + " - ".join(str(node) for node in result["node_ids"]),
        ]
    if tool == "read_case_context":
        return [f"{result['documents']} documents, {result['total_tokens']:,} tokens"]
    if tool == "propose_wiki_update":
        state = "created" if result["created"] else "appended"
        return [f"{state} {result['path']} ({result['bytes_written']:,} bytes)"]
    if tool == "demo.human_edit":
        return [f"{result['chars']:,} characters written by hand"]
    return [", ".join(f"{name}={value}" for name, value in result.items())]


def _read_json_lines(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


if __name__ == "__main__":
    sys.exit(main())
