"""House style on the way into the wiki, and the count that says it happened."""

from __future__ import annotations

from agents.text import normalise


def test_a_non_breaking_hyphen_becomes_a_hyphen() -> None:
    """The one that started this: identical on screen, invisible to a grep."""
    result = normalise("vendor\u2011operated systems")

    assert result.text == "vendor-operated systems"
    assert result.replacements == 1
    assert result.changed


def test_a_separator_dash_becomes_the_house_separator() -> None:
    assert normalise("exposure \u2014 severity high").text == "exposure - severity high"
    assert normalise("exposure\u2013severity").text == "exposure - severity"


def test_spaces_around_a_separator_are_collapsed_but_line_breaks_are_not() -> None:
    assert normalise("a  \u2014  b").text == "a - b"
    assert normalise("first\n\n\u2014 second").text == "first\n\n - second"


def test_invisible_characters_are_dropped_rather_than_replaced() -> None:
    """A soft hyphen inside an id is why an id stops matching itself."""
    assert normalise("CY\u00adEX\u200b-04").text == "CYEX-04"


def test_a_semicolon_between_two_ids_becomes_the_house_separator() -> None:
    """The model writes "; " on one claim and " - " on the next. The wiki gets one."""
    result = normalise("[Case:SUB-2025-007; Clause:CY-EX-04]")

    assert result.text == "[Case:SUB-2025-007 - Clause:CY-EX-04]"
    assert result.replacements == 1
    assert result.changed


def test_a_block_mixing_both_separators_leaves_carrying_one() -> None:
    original = "[Case:CLM-2024-042 - raw/clm042-fnol.md#c000;Lesson:L-001 ; Clause:CY-EX-04]"

    result = normalise(original)

    assert result.text == (
        "[Case:CLM-2024-042 - raw/clm042-fnol.md#c000 - Lesson:L-001 - Clause:CY-EX-04]"
    )
    assert result.replacements == 2


def test_a_semicolon_in_prose_outside_a_block_is_punctuation_and_stays() -> None:
    """The rule is about a list of ids, not about how the drafter writes a sentence."""
    original = "The wording is disputed; the exposure is not [Clause:CY-EX-04]."

    result = normalise(original)

    assert result.text == original
    assert result.replacements == 0
    assert not result.changed


def test_a_block_already_using_the_house_separator_is_left_alone() -> None:
    original = "matches the pattern [Case:SUB-2024-018 - Lesson:L-001]"

    result = normalise(original)

    assert result.text == original
    assert result.replacements == 0


def test_text_already_in_house_style_is_left_exactly_as_it_is() -> None:
    original = "exposure - severity high, wiki/claims/CLM-2024-042/index.md#c001 -> refer"

    result = normalise(original)

    assert result.text == original
    assert result.replacements == 0
    assert not result.changed


def test_every_replaced_character_is_counted() -> None:
    result = normalise("a\u2014b\u2011c\u2013d")

    assert result.replacements == 3
    assert result.text == "a - b-c - d"
