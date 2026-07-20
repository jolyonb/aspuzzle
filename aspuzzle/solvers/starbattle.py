from typing import Any, ClassVar

from aspalchemy import ANY, Count, Field, Predicate, V
from aspuzzle.grids.base import GridCell
from aspuzzle.rendering import (
    ASCII_ONLY,
    SVG_ONLY,
    FromClues,
    Glyph,
    GlyphRule,
    RegionBorderRule,
    RegionFillRule,
    RenderSpec,
    SceneStyle,
)
from aspuzzle.rendering import PaletteColor as Color
from aspuzzle.solvers.base import Solver
from aspuzzle.symbolset import SymbolSet


class Region(Predicate, show=False):
    loc: Field[GridCell]
    id: Field[int]


class Starbattle(Solver):
    solver_name = "Starbattle puzzle solver"
    default_config: ClassVar[dict[str, Any]] = {"star_count": 1}
    map_grid_to_integers = True

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, config, _grid_data = self.unpack_data()

        star_count = puzzle.define_constant("star_count", config["star_count"])

        N = V.N
        cell = grid.cell()
        cell_adj = grid.cell(suffix="adj")

        # Define regions
        regions = puzzle.add_segment("Regions")
        regions.fact(*[Region(loc=grid.Cell(*loc), id=region_id) for loc, region_id in self.int_grid_data])

        # Define star placement
        symbols = SymbolSet(grid).add_symbol("star")

        # Rule 1: Place star_count stars on each line (row/column/etc) and region
        puzzle.section("Star placement rules")

        # 1a) Per line (row or column): exactly star_count stars in each line
        puzzle.when(grid.Line(direction=V.Dir, index=N, loc=ANY)).require(
            Count(cell, condition=[symbols["star"](cell), grid.Line(direction=V.Dir, index=N, loc=cell)]) == star_count
        )

        # 1b) Per region: exactly star_count stars in each region
        puzzle.when(Region(loc=ANY, id=N)).require(
            Count(cell, condition=[symbols["star"](cell), Region(loc=cell, id=N)]) == star_count
        )

        # Rule 2: Stars cannot share a vertex or edge
        puzzle.section("Star adjacency constraints")
        puzzle.when(grid.vertex_sharing(suffix_2="adj")).forbid(symbols["star"](cell), symbols["star"](cell_adj))

    def get_render_spec(self) -> RenderSpec:
        # Character grids show the regions as colored blocks; backends
        # with real geometry draw the traditional region borders
        return RenderSpec(
            atoms=[
                RegionFillRule(
                    FromClues(),
                    palette=(Color.BRIGHT_BLUE, Color.GREEN, Color.RED, Color.CYAN),
                    backends=ASCII_ONLY,
                ),
                RegionBorderRule(source=FromClues(), backends=SVG_ONLY),
                GlyphRule("star/1", glyph=Glyph("★", svg="⭐"), color=Color.BRIGHT_YELLOW),
            ],
            style=SceneStyle(packed=True),
        )
