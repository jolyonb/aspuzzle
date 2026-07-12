from typing import Any

from aspalchemy import ANY, Predicate, V
from aspuzzle.grids.rendering import BgColor, Color, RenderSymbol
from aspuzzle.regionconstructor import RegionConstructor
from aspuzzle.solvers.base import Solver


class Nurikabe(Solver):
    solver_name = "Nurikabe puzzle solver"
    supported_symbols = (".", *range(1, 100))  # Support numbers 1-99 as island sizes

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, _config, grid_data = self.unpack_data()

        # Define predicates
        Clue = Predicate.define("clue", ["loc", "size"], show=False)

        # Define island clues from the input grid
        clues = puzzle.add_segment("Clues")
        clues.section("Define numbered islands")
        clues.fact(
            *[Clue(loc=grid.Cell(*loc), size=size) for loc, size in grid_data],
        )

        # Create the region constructor for islands, anchored on the clues
        # This handles a LOT of the rules!
        region_constructor = RegionConstructor(
            puzzle=puzzle,
            grid=grid,
            anchor_predicate=Clue,  # Clue cells are anchors for islands
            anchor_fields={"size": ANY},
            allow_regionless=True,  # Regionless cells form the stream
            forbid_regionless_pools=True,  # No 2x2 pools of stream
            contiguous_regionless=True,  # Stream must be contiguous
            non_adjacent_regions=True,  # Each island must be isolated
        )

        puzzle.section("Each island must have the correct size")
        C = V.C
        puzzle.when(Clue(loc=C, size=V.N), region_constructor.RegionSize(anchor=C, size=V.Size)).require(V.N == V.Size)

        if any(size == 1 for loc, size in grid_data):
            puzzle.section("Size-1 islands must be fully surrounded by stream")
            puzzle.when(
                Clue(loc=C, size=1),
                grid.Orthogonal(cell1=C, cell2=C["adj"]),
            ).derive(region_constructor.Regionless(loc=C["adj"]))

        puzzle.section("Solution readout")
        Stream = Predicate.define("stream", ["loc"], show=True)
        Island = Predicate.define("island", ["loc"], show=True)
        puzzle.when(region_constructor.Regionless(loc=C)).derive(Stream(loc=C))
        puzzle.when(region_constructor.Region(loc=C, anchor=ANY)).derive(Island(loc=C))

    def get_render_config(self) -> dict[str, Any]:
        """
        Get the rendering configuration for the Nurikabe solver.

        Returns:
            Dictionary with rendering configuration for Nurikabe
        """
        # For clue numbers, use the digits as is
        puzzle_symbols = {i: RenderSymbol(str(i), Color.BRIGHT_BLUE) for i in range(1, 100)}

        return {
            "puzzle_symbols": puzzle_symbols,
            "predicates": {
                "stream": {"symbol": None, "background": BgColor.BRIGHT_BLACK},
                "island": {"symbol": None, "background": None},
            },
            "join_char": "",
        }
