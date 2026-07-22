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

from aspuzzle.solver import Solver

PLUMBING_MARKERS = (
    "aspuzzle/puzzle.py",
    "aspuzzle/symbolset.py",
    "aspuzzle/regionconstructor.py",
    "aspuzzle/grids/",
    "aspuzzle/solver.py",
    "aspuzzle/rendering/",
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


@pytest.mark.parametrize("puzzle_file", sorted(PUZZLES_DIR.glob("*.json")), ids=lambda p: p.name)
def test_a_preview_does_not_alter_the_program(puzzle_file: Path) -> None:
    """Drawing a picture must emit nothing.

    The CLI previews before constructing (solveit.py --no-preview turns it
    off), and a render walks the grid's cells and reads a solver's own
    get_render_spec callbacks. Reaching for a rule-defining predicate from
    either would emit its rules from the rendering code, stamped with a
    rendering line — which is what grid.cell_class exists to prevent.

    Asserted as "the program is unchanged" rather than "no filename matches a
    plumbing marker": a leak from a solver's own render callback is invisible
    to a per-file whitelist, and that is exactly where the last one hid.
    """
    config = json.loads(puzzle_file.read_text())

    previewed = Solver.from_config(config)
    previewed.render_puzzle()  # the preview, before any rule is emitted
    previewed.construct_puzzle()

    plain = Solver.from_config(config)
    plain.construct_puzzle()

    # annotate=True so the comparison covers where each rule was authored,
    # not just what it says
    assert previewed.puzzle.render(annotate=True) == plain.puzzle.render(annotate=True)
