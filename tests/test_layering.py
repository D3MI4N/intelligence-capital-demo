"""The rules that keep the swappable parts swappable, checked rather than trusted.

Three boundaries, each one a promise the architecture makes:

  the engine    only stores/ opens an index, so moving the graph onto another
                engine is a one-package change
  the provider  only agents/llm.py imports the model SDK, so the provider is
                invisible to everything that calls complete() and embed()
  the framework only agents/graph.py imports the graph framework, so the
                specialist and orchestrator logic stays plain typed Python

All three are cheap to check and expensive to discover broken.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ingest import layout
from stores import GraphStore, SqliteGraphStore, SqliteVectorStore, VectorStore

# Names that only the storage package may import.
ENGINE_MODULES = {"sqlite3", "sqlite_vec"}

# Names that only one file in the repo may import.
PROVIDER_MODULES = {"openai"}
FRAMEWORK_MODULES = {"langgraph"}
PROVIDER_FILE = "agents/llm.py"
FRAMEWORK_FILE = "agents/graph.py"

STORE_PACKAGE = "stores"
SEARCHED = ("agents", "ingest", "mcp_server", "stores", "tests")


def imports(path: Path) -> set[str]:
    """Top-level module names imported by a file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def sources() -> list[Path]:
    """Every python file in the repo, packages and root modules alike."""
    packaged = [
        path
        for directory in SEARCHED
        for path in (layout.REPO_ROOT / directory).rglob("*.py")
        if "__pycache__" not in path.parts
    ]
    return sorted([*packaged, *layout.REPO_ROOT.glob("*.py")])


def _files_importing(modules: set[str]) -> list[str]:
    """Every file in the repo that imports one of these top-level modules."""
    return sorted(
        path.relative_to(layout.REPO_ROOT).as_posix()
        for path in sources()
        if imports(path) & modules
    )


def test_the_repo_has_python_to_check() -> None:
    assert len(sources()) > 10


def test_only_the_storage_package_imports_the_database_engine() -> None:
    offenders = sorted(
        {
            path.relative_to(layout.REPO_ROOT).parts[0]
            for path in sources()
            if imports(path) & ENGINE_MODULES
        }
    )

    assert offenders == [STORE_PACKAGE]


def test_only_the_llm_module_imports_the_provider_sdk() -> None:
    """Who serves the completions is one file's business and nobody else's."""
    assert _files_importing(PROVIDER_MODULES) == [PROVIDER_FILE]


def test_only_the_graph_module_imports_the_orchestration_framework() -> None:
    """The specialists and the orchestrator read as plain functions, and stay that way."""
    assert _files_importing(FRAMEWORK_MODULES) == [FRAMEWORK_FILE]


def test_the_storage_package_does_not_depend_on_the_server() -> None:
    """Storage is the lower layer. The dependency runs one way only."""
    package = layout.REPO_ROOT / STORE_PACKAGE
    reached = {module for path in package.rglob("*.py") for module in imports(path)}

    assert "mcp_server" not in reached


def test_the_shipped_implementations_satisfy_the_protocols() -> None:
    """Checked by the type checker on these annotations, and kept honest here."""
    vectors: VectorStore = SqliteVectorStore()
    graph: GraphStore = SqliteGraphStore()

    assert callable(vectors.search)
    assert callable(graph.traverse)
    assert callable(graph.neighbours)
    assert callable(graph.get_node)
