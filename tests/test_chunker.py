from ingest.chunker import MAX_TOKENS, TARGET_TOKENS, chunk_sections, split_sections
from ingest.tokens import estimate_tokens


def test_sections_carry_their_heading_path() -> None:
    body = "intro line\n\n# Top\n\nfirst\n\n## Nested\n\nsecond\n\n# Other\n\nthird\n"

    sections = split_sections(body)

    assert [section.titles for section in sections] == [
        (),
        ("Top",),
        ("Top", "Nested"),
        ("Other",),
    ]
    assert sections[2].body == "second"


def test_headings_inside_code_fences_are_not_headings() -> None:
    body = "# Top\n\n```\n# not a heading\n```\n\ntail\n"

    assert [section.titles for section in split_sections(body)] == [("Top",)]


def test_chunk_text_starts_with_its_heading_context() -> None:
    body = "# Case\n\nlead\n\n## Coverage\n\n" + ("detail line. " * 200)

    chunks = chunk_sections(split_sections(body))

    coverage = [chunk for chunk in chunks if chunk.heading_path == ("Case", "Coverage")]
    assert coverage
    for chunk in coverage:
        assert chunk.text.startswith("# Case\n## Coverage\n\n")


def test_small_sections_are_packed_together() -> None:
    body = "# Top\n\n" + "\n\n".join(f"## S{n}\n\n{'word ' * 40}" for n in range(6))

    chunks = chunk_sections(split_sections(body))

    assert len(chunks) < 7
    assert any(chunk.tokens >= TARGET_TOKENS for chunk in chunks)


def test_long_sections_are_split_under_the_maximum() -> None:
    paragraphs = "\n\n".join("sentence about the loss. " * 20 for _ in range(20))
    body = f"# Top\n\n## Detail\n\n{paragraphs}\n"

    chunks = chunk_sections(split_sections(body))

    assert len(chunks) > 1
    assert all(chunk.tokens <= MAX_TOKENS for chunk in chunks)


def test_a_single_oversized_paragraph_still_splits() -> None:
    body = "# Top\n\n" + ("uninterrupted prose " * 600)

    chunks = chunk_sections(split_sections(body))

    assert len(chunks) > 1
    assert all(chunk.tokens <= MAX_TOKENS for chunk in chunks)


def test_empty_and_whitespace_bodies_produce_no_chunks() -> None:
    assert chunk_sections(split_sections("")) == []
    assert chunk_sections(split_sections("\n   \n")) == []


def test_reported_tokens_match_the_estimator() -> None:
    chunks = chunk_sections(split_sections("# Top\n\nsome body text here\n"))

    assert [chunk.tokens for chunk in chunks] == [estimate_tokens(chunks[0].text)]
