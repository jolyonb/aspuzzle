"""
The geometry class hierarchy's root: every behavior a rendering geometry
can state in pure grid topology, regardless of grid shape or backend —
substrate enumeration over canonical edges and vertices, and the line
vocabulary behind outside-label limits. Grid-shape bases
(RectangularGeometryBase) add their lattice model; backend leaves add
their coordinate space.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aspuzzle.rendering.gridview import RenderGrid
    from aspuzzle.rendering.scene import Edge, Vertex


class GeometryBase[GridT: "RenderGrid"]:
    """A rendering geometry over a grid."""

    def __init__(self, grid: GridT) -> None:
        self.grid = grid

    def all_edges(self) -> list[Edge]:
        """Every canonical edge of the grid, deterministically ordered —
        the full-lattice substrate enumeration."""
        return self._edges(want_neighbor=None)

    def boundary_edges(self) -> list[Edge]:
        """The canonical edges on the outer boundary (no neighbor across),
        deterministically ordered — the frame enumeration."""
        return self._edges(want_neighbor=False)

    def interior_edges(self) -> list[Edge]:
        """The canonical edges between two in-grid cells, deterministically
        ordered."""
        return self._edges(want_neighbor=True)

    def _edges(self, want_neighbor: bool | None) -> list[Edge]:
        """Canonical edges filtered by whether a cell sits across them
        (None keeps all)."""
        grid = self.grid
        edges: set[Edge] = set()
        for cell in grid.all_cells():
            for direction in grid.orthogonal_direction_names:
                has_neighbor = grid.neighbor(cell, direction) is not None
                if want_neighbor is None or has_neighbor == want_neighbor:
                    edges.add(grid.edge(cell, direction))
        return sorted(edges, key=lambda edge: (grid.cell_coords(edge.cell), edge.direction))

    def all_vertices(self) -> list[Vertex]:
        """Every canonical vertex of the grid, deterministically ordered."""
        grid = self.grid
        vertices: set[Vertex] = set()
        for cell in grid.all_cells():
            for corner in grid.corner_names:
                vertices.add(grid.vertex(cell, corner))
        return sorted(vertices, key=lambda vertex: (grid.cell_coords(vertex.cell), vertex.corner))

    def line_limit(self, direction: str) -> int:
        """How many lines an outside label can index in looking-direction
        `direction` — the grid's line vocabulary, entered from either end
        of a line (a label looking "n" indexes the same lines as "s").
        Raises for directions that address no line of this grid."""
        grid = self.grid
        if direction in grid.line_direction_names:
            return grid.get_line_count(direction)
        if direction in grid.orthogonal_direction_names:
            opposite = grid.opposite_direction(direction)
            if opposite in grid.line_direction_names:
                return grid.get_line_count(opposite)
        raise ValueError(f"{direction!r} is not a label direction of this grid")

    def line_index_valid(self, direction: str, index: int) -> bool:
        """Whether an outside label's index addresses a line of this grid."""
        return 1 <= index <= self.line_limit(direction)
