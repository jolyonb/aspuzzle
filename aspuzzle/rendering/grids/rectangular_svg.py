"""
SVG geometry for RectangularGrid: unit squares in the renderer's
unit-cell coordinate space. The grid is 1-based, so cell (row, col) spans
x in [col-1, col] and y in [row-1, row]. Methods are total over in-grid
inputs; the renderer pre-filters out-of-grid references.
"""

from typing import TYPE_CHECKING, Final

from aspuzzle.rendering.svg.geometry import Point, TextAnchor

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from aspuzzle.grids.base import GridCell
    from aspuzzle.grids.rectangulargrid import RectangularGrid
    from aspuzzle.rendering.scene import Edge, Vertex

# Corner name -> offset from the cell's top-left corner, in unit cells
_CORNER_OFFSETS: Final[Mapping[str, tuple[float, float]]] = {
    "nw": (0.0, 0.0),
    "ne": (1.0, 0.0),
    "se": (1.0, 1.0),
    "sw": (0.0, 1.0),
}


class RectangularSvgGeometry:
    """Point mapping for RectangularGrid (satisfies SvgGeometry)."""

    def __init__(self, grid: RectangularGrid) -> None:
        self.grid = grid

    def _origin(self, cell: GridCell) -> tuple[float, float]:
        """A cell's top-left corner."""
        row, col = self.grid.cell_coords(cell)
        return float(col - 1), float(row - 1)

    def cell_polygon(self, cell: GridCell) -> Sequence[Point]:
        x, y = self._origin(cell)
        return (Point(x, y), Point(x + 1, y), Point(x + 1, y + 1), Point(x, y + 1))

    def cell_center(self, cell: GridCell) -> Point:
        x, y = self._origin(cell)
        return Point(x + 0.5, y + 0.5)

    def edge_endpoints(self, edge: Edge) -> tuple[Point, Point]:
        x, y = self._origin(edge.cell)
        match edge.direction:
            case "n":
                return Point(x, y), Point(x + 1, y)
            case "s":
                return Point(x, y + 1), Point(x + 1, y + 1)
            case "w":
                return Point(x, y), Point(x, y + 1)
            case "e":
                return Point(x + 1, y), Point(x + 1, y + 1)
        raise ValueError(f"{edge.direction!r} is not a rectangular edge direction")

    def vertex_point(self, vertex: Vertex) -> Point:
        x, y = self._origin(vertex.cell)
        dx, dy = _CORNER_OFFSETS[vertex.corner]
        return Point(x + dx, y + dy)

    def outside_anchor(self, direction: str, index: int, offset: int) -> tuple[Point, TextAnchor]:
        # A label lives in the virtual cell one step outside the boundary
        # (ring `offset` steps further out), centered like any cell glyph
        match direction:
            case "e":
                return Point(-0.5 - offset, index - 0.5), "middle"
            case "w":
                return Point(self.grid.cols + 0.5 + offset, index - 0.5), "middle"
            case "s":
                return Point(index - 0.5, -0.5 - offset), "middle"
            case "n":
                return Point(index - 0.5, self.grid.rows + 0.5 + offset), "middle"
        raise ValueError(f"{direction!r} is not a rectangular label direction")
