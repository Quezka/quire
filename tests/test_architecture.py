"""Enforce the dependency rule: source code dependencies only point inwards."""
import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "quire"

# layer -> modules it must never import
FORBIDDEN = {
    "domain": ["quire.application", "quire.infrastructure", "quire.presentation",
               "quire.bootstrap", "PySide6", "sqlite3"],
    "application": ["quire.infrastructure", "quire.presentation", "quire.bootstrap",
                    "PySide6", "sqlite3"],
    "infrastructure": ["quire.presentation", "quire.bootstrap", "PySide6"],
    "presentation": ["quire.infrastructure", "quire.bootstrap", "sqlite3"],
}


def imports_of(path: Path) -> set[str]:
    parts = path.relative_to(PACKAGE.parent).with_suffix("").parts
    package = ".".join(parts[:-1])  # for __init__.py this is the package itself
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                base = base[: len(base) - node.level + 1]
                name = ".".join(base + ([node.module] if node.module else []))
            else:
                name = node.module
            found.add(name)
    return found


@pytest.mark.parametrize("layer", sorted(FORBIDDEN))
def test_layer_respects_dependency_rule(layer):
    violations = []
    for path in sorted((PACKAGE / layer).rglob("*.py")):
        for imported in imports_of(path):
            for banned in FORBIDDEN[layer]:
                if imported == banned or imported.startswith(banned + "."):
                    violations.append(f"{path.relative_to(PACKAGE)} imports {imported}")
    assert not violations, "\n".join(violations)
