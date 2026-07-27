"""A miniature wiki on disk, and the tool wiring over it.

Nothing here reaches the network. Tests that need vectors use the hash backend
from ingest/hash_embedder.py, the same one EMBED_BACKEND=hash selects, and
tests that need token counts use a word counter rather than the real
tokenizer, which has a table to fetch. tests/test_tokens.py covers the real
one on its own.

The fixture wiki is small but complete: a three-level AGENTS.md cascade, a
case with an index and a briefing, a second case with no briefing yet, an
append-only decisions.md and a human-only vocabulary file. Those are what the
MCP tools have rules about.

The agent tests want the real wiki as well - the cascade the demo runs, the
cases it cites - so the sandbox fixture copies it somewhere a run may write to
and indexes it offline. The stand-ins both fixtures use are in tests/fakes.py.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from ingest import layout
from ingest.embed import build_vector_index
from ingest.graph import build_graph
from ingest.hash_embedder import hash_embed
from ingest.parse import parse_corpus
from mcp_server.context import ToolContext
from stores import SqliteGraphStore, SqliteVectorStore, write_graph
from tests.fakes import FakeLLM, Sandbox, count_words

FILES: dict[str, str] = {
    "wiki/AGENTS.md": """# Platform rules

Agents follow these rules.

## Behaviour
Cite a source for every claim.

## Vocabulary
Terms come from wiki/vocabulary only.
""",
    "wiki/claims/AGENTS.md": """# Claims domain rules

Extends the platform AGENTS.md.

- Record what happened, whether cover responds, and what remains open.
""",
    "wiki/claims/CLM-9999-001/AGENTS.md": """# Case rules - CLM-9999-001

Extends claims/AGENTS.md.

- Settled and closed. Read as precedent, do not work it.
""",
    "wiki/claims/CLM-9999-001/index.md": """---
case_id: CLM-9999-001
type: claim
status: settled-closed
class: cyber-logistics
insured: Testco Logistics BV
peril: [ransomware, vendor-compromise]
linked_submission: SUB-9999-001
opened: 2024-06-11
closed: 2024-11-28
---

# CLM-9999-001 - Testco - Ransomware

Coverage disputed on exclusion CY-EX-04, resolved for the insured.

## Related
- [[submissions/SUB-9999-001/index|SUB-9999-001]] - the originating submission
""",
    "wiki/claims/CLM-9999-001/briefing.md": """---
case_id: CLM-9999-001
updated: 2024-11-28
---

# Briefing - at close

Ransomware through the vendor's remote access. Settled for the insured.

## Assessment
Vendor topology was known and not treated as a distinct exposure path.

## Open points
None at close.
""",
    "wiki/claims/CLM-9999-001/decisions.md": """---
case_id: CLM-9999-001
---

# Decisions

## D-001 - 2024-06-12 - Initial reserve
Reserve set at EUR 2.5M. Decided by: claims manager (illustrative).
""",
    "wiki/claims/CLM-9999-001/lessons.md": """---
case_id: CLM-9999-001
status: candidate
---

# Lessons

## L-900 - Vendor standing access is a distinct exposure path
The claim entered through vendor infrastructure. See
[[submissions/SUB-9999-001/index|SUB-9999-001]] and skill SK-900.
""",
    "wiki/claims/CLM-9999-001/sources/note.md": """---
source_id: SRC-999-01
original: raw/testco-survey.md
ingested: 2024-06-11
---

# Source note - survey

Key facts:
- Single system across all sites

Locator: raw/testco-survey.md
""",
    "wiki/submissions/SUB-9999-001/index.md": """---
case_id: SUB-9999-001
type: submission
status: bound-closed
class: cyber-logistics
insured: Testco Logistics BV
peril_focus: [ransomware, network-outage]
linked_claim: CLM-9999-001
---

# SUB-9999-001 - Testco - Cyber

Bound with exclusions CY-EX-04 and CY-EX-01.
""",
    "wiki/platform-ic/skills/precedent.md": """---
skill_id: SK-900
domain: cyber-logistics
---

# Precedent search

Query the knowledge base before drafting an appetite position.
""",
    "wiki/vocabulary/perils.md": """# Perils

| term | meaning |
| ---- | ------- |
| ransomware | encryption of systems for extortion |
""",
    "wiki/submissions/SUB-9999-001/sources/.gitkeep": "",
    "wiki/notes.txt": "not markdown, must be skipped",
    "wiki/.obsidian/private.md": "# hidden vault config, must be skipped",
    "raw/testco-survey.md": """---
doc_id: RAW-900
type: risk-survey
claim: CLM-9999-001
insured: Testco Logistics BV
---

# Risk survey - Testco

One system serves every site.
""",
}


@pytest.fixture
def corpus(tmp_path: Path) -> tuple[tuple[str, Path], ...]:
    """Write the fixture wiki and return roots in the shape parse_corpus wants."""
    for relative, content in FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return (("wiki", tmp_path / "wiki"), ("raw", tmp_path / "raw"))


@pytest.fixture
def wiki(corpus: tuple[tuple[str, Path], ...]) -> Path:
    """The wiki root of the fixture corpus."""
    return corpus[0][1]


@pytest.fixture
def tool_context(corpus: tuple[tuple[str, Path], ...], tmp_path: Path) -> ToolContext:
    """The four tools wired to indexes built from the fixture wiki."""
    return _wire(corpus, tmp_path / "index", tmp_path / "traces")


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    """The real wiki, copied so a run can write to it, indexed offline.

    The agent tests need the wiki the demo runs on - its cascade, its cases,
    its vocabulary - but a run writes to briefing.md and decisions.md, and a
    test that edits the repo's own wiki is a test that ruins the next one.
    Vectors come from the hash backend, so this stays offline; retrieval
    ranking is meaningless here, provenance is not.
    """
    root = tmp_path / "demo"
    shutil.copytree(layout.WIKI_DIR, root / "wiki")
    shutil.copytree(layout.RAW_DIR, root / "raw")
    corpus = (("wiki", root / "wiki"), ("raw", root / "raw"))
    context = _wire(corpus, tmp_path / "index", tmp_path / "traces")

    documents, chunks = parse_corpus(corpus)
    graph = build_graph(documents)
    ids = {chunk.chunk_id for chunk in chunks} | {node.node_id for node in graph.nodes}
    return Sandbox(context=context, ids=frozenset(ids))


@pytest.fixture
def fake_llm() -> FakeLLM:
    """A model that answers the same way every time. See tests/fakes.py."""
    return FakeLLM()


def _wire(corpus: tuple[tuple[str, Path], ...], index_dir: Path, traces_dir: Path) -> ToolContext:
    """Build the indexes for a corpus and wire the tools over them."""
    documents, chunks = parse_corpus(corpus)
    vector_db = index_dir / "vectors" / "chunks.db"
    graph_db = index_dir / "graph" / "graph.db"
    build_vector_index(chunks, hash_embed, vector_db)
    write_graph(build_graph(documents), graph_db)
    return ToolContext(
        vectors=SqliteVectorStore(vector_db),
        graph=SqliteGraphStore(graph_db),
        embed=hash_embed,
        count_tokens=count_words,
        wiki_dir=corpus[0][1],
        traces_dir=traces_dir,
    )
