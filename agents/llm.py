"""The only module that imports the model provider SDK.

Everything else in the repo calls complete() and embed() and stays unaware of
who serves them. Swapping providers means rewriting this file and nothing else.

Configuration comes from the environment only, with no defaults in code - an
unset variable is an error, not a silent fallback to some other model:
  OPENAI_API_KEY  credentials
  LLM_MODEL       completion model name
  EMBED_MODEL     embedding model name
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


def required_env(name: str) -> str:
    """Read a required environment variable, or say exactly what is missing."""
    load_dotenv()
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set - add it to .env")
    return value


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    """Build the provider client once."""
    return OpenAI(api_key=required_env("OPENAI_API_KEY"))


def complete(prompt: str, system: str | None = None, temperature: float | None = None) -> str:
    """Return a single completion for prompt.

    temperature is omitted from the request unless given: newer models accept
    only their default, so sending one unasked makes the call fail.
    """
    messages: list[dict[str, str]] = []
    if system is not None:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    options: dict[str, Any] = {}
    if temperature is not None:
        options["temperature"] = temperature

    response = _client().chat.completions.create(
        model=required_env("LLM_MODEL"),
        messages=messages,  # type: ignore[arg-type]
        **options,
    )
    return response.choices[0].message.content or ""


def embed(texts: list[str]) -> list[list[float]]:
    """Return one embedding vector per input text, in input order."""
    if not texts:
        return []
    response = _client().embeddings.create(model=required_env("EMBED_MODEL"), input=texts)
    ordered = sorted(response.data, key=lambda item: item.index)
    return [list(item.embedding) for item in ordered]
