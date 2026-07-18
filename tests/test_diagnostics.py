"""Diagnostics integration: source locations must attribute to solver code.

The aspuzzle package registers its plumbing modules with aspalchemy's
skip registry (see aspuzzle/__init__.py), and Puzzle.finalize() attributes
module-emitted rules to each module's construction site. Together these
guarantee that grounding diagnostics name puzzle-author lines, never
framework internals.
"""

import json
from pathlib import Path

import pytest

from aspuzzle.solvers.base import Solver

PLUMBING_MARKERS = (
    "aspuzzle/puzzle.py",
    "aspuzzle/symbolset.py",
    "aspuzzle/regionconstructor.py",
    "aspuzzle/grids/",
    "aspuzzle/solvers/base.py",
)


PUZZLES_DIR = Path(__file__).parent.parent / "puzzles"


def build(name: str) -> Solver:
    config = json.loads((PUZZLES_DIR / f"{name}.json").read_text())
    solver = Solver.from_config(config)
    solver.construct_puzzle()
    return solver


@pytest.mark.parametrize("name, solver_file", [("galaxies", "galaxies.py"), ("nurikabe", "nurikabe.py")])
def test_grounding_profile_attributes_to_solver_code(name: str, solver_file: str) -> None:
    solver = build(name)
    profile = solver.ground().grounding_profile()
    assert profile, "expected a non-empty grounding profile"

    for signature in profile:
        for location in signature.derived_at:
            assert location is not None, f"{signature.name}/{signature.arity} has an unlocated deriving statement"
            assert not any(marker in location.filename for marker in PLUMBING_MARKERS), (
                f"{signature.name}/{signature.arity} attributes to framework plumbing: {location.display()}"
            )
            assert location.filename.endswith(solver_file), (
                f"{signature.name}/{signature.arity} attributes outside the solver: {location.display()}"
            )


def test_ground_is_cached() -> None:
    solver = build("sudoku_4x4")
    assert solver.ground() is solver.ground()
