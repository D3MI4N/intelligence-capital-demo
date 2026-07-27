"""Live records, replay resolves, and a miss says which call it was.

Nothing here reaches the provider: the live path is exercised through a stub
completion and a stub embedder, so the recording format is still the real one.

Embeddings get the same treatment as completions, and for the same reason. The
demo embeds a query on every search and the whole corpus on every rebuild; a
replay that could not answer those would announce itself as offline and then
call the provider anyway.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents import llm


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """A bare environment with model names, and no .env underneath it."""
    monkeypatch.setattr(llm, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("EMBED_MODEL", "test-embed-model")
    monkeypatch.delenv("LLM_MODE", raising=False)


def stub(monkeypatch: pytest.MonkeyPatch, answer: str) -> None:
    """Stand in for the provider call, so the live path can be tested offline."""
    monkeypatch.setattr(llm, "_live_completion", lambda model, system, prompt: answer)


def stub_embeddings(monkeypatch: pytest.MonkeyPatch, first: float = 0.5) -> None:
    """Stand in for the provider embedder: one vector per text, told apart by index."""
    monkeypatch.setattr(
        llm,
        "_live_embeddings",
        lambda model, texts: [[first + index, 0.25] for index, _ in enumerate(texts)],
    )


def no_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if anything reaches for the provider once replay is on."""
    monkeypatch.setattr(
        llm, "_live_completion", lambda *args: pytest.fail("replay called the provider")
    )
    monkeypatch.setattr(
        llm, "_live_embeddings", lambda *args: pytest.fail("replay called the provider")
    )


def test_the_default_mode_is_live() -> None:
    assert llm.mode() == llm.LIVE


def test_an_unknown_mode_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODE", "rehearsal")

    with pytest.raises(ValueError, match="rehearsal"):
        llm.mode()


def test_the_key_is_the_model_the_system_prompt_and_the_prompt() -> None:
    key = llm.call_key("m", "system", "prompt")

    assert key == llm.call_key("m", "system", "prompt")
    assert key != llm.call_key("m", "system", "other prompt")
    assert key != llm.call_key("m", "other system", "prompt")
    assert key != llm.call_key("other-model", "system", "prompt")


def test_a_live_call_records_itself(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub(monkeypatch, "the answer")

    assert llm.complete("system", "prompt", tmp_path) == "the answer"

    lines = [
        json.loads(line)
        for line in llm.cache_file(tmp_path).read_text(encoding="utf-8").splitlines()
    ]
    assert len(lines) == 1
    assert lines[0]["key"] == llm.call_key("test-model", "system", "prompt")
    assert lines[0]["model"] == "test-model"
    assert lines[0]["prompt"] == "prompt"
    assert lines[0]["response"] == "the answer"
    assert lines[0]["ts"]


def test_replay_answers_from_the_recording(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub(monkeypatch, "recorded once")
    llm.complete("system", "prompt", tmp_path)

    monkeypatch.setenv("LLM_MODE", "replay")
    no_provider(monkeypatch)

    assert llm.complete("system", "prompt", tmp_path) == "recorded once"


def test_replay_takes_the_newest_recording_of_a_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub(monkeypatch, "first")
    llm.complete("system", "prompt", tmp_path)
    stub(monkeypatch, "second")
    llm.complete("system", "prompt", tmp_path)

    monkeypatch.setenv("LLM_MODE", "replay")

    assert llm.complete("system", "prompt", tmp_path) == "second"


def test_a_replay_miss_names_the_call_and_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub(monkeypatch, "recorded")
    llm.complete("system", "prompt", tmp_path)

    monkeypatch.setenv("LLM_MODE", "replay")

    with pytest.raises(RuntimeError, match="replay miss") as raised:
        llm.complete("system", "a prompt that was never recorded", tmp_path)

    message = str(raised.value)
    assert str(llm.cache_file(tmp_path)) in message
    assert "a prompt that was never recorded" in message
    assert "LLM_MODE=live" in message


def test_replay_with_no_recording_at_all_is_a_miss_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_MODE", "replay")

    with pytest.raises(RuntimeError, match="replay miss"):
        llm.complete("system", "prompt", tmp_path)


def test_the_embedding_key_is_the_model_and_the_text() -> None:
    key = llm.embed_key("m", "text")

    assert key == llm.embed_key("m", "text")
    assert key != llm.embed_key("m", "other text")
    assert key != llm.embed_key("other-model", "text")


def test_a_live_embedding_records_itself_one_line_per_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_embeddings(monkeypatch)

    vectors = llm.embed(["first", "second"], tmp_path)

    assert vectors == [[0.5, 0.25], [1.5, 0.25]]
    lines = [
        json.loads(line)
        for line in llm.embed_cache_file(tmp_path).read_text(encoding="utf-8").splitlines()
    ]
    assert [line["text"] for line in lines] == ["first", "second"]
    assert lines[0]["key"] == llm.embed_key("test-embed-model", "first")
    assert lines[0]["model"] == "test-embed-model"
    assert lines[0]["vector"] == [0.5, 0.25]


def test_replay_answers_every_embedding_from_the_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rebuild in beat five re-embeds the corpus - all of it has to hit."""
    stub_embeddings(monkeypatch)
    llm.embed(["first", "second"], tmp_path)

    monkeypatch.setenv("LLM_MODE", "replay")
    no_provider(monkeypatch)

    assert llm.embed(["second", "first"], tmp_path) == [[1.5, 0.25], [0.5, 0.25]]


def test_a_rebatched_text_still_replays(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keyed per text, so a rebuild that groups the corpus differently still resolves."""
    stub_embeddings(monkeypatch)
    llm.embed(["first", "second"], tmp_path)

    monkeypatch.setenv("LLM_MODE", "replay")
    no_provider(monkeypatch)

    assert llm.embed(["second"], tmp_path) == [[1.5, 0.25]]


def test_replay_takes_the_newest_recording_of_an_embedding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_embeddings(monkeypatch, first=0.5)
    llm.embed(["first"], tmp_path)
    stub_embeddings(monkeypatch, first=9.5)
    llm.embed(["first"], tmp_path)

    monkeypatch.setenv("LLM_MODE", "replay")

    assert llm.embed(["first"], tmp_path) == [[9.5, 0.25]]


def test_an_embedding_replay_miss_names_the_text_and_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub_embeddings(monkeypatch)
    llm.embed(["first"], tmp_path)

    monkeypatch.setenv("LLM_MODE", "replay")

    with pytest.raises(RuntimeError, match="replay miss") as raised:
        llm.embed(["a chunk that was never embedded"], tmp_path)

    message = str(raised.value)
    assert str(llm.embed_cache_file(tmp_path)) in message
    assert "a chunk that was never embedded" in message
    assert "LLM_MODE=live" in message


def test_embedding_nothing_asks_for_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    no_provider(monkeypatch)

    assert llm.embed([], tmp_path) == []
