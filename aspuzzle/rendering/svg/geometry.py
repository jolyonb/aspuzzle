"""
The SVG geometry contract: how a grid maps cells, edges, and vertices
onto the 2D plane for the SVG renderer.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from aspuzzle.grids.base import GridCell
    from aspuzzle.rendering.scene import Edge, Scene, Vertex


@dataclass(frozen=True)
class Point:
    x: float
    y: float


# SVG text-anchor values: which side of the anchor point label text grows
# from. Which anchoring a label needs is grid knowledge (a left-ring label
# ends at its point, a top-ring label centers on it), so the geometry says.
type TextAnchor = Literal["start", "middle", "end"]


class SvgGeometry(Protocol):
    def bounds(self, scene: Scene) -> tuple[Point, Point]:
        """Drawing bounds (min, max) computed over scene.visible(Backend.SVG)
        — ASCII-only elements never inflate the viewBox."""
        ...

    def cell_polygon(self, cell: GridCell) -> Sequence[Point]: ...

    def cell_center(self, cell: GridCell) -> Point: ...

    def edge_endpoints(self, edge: Edge) -> tuple[Point, Point]: ...

    def vertex_point(self, vertex: Vertex) -> Point: ...

    def outside_anchor(self, direction: str, index: int, offset: int) -> tuple[Point, TextAnchor]: ...
