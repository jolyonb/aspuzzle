from typing import Any, ClassVar

from aspalchemy import ANY, Choice, Count, Field, Predicate, V
from aspuzzle.grids.base import GridCell
from aspuzzle.rendering import (
    ASCII_ONLY,
    CHARACTER_BACKENDS,
    SVG_ONLY,
    FromClues,
    Glyph,
    LinkRule,
    RegionBorderRule,
    RegionFillRule,
    RenderSpec,
    SceneStyle,
)
from aspuzzle.rendering import PaletteColor as Color
from aspuzzle.solvers.base import Solver


class Region(Predicate, show=False):
    loc: Field[GridCell]
    id: Field[int]


class AdjoiningRegion(Predicate, show=False):
    id1: Field[int]
    id2: Field[int]


class Stitch(Predicate):
    loc1: Field[GridCell]
    loc2: Field[GridCell]


class ExpectedCounts(Predicate, name="expected_count", show=False):
    dir: Field[str]
    index: Field[int]
    count: Field[int]


class CellInStitch(Predicate, show=False):
    loc: Field[GridCell]


class Stitches(Solver):
    solver_name = "Stitches puzzle solver"
    default_config: ClassVar[dict[str, Any]] = {"stitch_count": 1}
    map_grid_to_integers = True

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, config, _grid_data = self.unpack_data()

        # Register stitch count as a symbolic constant
        stitch_count = puzzle.define_constant("stitch_count", config["stitch_count"])

        # Create variables
        N, A, B = V.N, V.A, V.B
        Id = V.Id
        cell = grid.cell()

        # Parse regions from the input
        regions = puzzle.add_segment("Regions")
        regions.section("Define regions")

        # Create Region facts
        regions.fact(*[Region(loc=grid.Cell(*loc), id=region_id) for loc, region_id in self.int_grid_data])

        # Define expected line counts
        clues = puzzle.add_segment("Clues")
        clues.section("Stitch counts")
        for direction in grid.line_direction_names:
            clue_key = f"{grid.line_direction_descriptions[direction]}_clues"
            for i, count in enumerate(config[clue_key], 1):
                if count is not None:
                    clues.fact(ExpectedCounts(dir=direction, index=i, count=count))

        # Rule 1: Identify adjoining regions (with Id1 < Id2)
        puzzle.section("Find adjoining regions")
        # Id[1] < Id[2] ensures we don't duplicate pairs
        puzzle.when(
            Region(loc=A, id=Id[1]),
            Region(loc=B, id=Id[2]),
            grid.Orthogonal(A, B),
            Id[1] < Id[2],
        ).derive(AdjoiningRegion(id1=Id[1], id2=Id[2]))

        # Rule 2: For each adjoining region pair, create exactly stitch_count stitches
        puzzle.section("Create stitches between adjoining regions")
        puzzle.when(
            AdjoiningRegion(id1=Id[1], id2=Id[2]),
        ).choose(
            Choice(
                element=Stitch(loc1=A, loc2=B),
                condition=[
                    Region(loc=A, id=Id[1]),
                    Region(loc=B, id=Id[2]),
                    grid.Orthogonal(A, B),
                ],
            ).exactly(stitch_count)
        )

        puzzle.section("Define cells in stitches")
        puzzle.when(Stitch(loc1=A, loc2=ANY)).derive(CellInStitch(loc=A))
        puzzle.when(Stitch(loc1=ANY, loc2=A)).derive(CellInStitch(loc=A))

        # Rule 3: Each cell can participate in at most one stitch
        puzzle.section("Cells can participate in at most one stitch")
        # For each cell that is in a stitch, count the number of other cells
        # that it is connected to via a stitch. We enforce that this must be one.
        cell_stitches = Count(element=cell, condition=Stitch(loc1=A, loc2=cell))
        cell_stitches.add(element=cell, condition=Stitch(loc1=cell, loc2=A))
        puzzle.when(CellInStitch(loc=A)).require(cell_stitches == 1)

        # Rule 4: Count stitches per line (row/column/etc)
        puzzle.section("Count stitches in each major line")
        puzzle.when(
            ExpectedCounts(dir=V.Dir, index=N, count=V.Counter),
        ).require(
            Count(cell, condition=[CellInStitch(loc=cell), grid.Line(direction=V.Dir, index=N, loc=cell)]) == V.Counter
        )

    def validate_config(self) -> None:
        """Validate the puzzle configuration."""
        self.validate_line_clues()

    def get_render_spec(self) -> RenderSpec:
        # Character grids show regions as colored blocks and pair the
        # stitches by color (there is no way to see which X ties to
        # which); backends with real geometry draw the traditional look
        # instead — region borders and red stitches, the tie connector
        # itself showing the pairing
        return RenderSpec(
            atoms=[
                RegionFillRule(FromClues(), backends=ASCII_ONLY),
                RegionBorderRule(source=FromClues(), backends=SVG_ONLY),
                LinkRule(
                    Stitch,
                    glyph=Glyph("X"),
                    palette=(Color.BRIGHT_MAGENTA, Color.BRIGHT_CYAN, Color.BRIGHT_YELLOW, Color.BRIGHT_GREEN),
                    backends=CHARACTER_BACKENDS,
                ),
                LinkRule(Stitch, glyph=Glyph("X"), color=Color.RED, backends=SVG_ONLY),
            ],
            labels=self.clue_labels(),
            style=SceneStyle(packed=True),
        )
