"""What an agent is given before it reasons, and what it may cite afterwards.

Three jobs, all of them about the boundary between evidence and invention:

  orient()          the cascade read - every AGENTS.md from the wiki root down
                    to the case, then index.md, then briefing.md. Direct file
                    reads rather than a tool call, because orientation is
                    direct injection by design: the rules an agent runs under
                    are not something it retrieves, they are something it is
                    handed. Each file carries its exact token count, and the
                    counter is the platform's, not a copy of it
  merge_retrieval() one context block out of ranked chunks and an entity
                    subgraph - the GraphRAG merge. Deterministic ordering, so
                    the same retrieval renders byte-identical every run
  available_ids()   the set of chunk ids and entity ids the agent was actually
                    given, with keep_known() and strip_unverified() to police
                    citations against it

Nothing here reads the derived indexes. Retrieval is the tools' business; this
module only lays out what came back.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from ingest import entities, layout
from ingest.frontmatter import split_frontmatter
from mcp_server import cases
from mcp_server.results import ChunkHit, SubgraphResult
from mcp_server.tokens import TokenCounter, count_tokens

# An id an agent is allowed to cite: a chunk id, or an entity id whose type
# comes from the published vocabulary. Anything else in a draft is invention.
ENTITY_TYPES = (
    entities.CASE,
    entities.CLAUSE,
    entities.DOCUMENT,
    entities.INSURED,
    entities.LESSON,
    entities.PERIL,
    entities.RISK_CLASS,
    entities.SKILL,
)
CITATION_PATTERN = re.compile(
    r"(?:" + "|".join(ENTITY_TYPES) + r"):[A-Za-z0-9._/-]+" r"|[A-Za-z0-9._/-]+\.md#c\d+"
)

# What replaces an id the agent was never given. Visible on purpose: a claim
# that lost its citation should look wrong to the human reading the draft. No
# square brackets - a marker landing inside an existing [...] would read as a
# wikilink, and the next rebuild would turn it into a graph edge.
UNVERIFIED = "(unverified)"


@dataclass(frozen=True)
class OrientationFile:
    """One file of the orientation read, and what reading it cost."""

    path: str
    role: str  # rules - index - briefing
    text: str
    tokens: int


@dataclass(frozen=True)
class Orientation:
    """Everything the orchestrator knows about a case before any retrieval."""

    case_id: str
    case_dir: str
    risk_class: str
    insured: str
    files: tuple[OrientationFile, ...]
    missing: tuple[str, ...]
    total_tokens: int
    text: str


def orient(
    case_path: str,
    wiki_dir: Path = layout.WIKI_DIR,
    count: TokenCounter = count_tokens,
) -> Orientation:
    """Read the AGENTS.md cascade, then index.md, then briefing.md.

    case_path is a case id or a path ending in one - "SUB-2025-007" and
    "wiki/submissions/SUB-2025-007" orient the same case, so a caller can pass
    whichever it happens to hold.

    A missing briefing.md is reported rather than raised: a case at intake has
    not been briefed yet, and refusing to orient at all would be the wrong
    answer. A missing index.md means the case does not exist, and that is.
    """
    directory = cases.case_dir(Path(case_path).name, wiki_dir)
    files: list[OrientationFile] = []
    missing: list[str] = []
    for path in cases.context_files(directory, wiki_dir):
        if not path.is_file():
            missing.append(_relative(path, wiki_dir))
            continue
        text = path.read_text(encoding="utf-8")
        files.append(
            OrientationFile(
                path=_relative(path, wiki_dir),
                role=cases.role_of(path),
                text=text,
                tokens=count(text),
            )
        )
    facts = _index_facts(files)
    return Orientation(
        case_id=directory.name,
        case_dir=_relative(directory, wiki_dir),
        risk_class=facts.get("class", ""),
        insured=facts.get("insured", ""),
        files=tuple(files),
        missing=tuple(missing),
        total_tokens=sum(file.tokens for file in files),
        text=_assemble(files),
    )


def merge_retrieval(
    chunks: Sequence[ChunkHit],
    subgraph: SubgraphResult | None = None,
) -> str:
    """Render ranked chunks and an entity subgraph as one context block.

    The two halves answer different questions - the chunks say what a document
    states, the subgraph says how the entities relate - and an agent that has
    to reconcile two separately formatted payloads spends its attention on
    formatting. Ordering is fixed: chunks by score then id, nodes by type then
    id, edges by source then relation then target.
    """
    return "\n\n".join((_render_chunks(chunks), _render_subgraph(subgraph)))


def available_ids(
    chunks: Sequence[ChunkHit],
    subgraph: SubgraphResult | None = None,
) -> frozenset[str]:
    """Every id the retrieval actually handed over, and therefore citable."""
    found = {chunk["chunk_id"] for chunk in chunks}
    if subgraph is not None:
        found.update(node["id"] for node in subgraph["nodes"])
        found.update(edge["src"] for edge in subgraph["edges"])
        found.update(edge["dst"] for edge in subgraph["edges"])
    return frozenset(found)


def keep_known(ids: Iterable[str], allowed: frozenset[str]) -> tuple[str, ...]:
    """Drop cited ids that were never retrieved, keeping order and dropping repeats."""
    kept: dict[str, None] = {}
    for value in ids:
        cleaned = value.strip()
        if cleaned in allowed:
            kept.setdefault(cleaned, None)
    return tuple(kept)


def strip_unverified(text: str, allowed: frozenset[str]) -> str:
    """Replace every id in prose that the agent was not given.

    A model that invents a plausible chunk id is the failure this platform
    cannot afford, and the check is cheap: the shape of an id is known, and so
    is the set that came back from retrieval.
    """
    return CITATION_PATTERN.sub(
        lambda match: match.group(0) if match.group(0) in allowed else UNVERIFIED, text
    )


def cited_ids(text: str) -> tuple[str, ...]:
    """Every id-shaped token in a piece of text, in order of appearance."""
    return tuple(dict.fromkeys(CITATION_PATTERN.findall(text)))


def _assemble(files: Sequence[OrientationFile]) -> str:
    """The cascade as one block, each file labelled with its role and cost."""
    return "\n\n".join(
        f"--- {file.path} ({file.role}, {file.tokens} tokens) ---\n{file.text.strip()}"
        for file in files
    )


def _index_facts(files: Sequence[OrientationFile]) -> dict[str, str]:
    """The frontmatter of index.md, which is where a case declares itself."""
    for file in files:
        if file.role != "index":
            continue
        frontmatter, _ = split_frontmatter(file.text)
        return {key: value for key, value in frontmatter.items() if isinstance(value, str)}
    return {}


def _render_chunks(chunks: Sequence[ChunkHit]) -> str:
    ranked = sorted(chunks, key=lambda hit: (-hit["score"], hit["chunk_id"]))
    if not ranked:
        return "## Retrieved chunks\nnone"
    lines = ["## Retrieved chunks"]
    for position, hit in enumerate(ranked, start=1):
        heading = " > ".join(hit["heading_path"]) or hit["doc"]
        lines.append(
            f"{position}. [{hit['chunk_id']}] {hit['doc']} - {heading} "
            f"(score {hit['score']:.3f})\n{hit['text'].strip()}"
        )
    return "\n".join(lines)


def _render_subgraph(subgraph: SubgraphResult | None) -> str:
    if subgraph is None or not subgraph["nodes"]:
        return "## Entity subgraph\nnone"
    nodes = sorted(subgraph["nodes"], key=lambda node: (node["type"], node["id"]))
    edges = sorted(
        subgraph["edges"],
        key=lambda edge: (edge["src"], edge["rel"], edge["dst"], edge["source_doc"]),
    )
    lines = [f"## Entity subgraph (seeds: {' - '.join(subgraph['seeds'])})", "Entities:"]
    lines.extend(
        f"- {node['id']} - {node['label']} - {node['depth']} hop(s) from seed" for node in nodes
    )
    lines.append("Relations:")
    lines.extend(
        f"- {edge['src']} -{edge['rel']}-> {edge['dst']} [{edge['source_doc']}]" for edge in edges
    )
    return "\n".join(lines)


def _relative(path: Path, wiki_dir: Path) -> str:
    """A path in the form the rest of the platform cites: wiki/claims/.../x.md."""
    resolved = path.resolve()
    root = wiki_dir.resolve().parent
    return resolved.relative_to(root).as_posix() if resolved.is_relative_to(root) else str(resolved)
