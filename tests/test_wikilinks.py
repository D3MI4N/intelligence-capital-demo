from ingest.models import WikiLink
from ingest.wikilinks import find_wikilinks, render_labels, targets


def test_path_and_label_are_separated() -> None:
    links = find_wikilinks("See [[submissions/SUB-2024-018/index|SUB-2024-018]] for context.")

    assert links == (WikiLink(target="submissions/SUB-2024-018/index", label="SUB-2024-018"),)


def test_label_defaults_to_target() -> None:
    links = find_wikilinks("See [[claims/CLM-2024-042/index]].")

    assert links[0].label == "claims/CLM-2024-042/index"


def test_anchor_is_dropped_from_the_target() -> None:
    links = find_wikilinks("[[claims/CLM-2024-042/coverage#Resolution|the resolution]]")

    assert links == (WikiLink(target="claims/CLM-2024-042/coverage", label="the resolution"),)


def test_render_labels_leaves_prose() -> None:
    text = "See [[submissions/SUB-2024-018/index|SUB-2024-018]] and [[vocabulary/perils]]."

    assert render_labels(text) == "See SUB-2024-018 and perils."


def test_targets_are_distinct_in_first_seen_order() -> None:
    text = "[[b/two|two]] [[a/one|one]] [[b/two|again]]"

    assert targets(text) == ("b/two", "a/one")


def test_plain_brackets_are_not_links() -> None:
    assert find_wikilinks("An array literal [not, a, link] stays text.") == ()
