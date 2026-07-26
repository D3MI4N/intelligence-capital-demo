"""Markdown-aware chunking.

Split on headings, then pack adjacent sections up to the target size. Every
chunk carries its heading context at the top so a retrieved slice still says
which document and which section it came from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ingest.tokens import estimate_tokens

TARGET_TOKENS = 300  # stop packing once a chunk has reached this size
MAX_TOKENS = 500  # never emit a chunk larger than this if it can be split

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Heading:
    level: int
    title: str

    def render(self) -> str:
        return f"{'#' * self.level} {self.title}"


@dataclass(frozen=True)
class Section:
    """One heading and the body under it, before any of its subsections."""

    path: tuple[Heading, ...]  # ancestors, own heading last; empty for a preamble
    body: str

    @property
    def titles(self) -> tuple[str, ...]:
        return tuple(heading.title for heading in self.path)


@dataclass(frozen=True)
class TextChunk:
    """Chunk text plus the heading path it started from."""

    text: str
    heading_path: tuple[str, ...]
    tokens: int


def split_sections(body: str) -> list[Section]:
    """Split a markdown body into sections, one per heading plus any preamble."""
    sections: list[Section] = []
    stack: list[Heading] = []
    buffer: list[str] = []
    in_fence = False

    def flush() -> None:
        text = "\n".join(buffer).strip("\n")
        if text or stack:
            sections.append(Section(path=tuple(stack), body=text))
        buffer.clear()

    for line in body.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if match is None:
            buffer.append(line)
            continue
        flush()
        heading = Heading(level=len(match.group(1)), title=match.group(2).strip())
        while stack and stack[-1].level >= heading.level:
            stack.pop()
        stack.append(heading)
    flush()
    return sections


def chunk_sections(sections: list[Section]) -> list[TextChunk]:
    """Pack sections into chunks of roughly TARGET_TOKENS, never over MAX_TOKENS."""
    chunks: list[TextChunk] = []
    pack: list[Section] = []

    def flush_pack() -> None:
        if not pack:
            return
        text = _render_pack(pack)
        if text.strip():
            chunks.append(
                TextChunk(text=text, heading_path=pack[0].titles, tokens=estimate_tokens(text))
            )
        pack.clear()

    for section in sections:
        rendered = _render_pack([section])
        if not rendered.strip():
            continue
        size = estimate_tokens(rendered)

        if size > MAX_TOKENS:
            flush_pack()
            chunks.extend(_split_oversized(section))
            continue

        if pack:
            packed = estimate_tokens(_render_pack(pack))
            if packed >= TARGET_TOKENS or packed + size > MAX_TOKENS:
                flush_pack()
        pack.append(section)

    flush_pack()
    return chunks


def _render_pack(pack: list[Section]) -> str:
    """Heading context of the first section, then each section's own heading."""
    parts: list[str] = []
    first = pack[0]
    context = "\n".join(heading.render() for heading in first.path)
    if context:
        parts.append(context)
    if first.body:
        parts.append(first.body)
    for section in pack[1:]:
        if section.path:
            parts.append(section.path[-1].render())
        if section.body:
            parts.append(section.body)
    return "\n\n".join(parts)


def _split_oversized(section: Section) -> list[TextChunk]:
    """Split one long section on paragraph, then line, then word boundaries."""
    context = "\n".join(heading.render() for heading in section.path)
    overhead = estimate_tokens(context) if context else 0
    budget = max(MAX_TOKENS - overhead, 1)

    pieces = _pack_units(_paragraphs(section.body), budget, separator="\n\n")
    chunks: list[TextChunk] = []
    for piece in pieces:
        text = f"{context}\n\n{piece}" if context else piece
        chunks.append(
            TextChunk(text=text, heading_path=section.titles, tokens=estimate_tokens(text))
        )
    return chunks


def _paragraphs(body: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", body) if block.strip()]


def _pack_units(units: list[str], budget: int, separator: str) -> list[str]:
    """Greedily group units so each group fits the budget, splitting what cannot."""
    groups: list[str] = []
    current: list[str] = []

    for unit in units:
        if estimate_tokens(unit) > budget:
            if current:
                groups.append(separator.join(current))
                current = []
            groups.extend(_split_unit(unit, budget))
            continue
        candidate = separator.join([*current, unit])
        if current and estimate_tokens(candidate) > budget:
            groups.append(separator.join(current))
            current = [unit]
        else:
            current.append(unit)

    if current:
        groups.append(separator.join(current))
    return groups


def _split_unit(unit: str, budget: int) -> list[str]:
    """A single unit that is too big: try lines, then words."""
    lines = [line for line in unit.splitlines() if line.strip()]
    if len(lines) > 1:
        return _pack_units(lines, budget, separator="\n")
    words = unit.split()
    if len(words) > 1:
        return _pack_units(words, budget, separator=" ")
    return [unit]
