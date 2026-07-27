from pathlib import Path

from ingest.parse import parse_corpus, read_chunks, read_documents, write_records

Roots = tuple[tuple[str, Path], ...]


def test_only_markdown_outside_hidden_directories_is_ingested(corpus: Roots) -> None:
    documents, _ = parse_corpus(corpus)

    ids = [document.doc_id for document in documents]
    assert "wiki/notes.txt" not in ids
    assert "wiki/.obsidian/private.md" not in ids
    assert not any(identifier.endswith(".gitkeep") for identifier in ids)
    assert "raw/testco-survey.md" in ids


def test_doc_ids_are_source_prefixed_paths_in_order(corpus: Roots) -> None:
    documents, _ = parse_corpus(corpus)

    assert [document.doc_id for document in documents] == [
        "wiki/AGENTS.md",
        "wiki/claims/AGENTS.md",
        "wiki/claims/CLM-9999-001/AGENTS.md",
        "wiki/claims/CLM-9999-001/briefing.md",
        "wiki/claims/CLM-9999-001/decisions.md",
        "wiki/claims/CLM-9999-001/index.md",
        "wiki/claims/CLM-9999-001/lessons.md",
        "wiki/claims/CLM-9999-001/sources/note.md",
        "wiki/platform-ic/skills/precedent.md",
        "wiki/submissions/SUB-9999-001/index.md",
        "wiki/vocabulary/perils.md",
        "raw/testco-survey.md",
    ]


def test_title_comes_from_the_first_heading(corpus: Roots) -> None:
    documents, _ = parse_corpus(corpus)
    by_id = {document.doc_id: document for document in documents}

    assert by_id["wiki/claims/CLM-9999-001/index.md"].title == "CLM-9999-001 - Testco - Ransomware"


def test_frontmatter_is_copied_onto_every_chunk(corpus: Roots) -> None:
    documents, chunks = parse_corpus(corpus)
    by_id = {document.doc_id: document for document in documents}

    for chunk in chunks:
        assert chunk.frontmatter == by_id[chunk.doc_id].frontmatter
    assert any(chunk.frontmatter.get("case_id") == "CLM-9999-001" for chunk in chunks)


def test_chunk_ids_are_ordinal_suffixed_doc_ids(corpus: Roots) -> None:
    _, chunks = parse_corpus(corpus)

    for chunk in chunks:
        assert chunk.chunk_id == f"{chunk.doc_id}#c{chunk.ordinal:03d}"


def test_wikilink_labels_are_text_and_paths_are_references(corpus: Roots) -> None:
    _, chunks = parse_corpus(corpus)
    by_id = {chunk.chunk_id: chunk for chunk in chunks}

    chunk = by_id["wiki/claims/CLM-9999-001/index.md#c000"]
    assert "SUB-9999-001 - the originating submission" in chunk.text
    assert "[[" not in chunk.text
    assert "submissions/SUB-9999-001/index" in chunk.references


def test_frontmatter_is_not_part_of_chunk_text(corpus: Roots) -> None:
    _, chunks = parse_corpus(corpus)

    assert all("case_id:" not in chunk.text for chunk in chunks)


def test_records_round_trip_through_disk(corpus: Roots, tmp_path: Path) -> None:
    documents, chunks = parse_corpus(corpus)
    documents_path = tmp_path / "out" / "documents.json"
    chunks_path = tmp_path / "out" / "chunks.json"

    write_records(documents, chunks, documents_path, chunks_path)

    assert read_documents(documents_path) == documents
    assert read_chunks(chunks_path) == chunks
