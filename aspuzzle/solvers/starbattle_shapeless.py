from typing import Any, ClassVar

from aspalchemy import ANY, Count, Predicate, V
from aspuzzle.grids.rendering import Color, RenderSymbol
from aspuzzle.solvers.base import Solver
from aspuzzle.symbolset import SymbolSet


class Starbattle_Shapeless(Solver):
    solver_name = "Shapeless Starbattle puzzle solver"
    supported_symbols = (".", "#")
    default_config: ClassVar[dict[str, Any]] = {"star_count": 1}

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, config, grid_data = self.unpack_data()

        star_count = puzzle.define_constant("star_count", config["star_count"])

        # Define predicates
        Excluded = Predicate.define("excluded", ["loc"], show=False)
        cell = grid.cell()
        cell_adj = grid.cell(suffix="adj")

        N, Dir = V.N, V.Dir

        # Define excluded area
        excluded = puzzle.add_segment("Excluded cells")
        excluded.fact(*[Excluded(loc=grid.Cell(*loc)) for loc, _ in grid_data])

        # Define star placement
        symbols = SymbolSet(grid).add_symbol("star").excluded_symbol(Excluded(loc=cell))

        # Rule 1: Place star_count stars on each line (row/column/etc)
        puzzle.section("Star placement rules")
        puzzle.when(grid.Line(direction=Dir, index=N, loc=ANY)).require(
            Count(cell, condition=[symbols["star"](cell), grid.Line(direction=Dir, index=N, loc=cell)]) == star_count
        )

        # Rule 2: Stars cannot share a vertex or edge
        puzzle.section("Star adjacency constraints")
        puzzle.forbid(symbols["star"](cell), symbols["star"](cell_adj), grid.vertex_sharing(suffix_2="adj"))

    def get_render_config(self) -> dict[str, Any]:
        """
        Get the rendering configuration for the Star Battle solver.

        Returns:
            Dictionary with rendering configuration for Star Battle
        """
        return {
            "puzzle_symbols": {
                "#": RenderSymbol("#", Color.WHITE),
            },
            "predicates": {
                "star": {"symbol": "★", "color": Color.BRIGHT_RED},
            },
        }
