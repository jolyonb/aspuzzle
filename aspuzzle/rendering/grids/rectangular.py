"""
The rectangular lattice model, stated once for every backend: how cells,
edges, and vertices of a RectangularGrid map onto the integer lattice of
row/column boundaries. Backend leaves (RectangularAsciiGeometry,
RectangularSvgGeometry) convert lattice coordinates into their own space
— character lanes or unit points — without restating these facts.
"""

from typing import TYPE_CHECKING

from aspuzzle.rendering.grids.geometry import GeometryBase

if TYPE_CHECKING:
    from aspuzzle.grids.rectangulargrid import RectangularGrid
    from aspuzzle.rendering.scene import Edge, Vertex


class RectangularGeometryBase(GeometryBase["RectangularGrid"]):
    """Lattice facts shared by the ASCII and SVG rectangular geometries.

    Horizontal lattice items are indexed by row boundary 0..rows (boundary
    b sits between cell rows b and b+1), vertical ones by column boundary;
    `along` counts cells along the lane, 1-based like the grid."""

    grid: RectangularGrid

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

    def on_lattice(self, edge: Edge) -> bool:
        return self._on_lattice(*self._edge_lattice(edge))

    def vertex_on_lattice(self, vertex: Vertex) -> bool:
        row_boundary, col_boundary = self._vertex_lattice(vertex)
        return 0 <= row_boundary <= self.grid.rows and 0 <= col_boundary <= self.grid.cols

    def _on_lattice(self, orientation: str, boundary: int, along: int) -> bool:
        """Whether an edge's lattice indices fall on the grid (edges of
        out-of-grid cells are skipped silently, like other elements)."""
        if orientation == "h":
            return 0 <= boundary <= self.grid.rows and 1 <= along <= self.grid.cols
        return 0 <= boundary <= self.grid.cols and 1 <= along <= self.grid.rows
