"""The rule that makes the store swappable: only stores/ knows the engine.

If a module outside the storage package opens an index itself, the protocols
stop being the boundary they are documented to be, and moving the graph onto a
different engine stops being a one-package change. This is cheap to check, so
it is checked rather than trusted.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ingest import layout
from stores import GraphStore, SqliteGraphStore, SqliteVectorStore, VectorStore

# Names that only the storage package may import.
ENGINE_MODULES = {"sqlite3", "sqlite_vec"}

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
