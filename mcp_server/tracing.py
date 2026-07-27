"""Every tool call leaves one line behind.

One JSONL file per day under traces/, one line per call, appended and never
rewritten. The line records what was asked and what came back in summary -
counts, ids, paths - not the payload itself. A trace is an audit record of
what an agent did, and it has to stay readable and cheap to keep; the chunk
text is in the index and the wiki text is in the wiki, both reachable from the
ids on the line.

Refusals are traced too, with status "error". A tool that declined is part of
what happened in the run, and the demo's replay reads these files.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from ingest import layout

OK = "ok"
ERROR = "error"


def append(
    tool: str,
    args: Mapping[str, object],
    result: Mapping[str, object],
    status: str = OK,
    traces_dir: Path = layout.TRACES_DIR,
) -> Path:
    """Write one trace line and return the file it went to."""
    stamped = datetime.now(UTC)
    path = traces_dir / f"{stamped.date().isoformat()}.jsonl"
    line = {
        "ts": stamped.isoformat(),
        "tool": tool,
        "status": status,
        "args": dict(args),
        "result": dict(result),
    }
    traces_dir.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def read(path: Path) -> list[dict[str, object]]:
    """Parse a trace file back, in the order the calls were made."""
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]
