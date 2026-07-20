"""
The AsciiGeometry protocol: layout and character knowledge only — the
positions and glyph vocabulary the grid-agnostic AsciiPainter paints
through. The shared core arbitrates paint-or-skip (cell membership for
cell content, the lattice predicates for edges and vertices), so these
methods are total over arbitrated inputs; None marks the genuinely
character-grid channels — a collapsed lane with no midpoint character, a
label index beyond the grid.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Protocol

from aspuzzle.rendering.ascii.canvas import CharCanvas, CharPos, TextSpan
from aspuzzle.rendering.painter import CommonGeometry

if TYPE_CHECKING:
    from aspuzzle.grids.base import GridCell
    from aspuzzle.rendering.color import ColorSpec
    from aspuzzle.rendering.scene import Edge, Vertex

__all__ = ["VERTEX_DOT", "AsciiGeometry", "JunctionState"]

VERTEX_DOT: Final[str] = "."


@dataclass
class JunctionState:
    """Accumulated stroke knowledge for junction resolution: per canvas
    position, the directions strokes point in, heavy membership, and the
    last color to arrive. The painter accumulates via stamp(); the
    geometry's finish() turns flags into box-drawing characters."""

    flags: dict[CharPos, set[str]] = field(default_factory=dict)
    heavy: set[CharPos] = field(default_factory=set)
    color: dict[CharPos, ColorSpec] = field(default_factory=dict)

    def stamp(self, pos: CharPos, directions: Iterable[str], heavy: bool, color: ColorSpec | None) -> None:
        self.flags.setdefault(pos, set()).update(directions)
        if heavy:
            self.heavy.add(pos)
        if color is not None:
            self.color[pos] = color


class AsciiGeometry(CommonGeometry, Protocol):
    """Constructed per render by Grid.ascii_geometry(needs, style);
    stateless across renders — per-render accumulation lives in the
    painter's JunctionState and fill registry."""

    def size(self) -> tuple[int, int]:
        """Canvas dimensions (rows, cols) for this layout."""
        ...

    def cell_span(self, cell: GridCell) -> TextSpan:
        """The cell's content position."""
        ...

    def edge_stamps(self, edge: Edge) -> Sequence[tuple[CharPos, frozenset[str]]]:
        """The junction stamps a stroked edge contributes: its run and the
        flags it points into flanking vertices. Empty when the edge's lane
        is collapsed or the edge lies off the lattice."""
        ...

    def edge_mark_pos(self, edge: Edge) -> CharPos | None:
        """The edge's midpoint character, or None when its lane is
        collapsed (no such character exists)."""
        ...

    def vertex_pos(self, vertex: Vertex) -> CharPos | None:
        """The vertex's character, or None when either lane is collapsed."""
        ...

    def label_span(self, direction: str, index: int, offset: int, width: int) -> TextSpan | None:
        """Where an outside label of `width` characters goes, or None when
        `index` addresses no line of this grid."""
        ...

    def path_glyph(self, directions: frozenset[str]) -> str:
        """The through-path character for a direction set."""
        ...

    def substrate_dots(self) -> Iterable[CharPos]:
        """Every materialized lane intersection, for style.vertex_dots."""
        ...

    def finish(
        self, canvas: CharCanvas, junctions: JunctionState, cell_fills: Mapping[tuple[int, ...], ColorSpec]
    ) -> None:
        """The layout-aware finishing passes: bridge stroke runs, extend
        equal fills across gaps, and resolve junction flags to characters."""
        ...
