"""
The AsciiGeometry protocol: the contract every per-grid ASCII geometry
(aspuzzle/rendering/grids/*) implements, and the only interface the
grid-agnostic AsciiRenderer paints through.
"""

from collections.abc import Sequence
from typing import TYPE_CHECKING, Protocol

from aspuzzle.rendering.ascii.canvas import CharCanvas, CharPos, TextSpan

# The layout summary is pure data and lives with the scene (which computes
# it per backend); this is its ASCII-facing name.
from aspuzzle.rendering.scene import LayoutNeeds as AsciiLayoutNeeds

if TYPE_CHECKING:
    from aspuzzle.grids.base import GridCell
    from aspuzzle.rendering.scene import SceneElement, Vertex

__all__ = ["AsciiGeometry", "AsciiLayoutNeeds"]


class AsciiGeometry(Protocol):
    """
    All grid-specific character knowledge, behind one protocol. Constructed
    per render by Grid.ascii_geometry(needs, style); stateless afterward.
    Answers exactly one question per element kind: which canvas characters
    realize this element?
    """

    def size(self) -> tuple[int, int]:
        """Canvas dimensions (rows, cols) for this layout."""
        ...

    def paint_base(self, canvas: CharCanvas) -> None:
        """Paint the substrate: empty-cell styling, frame, lattice."""
        ...

    def paint(self, canvas: CharCanvas, element: SceneElement) -> None:
        """Paint one element (single dispatch on element kind)."""
        ...

    def resolve_junctions(self, canvas: CharCanvas) -> None:
        """Convert accumulated edge flags into box-drawing characters."""
        ...

    # -- building blocks shared by paint(); useful to geometry subclasses --

    def content_span(self, cell: GridCell) -> TextSpan:
        """Where a cell's glyph goes (carries the content width)."""
        ...

    def interior_spans(self, cell: GridCell) -> Sequence[TextSpan]:
        """A cell's full interior footprint (plural for hex/tri layouts)."""
        ...

    def vertex_pos(self, vertex: Vertex) -> CharPos:
        """The canvas position of a vertex."""
        ...

    def path_glyph(self, cell: GridCell, directions: frozenset[str]) -> str:
        """The single character for a path through a cell via `directions`."""
        ...

    def label_span(self, direction: str, index: int, offset: int, width: int) -> TextSpan:
        """Where an outside label goes, in the margin reserved for its ring."""
        ...
