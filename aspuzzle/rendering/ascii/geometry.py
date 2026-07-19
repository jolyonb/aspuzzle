"""
The AsciiGeometry protocol: the contract every per-grid ASCII geometry
(aspuzzle/rendering/grids/*) implements, and the only interface the
grid-agnostic AsciiRenderer paints through. Deliberately minimal — the
four methods the renderer calls; layout arithmetic is each geometry's
private business.
"""

from typing import TYPE_CHECKING, Protocol

from aspuzzle.rendering.ascii.canvas import CharCanvas

if TYPE_CHECKING:
    from aspuzzle.rendering.scene import SceneElement

__all__ = ["AsciiGeometry"]


class AsciiGeometry(Protocol):
    """Constructed per render by Grid.ascii_geometry(needs, style);
    stateless across renders."""

    def size(self) -> tuple[int, int]:
        """Canvas dimensions (rows, cols) for this layout."""
        ...

    def paint_base(self, canvas: CharCanvas) -> None:
        """Paint the substrate: empty-cell styling, lattice, dots."""
        ...

    def paint(self, canvas: CharCanvas, element: SceneElement) -> None:
        """Paint one element (single dispatch on element kind)."""
        ...

    def resolve_junctions(self, canvas: CharCanvas) -> None:
        """Finish multi-element character decisions (junctions, bridges, fills)."""
        ...
