"""The human edit in the loop, and how a rehearsal reproduces one.

The claim this beat makes is that the markdown is the primary store: a human
opens a file in Obsidian, types, saves, and the next run reads what they wrote.
There is nothing to import and nothing to re-index, so a human edit is a plain
file write - not a tool call, and not something an agent could have done.

Live, the presenter makes that edit themselves. In replay, a checked-in fixture
stands in for them, because a rehearsal that depends on someone typing the same
sentence twice is not a rehearsal: the same edit produces the same corpus, the
same chunk texts and the same recorded embeddings when beat five rebuilds. The
screen says which of the two happened, every time.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path

from ingest import layout
from mcp_server import tracing

FIXTURE = layout.REPO_ROOT / "fixtures" / "hitl-edit.md"
BRIEFING = "briefing.md"


@dataclass(frozen=True)
class Edit:
    """One human edit to one file."""

    path: str  # wiki/submissions/SUB-2025-007/briefing.md
    section: str  # what the human added
    scripted: bool  # applied from the fixture rather than typed on the night


def target(wiki_dir: Path, case_dir: str, name: str = BRIEFING) -> Path:
    """The file the human edits: the case briefing, by default."""
    return wiki_dir.parent / case_dir / name


def read(path: Path) -> str:
    """What the file says now, for comparing before and after."""
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def apply_fixture(
    wiki_dir: Path,
    case_dir: str,
    traces_dir: Path,
    fixture: Path = FIXTURE,
    name: str = BRIEFING,
) -> Edit:
    """Append the scripted edit to the case file, as a human's editor would.

    Deliberately a direct write. propose_wiki_update is the agents' door and
    this is not an agent - the wiki rules say direct writes are for humans. The
    trace still records that the demo did it, because a run nobody can
    reconstruct is not an auditable run.
    """
    section = fixture.read_text(encoding="utf-8").strip()
    path = target(wiki_dir, case_dir, name)
    existing = read(path)
    body = f"{existing.rstrip()}\n\n{section}\n" if existing.strip() else f"{section}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")

    edit = Edit(path=f"{case_dir}/{name}", section=section, scripted=True)
    tracing.append(
        "demo.human_edit",
        {"path": edit.path, "source": str(fixture.relative_to(layout.REPO_ROOT))},
        {"scripted": True, "chars": len(section)},
        tracing.OK,
        traces_dir,
    )
    return edit


def typed_edit(path: str, before: str, after: str, traces_dir: Path) -> Edit:
    """Record an edit the presenter made themselves, and return what changed."""
    section = "\n".join(_added(before, after)).strip()
    tracing.append(
        "demo.human_edit",
        {"path": path, "source": "typed in the editor"},
        {"scripted": False, "chars": len(section)},
        tracing.OK,
        traces_dir,
    )
    return Edit(path=path, section=section, scripted=False)


def _added(before: str, after: str) -> list[str]:
    """The lines the human added, in order."""
    changed = difflib.ndiff(before.splitlines(), after.splitlines())
    return [line[2:] for line in changed if line.startswith("+ ")]
