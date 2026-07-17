from typing import Any

from aspalchemy import ANY, Choice, Count, Field, Predicate, V
from aspuzzle.grids.base import GridCell
from aspuzzle.grids.rendering import Color, RenderSymbol
from aspuzzle.solvers.base import Solver


class Tree(Predicate, show=False):
    loc: Field[GridCell]


class Tent(Predicate):
    loc: Field[GridCell]


class Tie(Predicate, show=False):
    tree_loc: Field[GridCell]
    dir: Field[str]


class TieDestination(Predicate, show=False):
    tree_loc: Field[GridCell]
    tent_loc: Field[GridCell]


class ExpectedCounts(Predicate, name="expected_count", show=False):
    dir: Field[str]
    index: Field[int]
    count: Field[int]


class Tents(Solver):
    solver_name = "Tents puzzle solver"
    supported_symbols = (".", "T")

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, config, grid_data = self.unpack_data()

        # Create variables
        C, D, A, B = V.C, V.D, V.A, V.B
        cell = grid.cell()
        vec = grid.cell(suffix="vec")

        # Define trees from input
        clues = puzzle.add_segment("Clues")
        clues.section("Trees")
        clues.fact(*[Tree(loc=grid.Cell(*loc)) for loc, _ in grid_data])

        # Define expected line counts
        clues.section("Tent counts")
        for direction in grid.line_direction_names:
            clue_key = f"{grid.line_direction_descriptions[direction]}_clues"
            for i, count in enumerate(config[clue_key], 1):
                if count is not None:
                    clues.fact(ExpectedCounts(dir=direction, index=i, count=count))

        # Rule 1: Each tree has exactly one tie in an orthogonal direction
        puzzle.section("Tree ties")
        # Decide on the direction
        puzzle.when(
            Tree(loc=C),
        ).choose(
            Choice(
                element=Tie(tree_loc=C, dir=D),
                condition=grid.OrthogonalDirections(D),
            ).exactly(1)
        )
        # Determine where it ties to
        puzzle.when(
            Tie(tree_loc=cell, dir=D),
            grid.Direction(D, vector=vec),
        ).derive(TieDestination(tree_loc=cell, tent_loc=grid.add_vector_to_cell(cell, vec)))

        # Rule 2: Place tents and validate their location
        puzzle.section("Tent placement")
        puzzle.when(TieDestination(tree_loc=ANY, tent_loc=C)).derive(Tent(loc=C))
        # Tents can only be placed in a valid cell
        puzzle.when(Tent(loc=cell)).require(cell)
        # Tents cannot be placed on a tree
        puzzle.when(Tree(C)).forbid(Tent(C))

        # Rule 3: Tents can't be shared by trees
        puzzle.when(TieDestination(tree_loc=A, tent_loc=C), TieDestination(tree_loc=B, tent_loc=C)).require(A == B)

        # Rule 4: Constraint on number of tents per line
        puzzle.section("Line tent count constraints")
        puzzle.when(
            ExpectedCounts(dir=D, index=V.N, count=V.Clue),
        ).require(Count(cell, condition=[Tent(loc=cell), grid.Line(direction=D, index=V.N, loc=cell)]) == V.Clue)

        # Rule 5: Tents cannot share a vertex
        puzzle.section("Tent adjacency constraints")
        puzzle.when(grid.VertexSharing(A, B)).forbid(Tent(A), Tent(B))

    def validate_config(self) -> None:
        """Validate the puzzle configuration."""
        self.validate_line_clues()

    def get_render_config(self) -> dict[str, Any]:
        """
        Get the rendering configuration for the Tents solver.

        Returns:
            Dictionary with rendering configuration for Tents
        """
        return {
            "puzzle_symbols": {
                "T": RenderSymbol("T", Color.GREEN),
            },
            "predicates": {
                "tent": {"symbol": "A", "color": Color.YELLOW},
            },
        }
