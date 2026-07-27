"""Build the knowledge graph from document structure.

No model extraction: every node and edge comes from something a human wrote
deliberately - a frontmatter field, a wikilink, an identifier like CY-EX-04, or
a source note locator line. That is what makes the graph reproducible and what
lets an agent cite an entity ID as evidence.

This module derives the graph and hands it to the store to persist. Where the
nodes and edges are kept, and how they are walked, is the store's business -
see stores/stores.py.
"""

from __future__ import annotations

from collections.abc import Sequence

from ingest import entities, parse
from ingest.entities import Edge, Graph, Node
from ingest.models import Document
from stores import write_graph

CASE_ATTRIBUTES = ("type", "status", "class", "insured", "opened", "closed")
PERIL_FIELDS = ("peril", "peril_focus", "perils")
# Frontmatter field -> the relation it declares.
CASE_LINK_RELATIONS = {
    "linked_claim": entities.LINKED_CLAIM,
    "linked_submission": entities.LINKED_SUBMISSION,
}
RAW_CASE_FIELDS = ("claim", "submission")


def build_graph(documents: Sequence[Document]) -> Graph:
    """Derive nodes and edges from parsed documents."""
    builder = _Builder(documents)
    return builder.build()


class _Builder:
    """Accumulates nodes and edges while walking the corpus once."""

    def __init__(self, documents: Sequence[Document]) -> None:
        self.documents = list(documents)
        self.known_docs = {document.doc_id for document in self.documents}
        self.labels: dict[str, str] = {}
        for document in self.documents:
            self.labels.update(entities.find_labels(document.text))
        self.case_of: dict[str, str] = {}
        for document in self.documents:
            case_id = _text(document.frontmatter.get("case_id"))
            if case_id:
                self.case_of[document.doc_id] = entities.node_id(entities.CASE, case_id)
        # A case is a directory. Files inside it that do not repeat case_id in
        # their frontmatter - source notes, for instance - still belong to it.
        self.case_dirs = sorted(
            (
                (doc_id.rsplit("/", 1)[0] + "/", case_node)
                for doc_id, case_node in self.case_of.items()
                if doc_id.endswith("/index.md")
            ),
            key=lambda item: len(item[0]),
            reverse=True,
        )
        self.nodes: dict[str, Node] = {}
        self.edges: dict[tuple[str, str, str, str], Edge] = {}

    def build(self) -> Graph:
        for document in self.documents:
            self._visit(document)
        nodes = tuple(sorted(self.nodes.values(), key=lambda node: (node.type, node.node_id)))
        edges = tuple(
            sorted(self.edges.values(), key=lambda e: (e.src, e.rel, e.dst, e.source_doc))
        )
        return Graph(nodes=nodes, edges=edges)

    def _visit(self, document: Document) -> None:
        doc_node = self._add(
            entities.DOCUMENT,
            document.doc_id,
            document.title,
            {"source": document.source, "path": document.doc_id},
        )
        case_node = self._case(document, doc_node)
        anchor = case_node or doc_node

        self._parties(document, case_node, doc_node)
        self._case_links(document, case_node)
        self._identifiers(document, anchor, doc_node)
        self._references(document, case_node, doc_node)

    def _case(self, document: Document, doc_node: str) -> str | None:
        """The case a document belongs to, or None for documents outside a case."""
        case_id = _text(document.frontmatter.get("case_id"))
        if case_id:
            attrs = {
                key: value
                for key in CASE_ATTRIBUTES
                if (value := _text(document.frontmatter.get(key)))
            }
            node = self._add(entities.CASE, case_id, case_id, attrs)
            self._link(doc_node, node, entities.BELONGS_TO, document.doc_id)
            return node

        # Raw documents carry no case_id - they name their case directly.
        for field_name in RAW_CASE_FIELDS:
            named = _text(document.frontmatter.get(field_name))
            if named:
                node = self._add(entities.CASE, named, named)
                self._link(doc_node, node, entities.ABOUT_CASE, document.doc_id)

        for prefix, case_node in self.case_dirs:
            if document.doc_id.startswith(prefix):
                self._link(doc_node, case_node, entities.BELONGS_TO, document.doc_id)
                return case_node
        return None

    def _parties(self, document: Document, case_node: str | None, doc_node: str) -> None:
        insured = _text(document.frontmatter.get("insured"))
        if insured:
            node = self._add(entities.INSURED, entities.slug(insured), insured)
            if case_node:
                self._link(case_node, node, entities.INSURED_BY, document.doc_id)
            else:
                self._link(doc_node, node, entities.MENTIONS_INSURED, document.doc_id)

        risk_class = _text(document.frontmatter.get("class"))
        if risk_class:
            node = self._add(entities.RISK_CLASS, risk_class, risk_class)
            if case_node:
                self._link(case_node, node, entities.IN_CLASS, document.doc_id)

        domain = _text(document.frontmatter.get("domain"))
        if domain and domain != "all":
            node = self._add(entities.RISK_CLASS, domain, domain)
            self._link(doc_node, node, entities.APPLIES_TO_CLASS, document.doc_id)

        for peril in _values(document.frontmatter, PERIL_FIELDS):
            node = self._add(entities.PERIL, peril, peril)
            self._link(case_node or doc_node, node, entities.INVOLVES_PERIL, document.doc_id)

    def _case_links(self, document: Document, case_node: str | None) -> None:
        if not case_node:
            return
        for field_name, relation in CASE_LINK_RELATIONS.items():
            target = _text(document.frontmatter.get(field_name))
            if not target:
                continue
            node = self._add(entities.CASE, target, target)
            self._link(case_node, node, relation, document.doc_id)

    def _identifiers(self, document: Document, anchor: str, doc_node: str) -> None:
        for clause in entities.find_clauses(document.text):
            node = self._add(entities.CLAUSE, clause, clause)
            self._link(doc_node, node, entities.MENTIONS_CLAUSE, document.doc_id)
            if anchor != doc_node:
                self._link(anchor, node, entities.MENTIONS_CLAUSE, document.doc_id)

        for lesson in entities.find_lessons(document.text):
            node = self._add(entities.LESSON, lesson, self.labels.get(lesson, lesson))
            self._link(doc_node, node, entities.RECORDS_LESSON, document.doc_id)
            if anchor != doc_node:
                self._link(anchor, node, entities.HAS_LESSON, document.doc_id)

        declared = _text(document.frontmatter.get("skill_id"))
        if declared:
            node = self._add(entities.SKILL, declared, document.title)
            self._link(doc_node, node, entities.DEFINES_SKILL, document.doc_id)
        for skill in entities.find_skills(document.text):
            if skill == declared:
                continue
            node = self._add(entities.SKILL, skill, self.labels.get(skill, skill))
            self._link(doc_node, node, entities.MENTIONS_SKILL, document.doc_id)

    def _references(self, document: Document, case_node: str | None, doc_node: str) -> None:
        case_of = self.case_of
        for link in document.links:
            target = self._resolve(link.target)
            if target is None:
                continue
            target_node = entities.node_id(entities.DOCUMENT, target)
            self._link(doc_node, target_node, entities.REFERENCES, document.doc_id)
            target_case = case_of.get(target)
            if case_node and target_case and target_case != case_node:
                self._link(case_node, target_case, entities.RELATED_CASE, document.doc_id)

        for locator in _origins(document):
            target = self._resolve(locator)
            if target is None:
                continue
            self._link(
                doc_node,
                entities.node_id(entities.DOCUMENT, target),
                entities.DERIVED_FROM,
                document.doc_id,
            )

    def _resolve(self, target: str) -> str | None:
        """Map a vault-root wikilink path or a repo-relative locator to a doc_id."""
        candidates = (target, f"{target}.md", f"wiki/{target}", f"wiki/{target}.md")
        for candidate in candidates:
            if candidate in self.known_docs:
                return candidate
        return None

    def _add(
        self, node_type: str, key: str, label: str, attrs: dict[str, str] | None = None
    ) -> str:
        identifier = entities.node_id(node_type, key)
        existing = self.nodes.get(identifier)
        merged: dict[str, object] = dict(existing.attrs) if existing else {}
        for name, value in (attrs or {}).items():
            merged.setdefault(name, value)
        self.nodes[identifier] = Node(
            node_id=identifier,
            type=node_type,
            label=_best_label(existing.label if existing else "", label, key),
            attrs=merged,
        )
        return identifier

    def _link(self, src: str, dst: str, rel: str, source_doc: str) -> None:
        if src == dst:
            return
        key = (src, rel, dst, source_doc)
        self.edges.setdefault(key, Edge(src=src, rel=rel, dst=dst, source_doc=source_doc))


