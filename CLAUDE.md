# Intelligence Capital Demo

Working demo of the Marionete Living Wiki architecture for specialty insurance:
a markdown-first knowledge base with derived indexes, consumed and updated by an
agent swarm through MCP tools. Built to be shown live to a client. The wiki
content is fictional (cyber submission for a logistics company) and must stay
consistent with the client deck this demo accompanies.

## Demo beats (acceptance criteria)

demo.py must run these five beats end to end:

1. ORIENT: orchestrator reads AGENTS.md cascade -> index.md -> briefing.md via
   direct file reads. Live token counter shown per read.
2. RETRIEVE: three specialists call MCP tools in parallel. search_knowledge_base()
   returns ranked chunks with provenance. traverse_graph() returns an entity
   subgraph. GraphRAG merge produces one context block.
3. WRITE BACK: draft assessment written to briefing.md and decisions.md, every
   claim citing chunk IDs and entity IDs.
4. HITL: a human edit made in any markdown file is picked up on the next run.
5. COMPOUND: case close promotes lessons.md to platform-ic/, indexes rebuild,
   the same precedent query returns one more result than before.

--replay flag runs all five beats from cached traces with zero network calls.

## Architecture rules (non-negotiable)

- The wiki markdown files are the primary store. Vector index and graph are
  derived, disposable, and rebuilt from the files with one command.
- Agents never touch storage directly. All retrieval goes through the MCP tools:
  search_knowledge_base(), traverse_graph(), read_case_context(),
  propose_wiki_update().
- Vendor-agnostic naming everywhere in code, comments, and docstrings:
  "vector index" not a product name, "knowledge graph" not a product name.
  The LLM provider is invisible outside llm.py.
- Every MCP call and every wiki write is appended to traces/ as JSONL.
- Wiki links use Obsidian wikilink syntax with vault-root paths:
  [[submissions/SUB-2024-018/index|SUB-2024-018]]. The ingest parser treats
  the label as text and the path as a graph edge.
- Graph and vector stores sit behind store protocols (GraphStore,
  VectorStore). The demo implementation is embedded SQLite; swapping to a
  native graph database (e.g. an embedded Cypher engine) is a deliberate
  post-rehearsal option and must only require a new protocol
  implementation passing the existing tests. Nothing outside the store
  modules may know which engine is in use.

## Repo layout

    wiki/          the living wiki (cases, vocabulary, platform-ic)
    raw/           sample domain documents, immutable, read-only
    ingest/        chunking, embedding, graph build; rebuild.sh regenerates all
    stores/        VectorStore and GraphStore protocols, traversal, the
                   embedded implementation; the only importer of the engine
    mcp_server/    the four MCP tools
    errors.py      the refusal vocabulary, shared by stores/ and mcp_server/
    agents/        graph.py (orchestration shell), specialists as pure functions,
                   context assembly, token counter
    traces/        JSONL traces, gitignored
    demo.py        runs the five beats
    tests/         pytest, no network

## Development workflow

- make check must pass before every push: ruff format, ruff check, mypy
  (strict), pytest, in that order. Never push red.
- Each build session happens on a feature branch, merged via PR.
- uv for everything: uv add for deps (runtime) and uv add --dev (tooling).
  Never pip. Commit uv.lock.
- Conventional commit style: short imperative subject, body only when the
  why is not obvious.

## Code conventions

- Python 3.12, full type annotations, mypy strict is the bar.
- Small modules with one job. If a file needs a section comment, split it.
- No framework magic in the agent loop: plain functions, explicit calls,
  readable by a client engineer in one sitting.
- llm.py is the only file that imports the LLM SDK. Everything else calls
  complete() and embed(). Model name comes from the LLM_MODEL env var.
- Config via environment only. .env is gitignored and never committed.
- In all text output (docstrings, prompts, generated markdown): no em dashes,
  use "->" for arrows, use " - " as separator.

## Testing

- Agent orchestration uses a graph framework, confined to agents/graph.py:
  state schema, node wiring, parallel dispatch, nothing else. Specialist and
  orchestrator logic are plain typed functions with no framework imports -
  readable by a client engineer in one sitting.
- What must be covered: chunking, index build and rebuild determinism, MCP
  tool contracts (inputs, outputs, error cases), AGENTS.md cascade assembly,
  token counting.

## Data rule

The OpenAI key used here belongs to an account with data sharing enabled in
exchange for free tokens. Only the fictional wiki content in this repo may go
through it. Nothing from any real client, ever. If real client material is
needed some day, this key gets replaced first and this rule gets rewritten.