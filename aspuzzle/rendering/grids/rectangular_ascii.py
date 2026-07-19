"""
The rectangular grid's ASCII geometry: all of its character-level layout
knowledge, behind the AsciiGeometry protocol.

One layout engine serves every look. Cell content occupies one character;
edge LANES — character rows/columns interleaved between the cells at grid
boundaries — materialize only where something uses them (a stroked edge, a
vertex, the lattice, a dot), and collapse to plain gap spacing (or zero
height) elsewhere. The all-collapsed case is the compact layout: cells
separated by one space, or touching when the style is packed.

Edge characters are chosen in two passes, because no single edge knows
what character a position needs: where a horizontal border crosses a
vertical one the right character is ┼, and neither edge can know the
other exists. So painting an edge only records, at each position it
covers, the compass directions a line leaves that position in (a
horizontal run leaves east and west; where the run ends at a vertex, the
vertex records just the one direction pointing back at the run). After
all painting, resolve_junctions() reads each position's accumulated
direction set and picks the character: {e,w} → ─, {e,s} → ┌,
{e,n,s,w} → ┼. Frames, region borders, and loops therefore junction
correctly no matter which of them supplied which line.
"""

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Final

from aspuzzle.rendering.ascii.canvas import CharCanvas, CharPos, TextSpan
from aspuzzle.rendering.backend import Backend
from aspuzzle.rendering.color import ColorSpec
from aspuzzle.rendering.scene import (
    CellFill,
    CellGlyph,
    CellLink,
    CellPath,
    Edge,
    EdgeSegment,
    EdgeWeight,
    Lattice,
    LayoutNeeds,
    OutsideLabel,
    SceneElement,
    SceneStyle,
    Vertex,
    VertexMark,
)

if TYPE_CHECKING:
    from aspuzzle.grids.base import GridCell
    from aspuzzle.grids.rectangulargrid import RectangularGrid

__all__ = ["BOX_CHARS", "BOX_CHARS_HEAVY", "RectangularAsciiGeometry"]

# The box-drawing vocabulary, keyed by direction sets.
BOX_CHARS: Final[Mapping[frozenset[str], str]] = {
    frozenset({"e"}): "╶",
    frozenset({"w"}): "╴",
    frozenset({"n"}): "╵",
    frozenset({"s"}): "╷",
    frozenset({"e", "w"}): "─",
    frozenset({"n", "s"}): "│",
    frozenset({"e", "s"}): "┌",
    frozenset({"s", "w"}): "┐",
    frozenset({"e", "n"}): "└",
    frozenset({"n", "w"}): "┘",
    frozenset({"e", "n", "s"}): "├",
    frozenset({"e", "n", "w"}): "┴",
    frozenset({"e", "s", "w"}): "┬",
    frozenset({"n", "s", "w"}): "┤",
    frozenset({"e", "n", "s", "w"}): "┼",
}

# Double-line variants for EdgeWeight.HEAVY. Doubles have no half-line
# forms, so a stub end renders as the full-width line.
BOX_CHARS_HEAVY: Final[Mapping[frozenset[str], str]] = {
    frozenset({"e"}): "═",
    frozenset({"w"}): "═",
    frozenset({"n"}): "║",
    frozenset({"s"}): "║",
    frozenset({"e", "w"}): "═",
    frozenset({"n", "s"}): "║",
    frozenset({"e", "s"}): "╔",
    frozenset({"s", "w"}): "╗",
    frozenset({"e", "n"}): "╚",
    frozenset({"n", "w"}): "╝",
    frozenset({"e", "n", "s"}): "╠",
    frozenset({"e", "n", "w"}): "╩",
    frozenset({"e", "s", "w"}): "╦",
    frozenset({"n", "s", "w"}): "╣",
    frozenset({"e", "n", "s", "w"}): "╬",
}

VERTEX_DOT: Final[str] = "."


