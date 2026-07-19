from aspalchemy import Field, Predicate, V
from aspuzzle.grids.base import GridCell
from aspuzzle.regionconstructor import RegionConstructor
from aspuzzle.rendering import CellStyle, Glyph, GlyphRule, RenderSpec, SceneStyle, glyph_for_value
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
    solver_name = "Fillomino puzzle solver"
    max_num: int = 0

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, _config, grid_data = self.unpack_data()

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

        # Rule 1: Fill each cell with a number corresponding to the size of its region
        puzzle.section("Region size determines the number in each cell")
        puzzle.when(
            region_constructor.Region(loc=C, anchor=A),
            region_constructor.RegionSize(anchor=A, size=S),
        ).derive(Number(loc=C, size=S))

        # Rule 2: Ensure that given clues match the numbers obtained from region sizes
        puzzle.section("Given clues must match their region sizes")
        puzzle.when(Clue(loc=C, size=S), Number(loc=C, size=N)).require(N == S)

        # Rule 3: Ensure that adjacent regions have different sizes
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

        # These rules did not help the solver

        # puzzle.section("Size-1 regions cannot connect to other cells")
        # puzzle.forbid(Clue(loc=C, size=1), region_constructor.ConnectsTo(loc1=C, loc2=ANY))

        # puzzle.section("Clues with different numbers cannot have the same anchor")
        # puzzle.forbid(
        #     Clue(loc=C, size=S),
        #     Clue(loc=C2, size=S2),
        #     region_constructor.Region(loc=C, anchor=A),
        #     region_constructor.Region(loc=C2, anchor=A),
        #     S != S2,
        # )

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
        # backend still shows the number)
        clues: dict[int | str, CellStyle] = {
            value: CellStyle(glyph=glyph_for_value(value), color=palette[(value - 1) % 9])
            for value in range(1, min(self.max_num, 35) + 1)
        }
        clues |= {
            value: CellStyle(glyph=Glyph("#", sheet=str(value)), color=palette[(value - 1) % 9])
            for value in range(36, self.max_num + 1)
        }
        return RenderSpec(
            clues=clues,
            atoms=[GlyphRule(Number, value_field="size", color=Color.BRIGHT_WHITE, fill=size_fill)],
            style=SceneStyle(packed=True),
        )
