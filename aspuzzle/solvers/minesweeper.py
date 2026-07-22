from typing import Any, ClassVar

from aspalchemy import ANY, Count, Field, Predicate, V
from aspuzzle.grids.base import GridCell
from aspuzzle.rendering import CellStyle, Glyph, GlyphRule, RenderSpec
from aspuzzle.rendering import PaletteColor as Color
from aspuzzle.solver import Solver
from aspuzzle.symbolset import SymbolSet


class Number(Predicate, show=False):
    loc: Field[GridCell]
    num: Field[int]


class Minesweeper(Solver):
    solver_name = "Minesweeper puzzle solver"
    supported_symbols = (*list(range(10)), ".")
    default_config: ClassVar[dict[str, Any]] = {"num_mines": None}

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, config, _grid_data = self.unpack_data()

        cell = grid.cell()
        cell_adj = grid.cell(suffix="adj")

        # Define clues
        clues = puzzle.add_segment("Clues")
        clues.fact(*[Number(loc=grid.Cell(*loc), num=num) for loc, num in self.int_grid_data])

        # Define mine placement
        symbols = SymbolSet(grid).add_symbol("mine").excluded_symbol(Number(loc=cell, num=ANY))

        # Rule 1: Each number indicates exactly how many mines are adjacent
        puzzle.section("Numbers indicate the number of adjacent mines")
        puzzle.when(Number(loc=cell, num=V.N)).require(
            Count(
                cell_adj,
                condition=[
                    grid.VertexSharing(cell1=cell, cell2=cell_adj),
                    symbols["mine"](loc=cell_adj),
                ],
            )
            == V.N
        )

        # (Optional) Rule 2: Global mine count constraint
        if config["num_mines"]:
            puzzle.section("Mine count constraint")
            puzzle.require(Count(cell, condition=symbols["mine"](loc=cell)) == config["num_mines"])

    def get_render_spec(self) -> RenderSpec:
        digit_colors = {
            0: Color.WHITE,
            1: Color.BLUE,
            2: Color.GREEN,
            3: Color.RED,
            4: Color.MAGENTA,
            5: Color.CYAN,
            6: Color.YELLOW,
            7: Color.WHITE,
            8: Color.WHITE,
        }
        return RenderSpec(
            clues={value: CellStyle(glyph=Glyph(str(value)), color=color) for value, color in digit_colors.items()},
            atoms=[GlyphRule("mine/1", glyph=Glyph("*", svg="💣"), color=Color.RED)],
        )
