"""The only module that imports the model provider SDK.

Everything else in the repo calls complete() and embed() and stays unaware of
who serves them. Swapping providers means rewriting this file and nothing else.

Configuration comes from the environment only, with no defaults in code - an
unset variable is an error, not a silent fallback to some other model:
  OPENAI_API_KEY  credentials
  LLM_MODEL       completion model name
  EMBED_MODEL     embedding model name
  LLM_MODE        live (the default) or replay

Two modes, because a demo run on a client's network cannot depend on the
network. In live mode every completion is answered by the provider and written
to traces/llm_calls.jsonl under a key derived from the model, the system prompt
and the prompt. In replay mode the same key is looked up in that file and
nothing leaves the machine; a key that is not there is an error naming the
call, never a fabricated answer. The cache is the one file in traces/ that
keeps payloads rather than a summary - a replay that only had counts to work
from would have nothing to replay.

Embeddings record and replay the same way, to traces/embeddings.jsonl, keyed by
the model and the text. Retrieval embeds a query on every search and a rebuild
embeds the whole corpus, so a replay that covered completions only would still
reach the network in the middle of the walkthrough.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from ingest import layout

LIVE = "live"
REPLAY = "replay"
MODES = (LIVE, REPLAY)
DEFAULT_MODE = LIVE

CACHE_FILE = "llm_calls.jsonl"
EMBED_CACHE_FILE = "embeddings.jsonl"

# What a specialist is handed: a system prompt and a prompt, in that order.
CompleteFn = Callable[[str, str], str]


def required_env(name: str) -> str:
    """Read a required environment variable, or say exactly what is missing."""
    load_dotenv()
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set - add it to .env")
    return value


def mode(name: str | None = None) -> str:
    """The mode that will be used: the argument, LLM_MODE, or the default."""
    load_dotenv()
    chosen = (name or os.environ.get("LLM_MODE") or DEFAULT_MODE).strip().lower()
    if chosen not in MODES:
        raise ValueError(f"unknown LLM_MODE '{chosen}' - use {' or '.join(MODES)}")
    return chosen


def cache_file(traces_dir: Path = layout.TRACES_DIR) -> Path:
    """Where recorded completions are kept for replay."""
    return traces_dir / CACHE_FILE


def embed_cache_file(traces_dir: Path = layout.TRACES_DIR) -> Path:
    """Where recorded embeddings are kept for replay."""
    return traces_dir / EMBED_CACHE_FILE


def call_key(model: str, system: str, prompt: str) -> str:
    """A stable identifier for one completion request.

    Same model, same system prompt, same prompt -> same key on any machine and
    in any process, which is what makes a recorded run replayable.
    """
    return _key({"model": model, "system": system, "prompt": prompt})


def embed_key(model: str, text: str) -> str:
    """A stable identifier for one embedding request, one text at a time.

    Keyed per text rather than per batch, so a rebuild that regroups the corpus
    into different batches still replays: only the text and the model decide
    the vector.
    """
    return _key({"model": model, "text": text})


def complete(system: str, prompt: str, traces_dir: Path = layout.TRACES_DIR) -> str:
    """Return a single completion, from the provider or from the recorded run."""
    model = required_env("LLM_MODEL")
    key = call_key(model, system, prompt)
    path = cache_file(traces_dir)
    if mode() == REPLAY:
        return replay(key, path, prompt)
    answer = _live_completion(model, system, prompt)
    record(key, model, system, prompt, answer, path)
    return answer


def replay(key: str, path: Path, prompt: str = "") -> str:
    """Answer a call from the recorded run, or refuse and say which call missed.

    The newest recording of a key wins, so re-recording a run corrects it
    without anyone having to prune the file.
    """
    for line in reversed(_recorded(path)):
        if line.get("key") == key:
            return str(line.get("response", ""))
    opening = prompt.strip().splitlines()[0][:80] if prompt.strip() else ""
    raise RuntimeError(
        f"replay miss: no recorded completion for key {key[:12]} in {path} - "
        f"record it with a live run (LLM_MODE=live) before replaying. "
        f"Prompt begins: {opening}"
    )


def record(key: str, model: str, system: str, prompt: str, response: str, path: Path) -> None:
    """Append one completion to the replay cache."""
    line = {
        "ts": datetime.now(UTC).isoformat(),
        "key": key,
        "model": model,
        "system": system,
        "prompt": prompt,
        "response": response,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")


def embed(texts: list[str], traces_dir: Path = layout.TRACES_DIR) -> list[list[float]]:
    """Return one embedding vector per input text, in input order."""
    if not texts:
        return []
    model = required_env("EMBED_MODEL")
    path = embed_cache_file(traces_dir)
    if mode() == REPLAY:
        recorded = recorded_embeddings(path)
        return [replay_embedding(embed_key(model, text), recorded, path, text) for text in texts]
    vectors = _live_embeddings(model, texts)
    for text, vector in zip(texts, vectors):
        record_embedding(embed_key(model, text), model, text, vector, path)
    return vectors


def replay_embedding(
    key: str, recorded: Mapping[str, list[float]], path: Path, text: str = ""
) -> list[float]:
    """Answer one embedding from the recorded run, or refuse and say which text missed."""
    vector = recorded.get(key)
    if vector is not None:
        return vector
    opening = " ".join(text.split())[:80]
    raise RuntimeError(
        f"replay miss: no recorded embedding for key {key[:12]} in {path} - "
        f"record it with a live run (LLM_MODE=live) before replaying. "
        f"Text begins: {opening}"
    )


def recorded_embeddings(path: Path) -> dict[str, list[float]]:
    """Every recorded vector by key, read once. The newest recording of a key wins."""
    found: dict[str, list[float]] = {}
    for line in _recorded(path):
        key = line.get("key")
        vector = line.get("vector")
        if isinstance(key, str) and isinstance(vector, list):
            found[key] = [float(value) for value in vector]
    return found


def record_embedding(key: str, model: str, text: str, vector: Sequence[float], path: Path) -> None:
    """Append one embedding to the replay cache."""
    line = {
        "ts": datetime.now(UTC).isoformat(),
        "key": key,
        "model": model,
        "text": text,
        "vector": list(vector),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    """Build the provider client once."""
    return OpenAI(api_key=required_env("OPENAI_API_KEY"))


def _live_completion(model: str, system: str, prompt: str) -> str:
    """One call to the provider.

    No temperature is sent: newer models accept only their default, and a run
    that is going to be replayed wants the fewest moving parts anyway.
    """
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    response = _client().chat.completions.create(
        model=model,
        messages=messages,  # type: ignore[arg-type]
    )
    return response.choices[0].message.content or ""


def _live_embeddings(model: str, texts: list[str]) -> list[list[float]]:
    """One call to the provider, one vector per text, in input order."""
    response = _client().embeddings.create(model=model, input=texts)
    ordered = sorted(response.data, key=lambda item: item.index)
    return [list(item.embedding) for item in ordered]


def _key(payload: Mapping[str, str]) -> str:
    """The hash both caches are keyed by."""
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _recorded(path: Path) -> list[dict[str, Any]]:
    """Every cached call, oldest first. A missing cache is an empty one."""
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]
