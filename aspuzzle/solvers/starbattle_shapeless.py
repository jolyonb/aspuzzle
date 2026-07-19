from typing import Any, ClassVar

from aspalchemy import ANY, Count, Field, Predicate, V
from aspuzzle.grids.base import GridCell
from aspuzzle.rendering import CellStyle, Glyph, GlyphRule, RenderSpec
from aspuzzle.rendering import PaletteColor as Color
from aspuzzle.solvers.base import Solver
from aspuzzle.symbolset import SymbolSet


class Excluded(Predicate, show=False):
    loc: Field[GridCell]


class Starbattle_Shapeless(Solver):
    solver_name = "Shapeless Starbattle puzzle solver"
    supported_symbols = (".", "#")
    default_config: ClassVar[dict[str, Any]] = {"star_count": 1}

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, config, grid_data = self.unpack_data()

        star_count = puzzle.define_constant("star_count", config["star_count"])

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
        puzzle.when(grid.vertex_sharing(suffix_2="adj")).forbid(symbols["star"](cell), symbols["star"](cell_adj))

    def get_render_spec(self) -> RenderSpec:
        return RenderSpec(
            clues={"#": CellStyle(glyph=Glyph("#"), color=Color.WHITE)},
            atoms=[GlyphRule("star", glyph=Glyph("★", svg="⭐"), color=Color.BRIGHT_RED)],
        )
