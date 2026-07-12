from typing import Any

from aspalchemy import ANY, Count, Predicate, V
from aspuzzle.grids.base import do_not_show_outside
from aspuzzle.grids.rectangulargrid import RectangularGrid
from aspuzzle.grids.rendering import BgColor, Color, RenderSymbol
from aspuzzle.solvers.base import Solver
from aspuzzle.symbolset import SymbolSet


class Cave(Solver):
    solver_name = "Cave/Bag/Corral puzzle solver"
    supported_symbols = (*range(1, 30), ".")  # Support numbers 1-29 and empty cells
    # TODO: Support for defining grids that have numbers > 9

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, _config, grid_data = self.unpack_data()

        # Define predicates
        Number = Predicate.define("number", ["loc", "value"], show=False)
        CanSee = Predicate.define("can_see", ["from_loc", "dir", "index", "position"], show=False)

        # Create variables
        C, Dir, Pos, Idx = V.C, V.Dir, V.Pos, V.Idx
        cell = grid.cell()
        cell_seen = grid.cell(suffix="seen")

        # Define numbers from the input grid
        clues = puzzle.add_segment("Clues")
        clues.section("Define numbered cells")
        clues.fact(*[Number(loc=grid.Cell(*loc), value=value) for loc, value in grid_data])

        # Define cave/wall cells using a symbol set
        symbols = SymbolSet(grid, fill_all_squares=True).add_symbol("cave").add_symbol("wall")

        # Rule 1: All outside border cells are walls
        puzzle.section("Outside border cells must be walls")
        puzzle.when(grid.OutsideGrid(C)).derive(symbols["wall"](C))
        do_not_show_outside(symbols["wall"](cell), grid)

        # Rule 2: All cave cells must form a single connected group
        symbols.make_contiguous("cave")

        # Rule 3: All wall cells must be connected to the edge of the grid
        symbols.make_contiguous("wall", anchor_cell=grid.OutsideGrid(C))

        # Rule 4: All numbered cells must be part of the cave
        puzzle.section("Numbered cells must be caves")
        puzzle.when(Number(loc=C, value=ANY)).derive(symbols["cave"](C))

        # Rule 5: Line-of-sight count for numbered cells
        puzzle.section("Line-of-sight counting")

        # Define the base case: a cell can see itself (along all orthogonal lines it sits on)
        puzzle.when(
            Number(loc=cell, value=ANY),
            grid.LineOfSight(direction=Dir, index=Idx, position=Pos, loc=cell),
        ).derive(CanSee(from_loc=cell, dir=Dir, index=Idx, position=Pos))

        # Define the recursive case: extend CanSee in positive direction only (all directions handled by LineOfSight)
        puzzle.when(
            CanSee(from_loc=cell, dir=Dir, index=Idx, position=Pos),
            grid.LineOfSight(direction=Dir, index=Idx, position=Pos + 1, loc=cell_seen),
            symbols["cave"](loc=cell_seen),
        ).derive(CanSee(from_loc=cell, dir=Dir, index=Idx, position=Pos + 1))

        # Count constraint: Numbered cells indicate how many cave cells they can see including themselves
        puzzle.when(
            Number(loc=cell, value=V.N),
        ).require(
            Count(
                cell_seen,
                condition=[
                    CanSee(from_loc=cell, dir=Dir, index=Idx, position=Pos),
                    grid.LineOfSight(direction=Dir, index=Idx, position=Pos, loc=cell_seen),
                ],
            )
            == V.N
        )

        # Supplementary Rule: No checkerboard patterns
        if isinstance(grid, RectangularGrid):
            grid.forbid_checkerboard(symbols["cave"], segment=symbols.segment)

    def get_render_config(self) -> dict[str, Any]:
        """
        Get the rendering configuration for the Cave puzzle solver.

        Returns:
            Dictionary with rendering configuration
        """
        # For numbers 1-9, use the digit as is
        puzzle_symbols = {i: RenderSymbol(str(i), Color.BRIGHT_BLUE) for i in range(1, 10)}

        # For numbers 10+, use # with a distinctive color
        for i in range(10, 30):
            puzzle_symbols[i] = RenderSymbol("#", Color.RED)

        return {
            "puzzle_symbols": puzzle_symbols,
            "predicates": {
                "cave": {"symbol": None, "background": None},
                "wall": {"symbol": None, "background": BgColor.BRIGHT_BLACK},
            },
            "join_char": "",
        }
