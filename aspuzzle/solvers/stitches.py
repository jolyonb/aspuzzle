from typing import Any, ClassVar

from aspalchemy import ANY, Choice, Count, Predicate, V
from aspuzzle.grids.region_coloring import assign_region_colors
from aspuzzle.grids.rendering import BgColor, Color, RenderItem, RenderSymbol
from aspuzzle.solvers.base import Solver


class Stitches(Solver):
    solver_name = "Stitches puzzle solver"
    default_config: ClassVar[dict[str, Any]] = {"stitch_count": 1}
    map_grid_to_integers = True
    _region_colors: dict[Any, BgColor]

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, config, grid_data = self.unpack_data()

        # Register stitch count as a symbolic constant
        stitch_count = puzzle.define_constant("stitch_count", config["stitch_count"])

        # Define predicates
        Region = Predicate.define("region", ["loc", "id"], show=False)
        AdjoiningRegion = Predicate.define("adjoining_region", ["id1", "id2"], show=False)
        Stitch = Predicate.define("stitch", ["loc1", "loc2"], show=True)
        ExpectedCounts = Predicate.define("expected_count", ["dir", "index", "count"], show=False)
        CellInStitch = Predicate.define("cell_in_stitch", ["loc"], show=False)

        # Create variables
        N, A, B = V.N, V.A, V.B
        Id = V.Id
        cell = grid.cell()

        # Parse regions from the input
        regions = puzzle.add_segment("Regions")
        regions.section("Define regions")

        # Create Region facts
        regions.fact(*[Region(loc=grid.Cell(*loc), id=region_id) for loc, region_id in grid_data])

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
        ).derive(
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
        puzzle.when(CellInStitch(loc=A), N == cell_stitches).require(N == 1)

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

    def get_render_config(self) -> dict[str, Any]:
        """
        Get the rendering configuration for the Stitches solver.

        Returns:
            Dictionary with rendering configuration for Stitches
        """
        # Create an array of distinct colors to cycle through
        stitch_colors = [
            Color.BRIGHT_MAGENTA,
            Color.BRIGHT_CYAN,
            Color.BRIGHT_YELLOW,
            Color.BRIGHT_GREEN,
        ]

        # Create a closure to track the color index
        color_index = [0]

        def stitch_renderer(pred: Predicate) -> list[RenderItem]:
            # Get the next color and increment the index
            color = stitch_colors[color_index[0] % len(stitch_colors)]
            color_index[0] += 1

            # Return both ends of the stitch with the same color
            return [
                RenderItem(loc=pred["loc1"], symbol="X", color=color),
                RenderItem(loc=pred["loc2"], symbol="X", color=color),
            ]

        puzzle_symbols = {}
        for region_id, background_color in self._region_colors.items():
            puzzle_symbols[region_id] = RenderSymbol(".", bgcolor=background_color)

        return {
            "puzzle_symbols": puzzle_symbols,
            "predicates": {
                "stitch": {"custom_renderer": stitch_renderer},
            },
            "join_char": "",
        }

    def _preprocess_config(self) -> None:
        """Precompute region colors for rendering."""
        regions: dict[Any, list[tuple[int, ...]]] = {}
        for loc, region_id in self.grid_data:
            regions.setdefault(region_id, []).append(loc)

        self._region_colors = assign_region_colors(self.grid, regions)
