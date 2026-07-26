"""Walk the markdown trees and produce Document and Chunk records.

This is the only place that reads the primary store. Everything downstream
works from the records written here, so a rebuild starts by re-running parse.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ingest import layout
from ingest.chunker import chunk_sections, split_sections
from ingest.frontmatter import split_frontmatter
from ingest.models import (
    Chunk,
    Document,
    chunk_from_json,
    chunk_to_json,
    document_from_json,
    document_to_json,
)
from ingest.wikilinks import find_wikilinks, render_labels, targets

MARKDOWN_SUFFIX = ".md"


def parse_document(path: Path, source: str, root: Path) -> Document:
    """Read one markdown file into a Document."""
    text = path.read_text(encoding="utf-8")
    frontmatter, body = split_frontmatter(text)
    doc_id = f"{source}/{path.relative_to(root).as_posix()}"
    return Document(
        doc_id=doc_id,
        source=source,
        title=_title(body) or path.stem,
        frontmatter=frontmatter,
        text=body,
        links=find_wikilinks(body),
    )


def parse_tree(source: str, root: Path) -> list[Document]:
    """Every markdown file under root, in path order. Non-markdown is skipped."""
    if not root.is_dir():
        return []
    documents: list[Document] = []
    for path in sorted(root.rglob(f"*{MARKDOWN_SUFFIX}")):
        if _hidden(path.relative_to(root)) or not path.is_file():
            continue
        documents.append(parse_document(path, source, root))
    return documents


def skipped_files(source: str, root: Path) -> list[tuple[str, str]]:
    """Files under root that ingest leaves out, each with the reason why."""
    if not root.is_dir():
        return []
    skipped: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        name = f"{source}/{relative.as_posix()}"
        if _hidden(relative):
            skipped.append((name, "hidden path"))
        elif path.suffix != MARKDOWN_SUFFIX:
            skipped.append((name, "not markdown"))
    return skipped


def parse_corpus(
    roots: tuple[tuple[str, Path], ...] | None = None,
) -> tuple[
    list[Document],
    list[Chunk],
]:
    """Parse every source tree and chunk every document."""
    documents: list[Document] = []
    for source, root in roots if roots is not None else layout.source_roots():
        documents.extend(parse_tree(source, root))
    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    return documents, chunks


def chunk_document(document: Document) -> list[Chunk]:
    """Split a document into chunks, frontmatter copied onto each one."""
    chunks: list[Chunk] = []
    for ordinal, piece in enumerate(chunk_sections(split_sections(document.text))):
        text = render_labels(piece.text)
        chunks.append(
            Chunk(
                chunk_id=f"{document.doc_id}#c{ordinal:03d}",
                doc_id=document.doc_id,
                source=document.source,
                ordinal=ordinal,
                heading_path=piece.heading_path,
                text=text,
                tokens=piece.tokens,
                frontmatter=dict(document.frontmatter),
                references=targets(piece.text),
            )
        )
    return chunks


def write_records(
    documents: list[Document],
    chunks: list[Chunk],
    documents_path: Path = layout.DOCUMENTS_PATH,
    chunks_path: Path = layout.CHUNKS_PATH,
) -> None:
    """Persist the parsed records for the embed and graph steps."""
    documents_path.parent.mkdir(parents=True, exist_ok=True)
    chunks_path.parent.mkdir(parents=True, exist_ok=True)
    _dump([document_to_json(document) for document in documents], documents_path)
    _dump([chunk_to_json(chunk) for chunk in chunks], chunks_path)


def read_documents(path: Path = layout.DOCUMENTS_PATH) -> list[Document]:
    return [document_from_json(raw) for raw in json.loads(path.read_text(encoding="utf-8"))]


def read_chunks(path: Path = layout.CHUNKS_PATH) -> list[Chunk]:
    return [chunk_from_json(raw) for raw in json.loads(path.read_text(encoding="utf-8"))]


def _dump(payload: object, path: Path) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _title(body: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _hidden(relative: Path) -> bool:
    return any(part.startswith(".") for part in relative.parts)


def main(argv: list[str] | None = None) -> None:
    verbose = "--verbose" in (sys.argv[1:] if argv is None else argv)
    documents, chunks = parse_corpus()
    write_records(documents, chunks)
    total_tokens = sum(chunk.tokens for chunk in chunks)
    print(f"parse: files={len(documents)} chunks={len(chunks)} tokens~{total_tokens}")

    if verbose:
        skipped = [
            entry for source, root in layout.source_roots() for entry in skipped_files(source, root)
        ]
        print(f"parse: skipped={len(skipped)}")
        for name, reason in skipped:
            print(f"  - {name} ({reason})")


if __name__ == "__main__":
    main()