def _best_label(existing: str, proposed: str, key: str) -> str:
    """A real label beats a bare identifier; otherwise the first one seen wins.

    A lesson or skill is usually named somewhere other than where it is first
    mentioned, and the naming document should win whichever order they are read.
    """
    if existing and existing != key:
        return existing
    return proposed or existing or key


def _origins(document: Document) -> tuple[str, ...]:
    """Where a source note says it came from: frontmatter original + Locator lines."""
    origins: list[str] = []
    original = _text(document.frontmatter.get("original"))
    if original:
        origins.append(original)
    origins.extend(entities.find_locators(document.text))
    return tuple(dict.fromkeys(origins))


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _values(frontmatter: dict[str, object], fields: Sequence[str]) -> tuple[str, ...]:
    found: list[str] = []
    for field_name in fields:
        value = frontmatter.get(field_name)
        if isinstance(value, str) and value.strip():
            found.append(value.strip())
        elif isinstance(value, list):
            found.extend(item.strip() for item in value if isinstance(item, str) and item.strip())
    return tuple(dict.fromkeys(found))


def main() -> None:
    documents = parse.read_documents()
    graph = build_graph(documents)
    write_graph(graph)
    print(f"graph: nodes={len(graph.nodes)} edges={len(graph.edges)}")


if __name__ == "__main__":
    main()
