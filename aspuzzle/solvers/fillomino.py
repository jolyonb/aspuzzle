from typing import Any

from aspalchemy import Field, Predicate, V
from aspuzzle.grids.base import GridCell
from aspuzzle.grids.rendering import BgColor, Color, RenderItem, RenderSymbol
from aspuzzle.regionconstructor import RegionConstructor
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

    def get_render_config(self) -> dict[str, Any]:
        """
        Get the rendering configuration for the Fillomino solver.

        Returns:
            Dictionary with rendering configuration for Fillomino
        """
        # Colors for the initial clues
        colors = [
            Color.BLUE,  # 1
            Color.GREEN,  # 2
            Color.RED,  # 3
            Color.MAGENTA,  # 4
            Color.CYAN,  # 5
            Color.YELLOW,  # 6
            Color.BRIGHT_BLUE,  # 7
            Color.BRIGHT_GREEN,  # 8
            Color.BRIGHT_RED,  # 9
        ]

        # Background colors for solved regions
        backgrounds = [
            BgColor.BLUE,  # 1
            BgColor.GREEN,  # 2
            BgColor.RED,  # 3
            BgColor.MAGENTA,  # 4
            BgColor.CYAN,  # 5
            BgColor.YELLOW,  # 6
            BgColor.BRIGHT_BLUE,  # 7
            BgColor.BRIGHT_GREEN,  # 8
            BgColor.BRIGHT_RED,  # 9
        ]

        # Map initial clues to symbols with colors
        puzzle_symbols = {
            i: RenderSymbol(
                symbol=str(i) if i < 10 else "#",
                color=colors[(i - 1) % 9],
            )
            for i in range(1, self.max_num)
        }

        # Setup predicates for rendering
        predicates = {
            "number": {
                "custom_renderer": lambda pred: [
                    RenderItem(
                        loc=pred["loc"],
                        symbol=str(pred["size"].value),
                        color=Color.BRIGHT_WHITE,
                        background=backgrounds[(pred["size"].value - 1) % 9],  # Cycle colors for large regions
                    )
                ],
            }
        }

        return {
            "puzzle_symbols": puzzle_symbols,
            "predicates": predicates,
            "join_char": "",  # No space between cells
        }
