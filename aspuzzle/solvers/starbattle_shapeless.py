from typing import Any, ClassVar

from aspalchemy import ANY, Count, Field, Predicate, V
from aspuzzle.grids.base import GridCell
from aspuzzle.rendering import Glyph, GlyphRule, RenderSpec, filled_clue
from aspuzzle.rendering import PaletteColor as Color
from aspuzzle.solver import Solver
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

        N, Dir = V.N, V.Dir

        # Define star placement
        symbols = SymbolSet(grid).add_symbol("star")

        # Define excluded area
        if grid_data:  # Don't have exclude rules on a completely open board
            excluded = puzzle.add_segment("Excluded cells")
            excluded.fact(*[Excluded(loc=grid.Cell(*loc)) for loc, _ in grid_data])
            symbols.excluded_symbol(Excluded(loc=cell))

        # Rule 1: Place star_count stars on each line (row/column/etc)
        puzzle.section("Star placement rules")
        puzzle.when(grid.Line(direction=Dir, index=N, loc=ANY)).require(
            Count(cell, condition=[symbols["star"](cell), grid.Line(direction=Dir, index=N, loc=cell)]) == star_count
        )

        # Rule 2: Stars cannot share a vertex or edge
        puzzle.section("Star adjacency constraints")
        A, B = V.A, V.B
        puzzle.when(
            grid.VertexSharing(cell1=A, cell2=B),
            A < B,
        ).forbid(symbols["star"](A), symbols["star"](B))

    def get_render_spec(self) -> RenderSpec:
        return RenderSpec(
            clues={"#": filled_clue(Glyph("#"), char_color=Color.WHITE)},
            atoms=[GlyphRule("star/1", glyph=Glyph("★", svg="⭐"), color=Color.BRIGHT_RED)],
        )
