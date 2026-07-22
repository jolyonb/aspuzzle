"""Lifecycle hardening: no entry point may reach clasp with rules missing.

Puzzle.solve() finalizes like ground()/render() do; Solver.ground() runs
construct_puzzle() if the caller has not; construct_puzzle() is idempotent;
and modules cannot be registered after finalization (their finalize() would
silently never run).
"""

import json
from itertools import islice
from pathlib import Path

import pytest

from aspuzzle.grids.rectangulargrid import RectangularGrid
from aspuzzle.puzzle import Puzzle
from aspuzzle.solver import Solver
from aspuzzle.symbolset import SymbolSet

PUZZLES_DIR = Path(__file__).parent.parent / "puzzles"


def build(name: str) -> Solver:
    config = json.loads((PUZZLES_DIR / f"{name}.json").read_text())
    return Solver.from_config(config)


def test_solver_solve_constructs_automatically() -> None:
    solver = build("sudoku_4x4")
    # No explicit construct_puzzle() call: ground() must run it
    solutions, result = solver.solve()
    assert result.satisfiable
    assert solver.validate_solutions(solutions)


def test_render_program_constructs_automatically() -> None:
    explicit = build("sudoku_4x4")
    explicit.construct_puzzle()
    expected = explicit.puzzle.render()

    assert build("sudoku_4x4").render_program() == expected


def test_construct_puzzle_is_idempotent() -> None:
    solver = build("sudoku_4x4")
    solver.construct_puzzle()
    rendered = solver.puzzle.render()
    solver.construct_puzzle()
    solver.ground()  # would construct a second time without the guard
    assert solver.puzzle.render() == rendered


def test_puzzle_solve_finalizes_modules() -> None:
    puzzle = Puzzle()
    grid = RectangularGrid(puzzle, rows=2, cols=2)
    symbols = SymbolSet(grid, fill_all_squares=True)
    symbols.add_symbol("x")
    # The placement choice is emitted in SymbolSet.finalize(); without
    # finalization, solve() would yield one model with no placements at all
    models = list(islice(puzzle.solve(), 2))
    assert len(models) == 1
    assert len(models[0].atoms(symbols["x"])) == 4


def test_register_module_after_finalize_raises() -> None:
    puzzle = Puzzle()
    grid = RectangularGrid(puzzle, rows=2, cols=2)
    puzzle.finalize()
    with pytest.raises(RuntimeError, match="finalized"):
        SymbolSet(grid)
