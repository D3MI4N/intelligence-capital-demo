"""Configuration comes from the environment, and missing values fail loudly."""

from __future__ import annotations

from pathlib import Path

import pytest

from agents import llm
from ingest import embed
from ingest.hash_embedder import hash_embed


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ignore the developer's .env so the tests see a bare environment."""
    monkeypatch.setattr(llm, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(embed, "load_dotenv", lambda *args, **kwargs: None)


@pytest.mark.parametrize("name", ["OPENAI_API_KEY", "LLM_MODEL", "EMBED_MODEL"])
def test_a_missing_variable_names_itself(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match=name):
        llm.required_env(name)


def test_a_blank_variable_counts_as_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "   ")

    with pytest.raises(RuntimeError, match="LLM_MODEL"):
        llm.required_env("LLM_MODEL")


def test_model_names_have_no_default_in_code() -> None:
    source = Path(str(llm.__file__)).read_text(encoding="utf-8")

    assert "gpt-" not in source
    assert "text-embedding" not in source


def test_the_hash_backend_is_selectable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBED_BACKEND", "hash")

    assert embed.select_embedder() is hash_embed
    assert embed.backend_name() == "hash"


def test_the_backend_argument_wins_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBED_BACKEND", "llm")

    assert embed.select_embedder("hash") is hash_embed


def test_the_default_backend_is_the_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EMBED_BACKEND", raising=False)

    assert embed.backend_name() == "llm"


def test_an_unknown_backend_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMBED_BACKEND", "elsewhere")

    with pytest.raises(ValueError, match="elsewhere"):
        embed.select_embedder()