class RectangularAsciiGeometry:
    """Layout engine for RectangularGrid (satisfies AsciiGeometry)."""

    def __init__(self, grid: RectangularGrid, needs: LayoutNeeds, style: SceneStyle) -> None:
        self.grid = grid
        self.style = style
        self.gap = 0 if style.packed else 1

        # -- which lanes materialize --
        # Horizontal lanes are indexed by row boundary 0..rows (lane rb sits
        # between cell rows rb and rb+1); vertical lanes by column boundary.
        h_lanes: set[int] = set()
        v_lanes: set[int] = set()
        for edge in needs.edges:
            orientation, boundary, along = self._edge_lattice(edge)
            if self._on_lattice(orientation, boundary, along):
                (h_lanes if orientation == "h" else v_lanes).add(boundary)
        for vertex in needs.vertices:
            row_boundary, col_boundary = self._vertex_lattice(vertex)
            if 0 <= row_boundary <= grid.rows and 0 <= col_boundary <= grid.cols:
                h_lanes.add(row_boundary)
                v_lanes.add(col_boundary)
        if style.lattice is not Lattice.NONE:
            h_lanes.update({0, grid.rows})
            v_lanes.update({0, grid.cols})
        if style.lattice is Lattice.FULL or style.vertex_dots:
            h_lanes.update(range(grid.rows + 1))
            v_lanes.update(range(grid.cols + 1))

        # -- margins for outside labels (one ring per side) --
        self._margin_left = needs.label_margins["e"] + 1 if "e" in needs.label_margins else 0
        self._margin_right = needs.label_margins["w"] + 1 if "w" in needs.label_margins else 0
        self._margin_top = 1 if "s" in needs.label_margins else 0
        self._margin_bottom = 1 if "n" in needs.label_margins else 0

        # -- char coordinates: cells and materialized lanes interleave;
        #    unmaterialized column boundaries collapse to gap spaces,
        #    unmaterialized row boundaries to nothing --
        self._col_x: dict[int, int] = {}
        self._lane_x: dict[int, int] = {}
        x = self._margin_left
        for boundary in range(grid.cols + 1):
            if boundary in v_lanes:
                self._lane_x[boundary] = x
                x += 1
            elif 0 < boundary < grid.cols:
                x += self.gap
            if boundary < grid.cols:
                self._col_x[boundary + 1] = x
                x += 1
        self._width = x + self._margin_right

        self._row_y: dict[int, int] = {}
        self._lane_y: dict[int, int] = {}
        y = self._margin_top
        for boundary in range(grid.rows + 1):
            if boundary in h_lanes:
                self._lane_y[boundary] = y
                y += 1
            if boundary < grid.rows:
                self._row_y[boundary + 1] = y
                y += 1
        self._height = y + self._margin_bottom

        # -- junction state: direction flags accumulate per position --
        self._flags: dict[CharPos, set[str]] = {}
        self._flag_heavy: set[CharPos] = set()
        self._flag_color: dict[CharPos, ColorSpec] = {}

    # -- lattice arithmetic helpers --

    def _edge_lattice(self, edge: Edge) -> tuple[str, int, int]:
        """(orientation, boundary index, cell index along the lane) of an edge."""
        row, col = self.grid.cell_coords(edge.cell)
        match edge.direction:
            case "n":
                return "h", row - 1, col
            case "s":
                return "h", row, col
            case "w":
                return "v", col - 1, row
            case "e":
                return "v", col, row
            case _:
                raise ValueError(f"{edge.direction!r} is not a rectangular edge direction")

    def _vertex_lattice(self, vertex: Vertex) -> tuple[int, int]:
        """(row boundary, column boundary) of a vertex."""
        row, col = self.grid.cell_coords(vertex.cell)
        vertical, horizontal = vertex.corner[0], vertex.corner[1]
        return (row - 1 if vertical == "n" else row, col - 1 if horizontal == "w" else col)

    def _on_lattice(self, orientation: str, boundary: int, along: int) -> bool:
        """Whether an edge's lattice indices fall on the grid (edges of
        out-of-grid cells are skipped silently, like other elements)."""
        if orientation == "h":
            return 0 <= boundary <= self.grid.rows and 1 <= along <= self.grid.cols
        return 0 <= boundary <= self.grid.cols and 1 <= along <= self.grid.rows

    # -- layout --

    def size(self) -> tuple[int, int]:
        return self._height, self._width

    def _cell_pos(self, cell: GridCell) -> CharPos | None:
        """Canvas position of a cell's character, or None if off-canvas
        (out-of-grid elements are skipped silently)."""
        row, col = self.grid.cell_coords(cell)
        if not (1 <= row <= self.grid.rows and 1 <= col <= self.grid.cols):
            return None
        return CharPos(self._row_y[row], self._col_x[col])

    def content_span(self, cell: GridCell) -> TextSpan:
        pos = self._cell_pos(cell)
        if pos is None:
            raise ValueError(f"{cell} is outside the grid")
        return TextSpan(pos.row, pos.col, 1)

    def interior_spans(self, cell: GridCell) -> Sequence[TextSpan]:
        return (self.content_span(cell),)

    def vertex_pos(self, vertex: Vertex) -> CharPos:
        row_boundary, col_boundary = self._vertex_lattice(vertex)
        if row_boundary not in self._lane_y or col_boundary not in self._lane_x:
            raise ValueError(f"{vertex} lies in a collapsed lane")
        return CharPos(self._lane_y[row_boundary], self._lane_x[col_boundary])

    def path_glyph(self, cell: GridCell, directions: frozenset[str]) -> str:
        glyph = BOX_CHARS.get(directions) if len(directions) >= 2 else None
        if glyph is None:
            raise ValueError(f"No path glyph for direction set {sorted(directions)} on a rectangular grid")
        return glyph

    def label_span(self, direction: str, index: int, offset: int, width: int) -> TextSpan:
        if offset != 0:
            raise NotImplementedError("Stacked label rings (offset > 0) are not supported")
        match direction:
            case "s":  # looking south: above the grid, over column `index`
                return TextSpan(self._margin_top - 1, self._col_x[index], width)
            case "n":  # looking north: below the grid
                return TextSpan(self._height - self._margin_bottom, self._col_x[index], width)
            case "e":  # looking east: left of the grid, one space before it
                return TextSpan(self._row_y[index], self._margin_left - 1 - width, width)
            case "w":  # looking west: right of the grid, one space after it
                return TextSpan(self._row_y[index], self._width - self._margin_right + 1, width)
            case _:
                raise ValueError(f"{direction!r} is not a rectangular label direction")

    # -- flag stamping --

    def _stamp(self, pos: CharPos, directions: set[str], weight: EdgeWeight, color: ColorSpec | None) -> None:
        self._flags.setdefault(pos, set()).update(directions)
        if weight is EdgeWeight.HEAVY:
            self._flag_heavy.add(pos)
        if color is not None:
            self._flag_color[pos] = color

    def _stamp_edge(self, edge: Edge, weight: EdgeWeight, color: ColorSpec | None) -> None:
        orientation, boundary, along = self._edge_lattice(edge)
        if not self._on_lattice(orientation, boundary, along):
            return
        if orientation == "h":
            y = self._lane_y[boundary]
            # The run covers the cell's char plus the gap back to the
            # previous cell; where a vertex bounds the run, the vertex
            # records only the direction pointing back at the run
            if along - 1 in self._lane_x:
                self._stamp(CharPos(y, self._lane_x[along - 1]), {"e"}, weight, color)
                start = self._lane_x[along - 1] + 1
            elif along > 1:
                start = self._col_x[along - 1] + 1
            else:
                start = self._col_x[along]
            if along in self._lane_x:
                self._stamp(CharPos(y, self._lane_x[along]), {"w"}, weight, color)
                end = self._lane_x[along] - 1
            else:
                end = self._col_x[along]
            for x in range(start, end + 1):
                self._stamp(CharPos(y, x), {"e", "w"}, weight, color)
        else:
            x = self._lane_x[boundary]
            if along - 1 in self._lane_y:
                self._stamp(CharPos(self._lane_y[along - 1], x), {"s"}, weight, color)
            if along in self._lane_y:
                self._stamp(CharPos(self._lane_y[along], x), {"n"}, weight, color)
            self._stamp(CharPos(self._row_y[along], x), {"n", "s"}, weight, color)

    def _lattice_edges(self) -> list[tuple[Edge, EdgeWeight]]:
        """The substrate's stroked edges, per the style's lattice setting."""
        grid, style = self.grid, self.style
        edges: list[tuple[Edge, EdgeWeight]] = []
        if style.lattice is Lattice.NONE:
            return edges
        for col in range(1, grid.cols + 1):
            edges.append((Edge(grid.Cell(row=1, col=col), "n"), style.frame_weight))
            edges.append((Edge(grid.Cell(row=grid.rows, col=col), "s"), style.frame_weight))
        for row in range(1, grid.rows + 1):
            edges.append((Edge(grid.Cell(row=row, col=1), "w"), style.frame_weight))
            edges.append((Edge(grid.Cell(row=row, col=grid.cols), "e"), style.frame_weight))
        if style.lattice is Lattice.FULL:
            for row in range(1, grid.rows + 1):
                for col in range(1, grid.cols + 1):
                    if row > 1:
                        edges.append((Edge(grid.Cell(row=row, col=col), "n"), EdgeWeight.NORMAL))
                    if col > 1:
                        edges.append((Edge(grid.Cell(row=row, col=col), "w"), EdgeWeight.NORMAL))
        return edges

    # -- painting --

    def paint_base(self, canvas: CharCanvas) -> None:
        empty = self.style.empty
        text = empty.glyph.for_backend(Backend.ASCII) if empty.glyph is not None else None
        for cell in self.grid.all_cells():
            span = self.content_span(cell)
            if text is not None:
                canvas.put_text(span, text, fg=empty.color)
            if empty.fill is not None:
                canvas.paint_bg(span, empty.fill)
        if self.style.vertex_dots:
            for y in self._lane_y.values():
                for x in self._lane_x.values():
                    canvas.put(CharPos(y, x), char=VERTEX_DOT)
        for edge, weight in self._lattice_edges():
            self._stamp_edge(edge, weight, None)

    def paint(self, canvas: CharCanvas, element: SceneElement) -> None:
        match element:
            case CellFill(cell=cell, color=color):
                if (pos := self._cell_pos(cell)) is not None:
                    canvas.paint_bg(TextSpan(pos.row, pos.col, 1), color)
            case CellGlyph(cell=cell, glyph=glyph, color=color):
                if (pos := self._cell_pos(cell)) is not None:
                    canvas.put_text(TextSpan(pos.row, pos.col, 1), glyph.for_backend(Backend.ASCII), fg=color)
            case CellPath(cell=cell, directions=directions, color=color):
                if (pos := self._cell_pos(cell)) is not None:
                    canvas.put(pos, char=self.path_glyph(cell, directions), fg=color)
            case CellLink(cell1=cell1, cell2=cell2, glyph=glyph, color=color):
                text = glyph.for_backend(Backend.ASCII) if glyph is not None else None
                for cell in (cell1, cell2):
                    if (pos := self._cell_pos(cell)) is not None:
                        canvas.put(pos, char=text, fg=color)
            case EdgeSegment(edge=edge, color=color, weight=weight):
                self._stamp_edge(edge, weight, color)
            case VertexMark(vertex=vertex, glyph=glyph, color=color):
                text = glyph.for_backend(Backend.ASCII) if glyph is not None else VERTEX_DOT
                canvas.put(self.vertex_pos(vertex), char=text, fg=color)
            case OutsideLabel(direction=direction, index=index, glyph=glyph, color=color, offset=offset):
                text = glyph.for_backend(Backend.ASCII)
                canvas.put_text(self.label_span(direction, index, offset, len(text)), text, fg=color)

    def resolve_junctions(self, canvas: CharCanvas) -> None:
        for pos, directions in self._flags.items():
            table = BOX_CHARS_HEAVY if pos in self._flag_heavy else BOX_CHARS
            canvas.put(pos, char=table[frozenset(directions)], fg=self._flag_color.get(pos))
