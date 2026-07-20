"""
The typed boundary between rendering and the ASP world.

Grid classes carry both faces — ASP emission and rendering vocabulary —
because the grid is the single geometry authority with two consumers.
RenderGrid is the rendering-side facet: a structural Protocol listing
exactly the surface rendering code may touch. Scene, renderers, and
geometries type against it, so the type checkers prove that nothing
rendering-side can reach the statement verbs or cached predicates. Grid
satisfies it structurally (no inheritance, no registration), and the
protocol doubles as the checklist a new grid author implements.
"""

from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from aspuzzle.grids.base import GridCell
    from aspuzzle.rendering.ascii.geometry import AsciiGeometry
    from aspuzzle.rendering.scene import Edge, LayoutNeeds, SceneStyle, Vertex
    from aspuzzle.rendering.sheet.geometry import SheetGeometry
    from aspuzzle.rendering.svg.geometry import SvgGeometry


class RenderGrid(Protocol):
    # -- cells --
    @property
    def Cell(self) -> type[GridCell]:
        """The grid's cell class, for constructing grounded cells from
        parsed coordinates (grid.Cell(*coords))."""
        ...

    # -- direction and line vocabulary --
    @property
    def orthogonal_direction_names(self) -> list[str]: ...

    @property
    def line_direction_names(self) -> list[str]: ...

    def get_line_count(self, direction: str) -> int: ...

    def opposite_direction(self, direction: str) -> str: ...

    # -- topology --
    def neighbor(self, cell: GridCell, direction: str) -> GridCell | None: ...

    def all_cells(self) -> Iterator[GridCell]: ...

    def cell_coords(self, cell: GridCell) -> tuple[int, ...]: ...

    def cell_at(self, coords: tuple[int, ...]) -> GridCell | None:
        """The in-grid cell at concrete coordinates, or None when no such
        cell exists — the test grid-agnostic renderers use to skip elements
        referencing out-of-grid cells."""
        ...

    # -- edges and vertices (canonical constructors) --
    @property
    def corner_names(self) -> Sequence[str]: ...

    def corner_across(self, corner: str, direction: str) -> str | None: ...

    def edge(self, cell: GridCell, direction: str) -> Edge: ...

    def vertex(self, cell: GridCell, corner: str) -> Vertex: ...

    # -- geometry factories --
    def ascii_geometry(self, needs: LayoutNeeds, style: SceneStyle) -> AsciiGeometry: ...

    def svg_geometry(self) -> SvgGeometry: ...

    def sheet_geometry(self, needs: LayoutNeeds) -> SheetGeometry: ...
