import dataclasses
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any

from aspalchemy import Expression, Field, Predicate, RangePool, Segment, V
from aspuzzle.grids.base import Grid, GridCell, GridCellData
from aspuzzle.grids.rendering import RenderItem, RenderSymbol, colorize
from aspuzzle.puzzle import Puzzle, cached_predicate

if TYPE_CHECKING:
    from aspalchemy import PredicateArg


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
    ):
        """Initialize a grid module with specified dimensions."""
        super().__init__(puzzle, name, primary_namespace)

        assert isinstance(rows, int)
        assert isinstance(cols, int)

        self.rows = rows
        self.cols = cols

    def with_new_puzzle(self, puzzle: Puzzle) -> RectangularGrid:
        """Return a copy of this Grid with a new puzzle."""
        return type(self)(
            puzzle=puzzle, rows=self.rows, cols=self.cols, name=self._name, primary_namespace=self._namespace == ""
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

    @property
    def line_characters(self) -> dict[str, str]:
        """Get ASCII line characters for direction combinations in rectangular grids."""
        return {
            "ew": "─",  # horizontal line
            "ns": "│",  # vertical line
            "es": "┌",  # top-left corner
            "sw": "┐",  # top-right corner
            "en": "└",  # bottom-left corner
            "nw": "┘",  # bottom-right corner
            "we": "─",  # horizontal line (reverse)
            "sn": "│",  # vertical line (reverse)
            "se": "┌",  # top-left corner (reverse)
            "ws": "┐",  # top-right corner (reverse)
            "ne": "└",  # bottom-left corner (reverse)
            "wn": "┘",  # bottom-right corner (reverse)
            # Three-line T-junctions (alphabetically sorted)
            "ens": "├",  # T pointing right
            "enw": "┴",  # T pointing up
            "esw": "┬",  # T pointing down
            "nsw": "┤",  # T pointing left
            # Four-line cross
            "ensw": "┼",  # cross/plus
        }

    def get_line_count(self, direction: str) -> int:
        """Returns the number of lines in the specified direction for a rectangular grid"""
        if direction == "e":  # rows
            return self.rows
        if direction == "s":  # columns
            return self.cols
        raise ValueError(f"Unknown direction: {direction}")

    @property
    @cached_predicate
    def Cell(self) -> type[RectangularCell]:
        """Get the Cell predicate for this grid."""
        Cell = RectangularCell.in_namespace(self.namespace)

        R, C = V.R, V.C

        # Define grid cells
        self.section("Define cells in the grid")
        self.when(R.in_(RangePool(1, self.rows)), C.in_(RangePool(1, self.cols))).derive(Cell(R, C))

        return Cell

    def cell(self, suffix: str = "") -> RectangularCell:
        """Get a cell predicate for this grid with variable values."""
        cell = super().cell(suffix)
        assert isinstance(cell, RectangularCell)
        return cell

    @property
    @cached_predicate
    def OutsideGrid(self) -> type[OutsideGrid]:
        """Get the OutsideGrid predicate identifying cells in the outside border."""
        Outside = OutsideGrid.in_namespace(self.namespace)

        R, C = V.R, V.C
        cell = self.Cell(R, C)

        self.section("Define outside border cells")

        # Top and bottom rows
        self.when(R.in_([0, self.rows + 1]), C.in_(RangePool(0, self.cols + 1))).derive(Outside(loc=cell))
        # Left and right columns (but not double counting the corners)
        self.when(C.in_([0, self.cols + 1]), R.in_(RangePool(1, self.rows))).derive(Outside(loc=cell))
        # Create cell locations in the outside border
        self.when(Outside(loc=cell)).derive(cell)

        # We've included the outside border
        self._has_outside_border = True

        return Outside

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
        row_step, col_step = dict(self.direction_vectors)[direction]
        row, col = cell.row + row_step, cell.col + col_step
        if 1 <= row <= self.rows and 1 <= col <= self.cols:
            return self.Cell(row=row, col=col)
        return None

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
                yield self.Cell(row=row, col=col)

    def forbid_2x2_blocks(
        self,
        symbol_predicate: type[Predicate],
        segment: Segment,
        fixed_fields: dict[str, PredicateArg] | None = None,
    ) -> None:
        """
        Forbid 2x2 blocks of a specific symbol/predicate in a rectangular grid.

        Args:
            symbol_predicate: The predicate class representing the symbol to constrain
            segment: Segment to publish these rules to
            fixed_fields: Fixed field values for the predicate (for multi-field predicates)

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
            symbol_predicate(loc=top_left_cell, **fixed_fields),
            symbol_predicate(loc=top_right_cell, **fixed_fields),
            symbol_predicate(loc=bottom_left_cell, **fixed_fields),
            symbol_predicate(loc=bottom_right_cell, **fixed_fields),
            top_left_cell,
            bottom_right_cell,
        )

    def forbid_checkerboard(
        self,
        symbol_predicate: type[Predicate],
        segment: Segment,
        fixed_fields: dict[str, PredicateArg] | None = None,
    ) -> None:
        """
        Forbids a 2x2 block checkerboard pattern of a given predicate in a rectangular grid.
        If the symbol is contiguous and not(symbol) is also contiguous, this configuration is invalid, as
        something must be surrounded.

        Args:
            symbol_predicate: The predicate class representing the symbol to constrain
            segment: Segment to publish these rules to
            fixed_fields: Fixed field values for the predicate (for multi-field predicates)
        """
        if fixed_fields is None:
            fixed_fields = {}

        segment.section(f"Forbid disconnecting checkerboard pattern for {symbol_predicate.get_name()}")

        R, C = V.R, V.C
        top_left_cell = self.Cell(row=R, col=C)
        top_right_cell = self.Cell(row=R, col=C + 1)
        bottom_left_cell = self.Cell(row=R + 1, col=C)
        bottom_right_cell = self.Cell(row=R + 1, col=C + 1)

        top_left = symbol_predicate(loc=top_left_cell, **fixed_fields)
        top_right = symbol_predicate(loc=top_right_cell, **fixed_fields)
        bottom_right = symbol_predicate(loc=bottom_right_cell, **fixed_fields)
        bottom_left = symbol_predicate(loc=bottom_left_cell, **fixed_fields)

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

    def render_ascii(
        self,
        puzzle_render_items: list[RenderItem],
        predicate_render_items: dict[int, list[RenderItem]],
        render_config: dict[str, Any],
        use_colors: bool = True,
    ) -> str:
        """
        Render the rectangular grid as ASCII text.

        This method takes preprocessed rendering items and converts them into an ASCII
        representation of the grid. Rendering is applied in order of priority, with higher
        priority items rendered later (on top).

        Args:
            puzzle_render_items: List of RenderItem objects for the puzzle symbols
            predicate_render_items: Dictionary mapping priority levels to lists of RenderItem objects
            render_config: Additional rendering configuration including:
                - 'join_char': Character to use in joining cells (default: " ")
                - 'draw_box': Whether to draw a box around the grid (default: False)
                - 'rows_per_box': Draw horizontal lines every N rows (default: None)
                - 'cols_per_box': Draw vertical lines every N columns (default: None)
            use_colors: Whether to use ANSI colors in the output

        Returns:
            ASCII string representation of the grid
        """
        # Build the grid of render symbols
        grid = self._build_render_grid(puzzle_render_items, predicate_render_items, render_config)

        # Check if we need complex box drawing
        if render_config.get("draw_box", False):
            return self._render_grid_with_boxes(grid, render_config, use_colors)
        return self._render_grid_simple(grid, render_config, use_colors)

    def _build_render_grid(
        self,
        puzzle_render_items: list[RenderItem],
        predicate_render_items: dict[int, list[RenderItem]],
        render_config: dict[str, Any],
    ) -> list[list[RenderSymbol]]:
        """Build the 2D grid of RenderSymbol objects from render items."""
        # Construct the dot representation
        dot = render_config.get("puzzle_symbols", {}).get(".", RenderSymbol("."))

        # Initialize grid with dots
        grid: list[list[RenderSymbol]] = [
            [dataclasses.replace(dot) for _ in range(self.cols)] for _ in range(self.rows)
        ]

        # Combine all render items in priority order
        all_render_items = list(puzzle_render_items)
        for priority in sorted(predicate_render_items.keys()):
            all_render_items.extend(predicate_render_items[priority])

        # Process all render items
        for item in all_render_items:
            # Extract row/col from the location predicate, adjusting for 1-based indexing
            loc = item.loc
            assert isinstance(loc, RectangularCell)
            grid_row = loc.row - 1
            grid_col = loc.col - 1

            # Skip if outside grid bounds
            if grid_row < 0 or grid_row >= self.rows or grid_col < 0 or grid_col >= self.cols:
                continue

            # Update what we're rendering
            render_symbol: RenderSymbol = grid[grid_row][grid_col]
            if item.symbol:
                render_symbol.symbol = item.symbol
            if item.color:
                render_symbol.color = item.color
            if item.background:
                render_symbol.bgcolor = item.background

        return grid

    @staticmethod
    def _render_grid_simple(grid: list[list[RenderSymbol]], render_config: dict[str, Any], use_colors: bool) -> str:
        """Render grid without box drawing - just cells with separators."""
        join_char = render_config.get("join_char", " ")

        result_lines = []
        for row_symbols in grid:
            row_parts = []
            for symbol in row_symbols:
                cell_str = colorize(symbol.symbol, symbol.color, symbol.bgcolor) if use_colors else symbol.symbol
                row_parts.append(cell_str)

            result_lines.append(join_char.join(row_parts))

        return "\n".join(result_lines)

    def _get_column_separator(
        self, col_index: int, cols_per_box: int | None, subdivision_char: str, normal_char: str
    ) -> str:
        """Get the appropriate separator character for a column position."""
        if col_index >= self.cols - 1:
            return ""
        if cols_per_box is not None and (col_index + 1) % cols_per_box == 0:
            return subdivision_char
        if normal_char:  # Only add if we have a non-empty separator
            return normal_char
        return ""

    def _render_grid_with_boxes(
        self, grid: list[list[RenderSymbol]], render_config: dict[str, Any], use_colors: bool
    ) -> str:
        """
        Convert a grid of RenderSymbol objects to ASCII text with complex box drawing.

        Args:
            grid: 2D grid of RenderSymbol objects to render
            render_config: Rendering configuration including box drawing options
            use_colors: Whether to apply ANSI color codes

        Returns:
            ASCII string representation of the grid with boxes
        """
        join_char = render_config.get("join_char", " ")
        cols_per_box = render_config.get("cols_per_box")
        rows_per_box = render_config.get("rows_per_box")
        line_chars = self.line_characters

        # Validate box drawing requirements
        if len(join_char) > 1:
            raise ValueError(
                f"Box drawing requires join_char to be at most 1 character, got {len(join_char)}: {join_char!r}"
            )

        # Precompute the three horizontal line types
        top_line = self._build_horizontal_line(cols_per_box, join_char, "top")
        separator_line = self._build_horizontal_line(cols_per_box, join_char, "separator")
        bottom_line = self._build_horizontal_line(cols_per_box, join_char, "bottom")

        # Start with top border
        result_lines = [top_line]

        # Process each grid row
        for r, row_in_grid in enumerate(grid):
            # Build row content
            row_str = []
            for c, render_symbol in enumerate(row_in_grid):
                if use_colors:
                    cell_str = colorize(render_symbol.symbol, render_symbol.color, render_symbol.bgcolor)
                else:
                    cell_str = render_symbol.symbol

                row_str.append(cell_str)
                row_str.append(self._get_column_separator(c, cols_per_box, line_chars["ns"], join_char))

            # Add side borders and add to result
            result_lines.append(line_chars["ns"] + "".join(row_str) + line_chars["ns"])

            # Add horizontal separator if needed
            if rows_per_box is not None and (r + 1) % rows_per_box == 0 and r < len(grid) - 1:
                result_lines.append(separator_line)

        # Add bottom border
        result_lines.append(bottom_line)

        return "\n".join(result_lines)

    def _build_horizontal_line(self, cols_per_box: int | None, join_char: str, line_type: str = "separator") -> str:
        """Build horizontal line (border or separator) with proper intersections."""
        line_chars = self.line_characters

        # Choose junction characters based on line type
        line_type_chars = {
            "top": (line_chars["es"], line_chars["sw"], line_chars["esw"]),
            "bottom": (line_chars["en"], line_chars["nw"], line_chars["enw"]),
            "separator": (line_chars["ens"], line_chars["nsw"], line_chars["ensw"]),
        }
        left_char, right_char, intersection_char = line_type_chars[line_type]

        # Build the contents
        content_parts: list[str] = []
        for c in range(self.cols):
            content_parts.append(line_chars["ew"])
            content_parts.append(self._get_column_separator(c, cols_per_box, intersection_char, line_chars["ew"]))

        # Assemble the full line
        return left_char + "".join(content_parts) + right_char
