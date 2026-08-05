# intelligence-capital-demo

A working demonstration of the Intelligence Capital platform's knowledge architecture: a Living Wiki of markdown files as the primary store, derived vector and graph indexes behind MCP tools, and an agent swarm that reads, reasons, writes back with citations, and compounds what it learned into the next case.

The scenario is fictional end to end: a cyber-logistics insurance submission (SUB-2025-007) assessed against an invented claim history. No real client data is involved anywhere.

## Run it (no API key needed)

The demo replays a blessed recording committed in this repo - every completion and embedding comes from the recording, zero network calls:

    uv sync
    uv run python intelligence_capital_demo.py reset --replay
    uv run python intelligence_capital_demo.py run --replay

The run streams five phases, pausing for a keypress between them: ORIENT (the orchestrator reads the case wiki, token cost on screen), RETRIEVE (three specialists in parallel through the MCP tools), WRITE BACK (a cited draft lands in the case files), HUMAN IN THE LOOP (a person edits markdown and the next read simply has it), COMPOUND (the case closes, its lesson is promoted behind a human gate, and the same precedent query returns one more result than before).

Presenting it to a room? The run-of-show manual is [PRESENTER.md](PRESENTER.md): machine setup, screen choreography, what to say in each phase, and a crib for likely questions.

## Run it live

Live mode generates fresh assessments instead of replaying:

    uv run --env-file .env python intelligence_capital_demo.py reset
    LLM_MODE=live uv run --env-file .env python intelligence_capital_demo.py run

Requires a provider API key in `.env`. Model and mode come from the `LLM_MODEL` and `LLM_MODE` environment variables; the vendor SDK is confined to a single file by a layering test.

## What is where

    wiki/          the Living Wiki - the primary store, plain markdown
    raw/           original source documents; summarised into the wiki, indexed for retrieval
    ingest/        parse, embed, graph: rebuilds all indexes from the wiki
    stores/        vector and graph storage behind protocols
    mcp_server/    the four MCP tools agents use to reach knowledge
    agents/        the risk assessment swarm and its orchestration
    intelligence_capital_demo.py
                   the five-phase driver: run, reset, bless (stage, hitl, case_close
                   and recording modules sit alongside it; demo.py is a shim that
                   points at the new name)
    traces/        append-only JSONL audit stream (gitignored)
    fixtures/      the blessed recording and the scripted human edit
    tests/         quality gate - run with `make check`

## Why it is built this way

Every non-obvious choice is recorded with its rationale in [DECISIONS.md](DECISIONS.md) - what was chosen, what was rejected, and why. The repo keeps a decisions record the same way every case in the wiki does: the demo practices its own architecture.