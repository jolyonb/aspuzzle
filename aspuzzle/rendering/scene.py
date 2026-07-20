"""
The scene model: the backend-agnostic intermediate representation between
solvers and renderers. Typed elements (fills, glyphs, paths, links, edge
segments, vertex marks, outside labels) at abstract grid locations, with
per-backend visibility and GIVEN/DERIVED provenance. One Scene holds
everything; renderers consume it through the two filtered views
(sorted_elements / layout_needs), the single choke point where backend
visibility applies.
"""

from collections.abc import Iterator, Mapping
from dataclasses import KW_ONLY, dataclass, field
from enum import Enum, IntEnum, auto
from typing import TYPE_CHECKING

from aspuzzle.rendering.backend import ALL_BACKENDS, Backend, BackendSet
from aspuzzle.rendering.color import ColorSpec
from aspuzzle.rendering.glyph import Glyph

if TYPE_CHECKING:
    # Type-only: grids import scene types at runtime (Edge/Vertex
    # construction), so the runtime dependency must point one way only
    from aspuzzle.grids.base import GridCell
    from aspuzzle.rendering.gridview import RenderGrid


class Provenance(Enum):
    """
    Where an element's information came from. Backends may style the two
    classes differently (e.g. SVG: uncolored givens default to black,
    solution values to blue); the default ASCII theme ignores it.
    Provenance is meaning, not paint order — it never affects layering.
    """

    GIVEN = auto()  # puzzle input: grid clues, config label arrays, input regions
    DERIVED = auto()  # solution atoms


class Layer(IntEnum):
    """
    Named paint order replacing raw priority ints. Elements carry
    kind-appropriate defaults; any int works for fine-grained tweaks.
    Within a layer, insertion order breaks ties (stable sort).
    """

    BASE = 0  # frame / lattice (painted by each backend's painter from SceneStyle)
    FILL = 10  # cell backgrounds
    GRID_MARK = 20  # structural borders (Sudoku boxes, region cages)
    PATH = 30  # in-cell paths, links, edge strokes, vertex marks
    GLYPH = 40  # clue and solution glyphs
    ANNOTATION = 50  # anything that must win


class EdgeWeight(Enum):
    NORMAL = auto()  # light box chars / normal SVG stroke
    HEAVY = auto()  # double-line box chars / thicker SVG stroke


class Lattice(Enum):
    """How much of the grid's own skeleton the substrate draws."""

    NONE = auto()  # no cell borders (the compact terminal look)
    FRAME = auto()  # outer boundary only
    FULL = auto()  # every cell edge (wireframe / printed-grid look)


@dataclass(frozen=True)
class Edge:
    """
    The edge of `cell` on side `direction`. Always store in canonical form
    (construct via Grid.edge, the only public constructor) so the same
    geometric edge seen from either adjacent cell compares and hashes equal.
    """

    cell: GridCell
    direction: str


@dataclass(frozen=True)
class Vertex:
    """
    A corner of `cell` named by the grid's corner vocabulary (rectangular:
    nw/ne/se/sw). Always canonical (construct via Grid.vertex).
    """

    cell: GridCell
    corner: str


@dataclass(frozen=True)
class SceneElementBase:
    """
    Fields shared by every scene element. KW_ONLY makes them keyword-only
    with defaults, so element subclasses keep their natural positional
    fields (dataclass ordering stays legal).
    """

    _: KW_ONLY
    backends: BackendSet = ALL_BACKENDS
    provenance: Provenance = Provenance.DERIVED


@dataclass(frozen=True)
class CellFill(SceneElementBase):
    """
    Paint a cell's background. Touches only the background channel — glyphs
    beneath show through. opacity=None means the backend theme's default
    fill softening; backends without an opacity channel ignore it.
    """

    cell: GridCell
    color: ColorSpec
    layer: int = Layer.FILL
    opacity: float | None = None


@dataclass(frozen=True)
class CellGlyph(SceneElementBase):
    """
    A glyph at the cell's content anchor. color=None inherits (terminal
    default); any fill underneath is preserved.
    """

    cell: GridCell
    glyph: Glyph
    color: ColorSpec | None = None
    layer: int = Layer.GLYPH


