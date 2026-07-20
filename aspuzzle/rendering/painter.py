"""
The scene-walking core every renderer shares: one backend-filtered pass
over the elements with paint-or-skip arbitration and per-kind dispatch,
so backends implement paint operations, not scene traversal. Cell content
filters on cell membership; edges and vertices are lattice items whose
canonical spelling may legitimately carry an outside cell (a frame
vertex), so the geometry's lattice predicates arbitrate those.

Backend-agnostic by construction (imports nothing from ascii/, svg/, or
sheet/ — the import-boundary tests enforce it); each backend package
subclasses ScenePainter with its own emission and state.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol

from aspuzzle.rendering.scene import (
    CellFill,
    CellGlyph,
    CellLink,
    CellMark,
    CellPath,
    Edge,
    EdgeMark,
    EdgeSegment,
    OutsideLabel,
    SceneElement,
    Vertex,
    VertexMark,
)

if TYPE_CHECKING:
    from aspuzzle.grids.base import GridCell
    from aspuzzle.rendering.gridview import RenderGrid


class CommonGeometry(Protocol):
    """The geometry surface both backends share (implemented once in
    GeometryBase): substrate enumeration and the line vocabulary."""

    def all_edges(self) -> list[Edge]: ...

    def boundary_edges(self) -> list[Edge]: ...

    def interior_edges(self) -> list[Edge]: ...

    def all_vertices(self) -> list[Vertex]: ...

    def line_index_valid(self, direction: str, index: int) -> bool: ...

    def on_lattice(self, edge: Edge) -> bool:
        """Whether the edge lies on this grid's lattice — the paint-or-skip
        arbiter for edge elements (canonical spellings may carry outside
        cells, so cell membership is not the question)."""
        ...

    def vertex_on_lattice(self, vertex: Vertex) -> bool:
        """Whether the vertex lies on this grid's lattice — the
        paint-or-skip arbiter for vertex marks."""
        ...


class ScenePainter(ABC):
    """
    Per-render painting state plus the one element walk: paint_element
    arbitrates paint-or-skip (solution dicts genuinely carry out-of-grid
    references, e.g. Slitherlink's outside atoms) — cell content on cell
    membership, edges and vertices through the geometry's lattice
    predicates — and dispatches each element kind to its abstract
    operation. Subclasses own emission — markup, canvas characters — and
    any accumulation their medium needs.
    """

    def __init__(self, grid: RenderGrid, geometry: CommonGeometry) -> None:
        self.grid = grid
        self.geometry = geometry

    def in_grid(self, cell: GridCell) -> bool:
        return self.grid.cell_at(self.grid.cell_coords(cell)) is not None

    def paint_element(self, element: SceneElement) -> None:
        match element:
            case CellFill(cell=cell) | CellGlyph(cell=cell) | CellPath(cell=cell) | CellMark(cell=cell):
                # Cell-membership is the right question for cell content
                if not self.in_grid(cell):
                    return
            case EdgeSegment(edge=edge) | EdgeMark(edge=edge):
                # Edges and vertices are lattice items whose canonical
                # spelling may legitimately carry an outside cell (a frame
                # vertex), so the geometry's lattice predicate arbitrates
                if not self.geometry.on_lattice(edge):
                    return
            case VertexMark(vertex=vertex):
                if not self.geometry.vertex_on_lattice(vertex):
                    return
            case CellLink() | OutsideLabel():
                pass  # links filter per cell below; labels bound via line_index_valid
        match element:
            case CellFill():
                self.paint_fill(element)
            case CellGlyph():
                self.paint_glyph(element)
            case CellPath(directions=directions):
                self.paint_path(element, sorted(directions))
            case CellLink(cell1=cell1, cell2=cell2):
                # Per-cell like every backend: glyphs for whichever cells
                # are in-grid; the connector (where the medium has one)
                # only when both are
                self.paint_link(element, [cell for cell in (cell1, cell2) if self.in_grid(cell)])
            case EdgeSegment():
                self.paint_edge(element)
            case CellMark():
                self.paint_cell_mark(element)
            case EdgeMark():
                self.paint_edge_mark(element)
            case VertexMark():
                self.paint_vertex_mark(element)
            case OutsideLabel():
                self.paint_label(element)

    @abstractmethod
    def paint_fill(self, element: CellFill) -> None: ...

    @abstractmethod
    def paint_glyph(self, element: CellGlyph) -> None: ...

    @abstractmethod
    def paint_path(self, element: CellPath, directions: list[str]) -> None: ...

    @abstractmethod
    def paint_link(self, element: CellLink, cells: list[GridCell]) -> None: ...

    @abstractmethod
    def paint_edge(self, element: EdgeSegment) -> None: ...

    @abstractmethod
    def paint_cell_mark(self, element: CellMark) -> None: ...

    @abstractmethod
    def paint_edge_mark(self, element: EdgeMark) -> None: ...

    @abstractmethod
    def paint_vertex_mark(self, element: VertexMark) -> None: ...

    @abstractmethod
    def paint_label(self, element: OutsideLabel) -> None: ...
