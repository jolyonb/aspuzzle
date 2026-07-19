import json
from pathlib import Path

import pytest

from aspuzzle.solvers.base import Solver
from aspuzzle.solvers.tents import Tent


def get_puzzle_files() -> list[Path]:
    """Find all puzzle JSON files in the puzzles directory."""
    puzzles_dir = Path(__file__).parent.parent / "puzzles"
    return list(puzzles_dir.glob("*.json"))


def test_find_puzzles() -> None:
    """Verify that we can find puzzle files."""
    puzzle_files = get_puzzle_files()
    assert len(puzzle_files) > 0, "No puzzle files found"


@pytest.mark.parametrize("puzzle_file", get_puzzle_files(), ids=lambda p: p.name)
def test_puzzle_solves(puzzle_file: Path) -> None:
    """Test that each puzzle can be solved without errors."""
    with open(puzzle_file) as f:
        config = json.load(f)

    solver = Solver.from_config(config)
    solver.construct_puzzle()
    # Solve exhaustively: validate_solutions demands exact set equality
    # against the config's expected solutions, so this also proves no
    # unlisted model exists (uniqueness, for single-solution puzzles)
    solutions, result = solver.solve(models=0)

    assert result.satisfiable, f"Puzzle {puzzle_file.name} should be satisfiable"

    # Just make sure the display code will run
    solver.display_results(solutions, result, True)

    if "solutions" in config:
        assert solver.validate_solutions(solutions), f"Solutions for {puzzle_file.name} do not match expected solutions"


def test_solution_dicts_are_signature_keyed_and_drop_negated_atoms() -> None:
    """Solution dicts key by "name/arity", and classically negated shown
    atoms are dropped — no renderer can draw one; a solver that wants -p
    visible derives a positive alias instead."""
    with open(Path(__file__).parent.parent / "puzzles" / "tents.json") as f:
        config = json.load(f)
    solver = Solver.from_config(config)
    solver.construct_puzzle()
    # A consistent negated shown fact: the unique solution has no tent here
    solver.puzzle.fact(-Tent(loc=solver.grid.Cell(row=1, col=1)))
    solutions, result = solver.solve()
    assert result.satisfiable
    assert set(solutions[0]) == {"tent/1", "tie_destination/2"}
    assert not any(atom.negated for atoms in solutions[0].values() for atom in atoms)
