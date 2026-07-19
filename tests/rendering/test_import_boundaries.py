"""
The rendering package's structural guardrails:

1. Backend-agnostic modules (backend, color, glyph, scene, spec, gridview)
   must not import anything from a backend package (ascii/, svg/) at
   runtime — TYPE_CHECKING imports are allowed.
2. ANSI escape literals exist in exactly one file: ascii/theme.py.
"""

import ast
from pathlib import Path

RENDERING = Path(__file__).parent.parent.parent / "aspuzzle" / "rendering"

# Every module directly under rendering/ is backend-agnostic by layout;
# backend-specific code lives in the subpackages
BACKEND_AGNOSTIC = sorted(path.name for path in Path(__file__).parents[2].glob("aspuzzle/rendering/*.py"))
BACKEND_PACKAGES = ("aspuzzle.rendering.ascii", "aspuzzle.rendering.svg", "aspuzzle.rendering.sheet")


def runtime_imports(path: Path) -> list[str]:
    """Module names imported at runtime (ignoring `if TYPE_CHECKING:` blocks)."""
    tree = ast.parse(path.read_text())

    def is_type_checking_block(node: ast.stmt) -> bool:
        return isinstance(node, ast.If) and isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING"

    imports: list[str] = []

    def collect(nodes: list[ast.stmt]) -> None:
        for node in nodes:
            if is_type_checking_block(node):
                continue
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module is not None:
                imports.append(node.module)
            elif isinstance(node, (ast.If, ast.Try)):
                collect(node.body)
                for handler in getattr(node, "handlers", []):
                    collect(handler.body)
                collect(node.orelse)

    collect(tree.body)
    return imports


def test_backend_agnostic_modules_import_no_backend_code() -> None:
    assert "spec.py" in BACKEND_AGNOSTIC and "regioncolor.py" in BACKEND_AGNOSTIC  # list is derived, not curated
    for name in BACKEND_AGNOSTIC:
        path = RENDERING / name
        for imported in runtime_imports(path):
            assert not imported.startswith(BACKEND_PACKAGES), (
                f"{name} imports {imported} at runtime; backend-agnostic modules may "
                f"reference backend types under TYPE_CHECKING only"
            )


def test_every_module_has_a_docstring() -> None:
    """Package convention: every non-__init__ module documents its role."""
    for path in RENDERING.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text())
        assert ast.get_docstring(tree), f"{path.relative_to(RENDERING)} is missing a module docstring"


def test_ansi_escapes_only_in_theme() -> None:
    for path in RENDERING.rglob("*.py"):
        if path.name == "theme.py" and path.parent.name == "ascii":
            continue
        source = path.read_text()
        assert "\\033" not in source and "\x1b" not in source, (
            f"{path.relative_to(RENDERING)} contains an ANSI escape literal; escape codes belong in ascii/theme.py only"
        )
