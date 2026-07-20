"""
The grid-agnostic ASCII renderer: walks the scene through the shared
ScenePainter core and paints onto a CharCanvas through whatever slim
AsciiGeometry the scene's grid supplies — positions and character
vocabulary come from the geometry, element semantics and junction/fill
accumulation live here. Contains zero grid-specific knowledge.
"""

from typing import TYPE_CHECKING, Final, assert_never

from aspuzzle.rendering.ascii.canvas import CharCanvas, CharPos
from aspuzzle.rendering.ascii.geometry import VERTEX_DOT, AsciiGeometry, JunctionState
from aspuzzle.rendering.ascii.theme import DEFAULT_THEME, AsciiTheme
from aspuzzle.rendering.backend import Backend
from aspuzzle.rendering.glyph import Glyph
from aspuzzle.rendering.painter import ScenePainter
from aspuzzle.rendering.scene import (
    CellFill,
    CellGlyph,
    CellLink,
    CellMark,
    CellPath,
    Edge,
    EdgeMark,
    EdgeSegment,
    EdgeWeight,
    Lattice,
    MarkElement,
    OutsideLabel,
    Scene,
    SceneStyle,
    VertexMark,
)

if TYPE_CHECKING:
    from aspuzzle.grids.base import GridCell
    from aspuzzle.rendering.color import ColorSpec
    from aspuzzle.rendering.gridview import RenderGrid


def mark_char(kind: str, glyph: Glyph | None) -> str:
    """The one-character form of a mark glyph (the default dot when None):
    a character grid has exactly one character per mark position."""
    if glyph is None:
        return VERTEX_DOT
    text = glyph.for_backend(Backend.ASCII)
    if len(text) != 1:
        raise ValueError(
            f"{kind} glyph {text!r} does not fit a one-character mark position; "
            "keep the baseline text one character and put the full form in a "
            "richer variant, e.g. Glyph('x', svg='10')"
        )
    return text


class AsciiRenderer:
    """
    Asks the scene's grid for a geometry, paints the substrate, then every
    ASCII-visible element in painter's order, lets the geometry finish
    (bridging, fill continuity, junction characters), and serializes
    through the theme.
    """

    backend: Final = Backend.ASCII

    def __init__(self, use_colors: bool = True, theme: AsciiTheme = DEFAULT_THEME) -> None:
        self.use_colors = use_colors
        self.theme = theme

    def render(self, scene: Scene) -> str:
        style = scene.style_for(self.backend)
        geometry = scene.grid.ascii_geometry(scene.layout_needs(self.backend), style)
        canvas = CharCanvas(*geometry.size())
        painter = AsciiPainter(scene.grid, geometry, canvas)
        painter.paint_substrate(style)
        for element in scene.sorted_elements(self.backend):
            painter.paint_element(element)
        geometry.finish(canvas, painter.junctions, painter.cell_fills)
        return canvas.to_string(self.theme, self.use_colors)


class AsciiPainter(ScenePainter):
    """One render's worth of state: the canvas, junction-flag accumulation,
    and the fill registry for continuity — plus the paint operations
    turning elements into geometry queries and canvas characters."""

    geometry: AsciiGeometry

    def __init__(self, grid: RenderGrid, geometry: AsciiGeometry, canvas: CharCanvas) -> None:
        super().__init__(grid, geometry)
        self.canvas = canvas
        self.junctions = JunctionState()
        self.cell_fills: dict[tuple[int, ...], ColorSpec] = {}

    # -- substrate --

    def paint_substrate(self, style: SceneStyle) -> None:
        empty = style.empty
        if Backend.ASCII in empty.backends:
            text = empty.glyph.for_backend(Backend.ASCII) if empty.glyph is not None else None
            for cell in self.grid.all_cells():
                span = self.geometry.cell_span(cell)
                if text is not None:
                    self.canvas.put_text(span, text, fg=empty.color)
                if empty.fill is not None:
                    self.canvas.paint_bg(span, empty.fill)
                    self.cell_fills[self.grid.cell_coords(cell)] = empty.fill
        if style.vertex_dots:
            for pos in self.geometry.substrate_dots():
                self.canvas.put(pos, char=VERTEX_DOT)
        if style.lattice is not Lattice.NONE:
            for edge in self.geometry.boundary_edges():
                self._stamp_edge(edge, style.frame_weight, None)
            if style.lattice is Lattice.FULL:
                for edge in self.geometry.interior_edges():
                    self._stamp_edge(edge, EdgeWeight.NORMAL, None)

    def _stamp_edge(self, edge: Edge, weight: EdgeWeight, color: ColorSpec | None) -> None:
        heavy = weight is EdgeWeight.HEAVY
        for pos, flags in self.geometry.edge_stamps(edge):
            self.junctions.stamp(pos, flags, heavy, color)

    def _cell_pos(self, cell: GridCell) -> CharPos:
        span = self.geometry.cell_span(cell)
        return CharPos(span.row, span.col)

    # -- paint operations (dispatch and filtering live in ScenePainter) --

    def paint_fill(self, element: CellFill) -> None:
        self.canvas.paint_bg(self.geometry.cell_span(element.cell), element.color)
        self.cell_fills[self.grid.cell_coords(element.cell)] = element.color

    def paint_glyph(self, element: CellGlyph) -> None:
        text = element.glyph.for_backend(Backend.ASCII)
        self.canvas.put_text(self.geometry.cell_span(element.cell), text, fg=element.color)

    def paint_path(self, element: CellPath, directions: list[str]) -> None:
        char = self.geometry.path_glyph(frozenset(directions))
        self.canvas.put(self._cell_pos(element.cell), char=char, fg=element.color)

    def paint_link(self, element: CellLink, cells: list[GridCell]) -> None:
        text = element.glyph.for_backend(Backend.ASCII) if element.glyph is not None else None
        for cell in cells:
            if text is not None:
                self.canvas.put_text(self.geometry.cell_span(cell), text, fg=element.color)
            else:
                self.canvas.put(self._cell_pos(cell), fg=element.color)

    def paint_edge(self, element: EdgeSegment) -> None:
        self._stamp_edge(element.edge, element.weight, element.color)

    def _mark_pos(self, element: MarkElement) -> CharPos | None:
        """Where a mark lands. None means the layout collapsed the lane the
        mark needed — it never means an unhandled element kind."""
        match element:
            case CellMark(cell=cell):
                return self._cell_pos(cell)
            case EdgeMark(edge=edge):
                return self.geometry.edge_mark_pos(edge)
            case VertexMark(vertex=vertex):
                return self.geometry.vertex_pos(vertex)
            case _:
                assert_never(element)

    def paint_mark(self, element: MarkElement) -> None:
        if (pos := self._mark_pos(element)) is not None:
            char = mark_char(type(element).__name__, element.glyph)
            self.canvas.put(pos, char=char, fg=element.color)

    def paint_label(self, element: OutsideLabel) -> None:
        text = element.glyph.for_backend(Backend.ASCII)
        span = self.geometry.label_span(element.direction, element.index, element.offset, len(text))
        if span is not None:
            self.canvas.put_text(span, text, fg=element.color)
