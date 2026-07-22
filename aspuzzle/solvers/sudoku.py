from typing import Any, ClassVar

from aspalchemy import Field, Predicate, RangePool, V
from aspuzzle.grids.base import GridCell
from aspuzzle.grids.rectangulargrid import RectangularGrid
from aspuzzle.rendering import GlyphRule, Lattice, RegionBorderRule, RenderSpec, SceneStyle, digit_clues
from aspuzzle.rendering import PaletteColor as Color
from aspuzzle.solver import Solver
from aspuzzle.symbolset import SymbolSet


class Block(Predicate, show=False):
    loc: Field[GridCell]
    block_id: Field[int]


class Sudoku(Solver[RectangularGrid]):
    """
    A generalized Sudoku puzzle solver.

    Features:
    - Handles standard 9x9 puzzles with 3x3 blocks
    - Supports any N^2×N^2 grid with N×N blocks (4×4, 16×16, etc.)
    - Supports non-square blocks (e.g., 6×6 with 2×3 blocks)
    - Handles number ranges from 1 to grid size
    """

    solver_name = "Sudoku puzzle solver"
    # Digits 1-9 and "." for empty cells by default, but gets modified for non-9x9 puzzles
    supported_symbols = (*list(range(1, 10)), ".")
    supported_grid_types = (RectangularGrid,)
    default_config: ClassVar[dict[str, Any]] = {
        "block_rows": None,  # Number of rows in a block
        "block_cols": None,  # Number of columns in a block
    }

    # None until validate_config resolves them (auto-derived for square grids)
    block_rows: int | None
    block_cols: int | None

    def validate_config(self) -> None:
        """Validate the Sudoku configuration."""
        grid = self.grid

        # Check that the grid is square
        if grid.rows != grid.cols:
            raise ValueError(f"Sudoku requires a square grid. Got {grid.rows}x{grid.cols}")

        # Get or calculate block dimensions
        self.block_rows = self.config["block_rows"]
        self.block_cols = self.config["block_cols"]

        grid_size = grid.rows

        # Auto-determine block size for perfect square grids (4×4, 9×9, 16×16, etc.)
        if self.block_rows is None and self.block_cols is None:
            # Try to find a perfect square factor
            n = int(grid_size**0.5)
            if n**2 == grid_size:
                self.block_rows = self.block_cols = n
            else:
                # For non-perfect squares like 6×6, we need explicit configuration
                raise ValueError(
                    f"For non-square-rooted grids like {grid_size}×{grid_size}, "
                    f"you must specify block_rows and block_cols in the configuration"
                )

        if self.block_rows is None:
            raise ValueError("block_rows must be specified in the configuration")
        if self.block_cols is None:
            raise ValueError("block_cols must be specified in the configuration")

        # Validate that block dimensions multiply to give the grid size
        if self.block_rows * self.block_cols != grid_size:
            raise ValueError(
                f"Block dimensions ({self.block_rows}×{self.block_cols}) "
                f"must multiply to give the grid size ({grid_size})"
            )

        # Update supported symbols depending on grid size
        self.supported_symbols = (*range(1, grid_size + 1), ".")

        self.remap_letter_clues(grid_size)

    def construct_puzzle(self) -> None:
        """Construct the Sudoku puzzle rules."""
        puzzle, grid, _config, grid_data = self.unpack_data()

        grid_size = grid.rows
        R, C, N, Idx = V.R, V.C, V.N, V.Idx
        Cell = V.Cell

        # Rule 1: Add numbers 1-9 to the grid, one per cell
        symbols = SymbolSet(grid, fill_all_squares=True)
        symbols.add_range_symbol(name="number", pool=RangePool(1, grid_size), show=True)
        Number = symbols["number"]

        # Rule 2: Each digit can appear only once in each row and column.
        # Pairwise "at most one" (this) versus a per-line count aggregate: the
        # aggregate grounds much cheaper (an N^4 term becomes N^2), but the
        # pairwise binary clauses propagate more strongly and solve faster on
        # hard instances. Kept pairwise deliberately — for 9x9 the ground size
        # is trivial either way, and the harder the variant, the more the
        # stronger propagation pays.
        puzzle.section("Each digit appears at most once in each row and column")
        puzzle.when(
            Number(loc=Cell[1], value=N),
            Number(loc=Cell[2], value=N),
            grid.Line(direction=V.D, index=Idx, loc=Cell[1]),
            grid.Line(direction=V.D, index=Idx, loc=Cell[2]),
        ).require(Cell[1] == Cell[2])

        # Define blocks
        puzzle.section("Define block membership")
        block_rows, block_cols = self.block_rows, self.block_cols
        assert block_rows is not None and block_cols is not None  # resolved by validate_config
        puzzle.when(
            grid.Cell(row=R, col=C),
            N == 1 + (C - 1) // block_cols + block_rows * ((R - 1) // block_rows),
        ).derive(Block(loc=grid.Cell(row=R, col=C), block_id=N))

        # Rule 3: Each digit can appear only once in each block
        puzzle.section("Each digit appears at most once in each block")
        puzzle.when(
            Number(loc=Cell[1], value=N),
            Number(loc=Cell[2], value=N),
            Block(Cell[1], block_id=Idx),
            Block(Cell[2], block_id=Idx),
        ).require(Cell[1] == Cell[2])

        # Add clues to the puzzle - these are the fixed starting values
        clues = puzzle.add_segment("Clues")
        clues.fact(*[Number(loc=grid.Cell(*loc), value=value) for loc, value in grid_data])

    def get_render_spec(self) -> RenderSpec:
        grid_size = self.grid.rows
        block_rows, block_cols = self.block_rows, self.block_cols
        assert block_rows is not None and block_cols is not None  # resolved by validate_config
        grid = self.grid

        def block_id(cell: GridCell) -> tuple[int, int]:
            row, col = grid.cell_coords(cell)
            return (row - 1) // block_rows, (col - 1) // block_cols

        return RenderSpec(
            clues=digit_clues(range(1, grid_size + 1), Color.BLUE),
            atoms=[
                GlyphRule("number/2", value_field="value", color=Color.GREEN),
                RegionBorderRule(by=block_id),
            ],
            style=SceneStyle(lattice=Lattice.FRAME),
        )
