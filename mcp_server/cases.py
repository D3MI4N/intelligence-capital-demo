"""Find a case in the wiki and collect the files that orient an agent to it.

A case is a directory named after its id - wiki/claims/CLM-2024-042 - holding
an index.md. That convention is the whole lookup: no registry file to keep in
step with the tree, and a case created by hand during the demo is findable on
the next call.

The AGENTS.md cascade is every AGENTS.md from the wiki root down to the case
directory, outermost first. Platform rules, then domain rules, then case
rules, each extending the last rather than repeating it, which is why the
order matters and why all of them are returned rather than the nearest one.
"""

from __future__ import annotations

import re
from pathlib import Path

from errors import UnknownCase
from ingest import layout

RULES_FILE = "AGENTS.md"
INDEX_FILE = "index.md"
BRIEFING_FILE = "briefing.md"

# Case ids are codes, not paths. Anything else is rejected before it is used
# to build a path.
CASE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def known_cases(wiki_dir: Path = layout.WIKI_DIR) -> tuple[str, ...]:
    """Every case id in the wiki, sorted."""
    return tuple(sorted(path.parent.name for path in wiki_dir.glob(f"*/*/{INDEX_FILE}")))


def case_dir(case_id: str, wiki_dir: Path = layout.WIKI_DIR) -> Path:
    """The directory holding a case, or a refusal naming the ids that do exist."""
    if not CASE_ID_PATTERN.match(case_id):
        raise UnknownCase(f"'{case_id}' is not a case id - ids look like CLM-2024-042")
    directory = None
    for candidate in sorted(wiki_dir.glob(f"*/{case_id}")):
        if (candidate / INDEX_FILE).is_file():
            directory = candidate
            break
    if directory is None:
        known = " - ".join(known_cases(wiki_dir)) or "none"
        raise UnknownCase(f"unknown case '{case_id}' - the wiki holds: {known}")
    return directory


def cascade(directory: Path, wiki_dir: Path = layout.WIKI_DIR) -> tuple[Path, ...]:
    """Every AGENTS.md from the wiki root down to directory, outermost first."""
    found: list[Path] = []
    current = wiki_dir
    for part in ("", *directory.relative_to(wiki_dir).parts):
        current = current / part if part else current
        rules = current / RULES_FILE
        if rules.is_file():
            found.append(rules)
    return tuple(found)


def context_files(directory: Path, wiki_dir: Path = layout.WIKI_DIR) -> tuple[Path, ...]:
    """The cascade, then index.md, then briefing.md - the order an agent reads them."""
    return (*cascade(directory, wiki_dir), directory / INDEX_FILE, directory / BRIEFING_FILE)


def role_of(path: Path) -> str:
    """What a context file is for, as the reader should label it."""
    if path.name == RULES_FILE:
        return "rules"
    if path.name == INDEX_FILE:
        return "index"
    if path.name == BRIEFING_FILE:
        return "briefing"
    return "document"
