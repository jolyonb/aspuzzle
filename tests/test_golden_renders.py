"""Byte-level golden tests for every puzzle, render mode, and backend.

Pins the exact output of rendering — parametrized over every config in
puzzles/, both modes (preview = render with no solution, solution = render
of the first model), and every render backend. ANSI escape bytes are part
of the pinned output for the ascii backend. Goldens live at
tests/goldens/<backend>/<puzzle>/<mode>.txt; new backends (svg, tsv) join
by adding one entry to BACKENDS.

After reviewing an intentional visual change, re-bless with:

    pytest tests/test_golden_renders.py --update-goldens
"""

import json
from collections.abc import Callable
from functools import cache
from pathlib import Path

import pytest

from aspalchemy import Predicate
from aspuzzle.solvers.base import Solver
from tests.test_puzzles import get_puzzle_files

GOLDEN_ROOT = Path(__file__).parent / "goldens"

type Solution = dict[str, list[Predicate]]

MODES = ("preview", "solution")

# One renderer per backend; svg and tsv join here when those backends land.
BACKENDS: dict[str, Callable[[Solver, Solution | None], str]] = {
    "ascii": lambda solver, solution: solver.render_puzzle(solution),
}


@cache
def solver_and_first_solution(puzzle_file: Path) -> tuple[Solver, Solution]:
    """Build the solver and solve once per puzzle, shared across parametrizations."""
    with open(puzzle_file) as f:
        config = json.load(f)

    solver = Solver.from_config(config)
    solutions, result = solver.solve()
    assert result.satisfiable, f"Puzzle {puzzle_file.name} should be satisfiable"
    return solver, solutions[0]


@pytest.mark.parametrize("backend", sorted(BACKENDS))
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("puzzle_file", get_puzzle_files(), ids=lambda p: p.name)
def test_golden_render(puzzle_file: Path, mode: str, backend: str, update_goldens: bool) -> None:
    solver, solution = solver_and_first_solution(puzzle_file)
    text = BACKENDS[backend](solver, solution if mode == "solution" else None)

    golden_path = GOLDEN_ROOT / backend / puzzle_file.stem / f"{mode}.txt"

    if update_goldens:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(text)
        return

    assert golden_path.exists(), f"Missing golden {golden_path}; generate with --update-goldens"
    assert text == golden_path.read_text(), (
        f"{backend}/{puzzle_file.stem}/{mode} differs from its golden; if the change is intentional, "
        f"re-bless with: pytest tests/test_golden_renders.py --update-goldens"
    )
