"""
The SVG geometry contract: how a grid maps cells, edges, and vertices
onto the 2D plane for the SVG renderer.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from aspuzzle.grids.base import GridCell
    from aspuzzle.rendering.scene import Edge, Scene, Vertex


@dataclass(frozen=True)
class Point:
    x: float
    y: float


class SvgGeometry(Protocol):
    def bounds(self, scene: Scene) -> tuple[Point, Point]:
        """Drawing bounds (min, max) computed over scene.visible(Backend.SVG)
        — ASCII-only elements never inflate the viewBox."""
        ...

    def cell_polygon(self, cell: GridCell) -> Sequence[Point]: ...

    def cell_center(self, cell: GridCell) -> Point: ...

    def edge_endpoints(self, edge: Edge) -> tuple[Point, Point]: ...

    def vertex_point(self, vertex: Vertex) -> Point: ...

    def outside_anchor(self, direction: str, index: int, offset: int) -> Point: ...
