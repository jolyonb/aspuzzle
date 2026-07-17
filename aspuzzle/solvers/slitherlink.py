from typing import Any

from aspalchemy import Count, Field, Predicate, V
from aspuzzle.grids.base import GridCell, do_not_show_outside
from aspuzzle.grids.rectangulargrid import RectangularGrid
from aspuzzle.grids.rendering import BgColor, Color, RenderSymbol
from aspuzzle.solvers.base import Solver
from aspuzzle.symbolset import SymbolSet


class Clue(Predicate, show=False):
    loc: Field[GridCell]
    num: Field[int]


class Sheep(Predicate, show=False):
    loc: Field[GridCell]


class Wolf(Predicate, show=False):
    loc: Field[GridCell]


class Slitherlink(Solver):
    solver_name = "Slitherlink puzzle solver"
    supported_symbols = (*list(range(4)), ".", "S", "W")

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, _config, grid_data = self.unpack_data()

        # Create variables
        N, C = V.N, V.C
        cell = grid.cell()
        cell_adj = grid.cell(suffix="adj")

        # Define clues
        clues = puzzle.add_segment("Clues")
        clues.section("Grid data")
        clues.fact(*[Clue(loc=grid.Cell(*loc), num=v) for loc, v in grid_data if v in (0, 1, 2, 3)])

        # Define sheep
        sheep_facts = [Sheep(loc=grid.Cell(*loc)) for loc, v in grid_data if v == "S"]
        if sheep_facts:
            clues.fact(*sheep_facts)

        # Define wolves
        wolf_facts = [Wolf(loc=grid.Cell(*loc)) for loc, v in grid_data if v == "W"]
        if wolf_facts:
            clues.fact(*wolf_facts)

        # Define inside/outside regions
        symbols = SymbolSet(grid, fill_all_squares=True).add_symbol("inside").add_symbol("outside")

        # Rule 1: All outside border cells are outside
        puzzle.section("Outside border cells must be outside")
        puzzle.when(grid.OutsideGrid(C)).derive(symbols["outside"](C))
        do_not_show_outside(symbols["outside"](cell), grid)

        # Rule 2: Sheep must be inside, wolves must be outside
        if sheep_facts:
            puzzle.section("Sheep constraints")
            puzzle.when(Sheep(C)).derive(symbols["inside"](C))

        if wolf_facts:
            puzzle.section("Wolf constraints")
            puzzle.when(Wolf(C)).derive(symbols["outside"](C))

        # Rule 3: Both inside and outside regions must be contiguous
        symbols.make_contiguous("inside")
        symbols.make_contiguous("outside", anchor_cell=grid.OutsideGrid(C))

        # Rule 4: Slitherlink clue constraints
        puzzle.section("Slitherlink clue constraints")

        puzzle.comment("Efficient handling for 0 clues")
        for t in ("inside", "outside"):
            puzzle.when(
                Clue(loc=C, num=0),
                symbols[t](loc=C),
                grid.Orthogonal(C, C["adj"]),
            ).require(symbols[t](loc=C["adj"]))

        puzzle.comment("General handling for 1/2/3 clues")
        # Count outside neighbors when the clue cell is inside
        puzzle.when(
            Clue(loc=cell, num=N),
            N > 0,
            symbols["inside"](loc=cell),
        ).require(Count(cell_adj, condition=[grid.orthogonal(), symbols["outside"](loc=cell_adj)]) == N)

        # Count inside neighbors when the clue cell is outside
        puzzle.when(
            Clue(loc=cell, num=N),
            N > 0,
            symbols["outside"](loc=cell),
        ).require(Count(cell_adj, condition=[grid.orthogonal(), symbols["inside"](loc=cell_adj)]) == N)

        # Helper for rectangular grids: no checkerboard patterns
        if isinstance(grid, RectangularGrid):
            grid.forbid_checkerboard(symbols["inside"], segment=symbols.segment)

    def get_render_config(self) -> dict[str, Any]:
        """
        Get the rendering configuration for the Slitherlink solver.

        Returns:
            Dictionary with rendering configuration for Slitherlink
        """
        return {
            "puzzle_symbols": {
                0: RenderSymbol("0", Color.BRIGHT_BLUE),
                1: RenderSymbol("1", Color.BRIGHT_BLUE),
                2: RenderSymbol("2", Color.BRIGHT_BLUE),
                3: RenderSymbol("3", Color.BRIGHT_BLUE),
                "S": RenderSymbol("S", Color.BRIGHT_WHITE),
                "W": RenderSymbol("W", Color.BRIGHT_RED),
            },
            "predicates": {
                "inside": {"symbol": None, "background": BgColor.BRIGHT_GREEN},
            },
            "join_char": "",
        }
