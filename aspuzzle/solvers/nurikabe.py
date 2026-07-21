from aspalchemy import ANY, Field, Predicate, Term, V
from aspuzzle.grids.base import GridCell
from aspuzzle.regionconstructor import RegionConstructor
from aspuzzle.rendering import FillRule, RenderSpec, SceneStyle, digit_clues
from aspuzzle.rendering import PaletteColor as Color
from aspuzzle.solvers.base import Solver


class Clue(Predicate, show=False):
    loc: Field[GridCell]
    size: Field[int]


class Stream(Predicate):
    loc: Field[GridCell]


class Island(Predicate):
    loc: Field[GridCell]


class Nurikabe(Solver):
    solver_name = "Nurikabe puzzle solver"
    supported_symbols = (".", *range(1, 100))  # Support numbers 1-99 as island sizes

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, _config, grid_data = self.unpack_data()

        # Define island clues from the input grid
        clues = puzzle.add_segment("Clues")
        clues.section("Define numbered islands")
        clues.fact(
            *[Clue(loc=grid.Cell(*loc), size=size) for loc, size in self.int_grid_data],
        )

        # Create the region constructor for islands, anchored on the clues
        # This handles a LOT of the rules!
        # Membership domain: an island of size S cannot reach cells at distance >= S
        # from its clue, so each island's grounding is bounded by its own clue size
        cell, anchor = grid.cell(), grid.cell(suffix="anchor")
        region_domain: list[Term] | None = None
        if (distance := grid.distance_bound(cell, anchor)) is not None:
            region_domain = [Clue(loc=anchor, size=V.S), distance < V.S]
        region_constructor = RegionConstructor(
            puzzle=puzzle,
            grid=grid,
            anchor_predicate=Clue,  # Clue cells are anchors for islands
            anchor_fields={"size": ANY},
            allow_regionless=True,  # Regionless cells form the stream
            forbid_regionless_pools=True,  # No 2x2 pools of stream
            contiguous_regionless=True,  # Stream must be contiguous
            non_adjacent_regions=True,  # Each island must be isolated
            region_domain=region_domain,
        )

        puzzle.section("Each island must have the correct size")
        puzzle.when(Clue(loc=V.C, size=V.N)).require(region_constructor.region_size(V.C) == V.N)

        C = V.C
        if any(size == 1 for loc, size in grid_data):
            puzzle.section("Size-1 islands must be fully surrounded by stream")
            puzzle.when(
                Clue(loc=C, size=1),
                grid.Orthogonal(cell1=C, cell2=C["adj"]),
            ).derive(region_constructor.Regionless(loc=C["adj"]))

        puzzle.section("Solution readout")
        puzzle.when(region_constructor.Regionless(loc=C)).derive(Stream(loc=C))
        puzzle.when(region_constructor.Region(loc=C, anchor=ANY)).derive(Island(loc=C))

    def get_render_spec(self) -> RenderSpec:
        # Digits and letters up to 35; larger clues render as # (single-char
        # displays cannot say more; the sheet backend still shows the number)
        clues = digit_clues(range(1, 100), Color.BRIGHT_BLUE)
        return RenderSpec(
            clues=clues,
            atoms=[FillRule(Stream, fill=Color.BRIGHT_BLACK)],
            style=SceneStyle(packed=True),
        )
