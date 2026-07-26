from ingest.frontmatter import split_frontmatter


def test_extracts_mapping_and_body() -> None:
    frontmatter, body = split_frontmatter("---\ncase_id: CLM-1\nclass: cyber\n---\n\n# Title\n")

    assert frontmatter == {"case_id": "CLM-1", "class": "cyber"}
    assert body == "# Title\n"


def test_list_values_survive() -> None:
    frontmatter, _ = split_frontmatter("---\nperil: [ransomware, vendor-compromise]\n---\nbody\n")

    assert frontmatter["peril"] == ["ransomware", "vendor-compromise"]


def test_dates_become_iso_strings() -> None:
    frontmatter, _ = split_frontmatter("---\nopened: 2024-06-11\n---\nbody\n")

    assert frontmatter["opened"] == "2024-06-11"


def test_no_frontmatter_returns_whole_text() -> None:
    assert split_frontmatter("# Title\n\nbody\n") == ({}, "# Title\n\nbody\n")


def test_unterminated_block_is_left_as_body() -> None:
    text = "---\ncase_id: CLM-1\n\n# Title\n"

    assert split_frontmatter(text) == ({}, text)


def test_non_mapping_block_is_ignored() -> None:
    frontmatter, body = split_frontmatter("---\n- one\n- two\n---\nbody\n")

    assert frontmatter == {}
    assert body == "body\n"