@dataclass(frozen=True)
class CellPath(SceneElementBase):
    """
    A path through a cell entering/leaving via the named directions (2 for
    a through-path; grids with more neighbors may see 1 or 3+). ASCII picks
    a glyph from the geometry's direction-set table ({'e','s'} -> corner
    char); SVG draws segments from edge midpoints through the cell center.
    """

    cell: GridCell
    directions: frozenset[str]
    color: ColorSpec | None = None
    layer: int = Layer.PATH


@dataclass(frozen=True)
class CellLink(SceneElementBase):
    """
    Two cells styled as one unit. ASCII draws `glyph` in both cells in the
    shared color; SVG additionally draws a connector between cell centers.
    """

    cell1: GridCell
    cell2: GridCell
    glyph: Glyph | None = None
    color: ColorSpec | None = None
    layer: int = Layer.PATH


@dataclass(frozen=True)
class EdgeSegment(SceneElementBase):
    """
    Draw along a cell edge: loops, block borders, region cages, fences.
    Use Layer.GRID_MARK for structural borders.
    """

    edge: Edge
    color: ColorSpec | None = None
    weight: EdgeWeight = EdgeWeight.NORMAL
    layer: int = Layer.PATH


@dataclass(frozen=True)
class CellMark(SceneElementBase):
    """
    A shape mark at the cell's center — distinct from CellGlyph, which is
    content text. glyph=None means the backend's default dot; ring=True an
    open circle in backends with a shape channel (character backends draw
    the glyph or default dot either way).
    """

    cell: GridCell
    glyph: Glyph | None = None
    color: ColorSpec | None = None
    ring: bool = False
    layer: int = Layer.PATH


@dataclass(frozen=True)
class EdgeMark(SceneElementBase):
    """
    A mark at an edge's midpoint (e.g. a Galaxies center between two
    orthogonal cells). glyph=None means the backend's default dot;
    ring=True an open circle where a shape channel exists. In character
    layouts the mark needs the edge's lane; a collapsed lane skips it.
    """

    edge: Edge
    glyph: Glyph | None = None
    color: ColorSpec | None = None
    ring: bool = False
    layer: int = Layer.PATH


@dataclass(frozen=True)
class VertexMark(SceneElementBase):
    """
    A mark at a cell corner. glyph=None means the geometry's default dot;
    ring=True an open circle where a shape channel exists.
    """

    vertex: Vertex
    glyph: Glyph | None = None
    color: ColorSpec | None = None
    ring: bool = False
    layer: int = Layer.PATH


@dataclass(frozen=True)
class OutsideLabel(SceneElementBase):
    """
    A label outside the grid where line-of-sight `direction` enters line
    `index` (edge clues, line counts). `offset` stacks label rings
    (0 = nearest the grid).
    """

    direction: str
    index: int
    glyph: Glyph
    color: ColorSpec | None = None
    offset: int = 0
    layer: int = Layer.GLYPH


type SceneElement = (
    CellFill | CellGlyph | CellMark | CellPath | CellLink | EdgeSegment | EdgeMark | VertexMark | OutsideLabel
)


@dataclass(frozen=True)
class CellStyle:
    """Style for a clue value from the input grid. Clue glyphs default to
    ANNOTATION so a solution atom covering the cell cannot repaint the
    given value in solution colors; lower `layer` to Layer.GLYPH when the
    solution's repaint is the desired look.

    The glyph and fill channels may address different backends (the '#'
    convention: character backends draw the glyph, SVG paints the cell
    solid — see filled_clue): fill_backends=None gives the fill the
    glyph's `backends`; fill_opacity=None the backend theme's default
    softening."""

    glyph: Glyph | None = None
    color: ColorSpec | None = None
    fill: ColorSpec | None = None
    layer: int = Layer.ANNOTATION
    backends: BackendSet = ALL_BACKENDS
    fill_backends: BackendSet | None = None
    fill_opacity: float | None = None


