"""The only way an agent changes the wiki, and the rules that stop it.

The wiki is the primary store, so an agent write is a real edit to a real file
a human will open next. Four guardrails decide whether it happens at all:

  - the path must resolve inside wiki/ and end in .md. A path that climbs out,
    by traversal or through a symlink, is refused, not clamped
  - decisions.md is append only. A decision record is the audit trail of who
    decided what and when - it is added to, never rewritten. The first append
    to a case that has none creates the file; that is still append only
  - AGENTS.md files are human-only. They are the instructions the agents run
    under, and an agent that can edit its own instructions is not governed
  - vocabulary/ is human-only. The graph is built from these terms, so an
    agent that could add one would be inventing the language it is judged in.
    Agents propose new terms in lessons.md instead

Everything a refusal needs to say is in the message: what was asked, and what
would have been allowed instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from errors import WriteRefused
from ingest import layout

APPEND_SECTION = "append_section"
REPLACE_SECTION = "replace_section"
CREATE_FILE = "create_file"
OPERATIONS = (APPEND_SECTION, REPLACE_SECTION, CREATE_FILE)

APPEND_ONLY = ("decisions.md",)
HUMAN_ONLY_FILES = ("AGENTS.md",)
HUMAN_ONLY_DIRS = ("vocabulary",)

MARKDOWN_SUFFIX = ".md"
HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")


@dataclass(frozen=True)
class WriteOutcome:
    """What a write did, for the caller and for the trace."""

    path: Path
    operation: str
    section: str | None
    created: bool
    bytes_written: int


def apply(
    path: str, operation: str, content: str, wiki_dir: Path = layout.WIKI_DIR
) -> WriteOutcome:
    """Check a proposed write against every guardrail, then perform it."""
    if operation not in OPERATIONS:
        raise WriteRefused(f"unknown operation '{operation}' - use {' - '.join(OPERATIONS)}")
    if not content.strip():
        raise WriteRefused("content is empty - nothing to write")

    target = resolve(path, wiki_dir)
    check_writable(target, operation, wiki_dir)

    if operation == CREATE_FILE:
        return _create_file(target, content)
    if operation == APPEND_SECTION:
        return _append_section(target, content)
    return _replace_section(target, content)


def resolve(path: str, wiki_dir: Path = layout.WIKI_DIR) -> Path:
    """Turn a proposed path into a real one under wiki/, or refuse it.

    Accepts what the wiki itself uses: a repo path (wiki/claims/.../x.md), a
    vault-root path (claims/.../x.md), or an absolute path. All three are
    resolved before the check, so symlinks and .. cannot escape.
    """
    root = wiki_dir.resolve()
    given = Path(path)
    if given.is_absolute():
        target = given.resolve()
    else:
        parts = given.parts
        relative = Path(*parts[1:]) if parts and parts[0] == root.name else given
        target = (root / relative).resolve()

    if target == root or not target.is_relative_to(root):
        raise WriteRefused(f"path '{path}' is outside the wiki - writes go under {root.name}/ only")
    if target.suffix != MARKDOWN_SUFFIX:
        raise WriteRefused(f"path '{path}' is not markdown - the wiki holds .md files")
    return target


def check_writable(target: Path, operation: str, wiki_dir: Path = layout.WIKI_DIR) -> None:
    """Refuse the human-only files, and refuse anything but append on append-only ones."""
    relative = target.relative_to(wiki_dir.resolve())
    if target.name in HUMAN_ONLY_FILES:
        raise WriteRefused(
            f"{target.name} is human-only - agents do not edit the instructions they run "
            "under. Propose the change in lessons.md"
        )
    if relative.parts[0] in HUMAN_ONLY_DIRS:
        raise WriteRefused(
            f"{relative.parts[0]}/ is human-only - the graph is built from these terms. "
            "Propose a new term in lessons.md"
        )
    if target.name in APPEND_ONLY and operation != APPEND_SECTION:
        raise WriteRefused(
            f"{target.name} is append-only - use {APPEND_SECTION}. A decision record is "
            "never rewritten"
        )


def headings(text: str) -> tuple[str, ...]:
    """Every heading line in a document, as written."""
    return tuple(line.strip() for line in text.splitlines() if HEADING.match(line.strip()))


def _create_file(target: Path, content: str) -> WriteOutcome:
    if target.exists():
        raise WriteRefused(
            f"{target.name} already exists - use {APPEND_SECTION} or {REPLACE_SECTION}"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    return _write(target, _body(content), CREATE_FILE, _first_heading(content), created=True)


def _append_section(target: Path, content: str) -> WriteOutcome:
    if not target.is_file():
        return _append_to_a_file_that_is_not_there_yet(target, content)
    existing = _read(target)
    body = f"{existing.rstrip()}\n\n{_body(content)}" if existing.strip() else _body(content)
    return _write(target, body, APPEND_SECTION, _first_heading(content), created=False)


def _append_to_a_file_that_is_not_there_yet(target: Path, content: str) -> WriteOutcome:
    """An append-only file is created by its first append. Anything else is not.

    A case that has taken no decisions yet has no decisions.md, and create_file
    is refused on one, so the first record would have nowhere to go. Creating
    it by appending is the same guarantee either way: the file only ever grows.

    Every other file has create_file available, so refusing here keeps a
    mistyped path from quietly becoming a new document.
    """
    if target.name not in APPEND_ONLY:
        raise WriteRefused(f"{target.name} does not exist - use {CREATE_FILE} first")
    target.parent.mkdir(parents=True, exist_ok=True)
    return _write(target, _body(content), APPEND_SECTION, _first_heading(content), created=True)


def _replace_section(target: Path, content: str) -> WriteOutcome:
    existing = _read(target)
    heading = _first_heading(content)
    if heading is None:
        raise WriteRefused(
            f"{REPLACE_SECTION} needs content that starts with the heading of the section "
            "to replace, for example '## Assessment'"
        )
    lines = existing.splitlines()
    start = _heading_line(lines, heading)
    if start is None:
        known = " - ".join(headings(existing)) or "none"
        raise WriteRefused(
            f"{target.name} has no section '{heading}' - it has: {known}. "
            f"Use {APPEND_SECTION} to add one"
        )
    level = _level(heading)
    end = len(lines)
    for index in range(start + 1, len(lines)):
        match = HEADING.match(lines[index].strip())
        if match and len(match.group(1)) <= level:
            end = index
            break
    replaced = [*lines[:start], *_body(content).splitlines(), "", *lines[end:]]
    return _write(target, "\n".join(replaced), REPLACE_SECTION, heading, created=False)


def _read(target: Path) -> str:
    if not target.is_file():
        raise WriteRefused(f"{target.name} does not exist - use {CREATE_FILE} first")
    return target.read_text(encoding="utf-8")


def _write(
    target: Path, body: str, operation: str, section: str | None, created: bool
) -> WriteOutcome:
    payload = body.rstrip() + "\n"
    target.write_text(payload, encoding="utf-8")
    return WriteOutcome(
        path=target,
        operation=operation,
        section=section,
        created=created,
        bytes_written=len(payload.encode("utf-8")),
    )


def _body(content: str) -> str:
    return content.strip("\n").rstrip()


def _first_heading(content: str) -> str | None:
    first = content.strip().splitlines()[0].strip()
    return first if HEADING.match(first) else None


def _heading_line(lines: list[str], heading: str) -> int | None:
    for index, line in enumerate(lines):
        if line.strip() == heading:
            return index
    return None


def _level(heading: str) -> int:
    match = HEADING.match(heading)
    return len(match.group(1)) if match else 1
