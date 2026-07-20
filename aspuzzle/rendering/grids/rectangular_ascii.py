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
all painting, the finish pass reads each position's accumulated
direction set and picks the character: {e,w} → ─, {e,s} → ┌,
{e,n,s,w} → ┼. Frames, region borders, and loops therefore junction
correctly no matter which of them supplied which line.
"""

import itertools
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Final

from aspuzzle.rendering.ascii.canvas import CharCanvas, CharPos, TextSpan
from aspuzzle.rendering.ascii.geometry import JunctionState
from aspuzzle.rendering.color import ColorSpec
from aspuzzle.rendering.grids.rectangular import RectangularGeometryBase
from aspuzzle.rendering.scene import (
    Edge,
    Lattice,
    LayoutNeeds,
    SceneStyle,
    Vertex,
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


class RectangularAsciiGeometry(RectangularGeometryBase):
    """Layout engine for RectangularGrid (satisfies AsciiGeometry): the
    lane-collapsing layout plus character vocabulary, over the lattice
    model inherited from RectangularGeometryBase."""

    def __init__(self, grid: RectangularGrid, needs: LayoutNeeds, style: SceneStyle) -> None:
        super().__init__(grid)
        gap = 0 if style.packed else 1

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

        # Top/bottom labels occupy horizontal space: multi-char labels widen
        # the column pitch so neighbors cannot collide, and the canvas
        # extends so the last column's label fits
        label_pitch = max(needs.label_margins.get("s", 1), needs.label_margins.get("n", 1))
        column_gap = gap if label_pitch <= 1 else max(gap, label_pitch)

        # -- char coordinates: cells and materialized lanes interleave;
        #    unmaterialized column boundaries collapse to gap spaces,
        #    unmaterialized row boundaries to nothing --
        # An internal lane normally replaces the boundary's gap; when labels
        # widened the pitch, padding around the lane keeps the pitch at
        # 1 + column_gap everywhere so neighboring labels cannot collide
        lane_pad = max(0, column_gap - 1)
        self._col_x: dict[int, int] = {}
        self._lane_x: dict[int, int] = {}
        x = self._margin_left
        for boundary in range(grid.cols + 1):
            if boundary in v_lanes:
                if 0 < boundary < grid.cols:
                    x += lane_pad // 2
                self._lane_x[boundary] = x
                x += 1
                if 0 < boundary < grid.cols:
                    x += lane_pad - lane_pad // 2
            elif 0 < boundary < grid.cols:
                x += column_gap
            if boundary < grid.cols:
                self._col_x[boundary + 1] = x
                x += 1
        if self._margin_top or self._margin_bottom:
            x = max(x, self._col_x[grid.cols] + label_pitch)
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

    # -- layout --

    def size(self) -> tuple[int, int]:
        return self._height, self._width

    def cell_span(self, cell: GridCell) -> TextSpan:
        """The cell's content position (total over in-grid cells)."""
        row, col = self.grid.cell_coords(cell)
        return TextSpan(self._row_y[row], self._col_x[col], 1)

    def path_glyph(self, directions: frozenset[str]) -> str:
        glyph = BOX_CHARS.get(directions)
        if glyph is None:
            raise ValueError(f"No path glyph for direction set {sorted(directions)} on a rectangular grid")
        return glyph

    def label_span(self, direction: str, index: int, offset: int, width: int) -> TextSpan | None:
        if not self.line_index_valid(direction, index):
            return None  # labels beyond the grid skip silently, like every element
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
                # Unreachable behind line_index_valid's direction check;
                # kept as fallthrough insurance (and for match totality)
                raise ValueError(f"{direction!r} is not a rectangular label direction")

    # -- protocol surface: positions, stamps, vocabulary --

    def edge_stamps(self, edge: Edge) -> list[tuple[CharPos, frozenset[str]]]:
        orientation, boundary, along = self._edge_lattice(edge)
        if not self._on_lattice(orientation, boundary, along):
            return []
        stamps: list[tuple[CharPos, frozenset[str]]] = []
        if orientation == "h":
            if boundary not in self._lane_y:
                return []
            y = self._lane_y[boundary]
            # The run stamps its own cell's char; a materialized vertex
            # bounding it records the direction pointing back at the run.
            # Gap chars between two stroked runs are bridged in finish, so
            # an isolated edge never claims a neighboring column.
            if along - 1 in self._lane_x:
                stamps.append((CharPos(y, self._lane_x[along - 1]), frozenset({"e"})))
            if along in self._lane_x:
                stamps.append((CharPos(y, self._lane_x[along]), frozenset({"w"})))
            stamps.append((CharPos(y, self._col_x[along]), frozenset({"e", "w"})))
        else:
            if boundary not in self._lane_x:
                return []
            x = self._lane_x[boundary]
            if along - 1 in self._lane_y:
                stamps.append((CharPos(self._lane_y[along - 1], x), frozenset({"s"})))
            if along in self._lane_y:
                stamps.append((CharPos(self._lane_y[along], x), frozenset({"n"})))
            stamps.append((CharPos(self._row_y[along], x), frozenset({"n", "s"})))
        return stamps

    def edge_mark_pos(self, edge: Edge) -> CharPos | None:
        orientation, boundary, along = self._edge_lattice(edge)
        if not self._on_lattice(orientation, boundary, along):
            return None
        if orientation == "h":
            if boundary not in self._lane_y:
                return None
            return CharPos(self._lane_y[boundary], self._col_x[along])
        if boundary not in self._lane_x:
            return None
        return CharPos(self._row_y[along], self._lane_x[boundary])

    def vertex_pos(self, vertex: Vertex) -> CharPos | None:
        row_boundary, col_boundary = self._vertex_lattice(vertex)
        if row_boundary not in self._lane_y or col_boundary not in self._lane_x:
            return None
        return CharPos(self._lane_y[row_boundary], self._lane_x[col_boundary])

    def substrate_dots(self) -> Iterable[CharPos]:
        for y in self._lane_y.values():
            for x in self._lane_x.values():
                yield CharPos(y, x)

    # -- finishing: the layout-aware passes --

    def finish(
        self, canvas: CharCanvas, junctions: JunctionState, cell_fills: Mapping[tuple[int, ...], ColorSpec]
    ) -> None:
        self._bridge_horizontal_runs(junctions)
        self._resolve_fills(canvas, cell_fills)
        for pos, directions in junctions.flags.items():
            table = BOX_CHARS_HEAVY if pos in junctions.heavy else BOX_CHARS
            canvas.put(pos, char=table[frozenset(directions)], fg=junctions.color.get(pos))

    def _bridge_horizontal_runs(self, junctions: JunctionState) -> None:
        """The chars between two neighboring anchors in a lane (cell chars
        and materialized vertices) are drawn only when both anchors carry a
        stroke pointing into the gap, so an isolated edge never claims a
        neighboring column."""
        anchors = sorted(set(self._col_x.values()) | set(self._lane_x.values()))
        for y in self._lane_y.values():
            for left_x, right_x in itertools.pairwise(anchors):
                if right_x - left_x < 2:
                    continue
                left = CharPos(y, left_x)
                right = CharPos(y, right_x)
                if "e" in junctions.flags.get(left, ()) and "w" in junctions.flags.get(right, ()):
                    heavy = left in junctions.heavy or right in junctions.heavy
                    color = junctions.color.get(left, junctions.color.get(right))
                    for x in range(left_x + 1, right_x):
                        junctions.stamp(CharPos(y, x), {"e", "w"}, heavy, color)

    def _resolve_fills(self, canvas: CharCanvas, fills: Mapping[tuple[int, ...], ColorSpec]) -> None:
        """Backgrounds extend across the characters between equal-fill
        neighbors (and the junction area where all four surrounding cells
        match), so filled regions read as solid blocks even when lanes or
        gaps separate their cells."""
        for (row, col), color in fills.items():
            right_match = fills.get((row, col + 1)) == color
            down_match = fills.get((row + 1, col)) == color
            if right_match:
                y = self._row_y[row]
                for x in range(self._col_x[col] + 1, self._col_x[col + 1]):
                    canvas.put(CharPos(y, x), bg=color)
            if down_match:
                x0 = self._col_x[col]
                for y in range(self._row_y[row] + 1, self._row_y[row + 1]):
                    canvas.put(CharPos(y, x0), bg=color)
            if right_match and down_match and fills.get((row + 1, col + 1)) == color:
                for y in range(self._row_y[row] + 1, self._row_y[row + 1]):
                    for x in range(self._col_x[col] + 1, self._col_x[col + 1]):
                        canvas.put(CharPos(y, x), bg=color)