@dataclass(frozen=True)
class SceneStyle:
    """
    The substrate: the puzzle's request for how the grid itself is drawn,
    painted by each backend's painter at Layer.BASE and interpreted per
    backend. Region borders and cages are content (EdgeSegments), not
    substrate.
    """

    lattice: Lattice = Lattice.NONE
    frame_weight: EdgeWeight = EdgeWeight.NORMAL  # HEAVY = bold outer boundary
    vertex_dots: bool = False  # substrate dot at every vertex
    # packed=True: cells touch, so fills merge into solid blocks — the
    # traditional tight terminal look; False: one space between cells
    packed: bool = False
    empty: CellStyle = field(default_factory=lambda: CellStyle(glyph=Glyph(".")))  # untouched cells
    # Print-substrate fields (SVG). Character backends ignore them — their
    # substrate questions are the layout-changing `lattice` and `packed`
    # above. A puzzle wanting a different SVG substrate without touching
    # its character render overrides via backend_styles (e.g. Slitherlink's
    # dot grid: hairline=False, vertex_dots=True, heavy_frame=False).
    hairline: bool = True  # full cell lattice as hairlines
    heavy_frame: bool = True  # outer boundary, heavier than the lattice


@dataclass(frozen=True)
class LayoutNeeds:
    """
    What a geometry must materialize for one backend's visible elements:
    the canonical edges and vertices in use, and per-direction label
    margins. Pure data — no character knowledge — so Scene can compute it
    without importing any backend. Geometries derive their lane/collapse decisions from
    the edge and vertex sets; mapping a line direction to a side of the
    canvas is the geometry's business, so the margin mapping is keyed by
    direction name, valued by the widest label text in that direction.
    """

    edges: frozenset[Edge] = frozenset()
    vertices: frozenset[Vertex] = frozenset()
    label_margins: Mapping[str, int] = field(default_factory=dict)


@dataclass
class Scene:
    """
    The backend-agnostic render description: one scene per render, holding
    every element regardless of backend visibility. Renderers consume it
    through the two filtered views (sorted_elements / layout_needs), which
    are the single choke point for backend visibility — layout and painting
    can never disagree about what a backend sees.
    """

    grid: RenderGrid
    style: SceneStyle = field(default_factory=SceneStyle)
    backend_styles: Mapping[Backend, SceneStyle] = field(default_factory=dict)
    _elements: list[SceneElement] = field(default_factory=list, repr=False)

    def style_for(self, backend: Backend) -> SceneStyle:
        """
        The substrate style a backend renders under: its entry in
        backend_styles, else the default. Whole-style replacement — no
        field merging. Geometries and layout decisions consult this, so a
        substrate requested for one backend never affects another's layout.
        """
        return self.backend_styles.get(backend, self.style)

    def add(self, *elements: SceneElement) -> None:
        self._elements.extend(elements)

    # -- the filtered views renderers consume --

    def visible(self, backend: Backend) -> Iterator[SceneElement]:
        """All elements visible to `backend`, in insertion order."""
        return (element for element in self._elements if backend in element.backends)

    def sorted_elements(self, backend: Backend) -> list[SceneElement]:
        """Visible elements in painter's order: (layer, insertion order)."""
        return sorted(self.visible(backend), key=lambda element: element.layer)

    def layout_needs(self, backend: Backend) -> LayoutNeeds:
        """
        Summarize what geometry must materialize for `backend`. Computed
        over the same filtered view as sorted_elements, so an element
        hidden from a backend can never influence that backend's layout.
        """
        edges: set[Edge] = set()
        vertices: set[Vertex] = set()
        label_margins: dict[str, int] = {}
        for element in self.visible(backend):
            match element:
                case EdgeSegment(edge=edge) | EdgeMark(edge=edge):
                    edges.add(edge)
                case VertexMark(vertex=vertex):
                    vertices.add(vertex)
                case OutsideLabel(direction=direction, glyph=glyph):
                    # Width of what THIS backend will draw (glyph variants
                    # may differ per backend)
                    width = len(glyph.for_backend(backend))
                    label_margins[direction] = max(label_margins.get(direction, 0), width)
                case _:
                    pass
        return LayoutNeeds(edges=frozenset(edges), vertices=frozenset(vertices), label_margins=label_margins)
