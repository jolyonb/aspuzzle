"""
SVG geometry for RectangularGrid: unit squares in the renderer's
unit-cell coordinate space. The grid is 1-based, so cell (row, col) spans
x in [col-1, col] and y in [row-1, row]. Methods are total over
arbitrated inputs; the shared core filters cell content on membership and
edges/vertices through the inherited lattice predicates.
"""

from typing import TYPE_CHECKING

from aspuzzle.rendering.grids.rectangular import RectangularGeometryBase
from aspuzzle.rendering.svg.geometry import Point, TextAnchor

if TYPE_CHECKING:
    from collections.abc import Sequence

    from aspuzzle.grids.base import GridCell
    from aspuzzle.rendering.scene import Edge, Vertex


class RectangularSvgGeometry(RectangularGeometryBase):
    """Point mapping for RectangularGrid (satisfies SvgGeometry): lattice
    coordinates from RectangularGeometryBase, converted to unit points —
    a horizontal boundary b is the line y=b, cell `along` spans
    [along-1, along]."""

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
        orientation, boundary, along = self._edge_lattice(edge)
        if orientation == "h":
            return Point(along - 1, boundary), Point(along, boundary)
        return Point(boundary, along - 1), Point(boundary, along)

    def vertex_point(self, vertex: Vertex) -> Point:
        row_boundary, col_boundary = self._vertex_lattice(vertex)
        return Point(col_boundary, row_boundary)

    def outside_anchor(self, direction: str, index: int, offset: int) -> tuple[Point, TextAnchor] | None:
        # A label lives in the virtual cell one step outside the boundary
        # (ring `offset` steps further out), centered like any cell glyph
        if not self.line_index_valid(direction, index):
            return None  # labels beyond the grid skip silently, like every element
        match direction:
            case "e":
                return Point(-0.5 - offset, index - 0.5), "middle"
            case "w":
                return Point(self.grid.cols + 0.5 + offset, index - 0.5), "middle"
            case "s":
                return Point(index - 0.5, -0.5 - offset), "middle"
            case "n":
                return Point(index - 0.5, self.grid.rows + 0.5 + offset), "middle"
        # Unreachable behind line_index_valid's direction check; kept as
        # fallthrough insurance (and for match totality)
        raise ValueError(f"{direction!r} is not a rectangular label direction")
