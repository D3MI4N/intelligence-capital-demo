"""Typed records the ingest pipeline produces, and their JSON form."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

Frontmatter = dict[str, object]


@dataclass(frozen=True)
class WikiLink:
    """An Obsidian wikilink. The label is text, the target is a graph edge."""

    target: str
    label: str


@dataclass(frozen=True)
class Document:
    """One markdown file, frontmatter separated from body."""

    doc_id: str  # repo-relative posix path, e.g. wiki/claims/CLM-2024-042/index.md
    source: str  # "wiki" or "raw"
    title: str
    frontmatter: Frontmatter
    text: str  # body with frontmatter removed, wikilinks left intact
    links: tuple[WikiLink, ...]


@dataclass(frozen=True)
class Chunk:
    """A retrievable slice of a document, carrying its own provenance."""

    chunk_id: str  # "<doc_id>#c000"
    doc_id: str
    source: str
    ordinal: int
    heading_path: tuple[str, ...]
    text: str  # heading context prepended, wikilinks rendered as their label
    tokens: int
    frontmatter: Frontmatter
    references: tuple[str, ...]  # wikilink targets found in this chunk


def document_to_json(document: Document) -> dict[str, Any]:
    return {
        "doc_id": document.doc_id,
        "source": document.source,
        "title": document.title,
        "frontmatter": document.frontmatter,
        "text": document.text,
        "links": [{"target": link.target, "label": link.label} for link in document.links],
    }


def document_from_json(raw: dict[str, Any]) -> Document:
    links = tuple(
        WikiLink(target=str(link["target"]), label=str(link["label"])) for link in raw["links"]
    )
    return Document(
        doc_id=str(raw["doc_id"]),
        source=str(raw["source"]),
        title=str(raw["title"]),
        frontmatter=cast(Frontmatter, raw["frontmatter"]),
        text=str(raw["text"]),
        links=links,
    )


def chunk_to_json(chunk: Chunk) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "source": chunk.source,
        "ordinal": chunk.ordinal,
        "heading_path": list(chunk.heading_path),
        "text": chunk.text,
        "tokens": chunk.tokens,
        "frontmatter": chunk.frontmatter,
        "references": list(chunk.references),
    }


def chunk_from_json(raw: dict[str, Any]) -> Chunk:
    return Chunk(
        chunk_id=str(raw["chunk_id"]),
        doc_id=str(raw["doc_id"]),
        source=str(raw["source"]),
        ordinal=int(raw["ordinal"]),
        heading_path=tuple(str(item) for item in raw["heading_path"]),
        text=str(raw["text"]),
        tokens=int(raw["tokens"]),
        frontmatter=cast(Frontmatter, raw["frontmatter"]),
        references=tuple(str(item) for item in raw["references"]),
    )
