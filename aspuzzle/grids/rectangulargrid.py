from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any

from aspalchemy import Expression, Field, Predicate, RangePool, Segment, V
from aspuzzle.grids.base import CellOrder, Grid, GridCell, GridCellData
from aspuzzle.puzzle import Puzzle, cached_predicate
from aspuzzle.rendering.grids.rectangular_ascii import RectangularAsciiGeometry
from aspuzzle.rendering.grids.rectangular_svg import RectangularSvgGeometry

if TYPE_CHECKING:
    from aspalchemy import PredicateArg
    from aspuzzle.rendering.scene import LayoutNeeds, SceneStyle


class RectangularCell(GridCell, name="cell", show=False):
    """A rectangular grid position, statically typed: solvers on a
    RectangularGrid read .row/.col directly."""

    row: Field[int]
    col: Field[int]


class OutsideGrid(Predicate, show=False):
    loc: Field[GridCell]


class Line(Predicate, show=False):
    direction: Field[str]
    index: Field[int]
    loc: Field[GridCell]


class LineOfSight(Predicate, show=False):
    direction: Field[str]
    index: Field[int]
    position: Field[int]
    loc: Field[GridCell]


class RectangularGrid(Grid):
    """Module for rectangular grid-based puzzles with rows and columns. Note that this uses 1-based indexing!"""

    def __init__(
        self,
        puzzle: Puzzle,
        rows: int,
        cols: int,
        name: str = "grid",
        primary_namespace: bool = True,
        outside_border: bool = False,
    ):
        """Initialize a grid module with specified dimensions."""
        super().__init__(puzzle, name, primary_namespace, outside_border=outside_border)

        assert isinstance(rows, int)
        assert isinstance(cols, int)

        self.rows = rows
        self.cols = cols

    def with_new_puzzle(self, puzzle: Puzzle) -> RectangularGrid:
        """Return a copy of this Grid with a new puzzle."""
        return type(self)(
            puzzle=puzzle,
            rows=self.rows,
            cols=self.cols,
            name=self._name,
            primary_namespace=self._namespace == "",
            outside_border=self.has_outside_border,
        )

    @property
    def cell_fields(self) -> list[str]:
        """Returns the list of field names associated with the Cell predicate for this grid"""
        return ["row", "col"]

    @property
    def cell_var_names(self) -> list[str]:
        """Returns the default list of variable names for the Cell predicate for this grid"""
        return ["R", "C"]

    @property
    def direction_vectors(self) -> list[tuple[str, tuple[int, ...]]]:
        """Returns the list of directions and vectors for this grid"""
        return [
            ("n", (-1, 0)),
            ("ne", (-1, 1)),
            ("e", (0, 1)),
            ("se", (1, 1)),
            ("s", (1, 0)),
            ("sw", (1, -1)),
            ("w", (0, -1)),
            ("nw", (-1, -1)),
        ]

    @property
    def orthogonal_direction_names(self) -> list[str]:
        """Returns the list of orthogonal direction names for this grid"""
        return ["n", "e", "s", "w"]

    @property
    def opposite_directions(self) -> list[tuple[str, str]]:
        """Returns the list of opposite direction names for this grid"""
        return [
            ("n", "s"),
            ("ne", "sw"),
            ("e", "w"),
            ("se", "nw"),
            ("s", "n"),
            ("sw", "ne"),
            ("w", "e"),
            ("nw", "se"),
        ]

    @property
    def line_direction_names(self) -> list[str]:
        """Returns the list of line direction names for rectangular grid"""
        return ["e", "s"]  # e for rows, s for columns

    @property
    def line_direction_descriptions(self) -> dict[str, str]:
        """Returns descriptions for rectangular grid lines"""
        return {"e": "row", "s": "column"}

    def get_line_count(self, direction: str) -> int:
        """Returns the number of lines in the specified direction for a rectangular grid"""
        if direction == "e":  # rows
            return self.rows
        if direction == "s":  # columns
            return self.cols
        raise ValueError(f"Unknown direction: {direction}")

    @property
    def cell_class(self) -> type[RectangularCell]:
        """The cell predicate class, defining nothing (see Grid.cell_class)."""
        return RectangularCell.in_namespace(self.namespace)

    @property
    @cached_predicate
    def Cell(self) -> type[RectangularCell]:
        """Get the Cell predicate for this grid, defining the cell domain."""
        Cell = self.cell_class

        R, C = V.R, V.C
        cell = Cell(R, C)

        border = self.has_outside_border
        rows = RangePool(0, self.rows + 1) if border else RangePool(1, self.rows)
        cols = RangePool(0, self.cols + 1) if border else RangePool(1, self.cols)

        self.section("Define cells in the grid")
        self.when(R.in_(rows), C.in_(cols)).derive(cell)

        if border:
            Outside = OutsideGrid.in_namespace(self.namespace)

            # Top and bottom rows, then the left and right columns without
            # double-counting the corners
            self.section("Define outside border cells")
            self.when(R.in_([0, self.rows + 1]), C.in_(RangePool(0, self.cols + 1))).derive(Outside(loc=cell))
            self.when(C.in_([0, self.cols + 1]), R.in_(RangePool(1, self.rows))).derive(Outside(loc=cell))

        return Cell

    def cell(self, suffix: str = "") -> RectangularCell:
        """Get a cell predicate for this grid with variable values."""
        cell = super().cell(suffix)
        assert isinstance(cell, RectangularCell)
        return cell

    @property
    @cached_predicate
    def CellOrder(self) -> type[CellOrder]:
        """
        Get the CellOrder predicate. Two interval rules construct the row-major
        successor chain, which is exactly ascending clingo term order for
        cell(R, C) — required so that chain-based anchor selection picks the
        same cell a lexicographic minimum would. Written over explicit index
        ranges rather than joins on cell atoms: cell/2 also holds
        outside-border cells when the border is in use, and those must never
        enter the chain (find_anchor_cell's guard turns an off-chain candidate
        into an UNSAT, so keeping the border out is a correctness requirement,
        not just tidiness).
        """
        CellOrderClone = CellOrder.in_namespace(self.namespace)
        R, C = V.R, V.C

        self.section("Cell order chain")
        # Within a row: cell(R, C) -> cell(R, C+1)
        self.when(R.in_(RangePool(1, self.rows)), C.in_(RangePool(1, self.cols - 1))).derive(
            CellOrderClone(prev=self.Cell(row=R, col=C), next=self.Cell(row=R, col=C + 1))
        )
        # Row wrap: cell(R, last_col) -> cell(R+1, 1)
        self.when(R.in_(RangePool(1, self.rows - 1))).derive(
            CellOrderClone(prev=self.Cell(row=R, col=self.cols), next=self.Cell(row=R + 1, col=1))
        )

        return CellOrderClone

    @property
    @cached_predicate
    def OutsideGrid(self) -> type[OutsideGrid]:
        """Get the OutsideGrid predicate identifying cells in the outside border."""
        if not self.has_outside_border:
            raise ValueError(
                f"Grid '{self.name}' has no outside border: set outside_border on the solver "
                f"(Solver.outside_border) if its rules need to talk about cells beyond the board."
            )

        # Make sure that cells have been emitted
        _ = self.Cell
        return OutsideGrid.in_namespace(self.namespace)

    @property
    @cached_predicate
    def Line(self) -> type[Line]:
        """Get the Line predicate defining major lines in the grid."""
        LineClone = Line.in_namespace(self.namespace)

        R, C = V.R, V.C
        cell = self.Cell(row=R, col=C)

        self.section("Define major lines in the grid")

        # For rectangular grids, define rows (direction E) and columns (direction S)
        # Row lines: all cells in the same row
        self.when(cell, R.in_(RangePool(1, self.rows))).derive(LineClone(direction="e", index=R, loc=cell))

        # Column lines: all cells in the same column
        self.when(cell, C.in_(RangePool(1, self.cols))).derive(LineClone(direction="s", index=C, loc=cell))

        return LineClone

    @property
    @cached_predicate
    def LineOfSight(self) -> type[LineOfSight]:
        """
        Get the LineOfSight predicate defining lines in all orthogonal directions with position ordering.

        For a rectangular grid, this defines lines in all 4 orthogonal directions (n, e, s, w)
        with a position parameter indicating the ordinal position along that line.
        """
        LineOfSightClone = LineOfSight.in_namespace(self.namespace)

        R, C = V.R, V.C
        cell = self.Cell(row=R, col=C)

        self.section("Define ordered positions along orthogonal lines in the grid")

        # East direction (rows): all cells in the same row, with column number as position
        self.when(cell).derive(LineOfSightClone(direction="e", index=R, position=C, loc=cell))

        # West direction (rows): all cells in the same row, with reversed column position
        self.when(cell).derive(LineOfSightClone(direction="w", index=R, position=self.cols + 1 - C, loc=cell))

        # South direction (columns): all cells in the same column, with row number as position
        self.when(cell).derive(LineOfSightClone(direction="s", index=C, position=R, loc=cell))

        # North direction (columns): all cells in the same column, with reversed row position
        self.when(cell).derive(LineOfSightClone(direction="n", index=C, position=self.rows + 1 - R, loc=cell))

        return LineOfSightClone

    @classmethod
    def from_config(
        cls,
        puzzle: Puzzle,
        config: dict[str, Any],
        name: str = "grid",
        primary_namespace: bool = True,
        outside_border: bool = False,
    ) -> RectangularGrid:
        """Create a rectangular grid from configuration."""
        # Get explicit grid parameters if provided
        grid_params = config.get("grid_params", {}).copy()
        grid: list[str] | list[list[str | int]] | None = config.get("grid")

        # Determine rows
        if "rows" in grid_params:
            rows = grid_params["rows"]
        elif grid is not None:
            rows = len(grid)
        else:
            raise ValueError("Grid rows must be specified in grid_params or grid")

        # Determine cols
        if "cols" in grid_params:
            cols = grid_params["cols"]
        elif grid is not None:
            cols = len(grid[0])
        else:
            raise ValueError("Grid cols must be specified in grid_params or grid")

        # Create and return the grid
        return cls(
            puzzle,
            rows=rows,
            cols=cols,
            name=name,
            primary_namespace=primary_namespace,
            outside_border=outside_border,
        )

    def parse_grid(
        self, grid_data: list[str] | list[list[str | int]], map_to_integers: bool = False
    ) -> list[GridCellData]:
        """
        Parse a rectangular grid into organized structures, ignoring any "." characters.

        Args:
            grid_data: The raw grid data as a list of strings, or a list of lists of strings or integers
            map_to_integers: Whether to convert symbols to unique integers

        Returns:
            List of (loc, value) tuples for non-empty cells
        """
        rows = self.rows
        cols = self.cols

        # Turn the input grid_data into a list of lists version as necessary
        clean_grid_data: list[list[str | int]] = [e if isinstance(e, list) else list(e) for e in grid_data]

        # Validate grid dimensions
        if len(clean_grid_data) != rows:
            raise ValueError(f"Expected {rows} rows in grid, got {len(clean_grid_data)}")
        for row in clean_grid_data:
            if len(row) != cols:
                raise ValueError(f"Expected {cols} cols in row, got {len(row)}")

        symbol_to_id = {}
        if map_to_integers:
            # First, collect all unique symbols
            unique_symbols = set()
            for row in clean_grid_data:
                for char in row:
                    if char != ".":
                        unique_symbols.add(char)

            # Create mapping from symbols to integer IDs
            # First map numbers to themselves (if they exist)
            used_ids = set()

            # Map numeric symbols first
            for symbol in unique_symbols:
                if isinstance(symbol, int) or (isinstance(symbol, str) and symbol.isdigit()):
                    id_num = int(symbol)
                    symbol_to_id[symbol] = id_num
                    used_ids.add(id_num)

            # Map non-numeric symbols to unused integers
            next_id = 1
            for symbol in sorted(unique_symbols):  # Sort for consistency
                if symbol not in symbol_to_id:
                    while next_id in used_ids:
                        next_id += 1
                    symbol_to_id[symbol] = next_id
                    used_ids.add(next_id)
                    next_id += 1

        # Parse cells
        cells: list[GridCellData] = []

        for r, line in enumerate(clean_grid_data):
            for c, char in enumerate(line):
                # Special case: ignore "." characters
                if char == ".":
                    continue

                # Process the value
                value: int | str
                if map_to_integers and char in symbol_to_id:
                    value = symbol_to_id[char]
                else:
                    value = int(char) if isinstance(char, str) and char.isdigit() else char

                # Add to cells list
                cell_entry = ((r + 1, c + 1), value)
                cells.append(cell_entry)

        return cells

    def add_vector_to_cell(self, cell_pred: GridCell, vector_pred: GridCell) -> GridCell:
        """Add a vector to a cell in rectangular coordinates."""
        assert isinstance(cell_pred, RectangularCell)
        assert isinstance(vector_pred, RectangularCell)
        return self.Cell(row=cell_pred.row + vector_pred.row, col=cell_pred.col + vector_pred.col)

    def distance_bound(self, cell1: GridCell, cell2: GridCell) -> Expression:
        """Manhattan distance — exact graph distance under orthogonal adjacency."""
        # Bracket access (the Term view) on purpose: these cells hold rule
        # variables, and attribute reads are statically typed by the ground
        # schema (int), which cannot build a typed Expression
        row_distance: Expression = abs(cell1["row"] - cell2["row"])
        col_distance: Expression = abs(cell1["col"] - cell2["col"])
        return row_distance + col_distance

    def neighbor(self, cell: GridCell, direction: str) -> RectangularCell | None:
        """Pure-arithmetic mirror of the orthogonal direction vectors."""
        assert isinstance(cell, RectangularCell)
        if direction not in self.orthogonal_direction_names:
            raise ValueError(f"{direction!r} is not an edge direction of a rectangular grid")
        row_step, col_step = self.direction_vector(direction)
        row, col = self.cell_coords(cell)
        adjacent = self.cell_at((row + row_step, col + col_step))
        assert adjacent is None or isinstance(adjacent, RectangularCell)
        return adjacent

    @property
    def corner_names(self) -> Sequence[str]:
        """Rectangular corners, vertical letter first."""
        return ("nw", "ne", "se", "sw")

    def corner_across(self, corner: str, direction: str) -> str | None:
        """Crossing an edge incident to the corner flips that axis of its name."""
        vertical, horizontal = corner[0], corner[1]
        if direction == vertical:
            return self.opposite_direction(vertical) + horizontal
        if direction == horizontal:
            return vertical + self.opposite_direction(horizontal)
        return None

    def all_cells(self) -> Iterator[GridCell]:
        """Every in-grid cell, row-major."""
        for row in range(1, self.rows + 1):
            for col in range(1, self.cols + 1):
                yield self.cell_class(row=row, col=col)

    @property
    def cell_count(self) -> int:
        return self.rows * self.cols

    def ascii_geometry(self, needs: LayoutNeeds, style: SceneStyle) -> RectangularAsciiGeometry:
        return RectangularAsciiGeometry(self, needs, style)

    def svg_geometry(self) -> RectangularSvgGeometry:
        return RectangularSvgGeometry(self)

    def forbid_2x2_blocks(
        self,
        symbol_predicate: type[Predicate],
        segment: Segment,
        fixed_fields: dict[str, PredicateArg] | None = None,
        loc_field: str = "loc",
    ) -> None:
        """
        Forbid 2x2 blocks of a specific symbol/predicate in a rectangular grid.

        Args:
            symbol_predicate: The predicate class representing the symbol to constrain
            segment: Segment to publish these rules to
            fixed_fields: Fixed field values for the predicate (for multi-field predicates)
            loc_field: The predicate's cell field, for predicates that name it
                something other than "loc"

        Example:
            # Forbid 2x2 blocks of mines
            grid.forbid_2x2_blocks(symbols["mine"], segment=symbols.segment)

            # For a predicate with multiple fields, specify which fields to fix
            grid.forbid_2x2_blocks(symbols["digit"], segment=symbols.segment, fixed_fields={"value": Var})
            # This forbids 2x2 blocks of any individual digit
        """
        if fixed_fields is None:
            fixed_fields = {}

        segment.section(f"Forbid 2x2 blocks of {symbol_predicate.get_name()}")

        R, C = V.R, V.C
        top_left_cell = self.Cell(row=R, col=C)
        top_right_cell = self.Cell(row=R, col=C + 1)
        bottom_left_cell = self.Cell(row=R + 1, col=C)
        bottom_right_cell = self.Cell(row=R + 1, col=C + 1)

        segment.forbid(
            symbol_predicate(**{loc_field: top_left_cell}, **fixed_fields),
            symbol_predicate(**{loc_field: top_right_cell}, **fixed_fields),
            symbol_predicate(**{loc_field: bottom_left_cell}, **fixed_fields),
            symbol_predicate(**{loc_field: bottom_right_cell}, **fixed_fields),
            top_left_cell,
            bottom_right_cell,
        )

    def require_rectangular(
        self,
        symbol_predicate: type[Predicate],
        segment: Segment,
        fixed_fields: dict[str, PredicateArg] | None = None,
        loc_field: str = "loc",
    ) -> None:
        """
        Force the cells holding a predicate to form rectangles: wherever three
        corners of a 2x2 hold it, so must the fourth.

        Args:
            symbol_predicate: The predicate class whose cells must be rectangular
            segment: Segment to publish these rules to
            fixed_fields: Fixed field values for the predicate (for multi-field
                predicates) — pass a variable to shape each value separately,
                e.g. fixed_fields={"anchor": V.A} for one rectangle per region
            loc_field: The predicate's cell field, for predicates that name it
                something other than "loc"

        Stated as four requirements rather than four derivations, which is what
        lets a caller apply this to a predicate whose domain is restricted:
        deriving the fourth corner would assert membership its own domain may
        bar, while requiring it simply rejects the three-corner configuration.
        """
        if fixed_fields is None:
            fixed_fields = {}

        segment.section(f"Rectangular regions of {symbol_predicate.get_name()}")

        R, C = V.R, V.C
        corners = [(0, 0), (1, 0), (0, 1), (1, 1)]

        def corner_atom(row_offset: int, col_offset: int) -> Predicate:
            # Offsets of zero are left off the term: cell(R, C) reads better
            # than cell(R + 0, C + 0) in the program this writes
            cell = self.Cell(row=R + row_offset if row_offset else R, col=C + col_offset if col_offset else C)
            return symbol_predicate(**{loc_field: cell}, **fixed_fields)

        for corner in corners:
            body = [corner_atom(row, col) for row, col in corners if (row, col) != corner]
            segment.when(*body).require(corner_atom(*corner))

    def forbid_checkerboard(
        self,
        symbol_predicate: type[Predicate],
        segment: Segment,
        fixed_fields: dict[str, PredicateArg] | None = None,
        loc_field: str = "loc",
    ) -> None:
        """
        Forbids a 2x2 block checkerboard pattern of a given predicate in a rectangular grid.
        If the symbol is contiguous and not(symbol) is also contiguous, this configuration is invalid, as
        something must be surrounded.

        Args:
            symbol_predicate: The predicate class representing the symbol to constrain
            segment: Segment to publish these rules to
            fixed_fields: Fixed field values for the predicate (for multi-field predicates)
            loc_field: The predicate's cell field, for predicates that name it
                something other than "loc"
        """
        if fixed_fields is None:
            fixed_fields = {}

        segment.section(f"Forbid disconnecting checkerboard pattern for {symbol_predicate.get_name()}")

        R, C = V.R, V.C
        top_left_cell = self.Cell(row=R, col=C)
        top_right_cell = self.Cell(row=R, col=C + 1)
        bottom_left_cell = self.Cell(row=R + 1, col=C)
        bottom_right_cell = self.Cell(row=R + 1, col=C + 1)

        top_left = symbol_predicate(**{loc_field: top_left_cell}, **fixed_fields)
        top_right = symbol_predicate(**{loc_field: top_right_cell}, **fixed_fields)
        bottom_right = symbol_predicate(**{loc_field: bottom_right_cell}, **fixed_fields)
        bottom_left = symbol_predicate(**{loc_field: bottom_left_cell}, **fixed_fields)

        # Forbid checkerboard on one diagonal
        segment.forbid(
            top_left,
            bottom_right,
            ~top_right,
            ~bottom_left,
            top_left_cell,
            bottom_right_cell,
        )

        # Forbid checkerboard on the other diagonal
        segment.forbid(
            top_right,
            bottom_left,
            ~top_left,
            ~bottom_right,
            top_left_cell,
            bottom_right_cell,
        )
