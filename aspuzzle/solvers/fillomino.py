from typing import Any, ClassVar

from aspalchemy import ANY, Choice, Field, Predicate, RangePool, V
from aspuzzle.grids.base import GridCell
from aspuzzle.regionconstructor import RegionConstructor
from aspuzzle.rendering import GlyphRule, Layer, RenderSpec, SceneStyle, digit_clues, overflow_clues
from aspuzzle.rendering import PaletteColor as Color
from aspuzzle.solvers.base import Solver


class Clue(Predicate, show=False):
    loc: Field[GridCell]
    size: Field[int]


class Number(Predicate):
    loc: Field[GridCell]
    size: Field[int]


class DifferentRegions(Predicate, show=False):
    cell1: Field[GridCell]
    cell2: Field[GridCell]


class Fillomino(Solver):
    """
    Fillomino solver.

    Config: `max_region_size` caps how large a region may be. Puzzles should
    state it — every cell offers a number for each size up to the cap, so the
    default (the whole grid, the only bound sound without further information)
    makes that choice quadratic in the number of cells. A real Fillomino's
    largest region is far smaller than its grid.
    """

    solver_name = "Fillomino puzzle solver"
    default_config: ClassVar[dict[str, Any]] = {"max_region_size": None}
    max_num: int = 0

    def validate_config(self) -> None:
        """Check max_region_size against the grid and the clues it must admit."""
        max_region_size = self.config["max_region_size"]
        if max_region_size is None:
            return
        if not isinstance(max_region_size, int) or isinstance(max_region_size, bool) or max_region_size < 1:
            raise ValueError(f"max_region_size must be a positive integer, got {max_region_size!r}")
        if max_region_size > self.grid.cell_count:
            raise ValueError(f"max_region_size {max_region_size} exceeds the {self.grid.cell_count} cells in the grid")
        for loc, size in self.int_grid_data:
            if size > max_region_size:
                raise ValueError(f"Clue {size} at position {loc} exceeds max_region_size {max_region_size}")

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, config, grid_data = self.unpack_data()

        # Regions can be no larger than the grid; a puzzle that states its true
        # maximum offers each cell that many candidate numbers instead of one
        # per cell in the grid
        max_region_size = config["max_region_size"] or grid.cell_count

        # Define clues from the input grid
        clues = puzzle.add_segment("Clues")
        clues.fact(
            *[Clue(loc=grid.Cell(*loc), size=size) for loc, size in self.int_grid_data],
        )

        # Create variables for convenience
        A, C, C_adj, N, S = V.A, V.C, V.C_adj, V.N, V.S

        # Create the region constructor to construct polyominoes
        region_constructor = RegionConstructor(
            puzzle=puzzle,
            grid=grid,
            anchor_predicate=None,
            allow_regionless=False,
        )

        # Rule 1: Each cell in a region has a number, corresponding to the region's size
        # Rule 1a: Each cell gets a number
        # Implementation note: this is much cheaper to ground than all anchors x all cells x all sizes
        puzzle.section("Each cell holds a number, constant across its region, and corresponding to its region size")
        cell = grid.cell()
        # Clue cells
        puzzle.when(Clue(loc=C, size=S)).derive(Number(loc=C, size=S))
        # Other cells
        puzzle.when(
            cell,
            ~Clue(loc=cell, size=ANY),
        ).choose(Choice(Number(loc=cell, size=N), N.in_(RangePool(1, max_region_size))).exactly(1))

        # Rule 1b: Cells in each region have the same number
        puzzle.when(
            region_constructor.ConnectsTo(loc1=C, loc2=C_adj),
            C < C_adj,  # ConnectsTo is symmetric
            Number(loc=C, size=N),
        ).require(Number(loc=C_adj, size=N))

        # Rule 1c: Each region's number is its size (pinned at the anchor only; 1b then propagates)
        puzzle.when(
            region_constructor.Anchor(loc=A),
            Number(loc=A, size=S),
        ).require(region_constructor.region_size(A) == S)

        # Rule 2: Ensure that adjacent regions have different sizes
        puzzle.section("Regions with same size cannot touch orthogonally")
        # Splitting off the separate predicate here is important for performance!
        puzzle.when(
            grid.Orthogonal(cell1=C, cell2=C_adj),
            region_constructor.Region(loc=C, anchor=A),
            ~region_constructor.Region(loc=C_adj, anchor=A),
        ).derive(DifferentRegions(cell1=C, cell2=C_adj))
        puzzle.when(DifferentRegions(C, C_adj)).forbid(Number(C, N), Number(C_adj, N))

        # Solver helpers
        if any(size == 1 for _, size in grid_data):
            puzzle.section("1 clues must be anchors")
            puzzle.when(Clue(loc=C, size=1)).derive(region_constructor.Anchor(loc=C))

        puzzle.section("Adjacent clues with the same value must be in the same region")
        puzzle.when(
            Clue(loc=C, size=S),
            Clue(loc=C_adj, size=S),
            grid.Orthogonal(cell1=C, cell2=C_adj),
        ).derive(region_constructor.ConnectsTo(loc1=C, loc2=C_adj))

        puzzle.section("Adjacent clues with different values must be in different regions")
        puzzle.when(
            Clue(loc=C, size=S),
            Clue(loc=C_adj, size=V.S2),
            S != V.S2,
            grid.Orthogonal(cell1=C, cell2=C_adj),
        ).forbid(region_constructor.ConnectsTo(loc1=C, loc2=C_adj))

    def validate_grid_symbols(self) -> None:
        """Validate that the grid contains only supported symbols."""
        max_num = 0
        for loc, symbol in self.grid_data:
            if isinstance(symbol, int) or symbol.isdigit():
                val = int(symbol)
                if val < 1:
                    raise ValueError(f"Found number {val} in the grid; values must be >= 1.")
                max_num = max(max_num, val)
                continue
            if symbol == ".":
                continue
            raise ValueError(f"Unsupported symbol '{symbol}' at position {loc}. Supported symbols: numbers and '.'")
        self.max_num = max_num

    # Value-cycled palette shared by clue foregrounds and region backgrounds
    RENDER_PALETTE = (
        Color.BLUE,
        Color.GREEN,
        Color.RED,
        Color.MAGENTA,
        Color.CYAN,
        Color.YELLOW,
        Color.BRIGHT_BLUE,
        Color.BRIGHT_GREEN,
        Color.BRIGHT_RED,
    )

    def get_render_spec(self) -> RenderSpec:
        palette = self.RENDER_PALETTE

        def size_fill(atom: Predicate) -> Color:
            return palette[(atom["size"].value - 1) % 9]

        # Letters cover clues up to 35; larger clues render as # (the sheet
        # backend still shows the number). Clues stay at Layer.GLYPH: their
        # color matches the region fill, so the solution's white repaint is
        # the readable look
        def size_color(value: int) -> Color:
            return palette[(value - 1) % 9]

        clues = digit_clues(range(1, min(self.max_num, 35) + 1), size_color, layer=Layer.GLYPH)
        clues |= overflow_clues(range(36, self.max_num + 1), size_color, layer=Layer.GLYPH)
        return RenderSpec(
            clues=clues,
            atoms=[GlyphRule(Number, value_field="size", color=Color.BRIGHT_WHITE, fill=size_fill)],
            style=SceneStyle(packed=True),
        )
