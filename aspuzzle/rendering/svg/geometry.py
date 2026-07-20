"""
The SVG geometry contract: how a grid maps cells, edges, and vertices
onto the 2D plane for the SVG renderer.

Geometries speak unit-cell coordinates (one cell spans one unit); the
renderer scales every point by its cell_size and folds the viewBox from
the points it actually draws, so geometries carry no bounds logic. All
methods are total over in-grid inputs — the renderer pre-filters elements
referencing out-of-grid cells before asking.

Shared points must come from shared arithmetic: the renderer chains edge
segments by exact coordinate match (rounded to 1e-4), so two edges
meeting at a point must compute that point identically — trivially true
for rectangular half-unit coordinates, a real obligation for geometries
with irrational coordinates (hex). A miss is cosmetic (a chain splits
into two butt-capped runs), not corrupt.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from aspuzzle.grids.base import GridCell
    from aspuzzle.rendering.scene import Edge, Vertex


@dataclass(frozen=True)
class Point:
    x: float
    y: float


# SVG text-anchor values: which side of the anchor point label text grows
# from. Which anchoring a label needs is grid knowledge, so the geometry
# says — rectangular grids center every label in a virtual cell outside
# the boundary; a slanted hex ring may need start/end.
type TextAnchor = Literal["start", "middle", "end"]


class SvgGeometry(Protocol):
    def cell_polygon(self, cell: GridCell) -> Sequence[Point]: ...

    def cell_center(self, cell: GridCell) -> Point: ...

    def edge_endpoints(self, edge: Edge) -> tuple[Point, Point]: ...

    def vertex_point(self, vertex: Vertex) -> Point: ...

    def outside_anchor(self, direction: str, index: int, offset: int) -> tuple[Point, TextAnchor]: ...
