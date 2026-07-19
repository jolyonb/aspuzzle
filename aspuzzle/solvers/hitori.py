from aspalchemy import Field, Predicate, V
from aspuzzle.grids.base import GridCell
from aspuzzle.rendering import FillRule, RenderSpec, SceneStyle, digit_clues
from aspuzzle.rendering import PaletteColor as Color
from aspuzzle.solvers.base import Solver
from aspuzzle.symbolset import SymbolSet


class Value(Predicate, show=False):
    loc: Field[GridCell]
    num: Field[int]


class Hitori(Solver):
    solver_name = "Hitori puzzle solver"
    supported_symbols = tuple(range(1, 10))  # Support digits 1-9 as symbols

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, _config, _grid_data = self.unpack_data()

        # Define the predicate for the number in a cell

        # Variables for use
        C = V.C
        cell = grid.cell()
        cell_adj = grid.cell(suffix="adj")

        # Define grid values from the input grid
        puzzle.section("Define grid values")
        clues = puzzle.add_segment("Clues")
        clues.fact(
            *[Value(loc=grid.Cell(*loc), num=v) for loc, v in self.int_grid_data],
        )

        # Define shaded/unshaded cells using a symbol set
        symbols = SymbolSet(grid, fill_all_squares=True).add_symbol("black").add_symbol("white")

        # Rule 1: No number should appear unshaded more than once in a line
        puzzle.section("Rule 1: No duplicated unshaded numbers in a line")
        puzzle.when(
            grid.Line(direction=V.D, index=V.Idx, loc=C[1]),
            grid.Line(direction=V.D, index=V.Idx, loc=C[2]),
            Value(loc=C[1], num=V.N),
            Value(loc=C[2], num=V.N),
            symbols["white"](loc=C[1]),
            symbols["white"](loc=C[2]),
        ).require(C[1] == C[2])

        # Rule 2: Two black cells cannot be adjacent horizontally or vertically
        puzzle.section("Rule 2: No adjacent black cells")
        puzzle.when(
            grid.Orthogonal(cell1=cell, cell2=cell_adj),
        ).forbid(
            symbols["black"](loc=cell),
            symbols["black"](loc=cell_adj),
        )

        # Rule 3: All white cells should be connected
        puzzle.section("Rule 3: All white cells must be connected")
        symbols.make_contiguous("white")

    def get_render_spec(self) -> RenderSpec:
        return RenderSpec(
            clues=digit_clues(range(1, 10), Color.BLUE),
            atoms=[FillRule("black/1", fill=Color.WHITE)],
            style=SceneStyle(packed=True),
        )
