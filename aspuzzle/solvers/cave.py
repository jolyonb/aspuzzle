from aspalchemy import ANY, Count, Field, Predicate, V
from aspuzzle.grids.base import GridCell, do_not_show_outside
from aspuzzle.grids.rectangulargrid import RectangularGrid
from aspuzzle.rendering import CellStyle, FillRule, Glyph, RenderSpec, SceneStyle, digit_clues
from aspuzzle.rendering import PaletteColor as Color
from aspuzzle.solvers.base import Solver
from aspuzzle.symbolset import SymbolSet


class Number(Predicate, show=False):
    loc: Field[GridCell]
    value: Field[int]


class CanSee(Predicate, show=False):
    from_loc: Field[GridCell]
    dir: Field[str]
    index: Field[int]
    position: Field[int]


class Cave(Solver):
    solver_name = "Cave/Bag/Corral puzzle solver"
    supported_symbols = (*range(1, 30), ".")  # Support numbers 1-29 and empty cells
    # TODO: Support for defining grids that have numbers > 9

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, _config, _grid_data = self.unpack_data()

        # Create variables
        C, Dir, Pos, Idx = V.C, V.Dir, V.Pos, V.Idx
        cell = grid.cell()
        cell_seen = grid.cell(suffix="seen")

        # Define numbers from the input grid
        clues = puzzle.add_segment("Clues")
        clues.section("Define numbered cells")
        clues.fact(*[Number(loc=grid.Cell(*loc), value=value) for loc, value in self.int_grid_data])

        # Define cave/wall cells using a symbol set
        symbols = SymbolSet(grid, fill_all_squares=True).add_symbol("cave").add_symbol("wall")

        # Rule 1: All outside border cells are walls
        puzzle.section("Outside border cells must be walls")
        puzzle.when(grid.OutsideGrid(C)).derive(symbols["wall"](C))
        do_not_show_outside(symbols["wall"](cell), grid)

        # Rule 2: All cave cells must form a single connected group
        symbols.make_contiguous("cave")

        # Rule 3: All wall cells must be connected to the edge of the grid
        symbols.make_contiguous("wall", anchor_cell=grid.OutsideGrid(C))

        # Rule 4: All numbered cells must be part of the cave
        puzzle.section("Numbered cells must be caves")
        puzzle.when(Number(loc=C, value=ANY)).derive(symbols["cave"](C))

        # Rule 5: Line-of-sight count for numbered cells
        puzzle.section("Line-of-sight counting")

        # Define the base case: a cell can see itself (along all orthogonal lines it sits on)
        puzzle.when(
            Number(loc=cell, value=ANY),
            grid.LineOfSight(direction=Dir, index=Idx, position=Pos, loc=cell),
        ).derive(CanSee(from_loc=cell, dir=Dir, index=Idx, position=Pos))

        # Define the recursive case: extend CanSee in positive direction only (all directions handled by LineOfSight)
        puzzle.when(
            CanSee(from_loc=cell, dir=Dir, index=Idx, position=Pos),
            grid.LineOfSight(direction=Dir, index=Idx, position=Pos + 1, loc=cell_seen),
            symbols["cave"](loc=cell_seen),
        ).derive(CanSee(from_loc=cell, dir=Dir, index=Idx, position=Pos + 1))

        # Count constraint: Numbered cells indicate how many cave cells they can see including themselves
        puzzle.when(
            Number(loc=cell, value=V.N),
        ).require(
            Count(
                cell_seen,
                condition=[
                    CanSee(from_loc=cell, dir=Dir, index=Idx, position=Pos),
                    grid.LineOfSight(direction=Dir, index=Idx, position=Pos, loc=cell_seen),
                ],
            )
            == V.N
        )

        # Supplementary Rule: No checkerboard patterns
        if isinstance(grid, RectangularGrid):
            grid.forbid_checkerboard(symbols["cave"], segment=symbols.segment)

    def get_render_spec(self) -> RenderSpec:
        # Digits as-is; numbers 10+ as # with a distinctive color
        clues = digit_clues(range(1, 10), Color.BRIGHT_BLUE)
        clues |= {value: CellStyle(glyph=Glyph("#", sheet=str(value)), color=Color.RED) for value in range(10, 30)}
        return RenderSpec(
            clues=clues,
            atoms=[FillRule("wall", fill=Color.BRIGHT_BLACK)],
            style=SceneStyle(packed=True),
        )
