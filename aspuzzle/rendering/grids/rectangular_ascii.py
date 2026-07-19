"""
The rectangular grid's ASCII geometry: all of its character-level layout
knowledge, behind the AsciiGeometry protocol. Implements the compact
layout — cell (r, c) maps to one character at (r-1, (c-1)*(1+gap)), cells
separated by cell_gap spaces. Element kinds needing edge lanes (edge
segments, vertex marks, frames, outside labels) are not supported by this
layout.
"""

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Final

from aspuzzle.rendering.ascii.canvas import CharCanvas, CharPos, TextSpan
from aspuzzle.rendering.backend import Backend
from aspuzzle.rendering.scene import (
    CellFill,
    CellGlyph,
    CellLink,
    CellPath,
    EdgeWeight,
    LayoutNeeds,
    SceneElement,
    SceneStyle,
)

if TYPE_CHECKING:
    from aspuzzle.grids.base import GridCell
    from aspuzzle.grids.rectangulargrid import RectangularGrid
    from aspuzzle.rendering.scene import Edge, Vertex

__all__ = ["BOX_CHARS", "RectangularAsciiGeometry"]

# The box-drawing vocabulary, keyed by direction SETS: no duplicated "ew"/"we" spellings
BOX_CHARS: Final[Mapping[frozenset[str], str]] = {
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


class RectangularAsciiGeometry:
    """Compact-layout geometry for RectangularGrid (satisfies AsciiGeometry)."""

    def __init__(self, grid: RectangularGrid, needs: LayoutNeeds, style: SceneStyle) -> None:
        if needs.edges or needs.vertices or style.frame or needs.label_margins:
            raise NotImplementedError("The compact ASCII layout cannot host edges, vertices, frames, or outside labels")
        self.grid = grid
        self.gap = style.cell_gap
        self.style = style

    # -- layout arithmetic --

    def size(self) -> tuple[int, int]:
        return self.grid.rows, (self.grid.cols - 1) * (1 + self.gap) + 1

    def _cell_pos(self, cell: GridCell) -> CharPos | None:
        """Canvas position of a cell's character, or None if off-canvas
        (out-of-grid elements are skipped silently)."""
        row, col = self.grid.cell_coords(cell)
        if not (1 <= row <= self.grid.rows and 1 <= col <= self.grid.cols):
            return None
        return CharPos(row - 1, (col - 1) * (1 + self.gap))

    def content_span(self, cell: GridCell) -> TextSpan:
        pos = self._cell_pos(cell)
        if pos is None:
            raise ValueError(f"{cell} is outside the grid")
        return TextSpan(pos.row, pos.col, 1)

    def interior_spans(self, cell: GridCell) -> Sequence[TextSpan]:
        return (self.content_span(cell),)

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
            case _:
                raise NotImplementedError(
                    f"{type(element).__name__} needs the expanded ASCII layout; "
                    f"the compact layout paints cell elements only"
                )

    def resolve_junctions(self, canvas: CharCanvas) -> None:
        pass  # nothing accumulates flags in the compact layout

    # -- building blocks --

    def path_glyph(self, cell: GridCell, directions: frozenset[str]) -> str:
        glyph = BOX_CHARS.get(directions)
        if glyph is None:
            raise ValueError(f"No path glyph for direction set {sorted(directions)} on a rectangular grid")
        return glyph

    def edge_chars(self, edge: Edge, weight: EdgeWeight) -> Sequence[tuple[CharPos, str]]:
        raise NotImplementedError("Edge lanes arrive with the expanded layout")

    def vertex_pos(self, vertex: Vertex) -> CharPos:
        raise NotImplementedError("Vertex positions arrive with the expanded layout")

    def label_span(self, direction: str, index: int, offset: int, width: int) -> TextSpan:
        raise NotImplementedError("Label margins arrive with the expanded layout")
