# ASPuzzle Rendering Redesign — Unified Design

**Status:** approved design (synthesis of three proposals, verified against the code; amended for per-backend element selection, testability, and dual rendering)
**Scope:** `aspuzzle/grids/rendering.py`, `Grid.render_ascii`/`Grid.line_characters`, `Solver.render_puzzle`/`get_render_config`/`_preprocess_*`, `region_coloring.py`, all 15 solver render configs
**Non-goals:** any change to ASP program construction or solving

---

## 1. Problem statement (verified against the source)

The current pipeline is `get_render_config() -> dict[str, Any]` → `Solver._preprocess_puzzle_symbols()` / `_preprocess_predicates()` → `grid.render_ascii()` building a rows×cols array of `RenderSymbol`. Concrete deficiencies, each confirmed in the code:

1. **ANSI is the color model.** `Color.BLUE = "\033[34m"` — the escape code *is* the enum value (`grids/rendering.py`). Every solver imports these; `region_coloring.py` returns `BgColor`. An SVG backend has nothing to consume.
2. **Everything is one character in a cell.** `RenderItem` = (cell predicate, one char, fg, bg). There is no way to draw on an edge, at a vertex, or outside the grid. Consequences today:
   - Skyscrapers' `top_clues`/`bottom_clues`/`left_clues`/`right_clues` are constrained but **never rendered**; likewise Tents' and Stitches' row/column counts.
   - Slitherlink renders a green inside-fill but cannot draw its actual loop, which lives on cell edges.
   - Sudoku's block borders are rectangular-only magic keys (`draw_box`/`rows_per_box`/`cols_per_box`) interpreted deep inside `RectangularGrid._render_grid_with_boxes`.
3. **The config is stringly typed.** `"priority"`, `"custom_renderer"`, `"symbol"`, `"color"`, `"background"`, `"value"`, `"loop_directions"`, `"dir1_field"`, `"dir2_field"`, `"join_char"` — mypy checks none of it. `Solver._preprocess_predicates` resolves Numberlink's box-drawing glyph by concatenating two direction strings and indexing `grid.line_characters` — grid-specific character knowledge in the solver base class.
4. **Grid classes own rendering logic, not just geometry.** ~180 lines of canvas assembly and junction tables in `RectangularGrid`; a hex grid would have to reimplement all of it.
5. **Stateful side channels.** Galaxies (`_preprocess_for_rendering`), Stitches and Starbattle (`_preprocess_config`) stash `self._region_colors` for closures in `get_render_config` to read — an implicit ordering contract with a "fallback that shouldn't be reached" in Galaxies. Stitches' `color_index = [0]` mutable-cell closure makes stitch colors call-order-dependent.
6. **Small latent defects.** `Solver.render_puzzle` never threads `use_colors` into `grid.render_ascii`; the >9→letters convention is applied to *clue* glyphs (Sudoku, Skyscrapers, hand-rolled twice) but solution values go through `str(pred[value_field])` and render multi-char; clue glyphs paint *below* solution atoms, so Sudoku's clue cells silently turn solution-green in solved renders.

The redesign replaces all of this with one idea: **solvers declare a typed, backend-agnostic Scene; grids supply geometry; renderers paint.**

---

## 2. Architecture overview

```
┌──────────────────────────────────────────────────────────────────────┐
│ Solver                                                               │
│   get_render_spec() -> RenderSpec    declarative 90% (typed rules)   │
│   build_scene() -> Scene             optional imperative hook        │
└───────────────────────────┬──────────────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Scene  (backend-agnostic IR — the SVG contract, fixed now)           │
│   elements: CellFill · CellGlyph · CellPath · CellLink ·             │
│             EdgeSegment · VertexMark · OutsideLabel                  │
│   locations: GridCell atoms · Edge · Vertex · (direction, index)     │
│   colors:    ColorSpec = PaletteColor | Rgb   (semantic, no ANSI)    │
│   layers:    Layer IntEnum + insertion order                         │
│   visibility: per-element BackendSet — ONE scene, query-time filter  │
│   provenance: GIVEN (puzzle input) | DERIVED (solution atoms)        │
└────────────┬─────────────────────────────────────┬───────────────────┘
             ▼                                     ▼
┌────────────────────────────┐       ┌────────────────────────────────┐
│ AsciiRenderer (now)        │       │ SvgRenderer (later)            │
│  CharCanvas + AsciiTheme   │       │  SvgTheme                      │
│  filters with Backend.ASCII│       │  filters with Backend.SVG      │
│  asks grid.ascii_geometry  │       │  asks grid.svg_geometry        │
└────────────┬───────────────┘       └────────────────┬───────────────┘
             ▼                                        ▼
┌────────────────────────────┐       ┌────────────────────────────────┐
│ RectangularAsciiGeometry   │       │ RectangularSvgGeometry         │
│ HexAsciiGeometry (soon)    │       │ HexSvgGeometry                 │
│ TriAsciiGeometry (soon)    │       │ cell → polygon, edge → segment │
└────────────────────────────┘       └────────────────────────────────┘
```

Division of responsibility (the CLAUDE.md ~99% grid-agnostic philosophy applied to rendering):

- **Solvers** know *what* to show, in vocabulary the ASP side already uses: cell atoms, direction names, line `(direction, index)`. Never characters, ANSI codes, pixels, or canvas coordinates. What a solver *may* say about backends is exactly one thing: **which backends an element is for** — a capability/taste judgment ("ASCII cannot do this loop justice; show fills there and draw the loop in SVG"), not a styling instruction.
- **Grids** know *where* things are: pure-Python neighbor/edge/vertex arithmetic, plus one geometry object per backend mapping abstract locations to canvas positions (ASCII) or ℝ² (SVG). Zero styling or element-interpretation logic.
- **Renderers** know *how* to paint: layer ordering, themes, canvas/`<svg>` serialization. Zero grid-specific knowledge. Hex and triangular grids implement geometry only — **no new renderer, no solver changes**.

Three cross-cutting requirements shape the model and are discharged structurally (each verified in the sections cited):

- **Per-backend element selection** (§3.5, §5.1, §7.6): ASCII often cannot render everything; SVG must render everything. The *solver* chooses what each backend shows, via a typed visibility field on elements and rules. The Scene stays a single IR — visibility is data on elements, filtering is a query parameter, never a fork into per-backend scenes.
- **Dual rendering** (§3.5, §4.1, §7.2): the unsolved puzzle (`render_puzzle(solution=None)`, `solveit.py`'s preview) and the solved state render through the *same* pipeline, and the puzzle-given vs solution-derived distinction is an explicit, typed part of the model (`Provenance`), which backends may style differently.
- **Unit-testability of every layer in isolation** (§9): scene as pure data, backends against golden strings from synthetic scenes, geometry contracts without solvers, specs as pure data without solving. This is an acceptance criterion, not an aspiration; the migration plan gates on it.

New package layout:

```
aspuzzle/rendering/
    __init__.py       re-exports the solver-facing vocabulary
    backend.py        Backend, BackendSet, visibility constants (leaf module)
    color.py          PaletteColor, Rgb, ColorSpec
    glyph.py          Glyph (per-backend variants), glyph_for_value
    scene.py          Provenance, Layer, Edge, Vertex, element dataclasses,
                      Scene, SceneStyle, LayoutNeeds
    gridview.py       RenderGrid protocol (the typed rendering/ASP boundary)
    spec.py           RenderSpec, CellStyle, LineLabels, rule dataclasses, build_scene
    regioncolor.py    region coloring core (moved from grids/region_coloring.py,
                      ColorSpec-typed, deterministic)
    grids/            per-grid geometry implementations, one module per
                      (grid type, backend) pair — no ASP anywhere here
        rectangular_ascii.py   RectangularAsciiGeometry
        hex_ascii.py           (with HexGrid)
        rectangular_svg.py     (with the SVG renderer)
    ascii/
        canvas.py     CharCanvas (styled-character compositing surface)
        geometry.py   AsciiGeometry protocol (canvas.py holds CharPos, TextSpan)
        renderer.py   AsciiRenderer
        theme.py      AsciiTheme (ColorSpec → ANSI; the only ANSI in the system)
    svg/              (later; protocols defined now)
        geometry.py   SvgGeometry protocol, Point
        renderer.py   SvgRenderer, SvgTheme
```

`aspuzzle/grids/rendering.py` (`Color`, `BgColor`, `colorize`, `RenderItem`, `RenderSymbol`) is deleted after migration, as are `Grid.render_ascii`, `Grid.line_characters`, `Solver.get_render_config`, `_preprocess_puzzle_symbols`, `_preprocess_predicates`, and `_preprocess_for_rendering`. `_preprocess_config` survives for non-render preprocessing.

---

## 3. The typed model

All code is mypy-strict-ready: frozen dataclasses, PEP 695 type aliases, Protocols.

### 3.1 Colors — semantic tokens, backend-mapped

```python
# aspuzzle/rendering/color.py
from dataclasses import dataclass
from enum import Enum, auto

class PaletteColor(Enum):
    """Semantic named colors. Backends map them: the ASCII theme to ANSI SGR
    codes, the SVG theme to designed hex values. The 16 names deliberately
    match terminal capability so ASCII output is never an approximation of
    the model."""
    BLACK = auto(); RED = auto(); GREEN = auto(); YELLOW = auto()
    BLUE = auto(); MAGENTA = auto(); CYAN = auto(); WHITE = auto()
    BRIGHT_BLACK = auto(); BRIGHT_RED = auto(); BRIGHT_GREEN = auto()
    BRIGHT_YELLOW = auto(); BRIGHT_BLUE = auto(); BRIGHT_MAGENTA = auto()
    BRIGHT_CYAN = auto(); BRIGHT_WHITE = auto()

@dataclass(frozen=True)
class Rgb:
    """Exact color for backends that support it. The ASCII theme quantizes
    to the nearest PaletteColor (truecolor emission is a later theme
    extension, invisible to solvers)."""
    r: int; g: int; b: int   # 0..255, validated in __post_init__

type ColorSpec = PaletteColor | Rgb
```

One color space for both roles; foreground vs background is carried by the element kind (`CellGlyph.color` vs `CellFill.color`), not by parallel enums. `None` everywhere means "inherit / terminal default" — this replaces Galaxies' `Color.RESET`-as-a-color hack. ANSI escape strings exist only in `ascii/theme.py`:

```python
# aspuzzle/rendering/ascii/theme.py
@dataclass(frozen=True)
class AsciiTheme:
    fg_codes: Mapping[PaletteColor, str]     # "\033[34m", ...
    bg_codes: Mapping[PaletteColor, str]
    def fg(self, c: ColorSpec) -> str: ...   # Rgb → nearest PaletteColor
    def bg(self, c: ColorSpec) -> str: ...

DEFAULT_THEME: Final[AsciiTheme]             # exactly today's SGR codes
```

### 3.2 Glyphs — with per-backend variants

```python
# aspuzzle/rendering/glyph.py
@dataclass(frozen=True)
class Glyph:
    """A renderable text mark with optional per-backend variants.

    `text` is the baseline every backend falls back to. Keep it one
    grapheme: character-grid geometries enforce their content width (1 char
    on rectangular grids), and emoji are double-width in terminals, which
    breaks column alignment. Richer backends may override — svg= for
    full-fidelity marks (emoji welcome), sheet= for spreadsheet cells (no
    width limit): Glyph("A", svg="⛺") renders a tent as 'A' in the
    terminal and as the emoji in SVG, from ONE element/rule."""
    text: str
    svg: str | None = None
    sheet: str | None = None

    def for_backend(self, backend: Backend) -> str:
        """The text this backend renders: its override if set, else text."""

def glyph_for_value(value: int) -> Glyph:
    """The single home of the digit convention: 0-9 as digits, 10+ as
    letters (10 -> 'A') on character grids. Currently duplicated in Sudoku
    and Skyscrapers clue maps — and *not* applied to solution values, which
    today render multi-char through str(); this fixes that inconsistency.
    10+ carries its literal number as the sheet variant (a spreadsheet
    wants "10", not "A"); SVG keeps the letter so the drawn puzzle matches
    the terminal render."""
```

Glyph variants vs the complementary-pair idiom (§3.5 rule 4): variants are for *the same mark drawn with different text* — one element, resolved by each renderer via `for_backend`, with `layout_needs` measuring the backend-resolved width. The pair idiom remains for *structurally different content* per backend (different element kinds, different layers, or omission). `Backend` itself lives in its own leaf module (`backend.py`) so both `glyph.py` and `scene.py` can import it without a cycle.

### 3.3 Locations — cell, edge, vertex, outside

Cells stay what they are: `GridCell` predicate instances — the typed, hashable value objects solvers already hold from solution atoms and `grid.Cell(*loc)`. No parallel `CellRef` type. Edges and vertices are new canonicalized value types:

```python
# aspuzzle/rendering/scene.py
@dataclass(frozen=True)
class Edge:
    """The edge of `cell` on side `direction`. Always stored in canonical
    form (construct via Grid.edge), so the same geometric edge seen from
    either adjacent cell compares and hashes equal."""
    cell: GridCell
    direction: str

@dataclass(frozen=True)
class Vertex:
    """A corner of `cell` named by the grid's corner vocabulary
    (rectangular: nw/ne/se/sw; hex: six names; triangular: three,
    orientation-dependent). Always canonical (construct via Grid.vertex)."""
    cell: GridCell
    corner: str
```

Outside-the-grid clue positions need no dataclass: they are addressed by the grid's existing **line vocabulary** as `(direction, index)` — "just outside the grid, where line-of-sight direction `direction` enters line `index`". Skyscrapers' top clue for column 3 is `("s", 3)`, exactly matching its existing `Clue(dir="s", index=3)` facts (verified: `clue_mapping` in `skyscrapers.py` maps top→"s", bottom→"n", left→"e", right→"w"). This reuses `line_direction_names`/`get_line_count` and is meaningful on hex grids with their own line directions. An `offset` field on `OutsideLabel` stacks multiple label rings — **deferred** (see §11): the geometry raises loudly on `offset > 0` until the first solver needs a second ring.

### 3.4 Grid additions (pure Python, no ASP, no grounding)

Rendering must not require grounding a program, so grids gain a small Python-side geometric vocabulary. These live directly on `Grid` (grids are plain objects already instantiable without grounding — no separate Topology companion class):

```python
# additions to aspuzzle/grids/base.py :: Grid
class Grid(Module, ABC):
    # -- concrete-coordinate helpers used only by rendering --
    def cell_coords(self, cell: GridCell) -> tuple[int, ...]:
        return tuple(cell[f].value for f in self.cell_fields)

    @abstractmethod
    def neighbor(self, cell: GridCell, direction: str) -> GridCell | None:
        """Edge-adjacent neighbor in `direction`, or None if off-grid
        (outside-border cells count as off-grid here). Must agree with the
        grid's ASP Orthogonal/Direction facts — enforced by a conformance
        test that grounds a small instance and diffs."""

    @property
    @abstractmethod
    def corner_names(self) -> Sequence[str]:
        """The corner vocabulary of this grid's cells (rect: nw/ne/se/sw)."""

    @abstractmethod
    def corner_across(self, corner: str, direction: str) -> str | None:
        """The name a cell-corner carries in the neighbor across
        `direction`, or None when that edge is not incident to the corner.
        The one grid-specific fact vertex() needs: the generic walk in the
        base class crosses incident edges collecting every spelling of the
        point, then keeps the lexicographically smallest. Cell-independent,
        as is the edge-direction vocabulary (orthogonal_direction_names):
        every cell of a rectangular or hex grid has the same shape. The
        deferred triangular exploration (§5.5) would widen these to
        per-cell signatures — a mechanical change, taken only when needed."""

    @abstractmethod
    def all_cells(self) -> Iterator[GridCell]:
        """Every in-grid cell as a grounded Cell instance (no outside
        border). Consumed by RegionBorderRule(by=...) (classify every
        cell), RegionBoundaryRule, and the conformance suites."""

    def edge(self, cell: GridCell, direction: str) -> Edge:
        """Canonical Edge between `cell` and its `direction`-neighbor
        (valid for boundary edges too). Default: flip through
        opposite_directions and keep the representation with the
        lexicographically smaller (cell_coords, direction). The only
        public Edge constructor."""

    def vertex(self, cell: GridCell, corner: str) -> Vertex:
        """Canonical Vertex; default resolves shared corners through
        neighbor(). The only public Vertex constructor."""

    # -- geometry factories consumed by renderers --
    @abstractmethod
    def ascii_geometry(self, needs: LayoutNeeds, style: SceneStyle) -> AsciiGeometry: ...
    def svg_geometry(self) -> SvgGeometry:   # later; default raises
        raise NotImplementedError(f"{type(self).__name__} has no SVG geometry yet")
```

`neighbor()` and `all_cells()` are contracts, not implementation mandates: rectangular grids answer by arithmetic over the shared `direction_vectors` table plus a bounds check; a grid whose boundary is complicated may instead extract and cache its ground `Cell` atoms (see the double-bookkeeping entry in §11 for the decided strategy) so membership is stated once, in ASP. Renderers and the conformance suite cannot tell the difference.

**The `RenderGrid` protocol — the typed rendering/ASP boundary.** Grid classes intentionally carry both faces (ASP emission and rendering vocabulary): the grid is the single geometry authority with two consumers, and the shared currency — cells as predicate instances, shared direction names — is the design's asset. The *dependency* boundary is what gets enforced: a structural Protocol `RenderGrid` in the rendering package lists exactly the surface above (topology methods, geometry factories, line vocabulary), and `Scene.grid`, renderers, and geometries are typed against it rather than `Grid`. `Grid` satisfies it structurally; nothing rendering-side can reach the statement verbs or cached predicates, and the protocol doubles as the checklist a new grid author implements. (Scope, decided at implementation: the guarantee covers scene/spec/renderers; a concrete geometry legitimately types against its own concrete grid — RectangularAsciiGeometry reads .rows/.cols. The protocol also carries Cell, for constructing grounded cells from parsed clue coordinates.) The inverse direction (rendering concerns perturbing the emitted ASP) is guarded behaviorally: goldens plus the checked-in `.lp` renders surface any program diff.

**Removed from `Grid`:** `render_ascii` (abstract method) and `line_characters` (abstract property). The box-drawing table moves into `RectangularAsciiGeometry`, re-keyed by `frozenset[str]` direction sets — killing today's duplicated `"ew"/"we"` string-concatenation keys.

### 3.5 Cross-cutting element fields: backends and provenance

Two enums and a shared keyword-only base carry the per-backend-selection and dual-rendering requirements into every element:

```python
# aspuzzle/rendering/scene.py
from dataclasses import KW_ONLY, dataclass, field

class Backend(Enum):
    """The closed set of rendering backends. Closed on purpose, like the
    element union: adding a backend is a conscious cross-cutting decision
    (it revisits every visibility constant, renderer, and golden)."""
    ASCII = auto()
    SVG = auto()
    SHEET = auto()   # tab-separated text for spreadsheet paste (§6.1)

type BackendSet = frozenset[Backend]
ALL_BACKENDS: Final[BackendSet] = frozenset(Backend)
ASCII_ONLY:   Final[BackendSet] = frozenset({Backend.ASCII})
SVG_ONLY:     Final[BackendSet] = frozenset({Backend.SVG})
SHEET_ONLY:   Final[BackendSet] = frozenset({Backend.SHEET})

class Provenance(Enum):
    """Where an element's information came from. Backends may style the two
    classes differently (e.g. SVG: bold clue digits, lighter solution
    values); the ASCII default theme ignores it, preserving today's look."""
    GIVEN = auto()     # puzzle input: grid clues, config label arrays, input regions
    DERIVED = auto()   # solution atoms

@dataclass(frozen=True)
class SceneElementBase:
    """Fields shared by every scene element. KW_ONLY makes them
    keyword-only with defaults, so element subclasses keep their natural
    positional fields (dataclass ordering stays legal)."""
    _: KW_ONLY
    backends: BackendSet = ALL_BACKENDS
    provenance: Provenance = Provenance.DERIVED
```

**Visibility semantics — stated precisely, because they are the model's answer to "ASCII cannot render everything":**

1. **One Scene, always.** The Scene contains *every* element regardless of visibility; there is no per-backend scene, ever. A future JSON serialization of a scene therefore loses nothing, and `build_scene` runs once per render regardless of backend.
2. **Filtering happens in the Scene's query methods, nowhere else.** `scene.sorted_elements(backend)` and `scene.layout_needs(backend)` both filter by `backend in element.backends`. Renderers pass their own `Backend` identity and never re-check. Because *layout* and *painting* consult the same filtered view, an element hidden from ASCII can never influence ASCII layout: an SVG-only `EdgeSegment` does not set `LayoutNeeds.edges` (so the compact layout survives), and an SVG-only `OutsideLabel` reserves no label margin. This single-choke-point rule is what makes the feature safe — there is no second place for layout and paint to disagree.
3. **Explicit solver choice wins over geometry fallbacks.** Geometry best-effort fallbacks (hex `CellPath` → `*`, §5.4) apply only to elements the solver *left visible* on that backend. If the solver marks the element `SVG_ONLY` (optionally providing an `ASCII_ONLY` alternative), the ASCII geometry never sees it and no fallback fires. Precedence order: visibility filter first, then geometry fidelity. Fallbacks remain the safety net for solvers that make no choice — the default is still `ALL_BACKENDS`, and the default behavior is unchanged.
4. **"Simplified alternative in ASCII" is the complementary-pair idiom**, not a special construct: one element/rule with `backends=SVG_ONLY`, one with `backends=ASCII_ONLY` (worked example in §7.6). Two rules reading the same predicate cost nothing extra.
5. **Visibility is the only sanctioned way to omit.** A renderer must never silently skip a visible element it cannot render exactly; it renders best-effort (or raises, per the geometry's documented contract). SVG, having full fidelity, is expected to be given `ALL_BACKENDS` or `SVG_ONLY` elements only in practice — but `ASCII_ONLY` is legal and simply invisible there.

**Provenance semantics:** `build_scene` stamps provenance mechanically — solvers never set it by hand in the declarative path. Clue styles, `LineLabels`, and input-data-driven rules (`RegionBorderRule(by=…)`, `FromClues` sources) emit `GIVEN`; predicate-sourced rules emit `DERIVED`; `CustomRule` and `build_scene` overrides may set either (default `DERIVED`). Provenance is *meaning*, not paint order — it deliberately does not affect layering, which is why it is a separate field rather than a `Layer` convention (Sudoku clue digits and solution digits share `Layer.GLYPH` yet differ in provenance).

### 3.6 Scene elements

*Amended at the SVG milestone:* the element union grew its one post-freeze
addition — marks at all three in-grid locations. Galaxies surfaced the
gap: its centers live at cell centers, edge midpoints, and vertices, and
the union had marks only at vertices. `CellMark` (shape mark at a cell
center, distinct from `CellGlyph`'s content text) and `EdgeMark` (mark at
an edge midpoint; contributes its edge to `LayoutNeeds.edges`, and a
collapsed character lane skips it) now mirror `VertexMark`, and all three
carry `ring: bool` — glyph=None draws the backend's default dot, ring=True
an open circle where a shape channel exists (character backends draw the
glyph or dot regardless). The snippet below predates the amendment.

```python
# aspuzzle/rendering/scene.py
from enum import IntEnum

class Layer(IntEnum):
    """Named paint order replacing raw priority ints. Elements carry
    kind-appropriate defaults; any int works for fine-grained tweaks.
    Within a layer, insertion order breaks ties (stable sort)."""
    BASE = 0        # frame / lattice (painted by geometry from SceneStyle)
    FILL = 10       # cell backgrounds
    GRID_MARK = 20  # structural borders (Sudoku boxes, region cages)
    PATH = 30       # in-cell paths, links, edge strokes, vertex marks
    GLYPH = 40      # clue and solution glyphs
    ANNOTATION = 50 # anything that must win

class EdgeWeight(Enum):
    NORMAL = auto()   # today's light box chars / normal SVG stroke
    HEAVY = auto()    # double-line box chars (═║╔…) / thicker stroke

@dataclass(frozen=True)
class CellFill(SceneElementBase):
    """Paint a cell's background. Touches only the background channel —
    glyphs beneath show through (the typed replacement for today's
    symbol=None RenderItem idiom used by Slitherlink/Hitori/Galaxies)."""
    cell: GridCell
    color: ColorSpec
    layer: int = Layer.FILL

@dataclass(frozen=True)
class CellGlyph(SceneElementBase):
    """A glyph at the cell's content anchor. color=None inherits (terminal
    default); any fill underneath is preserved."""
    cell: GridCell
    glyph: Glyph
    color: ColorSpec | None = None
    layer: int = Layer.GLYPH

@dataclass(frozen=True)
class CellPath(SceneElementBase):
    """A path through a cell entering/leaving via the named directions
    (2 for a through-path; grids with more neighbors may see 1 or 3+).
    ASCII picks a glyph from the geometry's direction-set table
    ({'e','s'} → '┌'); SVG draws segments from edge midpoints through the
    cell center. Replaces 'loop_directions'."""
    cell: GridCell
    directions: frozenset[str]
    color: ColorSpec | None = None
    layer: int = Layer.PATH

@dataclass(frozen=True)
class CellLink(SceneElementBase):
    """Two cells styled as one unit (Stitches). ASCII draws `glyph` in both
    cells in the shared color; SVG additionally draws a connector between
    the cell centers."""
    cell1: GridCell
    cell2: GridCell
    glyph: Glyph | None = None
    color: ColorSpec | None = None
    layer: int = Layer.PATH

@dataclass(frozen=True)
class EdgeSegment(SceneElementBase):
    """Draw along a cell edge: Slitherlink's loop, Sudoku block borders,
    region cages, fences."""
    edge: Edge
    color: ColorSpec | None = None
    weight: EdgeWeight = EdgeWeight.NORMAL
    layer: int = Layer.PATH          # use Layer.GRID_MARK for structure

@dataclass(frozen=True)
class VertexMark(SceneElementBase):
    """A mark at a cell corner (loop-puzzle dots; needed by hex/tri
    puzzles). glyph=None means the geometry's junction/default dot."""
    vertex: Vertex
    glyph: Glyph | None = None
    color: ColorSpec | None = None
    layer: int = Layer.PATH

@dataclass(frozen=True)
class OutsideLabel(SceneElementBase):
    """A label outside the grid where line-of-sight `direction` enters
    line `index` (Skyscrapers clues, Tents/Stitches counts). `offset`
    stacks label rings (0 = nearest the grid)."""
    direction: str
    index: int
    glyph: Glyph
    color: ColorSpec | None = None
    offset: int = 0
    layer: int = Layer.GLYPH

type SceneElement = (CellFill | CellGlyph | CellPath | CellLink
                     | EdgeSegment | VertexMark | OutsideLabel)
```

Every element inherits `backends`/`provenance` from `SceneElementBase` as trailing keyword-only fields — `CellFill(cell, PaletteColor.GREEN, backends=SVG_ONLY)` reads naturally and existing positional construction is untouched.

This is a deliberately **closed** union: every renderer must handle every kind, so adding a kind is a conscious cross-backend decision.

### 3.7 Scene container and style

```python
@dataclass(frozen=True)
class CellStyle:
    """Style for a clue value from the input grid (replaces RenderSymbol).
    Elements built from it are stamped Provenance.GIVEN."""
    glyph: Glyph | None = None
    color: ColorSpec | None = None
    fill: ColorSpec | None = None
    backends: BackendSet = ALL_BACKENDS

class Lattice(Enum):
    """How much of the grid's own skeleton the substrate draws."""
    NONE = auto()    # no cell borders (the compact terminal look)
    FRAME = auto()   # outer boundary only
    FULL = auto()    # every cell edge (wireframe / printed-grid look)

@dataclass(frozen=True)
class SceneStyle:
    lattice: Lattice = Lattice.NONE
    frame_weight: EdgeWeight = EdgeWeight.NORMAL   # HEAVY = bold outer boundary
    vertex_dots: bool = False    # substrate dot at every vertex (loop puzzles)
    packed: bool = False         # character-grid backends only: cells touch (old join_char "")
    empty: CellStyle = CellStyle(glyph=Glyph("."))   # character-grid backends only

@dataclass
class Scene:
    grid: RenderGrid
    style: SceneStyle = SceneStyle()
    backend_styles: Mapping[Backend, SceneStyle] = ...   # whole-style override per backend
    _elements: list[SceneElement] = field(default_factory=list)

    def style_for(self, backend: Backend) -> SceneStyle:
        """backend_styles.get(backend, style) — whole-style replacement,
        no field merging. layout_needs(backend) consults this, so (e.g.)
        SVG-only vertex dots never force ASCII into the expanded layout."""

    def add(self, *elements: SceneElement) -> None: ...
    # Not shipped: extend() and the convenience emitters (glyph/fill/
    # line_labels) sketched here were dropped at implementation — rules
    # emit elements directly, label emission lives in LineLabels.apply
    # (its one consumer), and no solver overrides build_scene. Revisit
    # only if build_scene overrides appear.

    # -- the only filtering choke point (see §3.5) --
    def visible(self, backend: Backend) -> list[SceneElement]:
        return [e for e in self._elements if backend in e.backends]
    def sorted_elements(self, backend: Backend) -> list[SceneElement]:
        """visible(backend), stable-sorted by (layer, insertion order) —
        the painter's order for that backend."""
    def layout_needs(self, backend: Backend) -> LayoutNeeds:
        """Summarize what geometry must materialize for that backend:
        edge/vertex lanes, per-side label margins (max label width per
        direction; keys widen to (direction, offset) when stacked rings
        land — see the ring deferral in §11). Computed over
        visible(backend) ONLY — an element hidden from ASCII can neither
        force the expanded layout nor reserve margins."""
```

**The substrate is the puzzle's request to the grid** (added July 2026, post-review): everything that isn't puzzle content — outer boundary, full wireframe lattice, vertex dots, plain — is `SceneStyle` vocabulary, painted by each backend's painter at `Layer.BASE` and interpreted per backend (ASCII `Lattice.FULL` = expanded layout with every lane stroked, junction-resolved; SVG `FULL` = light strokes on every cell polygon; sheet ignores lattice entirely). The same puzzle legitimately wants different substrates per backend — Slitherlink: compact fills in the terminal, dots-no-lines in SVG (`backend_styles={Backend.SVG: SceneStyle(vertex_dots=True)}`); Sudoku: sparse heavy-framed boxes in ASCII, full printed lattice in SVG — hence `backend_styles` with whole-style replacement. Region borders (Sudoku blocks, cages) deliberately stay *content* (`RegionBorderRule` → `EdgeSegment`s), not substrate: they are puzzle-specific structure and already compose per backend via rule visibility. Implementation lands with migration Step 5 (ASCII) and the SVG renderer; `RenderSpec` grows the matching `style`/`backend_styles` fields in Step 6.

**Compositing semantics** (today's, now structural): elements paint in `(layer, insertion order)`. A `CellFill` touches only the background channel; a `CellGlyph` touches glyph + foreground. "Clue digit over region fill" composes with no `symbol=None` convention. Elements at locations outside the drawable area are skipped silently, preserving today's behavior for Slitherlink's outside-border atoms.

---

## 4. The solver-facing spec

`get_render_config()` becomes `get_render_spec() -> RenderSpec`. The 80% case across the 15 solvers is a table — value → style for clues, predicate → style for solution atoms — and stays a table, just typed. Rules are small frozen dataclasses; closures survive where they earn their keep, but with signatures mypy can check.

**Backend selection at the spec level:** every rule dataclass below, and `LineLabels`, carries a trailing keyword-only field `backends: BackendSet = ALL_BACKENDS`; `build_scene` stamps it onto every element the rule emits. The default means "everywhere" — a solver that never thinks about backends gets identical output on all of them. Restricting is one keyword: `RegionBoundaryRule("inside", backends=SVG_ONLY)`. The "simplified ASCII alternative" is two rules over the same predicate with complementary `backends` (§7.6). The field is shown explicitly on the rules used in the worked examples and elided (`# + backends`) elsewhere for brevity — it exists on all of them.

```python
# aspuzzle/rendering/spec.py
type Colorer = Callable[[Predicate], ColorSpec]

@dataclass(frozen=True)
class RenderContext:
    grid: RenderGrid   # the typed boundary (§3.4) — rules cannot reach ASP verbs
    grid_data: Sequence[GridCellData]
    solution: Mapping[str, list[Predicate]]
    def atoms(self, predicate: str) -> Sequence[Predicate]:
        return self.solution.get(predicate, [])

@dataclass(frozen=True)
class GlyphRule:
    """predicate atoms → CellGlyph (+ optional CellFill). Replaces the
    'symbol'/'color'/'background'/'value' keys and most custom_renderer
    closures. Emits Provenance.DERIVED."""
    predicate: PredicateRef   # class (typo-loud, isinstance-filtered) or name
    loc_field: str = "loc"
    glyph: Glyph | None = None            # fixed glyph, or:
    value_field: str | None = None        # glyph_for_value(pred[value_field])
    color: ColorSpec | Colorer | None = None
    fill: ColorSpec | Colorer | None = None
    layer: int = Layer.GLYPH
    backends: BackendSet = ALL_BACKENDS

@dataclass(frozen=True)
class FillRule:
    """predicate atoms → CellFill (Slitherlink 'inside', Hitori 'black')."""
    predicate: PredicateRef   # class (typo-loud, isinstance-filtered) or name
    fill: ColorSpec | Colorer
    loc_field: str = "loc"
    layer: int = Layer.FILL
    backends: BackendSet = ALL_BACKENDS

@dataclass(frozen=True)
class PathRule:
    """predicate atoms → CellPath. Replaces 'loop_directions' /
    'dir1_field' / 'dir2_field'."""
    predicate: PredicateRef   # class (typo-loud, isinstance-filtered) or name
    loc_field: str = "loc"
    direction_fields: tuple[str, ...] = ("dir1", "dir2")
    color: ColorSpec | None = None
    layer: int = Layer.PATH
    backends: BackendSet = ALL_BACKENDS

@dataclass(frozen=True)
class EdgeRule:
    """predicate atoms carrying (cell, direction) → EdgeSegment — for loops
    or fences already derived in ASP."""
    predicate: PredicateRef   # class (typo-loud, isinstance-filtered) or name
    loc_field: str = "loc"
    direction_field: str = "direction"
    color: ColorSpec | None = None
    weight: EdgeWeight = EdgeWeight.NORMAL
    layer: int = Layer.PATH
    # + backends

@dataclass(frozen=True)
class LinkRule:
    """predicate atoms → CellLink, palette cycled deterministically per atom
    in sorted-atom order (Stitches — kills the mutable color_index[0])."""
    predicate: PredicateRef   # class (typo-loud, isinstance-filtered) or name
    loc_fields: tuple[str, str] = ("loc1", "loc2")
    glyph: Glyph | None = None
    palette: Sequence[ColorSpec] = ()
    layer: int = Layer.PATH
    # + backends

@dataclass(frozen=True)
class FromPredicate:
    predicate: PredicateRef; id_field: str = "id"; loc_field: str = "loc"

@dataclass(frozen=True)
class FromClues:
    """Region ids are the parsed grid_data values (Stitches/Starbattle,
    which use map_grid_to_integers). Runs with or without a solution;
    emits Provenance.GIVEN (input data, not solution)."""

@dataclass(frozen=True)
class RegionFillRule:
    """CellFill per cell, colors chosen by a deterministic four-coloring
    so adjacent regions differ. Runs the coloring internally — deletes the
    _preprocess_for_rendering / _preprocess_config / _region_colors
    plumbing from Galaxies, Stitches, and Starbattle. Provenance follows
    the source: FromClues → GIVEN, FromPredicate → DERIVED."""
    source: FromPredicate | FromClues
    palette: Sequence[ColorSpec] = DEFAULT_REGION_PALETTE   # ≥ 4 colors
    layer: int = Layer.FILL
    # + backends

@dataclass(frozen=True)
class RegionBorderRule:
    """EdgeSegments wherever a cell classification changes between
    neighbors — Sudoku blocks, Suguru cages, region outlines. Pure Python
    via grid.neighbor/grid.edge; works on any grid; with `by` it needs no
    solution (renders in previews, Provenance.GIVEN). Boundary edges
    (neighbor off-grid) are included when include_boundary=True (usually
    the frame covers them)."""
    by: Callable[[GridCell], object] | None = None     # classification, or:
    source: FromPredicate | FromClues | None = None
    weight: EdgeWeight = EdgeWeight.NORMAL
    color: ColorSpec | None = None
    include_boundary: bool = False
    layer: int = Layer.GRID_MARK
    # + backends

@dataclass(frozen=True)
class RegionBoundaryRule:
    """EdgeSegments around the boundary of a cell SET: edges between a
    member cell and any non-member or off-grid cell. Draws Slitherlink's
    actual loop straight from its 'inside' atoms — zero ASP changes."""
    predicate: PredicateRef   # class (typo-loud, isinstance-filtered) or name
    loc_field: str = "loc"
    color: ColorSpec | None = None
    weight: EdgeWeight = EdgeWeight.NORMAL
    layer: int = Layer.PATH
    backends: BackendSet = ALL_BACKENDS

@dataclass(frozen=True)
class CustomRule:
    """Typed escape hatch. Receives ALL atoms of the predicate at once
    (unlike per-instance closures) so whole-set decisions need no hidden
    mutable state; atoms arrive sorted for determinism. The callable sets
    backends/provenance on its elements directly; additionally, a
    non-default rule-level backends= is stamped onto emitted elements that
    kept ALL_BACKENDS, so the rule composes with visibility like every
    other rule."""
    predicate: PredicateRef   # class (typo-loud, isinstance-filtered) or name
    make: Callable[[Sequence[Predicate], RenderContext], Iterable[SceneElement]]

type AtomRule = (GlyphRule | FillRule | PathRule | EdgeRule | LinkRule
                 | RegionFillRule | RegionBorderRule | RegionBoundaryRule
                 | CustomRule)

@dataclass(frozen=True)
class LineLabels:
    """A ring of outside clues declared from a config array: one
    OutsideLabel per non-None value at (direction, i), 1-based.
    Emits Provenance.GIVEN."""
    direction: str
    values: Sequence[int | str | None]
    color: ColorSpec | None = None
    offset: int = 0
    backends: BackendSet = ALL_BACKENDS

@dataclass(frozen=True)
class RenderSpec:
    clues: Mapping[int | str, CellStyle] = field(default_factory=dict)  # was puzzle_symbols
    atoms: Sequence[AtomRule] = ()                                      # was predicates
    labels: Sequence[LineLabels] = ()                                   # NEW: outside clues
    style: SceneStyle = SceneStyle()
```

### 4.1 Scene construction and Solver integration

**Dual rendering is an explicit requirement, discharged here.** One pipeline serves both `solveit.py`'s puzzle preview (`render_puzzle(solution=None)`) and solved output; there is no separate preview path to drift. The seams that make previews *complete*, each verified against the spec machinery: clue glyphs/fills come from `spec.clues` over `grid_data` (no solution needed); outside labels come from `spec.labels` over config arrays (no solution needed); Sudoku boxes come from `RegionBorderRule(by=…)` (pure Python over cells, no solution needed); input-region coloring comes from `RegionFillRule(FromClues())` (grid data, no solution needed). So previews show region colors, boxes, and labels — strictly more than today's previews do. Solution-sourced rules over an absent solution simply emit nothing. The GIVEN/DERIVED split (§3.5) is the typed residue of this distinction, available to backends for differential styling.

```python
# aspuzzle/rendering/spec.py
def build_scene(grid: Grid, spec: RenderSpec, grid_data: Sequence[GridCellData],
                solution: Mapping[str, list[Predicate]] | None) -> Scene:
    """~50 lines of straight-line typed code replacing
    _preprocess_puzzle_symbols + _preprocess_predicates:
      1. Clue glyphs/fills from spec.clues over grid_data (Layer.GLYPH /
         Layer.FILL, inserted FIRST — so later atom rules at the same layer
         override clue cells, exactly today's paint order; verified:
         _build_render_grid paints puzzle items before predicate items).
         Stamped Provenance.GIVEN, backends from the CellStyle.
      2. Atom rules in sequence, each stamping its `backends` and its
         source-appropriate provenance onto every element it emits.
         Data-driven rules (RegionBorderRule with `by`, RegionFillRule/
         RegionBorderRule with FromClues) run even when solution is None,
         so previews show boxes and region colors. Predicate-sourced rules
         over absent predicates emit nothing (a predicate may legitimately
         be empty in a model).
      3. spec.labels via scene.line_labels (Provenance.GIVEN).
    RegionFillRule runs the four-coloring once per build (pure Python, deterministically
    — see §9); every Edge is already canonical because Grid.edge is the
    only constructor. build_scene never inspects element visibility — the
    Scene holds everything; backends filter at query time."""

# aspuzzle/solvers/base.py
class Solver(ABC):
    def get_render_spec(self) -> RenderSpec:
        """Declarative rendering description. Default: bare grid."""
        return RenderSpec()

    def build_scene(self, solution: dict[str, list[Predicate]] | None = None) -> Scene:
        """Override (call super, then scene.add(...)) only for elements the
        spec cannot express."""
        return build_scene(self.grid, self.get_render_spec(), self.grid_data, solution)

    def render_puzzle(self, solution: dict[str, list[Predicate]] | None = None,
                      *, use_colors: bool = True) -> str:
        # use_colors finally threaded end-to-end (today it silently isn't)
        return AsciiRenderer(use_colors=use_colors).render(self.build_scene(solution))
```

`solveit.py` keeps calling `solver.render_puzzle(...)` unchanged for both the preview and each solution; `--svg out.svg` is a one-line addition later (same `build_scene`, different renderer — including an SVG preview for free).

---

## 5. ASCII rendering

*Amended at the common-core rework (July 2026):* rendering now shares
one scene-walking engine across backends. `rendering/painter.py` holds
`ScenePainter` — per-kind dispatch, paint-or-skip arbitration, and
`CellLink`/`CellPath` decomposition — with `AsciiPainter` and
`SvgPainter` as its two leaves. (Backend filtering stays where it always
was, `Scene.sorted_elements`; substrate enumeration lives on
`GeometryBase` below.) Arbitration is split by location kind: cell
content filters on cell membership, while edges and vertices — lattice
items whose canonical spelling may carry an outside cell (a frame
vertex) — filter through the geometry's `on_lattice`/`vertex_on_lattice`
predicates, implemented once per grid shape, so both backends arbitrate
identically; geometry methods are total over inputs that pass
arbitration. The ASCII painter owns the per-render state
(`JunctionState` flag accumulation, the fill registry); the geometry
owns layout and character vocabulary only, and finishes the render
(`finish()`: run bridging, fill continuity, junction characters). The
`AsciiGeometry` protocol below reflects the reworked slim contract,
superseding the four-method paint-everything protocol this section
originally specified. Geometries themselves form a class hierarchy:
`GeometryBase` (everything statable in pure grid topology: substrate
enumeration `all/boundary/interior_edges` + `all_vertices`, the label
bounds via the grids' line vocabulary) → `RectangularGeometryBase` (the
lattice model — `_edge_lattice`/`_vertex_lattice`/`_on_lattice`, stated
once) → per-backend leaves; the SVG leaf derives its edge endpoints and
vertex points from the same lattice facts the ASCII leaf maps through
its lanes. A new grid shape adds one lattice model plus two thin
converters.

### 5.1 The renderer (grid-agnostic, the only painter)

```python
# aspuzzle/rendering/ascii/canvas.py
@dataclass(frozen=True)
class CharPos: row: int; col: int

@dataclass(frozen=True)
class TextSpan: row: int; col: int; width: int

class CharCanvas:
    """A styled-character compositing surface. put() with char=None
    preserves the char (fill under glyph); fg/bg=None preserve the
    channel — the transparency rule, in one place."""
    def __init__(self, rows: int, cols: int) -> None: ...
    def put(self, pos: CharPos, char: str | None = None,
            fg: ColorSpec | None = None, bg: ColorSpec | None = None) -> None: ...
    def put_text(self, span: TextSpan, text: str, fg: ColorSpec | None = None) -> None: ...
    def paint_bg(self, span: TextSpan, bg: ColorSpec) -> None: ...
    def to_string(self, theme: AsciiTheme, use_colors: bool) -> str: ...

# aspuzzle/rendering/ascii/renderer.py
class AsciiRenderer:
    backend: Final = Backend.ASCII

    def __init__(self, use_colors: bool = True, theme: AsciiTheme = DEFAULT_THEME): ...
    def render(self, scene: Scene) -> str:
        # Both queries filter with the SAME backend identity (§3.5): an
        # element hidden from ASCII affects neither layout nor paint.
        geom = scene.grid.ascii_geometry(scene.layout_needs(self.backend), scene.style_for(self.backend))
        canvas = CharCanvas(*geom.size())
        geom.paint_base(canvas)                          # frame / lattice / empties
        for element in scene.sorted_elements(self.backend):
            geom.paint(canvas, element)                  # single dispatch on kind
        geom.resolve_junctions(canvas)                   # box-char merging
        return canvas.to_string(self.theme, self.use_colors)
```

The default `AsciiTheme` renders GIVEN and DERIVED identically (golden fidelity); a theme *may* map provenance to emphasis (e.g. bold SGR for clues) as a later, purely-theme-level option.

### 5.2 The geometry protocol (per grid — all grid-specific character knowledge)

```python
# aspuzzle/rendering/ascii/geometry.py
@dataclass(frozen=True)
class LayoutNeeds:   # defined in scene.py; one name, no re-export
    edges: frozenset[Edge] = frozenset()       # ASCII-visible stroked edges
    vertices: frozenset[Vertex] = frozenset()  # ASCII-visible vertex marks
    label_margins: Mapping[str, int] = field(default_factory=dict)
        # direction → widest ASCII-visible label text; geometries derive
        # lane materialization/collapse from the edge and vertex sets

class AsciiGeometry(Protocol):
    """Constructed per render by Grid.ascii_geometry(needs, style);
    stateless afterward. Answers exactly one question per element kind:
    which canvas characters realize this element? Geometries never see
    elements the visibility filter removed (§3.5)."""
    def size(self) -> tuple[int, int]: ...
    def paint_base(self, canvas: CharCanvas) -> None: ...
    def paint(self, canvas: CharCanvas, element: SceneElement) -> None: ...
    def resolve_junctions(self, canvas: CharCanvas) -> None: ...
```

The shipped protocol is exactly these four methods — the renderer's whole
vocabulary. Building blocks the earlier sketch listed here (`content_span`,
`interior_spans` plural for multi-run hex/tri interiors, `vertex_pos`,
`path_glyph`, `label_span`) live as private methods of the concrete
rectangular geometry; the shared surface re-emerges with the
`AsciiGeometryBase` extraction when the hex geometry lands (§11), shaped by
two real implementations instead of one.

### 5.3 Rectangular geometry: one lane-collapsing engine

One layout engine serves every look. Edge lanes interleave cell rows/columns (vertices at lane intersections); a lane materializes only where something ASCII-visible uses it (a stroked edge, a vertex, the lattice, a dot) and otherwise collapses to zero height / gap width. The **all-collapsed degenerate case is the compact layout**: cell `(r, c)` → char `(r-1, (c-1)·(1+gap))` (gap 0 when packed, else 1), byte-for-byte reproducing the first pipeline's `join_char` output for Numberlink, Galaxies, Tents, Minesweeper, Hitori, etc. — goldens gate this; there is no mode branch. Note the visibility interaction: a scene *containing* `EdgeSegment`s that are all `SVG_ONLY` still renders compact in ASCII — this is the intended lever for solvers that prefer tight terminal output while giving SVG the full drawing (§7.6). Sudoku's classic look — thin grid, lines only at block boundaries and the frame — falls out of collapsing rather than special-cased `rows_per_box` arithmetic; Slitherlink keeps all lanes because its loop populates them.

**Junction resolution via direction flags.** Painting an `EdgeSegment` never chooses `─`/`│`/`┌` directly. The geometry stamps direction flags onto lattice positions: a horizontal edge marks its run `{e,w}` and contributes `e`/`w` flags to its two flanking vertex positions; the frame and block borders do the same. `resolve_junctions` converts each flagged position's accumulated `frozenset[str]` into a character via the box-drawing table (today's `line_characters` content, moved here, re-keyed by direction *sets*, extended with the double-line family `═║╔…` for HEAVY; mixed weights fall back to "heavy wins" initially). One mechanism produces `├ ┬ ┼ ┘` correctly for Sudoku boxes meeting the frame, a Slitherlink loop crossing lanes, and any combination of independent edge sources — replacing `_build_horizontal_line`'s hand-rolled cases.

**Fill continuity.** Painting records each cell's final background; after all elements paint, a resolve pass extends backgrounds across the characters between equal-fill neighbors (and the junction area where all four surrounding cells match), so filled regions read as solid blocks even when materialized lanes or gaps separate their cells. Edge runs stamp only their own cell's character; the gap between two cells is bridged only when both sides carry a stroked run in the same lane, so an isolated edge never claims a neighboring column.

**Margins for OutsideLabels.** The geometry reserves margin rows/columns on any side that `layout_needs` reports (ASCII-visible labels only). Mapping a line-of-sight direction to a side of the canvas is the geometry's business: `("s", index=c)` anchors above column `c`, `("e", index=r)` anchors left of row `r`. Multi-char top/bottom labels widen the column pitch so neighboring labels cannot collide, and the canvas extends so the last column's label fits; left/right labels reserve width-aware margins. The same solver call sites work on a hex geometry with different sides.

**CellPath** maps its direction set through the geometry's table (`{"e","s"}` → `┌`), preserving Numberlink's exact current look; an unknown set (hex directions on a rectangular geometry) raises at render time.

### 5.4 Hexagonal ASCII — geometry only, no new renderer

Flat-top hexes, the classic `__/  \__` tiling, in which **every geometric edge is exactly one shared character run** — the property that makes edge decoration work. Offset coordinates, odd columns shifted down half a cell. A 2×3 grid, cells numbered 1–6:

```
 __    __
/1 \__/3 \
\__/2 \__/
/4 \__/6 \
\__/5 \__/
   \__/
```

Layout formulas (scale 1, content width 2): cell `(r, c)` has `x0 = 3(c-1)`, `y_top = 2(r-1) + (0 if c odd else 1)`; `content_span = (y_top+1, x0+1, width 2)`. The six edges are concrete char runs: `n` = `__` at `(y_top, x0+1..x0+2)`; `nw` = `/` at `(y_top+1, x0)`; `ne` = `\` at `(y_top+1, x0+3)`; etc. The `\` right of cell 1 *is* the `\` upper-left of cell 2 — `grid.edge((1,1),"ne") == grid.edge((1,2),"nw")` maps to that one char, so an `EdgeSegment` restyles it (color; heavy variants best-effort). Direction vocabulary: `n, s, ne, nw, se, sw` (no e/w), matching what `HexGrid.direction_vectors` will declare — so `CellPath` directions, ASP predicates, and geometry agree. `path_glyph`: `{n,s}` → `|`, `{ne,sw}` → `/`, mixed pairs fall back to `*` — the fallback of last resort for solvers that declared no backend preference; a solver that cares marks its `PathRule` `SVG_ONLY` and supplies an `ASCII_ONLY` alternative instead (§3.5 point 3, worked example §7.6). Fills paint the 2-char interior; a `scale` knob widens cells (`/ 12 \`) for larger content. `OutsideLabel` margins follow the row stagger.

### 5.5 Triangular ASCII — deferred; exploratory sketch only

**Scope decision (July 2026): grids ship rectangular + hex first; triangular is deferred.** Hex fits the existing `Grid` machinery as-is (axial coordinates give one uniform vector per direction name, which is what the base `Direction`/`Orthogonal` derivations assume). Triangular breaks that assumption across the whole stack, not just rendering: an up-triangle's northern *cell* exists without being edge-adjacent, so the base `Orthogonal`/`OrthogonalDir`/`VertexSharing` cached predicates would derive wrong adjacencies and need parity-conditioned overrides; `add_vector_to_cell` and the `Line`/`LineOfSight` story need their own design pass. On the rendering side, triangular's known requirement is widening the topology vocabulary to per-cell signatures (an up-triangle's sides are w/e/s, a down-triangle's w/e/n — no constant list serves both, and corner names/reflections vary the same way); the shipped rect/hex surface deliberately keeps those cell-free (`corner_names` property, `corner_across(corner, direction)`, edge directions from `orthogonal_direction_names`) rather than carrying speculative generality. What follows is the exploratory sketch, kept as a starting point.

Alternating up/down triangles, orientation `up iff (r+c) even`, zigzag band layout. A 2×4 grid:

```
     ___     ___
/ 1 \ 2 / 3 \ 4 /
 ___     ___
\ 5 / 6 \ 7 / 8 \
     ___     ___
```

Content rows at `y = 2r-1` (center char at `x = 4c-2`); diagonal edges are single shared chars at `(2r-1, 4c)` (`\` or `/` by orientation); horizontal edges are 3-char `___` runs on interleaved edge rows — an up cell's south edge coincides with its lower neighbor's north edge: one run, one canonical `Edge`. The side inventory is orientation-dependent (up: w/e/s; down: w/e/n) — which is exactly why triangular needs the per-cell signature widening noted above. Vertices sit at edge-row/diagonal intersections.

Both geometries are pure Python with O(1) formulas per element. **No solver and no renderer code changes for either grid** — that is the payoff of the split, and a conformance test suite (render a synthetic scene containing every element kind through every registered geometry) keeps geometries honest.

### 5.6 Orientation variants — sibling subclasses, not new machinery

Both tessellations come in two orientations, and the sections above deliberately specify only one of each: hexes are **flat-top** (§5.4; the other variety is pointy-top) and triangles are **up/down** (§5.5; the other is left/right, with vertical bases). Each tessellation gets an abstract base class carrying everything orientation-independent, with **two concrete sibling subclasses** fixing the orientation — `HexGrid` → `FlatTopHexGrid` / `PointyTopHexGrid`, `TriangularGrid` → the up/down and left/right varieties. (Subclassing also fits the config loader: `"grid_type": "FlatTopHexGrid"` resolves by class name exactly like `"RectangularGrid"` does today, and solvers can declare `supported_grid_types = (HexGrid,)` to accept either orientation.) Everything orientation touches is per-class vocabulary the subclass overrides:

- **Direction names**: flat-top hex has `n/s` plus four diagonals (no `e/w`); pointy-top has `e/w` plus four diagonals (no `n/s`). Up/down triangles have horizontal bases (`s` or `n` edges); left/right have vertical bases (`w` or `e` edges). These flow from `direction_vectors`/`orthogonal_direction_names` as usual — and the ASP program the grid emits uses the same names, so solver rules and render locations stay in one vocabulary per instance.
- **Corner names and `corner_across`**: per-cell and per-instance already; each orientation states its own reflection table.
- **ASCII/SVG geometry**: each orientation is its own layout arithmetic (a left/right triangle band zigzags vertically; pointy-top hex is a different character tiling), returned by the subclass's geometry factory.

The scene model, canonicalization walk, renderers, and conformance suites are orientation-blind; each concrete subclass joins `ALL_GRID_FACTORIES` and inherits the whole test suite. Which orientations ship first is a per-tessellation decision at implementation time — nothing in the framework prefers one.

---

## 6. The SVG backend (later; contracts frozen now)

```python
# aspuzzle/rendering/svg/geometry.py
@dataclass(frozen=True)
class Point: x: float; y: float

class SvgGeometry(Protocol):
    # Unit-cell coordinates: one cell spans one unit; the renderer scales
    # by cell_size. Methods are total over in-grid inputs.
    def cell_polygon(self, cell: GridCell) -> Sequence[Point]: ...
    def cell_center(self, cell: GridCell) -> Point: ...
    def edge_endpoints(self, edge: Edge) -> tuple[Point, Point]: ...
    def vertex_point(self, vertex: Vertex) -> Point: ...
    def outside_anchor(self, direction: str, index: int, offset: int) -> tuple[Point, TextAnchor]: ...
        # amended at contract-freeze time: the anchor point alone cannot
        # say which way the text extends; TextAnchor ("start"|"middle"|
        # "end") travels with it

# aspuzzle/rendering/svg/renderer.py
class SvgRenderer:
    backend: Final = Backend.SVG
    def __init__(self, theme: SvgTheme = DEFAULT_SVG_THEME, cell_size: float = 64): ...
    def render(self, scene: Scene) -> str: ...   # iterates scene.sorted_elements(Backend.SVG)
```

Decisions settled at implementation (July 2026), superseding the two
recorded at contract-freeze time:

- **Out-of-drawable elements** — the pre-filter, as recorded: the renderer
  skips any element whose referenced cell has
  `grid.cell_at(grid.cell_coords(cell)) is None` (solution dicts genuinely
  carry such cells, e.g. Slitherlink's `outside` atoms), keeping geometry
  methods total over in-grid inputs. `cell_at` joined the `RenderGrid`
  protocol for this (already implemented on `Grid`).
- **`bounds`** — the fold, as §6.0's auto-extent note favored: the method
  left the protocol; the renderer folds the viewBox from every point it
  draws plus a quarter-cell margin, with an estimated text extent folded
  per label so start/end-anchored outside labels never clip. Geometries
  are pure point mappings in **unit-cell coordinates**, scaled by the
  renderer's `cell_size` — which defaults to 64 (not the sketch's 32) so
  the dbpuzzles constants (§6.0) transfer verbatim.
- **Substrate interpretation** (new at implementation) — `Lattice`,
  `frame_weight`, `packed`, and `empty` are character-grid vocabulary the
  SVG backend ignores; the print substrate is three `SceneStyle` bools:
  `hairline` (full hairline cell lattice, default True), `vertex_dots`
  (shared with ASCII), and `heavy_frame` (outer boundary drawn heavier
  than the lattice, default True — not unconditional, because Slitherlink's
  traditional look is a bare dot grid with *no* frame). The defaults give
  every existing solver a published-puzzle SVG with zero edits; a puzzle
  wanting a different SVG substrate without touching its character render
  overrides via `backend_styles` (Slitherlink: `hairline=False,
  vertex_dots=True, heavy_frame=False`).
- **Out-of-range `OutsideLabel` indices** — resolved at the common-core
  rework: `outside_anchor` returns None past `line_limit`, matching the
  character geometries' silent skip, so a stray label can no longer
  inflate the viewBox. (Originally recorded as a latent divergence when
  the skip had no grid-agnostic home; `GeometryBase.line_limit` gave it
  one.)
- **Output framing** — every render begins with
  `<!-- Generated by ASPuzzle https://github.com/jolyonb/aspuzzle -->`;
  one generated `<style>` block carries the theme's font/halo/substrate
  styling (typed Python fields, honoring §6.0's no-CSS-dialect
  anti-lesson) while per-element colors are inline attributes; glyph text
  sizes by rendered length (1/2/3+ chars), the dbpuzzles convention.

Element mapping is mechanical because the scene is already geometric: `CellFill` → `<polygon fill=…>`; `CellGlyph` → centered `<text>` (full text — no letter compaction needed); `EdgeSegment` → `<line>` (HEAVY → larger stroke-width); `CellPath` → polyline from edge midpoints through the cell center (*exact* on hex/tri, where ASCII is best-effort — same scene, better output); `CellLink` → connector line + glyphs; `CellMark`/`EdgeMark`/`VertexMark` → `<text>` for glyph marks, else a `<circle>` — the theme's dot, or with `ring=True` a halo-filled open ring (Galaxies centers); `OutsideLabel` → anchored `<text>`. Layers become ordered `<g data-layer=…>` groups; every element additionally carries `data-provenance="given"|"derived"`, and `SvgTheme` may style the classes differently — the default distinguishes them **by color alone**: uncolored givens render black, uncolored solution values in the theme's value blue, with zero solver involvement. (A bold-givens variant was tried at the polish pass and rejected as too heavy.) `SvgTheme` maps `PaletteColor` → curated hex, `Rgb` verbatim. Per grid, the geometry is ~30 lines (unit squares; six-corner polygons from offset coords; three-corner triangles).

SVG is the **full-fidelity backend**: it renders every element kind exactly, so the visibility mechanism is expected to *hide from ASCII*, not from SVG — `SVG_ONLY` marks "too rich for the terminal" content, `ASCII_ONLY` marks its simplified stand-in, and a scene's SVG output is the superset view by construction whenever solvers follow that convention.

Adding SVG is: two renderer/theme files, `svg_geometry()` per grid, `--svg out.svg` in `solveit.py`. **Zero solver edits** — requirement 2 discharged structurally, and enforced by the import-boundary guardrail test (scene/spec import nothing from `ascii/`). (`Backend` names backends but carries no backend internals — it lives in the leaf module `backend.py` and imports nothing.)

### 6.0 Implementation notes salvaged from dbpuzzles (surveyed July 2026)

`~/gitrepos/dbpuzzles` (`solvers/puzzledraw/`, the 2023 f-string SVG renderer; Jinja there generated clingo, not SVG) was surveyed for salvage. Adopt when building this backend:

- **Auto-extent viewBox**: bounds from drawn content plus ¼-cell padding (`base.py:73-81`, `rectangulargrid.py:70-83`) — outside labels expand the canvas for free; matches `SvgGeometry.bounds(scene)` computed over `visible(Backend.SVG)`.
- **Scale and centering constants**: 64 px/cell; cell centers at `(col−0.5, row−0.5)·cell`; text via `text-anchor:middle; dominant-baseline:middle`, font size by glyph length (3/2/1.5 rem) with a small hand-tuned baseline nudge (`styles.css:89-111`).
- **Stroke settings**: `vector-effect:non-scaling-stroke` + `shape-rendering:geometricprecision` for hairline grids; `stroke-linejoin:bevel` for lattice lines, `round` for feature paths (`styles.css:7-38`).
- **Glyph halo**: `paint-order="stroke fill"` with a 2px white stroke so text reads over fills (surviving only in the committed `solvers/test.svg:70`).
- **Theme seeds**: SudokuPad-derived semantic colors (`--puzzle-given:#000`, `--puzzle-value:#1d6ae5`) and its 10-color categorical palette (`old_solvers/puzzledraw/httptest/style.css:500-537`, skip the negative-rgba row).
- **Dev loop**: recreate the livereload SVG preview harness (`old_solvers/puzzledraw/httptest/serve.py`).
- **Hex pointer**: dbpuzzles' own note recommends Red Blob Games doubled coordinates — weigh against axial when `HexGrid` is designed (both give uniform integer vectors).
- **Anti-lessons**: escape or type-build all markup (dbpuzzles interpolated raw text into f-string SVG); no homegrown CSS dialects; a renderer not driven by the real pipeline drifts (their committed sample SVG was richer than the code that "produced" it). Its unbuilt `regions.py` boundary tracer is unnecessary here — `RegionBoundaryRule` + unordered canonical `EdgeSegment`s already cover it.

### 6.1 The sheet backend — TSV for spreadsheet solving (mystery hunts)

A third consumer of the same Scene: plain tab-separated text that pastes into Google Sheets so a hunt team can annotate, formula, and co-solve on top of the grid. One grid cell = one spreadsheet cell; columns are `\t`, rows are `\n`; no ANSI, ever (a paste carries no formatting).

```python
# aspuzzle/rendering/sheet/geometry.py
class SheetGeometry(Protocol):
    """Maps abstract locations to (sheet_row, sheet_col) cell coordinates.
    Constructed per render by Grid.sheet_geometry(needs); like AsciiGeometry
    it consumes LayoutNeeds so label margins reserve real sheet rows/cols."""
    def size(self) -> tuple[int, int]: ...
    def cell_pos(self, cell: GridCell) -> tuple[int, int]: ...
    def label_pos(self, direction: str, index: int, offset: int) -> tuple[int, int]: ...

# aspuzzle/rendering/sheet/renderer.py
class SheetRenderer:
    backend: Final = Backend.SHEET
    def __init__(self, empty: str = ""): ...      # untouched cells: "" beats "." in a sheet
    def render(self, scene: Scene) -> str: ...    # iterates scene.sorted_elements(Backend.SHEET)
```

Element mapping (the renderer's documented contract, per visibility rule 5):

- `CellGlyph` → the cell's text, via `glyph.for_backend(Backend.SHEET)`. **No width limit** — a sheet cell holds arbitrary text, and `glyph_for_value` already carries the literal number as its sheet variant for values ≥ 10 (§3.2), so sheets show `10` where character grids show `A`, with no extra rule. Later elements at the same position overwrite (paint order degenerates to last-writer-wins per cell).
- `CellPath` → the geometry's path glyph as cell text (box-drawing characters paste fine as text); `CellLink` → its glyph in both cells; `OutsideLabel` → text in a reserved margin row/column — outside clues are a *natural* fit for sheets, they become real cells you can reference in formulas.
- `CellFill`, `EdgeSegment`, `VertexMark`, `EdgeMark`, `CellMark` with glyph=None, colors, `EdgeWeight` → **documented no-ops** (plain-text paste cannot carry them; a glyph-bearing `CellMark` writes its glyph like `CellGlyph`). This is contract, not silent skipping: the backend's stated fidelity is "textual content only". Solvers that want region structure visible in sheets emit `SHEET_ONLY` glyph alternatives (e.g. a `GlyphRule` writing region ids).
- `Provenance` → ignored (no styling channel), retained in the scene as always.
- `SceneStyle.empty` → ignored by design: untouched cells are the renderer's `empty` string (`""` beats `"."` in a sheet). This is the one place a renderer overrides a style rather than honoring it at the choke point — stated here so rule 5's no-silent-skipping narrative stays intact.
- **Structural characters**: a glyph's sheet text containing `\t` or `\n` would corrupt the paste's row/column structure. The renderer rejects them with a precise error (space-substitution would silently alter content). Leading `=` (spreadsheet formula injection) is deliberately allowed — hunt teams may want live formulas in the paste.

Geometry per grid is a few lines: rectangular is the identity mapping (plus margins); hex uses its offset coordinates directly — the row stagger that costs half-cell shifts in ASCII is simply *dropped* in sheets, where adjacency is implied by the offset convention; triangular maps its `(row, col)` bands the same way. Coarser than ASCII, and exactly what a hunt spreadsheet wants.

`solveit.py` later grows `--tsv` (print to stdout for piping to `pbcopy`). Adding the backend is: the enum member, the two small files, `sheet_geometry()` per grid, per-backend goldens under `tests/goldens/tsv/` — zero solver edits, same as SVG.

### 7.1 Tents (simple table + previously-invisible clue counts)

*Amended at the Step 7 port:* `TieDestination` was flipped to shown — the tree-to-tent assignment is solution content, and an `SVG_ONLY` `LinkRule` draws it as a connector in SVG. A deliberate, narrow exception to the "no ASP output changes" non-goal, recorded here: expected-solutions data was regenerated (uniqueness unchanged — solutions were already unique including hidden scaffolding).

```python
# BEFORE: untyped dict; row/column clues silently unrendered
def get_render_config(self) -> dict[str, Any]:
    return {
        "puzzle_symbols": {"T": RenderSymbol("T", Color.GREEN)},
        "predicates": {"tent": {"symbol": "A", "color": Color.YELLOW}},
    }

# AFTER: typed; counts render in the margins for the first time
def get_render_spec(self) -> RenderSpec:
    return RenderSpec(
        clues={"T": CellStyle(glyph=Glyph("T"), color=PaletteColor.GREEN)},
        # 'A' on the character grid (emoji are double-width in terminals),
        # the real thing in SVG — one rule, per-backend glyph variants
        atoms=[GlyphRule("tent", glyph=Glyph("A", svg="⛺"), color=PaletteColor.YELLOW)],
        labels=[LineLabels(d, self.config[f"{self.grid.line_direction_descriptions[d]}_clues"])
                for d in self.grid.line_direction_names],
    )
```

### 7.2 Sudoku (boxes become grid-agnostic border edges; fully declarative; previews complete)

```python
# BEFORE: draw_box / rows_per_box / cols_per_box magic keys; letter logic
#         duplicated; clue cells turn green in solved renders
def get_render_spec(self) -> RenderSpec:
    br, bc = self.block_rows, self.block_cols
    assert br is not None and bc is not None
    return RenderSpec(
        clues={v: CellStyle(glyph=glyph_for_value(v), color=PaletteColor.BLUE)
               for v in range(1, self.grid.rows + 1)},
        atoms=[
            GlyphRule("number", value_field="value", color=PaletteColor.GREEN),
            RegionBorderRule(by=lambda cell: ((cell["row"].value - 1) // br,
                                              (cell["col"].value - 1) // bc)),
        ],
        style=SceneStyle(lattice=Lattice.FRAME),
    )
```

No `build_scene` override needed: `RegionBorderRule(by=…)` runs without a solution, so **the preview and the solved render are the same pipeline with the same boxes** — dual rendering as designed, not as accident. In a solved render the clue digits carry `Provenance.GIVEN` and the solution digits `Provenance.DERIVED`; the SVG theme bolds the former. The same rule renders jigsaw-Sudoku cages and hex-region variants with zero new machinery — `rows_per_box` never could. Lane collapsing + junction resolution reproduce today's `├ ┼ ┤` output.

### 7.3 Numberlink (paths, minus the base-class special case)

*Amended at the SVG milestone:* per-atom colorers landed
(`PathRule.color` and `LinkRule.color` accept a `Colorer`), with
pair-colored Numberlink as the showcase. `CellDirections` gained `sym`
(the pair identity `PropagatedSymbol` carried but hid) and a new shown
`EndpointDirection(loc, direction, sym)` draws each path into its
endpoint clues — single-direction stubs the clue glyph paints over in
character grids. `symbol_colorer` shares `symbol_clues`' first-appearance
ordering, so paths match their clue colors exactly in every backend.
Expected-solutions data was regenerated (uniqueness unchanged — the new
atoms are deterministic functions of the existing solution). The AFTER
snippet below predates the amendment.

```python
# BEFORE: "cell_directions": {"loop_directions": True, "color": Color.CYAN}
#         with the glyph lookup living in Solver._preprocess_predicates
def get_render_spec(self) -> RenderSpec:
    clue_syms: list[int | str] = []
    for _loc, sym in self.grid_data:
        if sym not in clue_syms:
            clue_syms.append(sym)
    return RenderSpec(
        clues={s: CellStyle(glyph=Glyph(str(s)), color=CLUE_PALETTE[i % len(CLUE_PALETTE)])
               for i, s in enumerate(clue_syms)},
        atoms=[PathRule("cell_directions", color=PaletteColor.CYAN)],
        style=SceneStyle(packed=True),
    )
```

The solver states the semantic fact ("a path passes through this cell via dir1/dir2"); glyph choice lives in each grid's geometry — box chars on rectangular, `/|\` best-effort on hex, true polylines in SVG. A hex Numberlink that finds the best-effort glyphs too noisy chooses per backend instead (the §3.5 pair idiom):

```python
atoms=[PathRule("cell_directions", color=PaletteColor.CYAN, backends=SVG_ONLY),
       GlyphRule("cell_directions", glyph=Glyph("+"), color=PaletteColor.CYAN,
                 backends=ASCII_ONLY)]   # simplified ASCII stand-in
```

### 7.4 Galaxies (region coloring without side channels)

*Amended at the SVG milestone:* the clue table's `o ^ v < > / \` styles
are `ASCII_ONLY` — they are the character-art *encoding* of the centers,
not the centers. An `SVG_ONLY` `CustomRule` over the (hidden, so
atom-less) `Center` predicate emits GIVEN ring marks at the true
geometric positions parsed from the config: `CellMark`, `EdgeMark`, or
`VertexMark` per flanking-pair shape — the published dot-and-ring look.
The character render is unchanged.

```python
# BEFORE: _preprocess_for_rendering stashes self._region_colors; a closure
#         reads it with a "shouldn't be reached" fallback — three
#         cooperating pieces. AFTER: one rule; the four-coloring runs
#         inside build_scene. _preprocess_for_rendering and _region_colors
#         are deleted (also from Stitches and Starbattle).
def get_render_spec(self) -> RenderSpec:
    center = CellStyle  # color=None → terminal default (was Color.RESET)
    # (no "." clue entry: parse_grid drops "." as empty, so it can never
    # match a clue key — empty-cell dots come from SceneStyle.empty)
    return RenderSpec(
        clues={"o": center(glyph=Glyph("o")), "^": center(glyph=Glyph("^")),
               "v": center(glyph=Glyph("v")), "<": center(glyph=Glyph("<")),
               ">": center(glyph=Glyph(">")),
               1: center(glyph=Glyph("/")), 2: center(glyph=Glyph("\\")),
               3: center(glyph=Glyph("\\")), 4: center(glyph=Glyph("/"))},
        atoms=[RegionFillRule(FromPredicate("galaxy"),
                              palette=(PaletteColor.YELLOW, PaletteColor.BRIGHT_BLUE,
                                       PaletteColor.GREEN, PaletteColor.RED))],
        style=SceneStyle(packed=True),
    )
```

`regioncolor.py` colors deterministically in pure Python — no solver involved (see §9 and the plan's Step 6 entry).

### 7.5 Skyscrapers (edge clues rendered for the first time)

```python
def get_render_spec(self) -> RenderSpec:
    cfg, n = self.config, self.grid.rows
    clue = PaletteColor.BRIGHT_WHITE
    return RenderSpec(
        clues={v: CellStyle(glyph=glyph_for_value(v), color=PaletteColor.GREEN)
               for v in range(1, n + 1)},
        atoms=[GlyphRule("height", value_field="value", color=PaletteColor.BRIGHT_BLUE)],
        style=SceneStyle(lattice=Lattice.FRAME),
        labels=[  # the exact direction convention the Clue facts already use
            LineLabels("s", cfg["top_clues"], color=clue),      # top: looking south
            LineLabels("n", cfg["bottom_clues"], color=clue),   # bottom: looking north
            LineLabels("e", cfg["left_clues"], color=clue),     # left: looking east
            LineLabels("w", cfg["right_clues"], color=clue),
        ],
    )
```

Rendered (4×4, margins allocated by the geometry from `layout_needs`):

```
    2 1 2 2
  ┌─────────┐
2 │ 3 4 1 2 │ 2
1 │ 4 3 2 1 │ 3
2 │ 2 1 4 3 │ 1
3 │ 1 2 3 4 │ 2
  └─────────┘
    2 3 2 1
```

### 7.6 Slitherlink (fills kept, real loop added — and per-backend selection worked through)

The default spec renders the true loop on **both** backends (expanded ASCII layout auto-selected):

```python
def get_render_spec(self) -> RenderSpec:
    return RenderSpec(
        clues={n: CellStyle(glyph=Glyph(str(n)), color=PaletteColor.BRIGHT_BLUE)
               for n in range(4)}
              | {"S": CellStyle(glyph=Glyph("S"), color=PaletteColor.BRIGHT_WHITE),
                 "W": CellStyle(glyph=Glyph("W"), color=PaletteColor.BRIGHT_RED)},
        atoms=[
            FillRule("inside", fill=PaletteColor.BRIGHT_GREEN),
            RegionBoundaryRule("inside", color=PaletteColor.BRIGHT_YELLOW),
        ],
        style=SceneStyle(packed=True),
    )
```

`RegionBoundaryRule` computes the loop in Python from the `inside` atoms via `grid.neighbor`/`grid.edge` — off-grid and outside-border cells count as non-members, so the loop closes at the grid boundary. Output:

```
              ┌───┐
  · 3 ┌───────┘ 2 │      loop chars from junction resolution,
  ┌───┘ ·   1   · │      inside cells green-filled beneath
  │ 2   ·   2 ┌───┘
  └───────────┘
```

**Reduced ASCII, full SVG — Requirement A worked end-to-end.** The expanded layout doubles the terminal footprint. A solver that prefers today's compact terminal output while SVG gets the real drawing changes exactly one keyword:

```python
        atoms=[
            FillRule("inside", fill=PaletteColor.BRIGHT_GREEN),          # both backends
            RegionBoundaryRule("inside", color=PaletteColor.BRIGHT_YELLOW,
                               backends=SVG_ONLY),                       # loop: SVG only
        ],
```

Semantics traced through the machinery: `build_scene` still emits every `EdgeSegment` into the one Scene. `AsciiRenderer` calls `scene.layout_needs(Backend.ASCII)`, which sees **no** ASCII-visible edge elements → `edges=False` → the rectangular geometry chooses the **compact layout**, and the ASCII output is byte-identical to today's fill-only render (clue digits over green inside-fills, one char per cell). `SvgRenderer` calls `scene.sorted_elements(Backend.SVG)`, sees the full set, and draws polygon fills *plus* the exact loop as `<line>` strokes. One spec, one scene, two faithful outputs — no geometry fallback involved, because the solver's explicit choice removed the elements from ASCII's view before the geometry ever saw them.

(An ASP-derived `LoopEdge(loc, direction)` + `EdgeRule` remains available for puzzles whose edges are genuinely solver output.) The identical spec on a future `HexGrid` draws the loop along hex seams — in both variants.

### 7.7 Stitches (pairs + region fills + counts, all declarative)

```python
# BEFORE: mutable color_index[0] closure (order-dependent colors) +
#         _preprocess_config region-color stash + invisible line counts
def get_render_spec(self) -> RenderSpec:
    return RenderSpec(
        atoms=[
            RegionFillRule(FromClues()),          # input regions, four-colored
            LinkRule("stitch", glyph=Glyph("X"),
                     palette=(PaletteColor.BRIGHT_MAGENTA, PaletteColor.BRIGHT_CYAN,
                              PaletteColor.BRIGHT_YELLOW, PaletteColor.BRIGHT_GREEN)),
        ],
        labels=[LineLabels(d, self.config[f"{self.grid.line_direction_descriptions[d]}_clues"])
                for d in self.grid.line_direction_names],
        style=SceneStyle(packed=True),
    )
```

`RegionFillRule(FromClues())` runs from grid data, so the *preview* shows the four-colored regions and the count labels before any solving — dual rendering again. Starbattle drops its `_preprocess_config`/`_region_colors` the same way via `RegionFillRule(FromClues())` + `GlyphRule("star", glyph=Glyph("★"), color=PaletteColor.BRIGHT_YELLOW)`.

### 7.8 Fillomino and Hitori (closures → typed one-liners)

```python
# Fillomino: the custom_renderer lambda becomes a typed Colorer
atoms=[GlyphRule("number", value_field="size", color=PaletteColor.BRIGHT_WHITE,
                 fill=lambda pred: REGION_BG[(pred["size"].value - 1) % len(REGION_BG)])]

# Hitori: symbol=None background overlays become structural fills
atoms=[FillRule("black", fill=PaletteColor.WHITE)]
```

---

## 8. Coverage: everything renderable today, plus the gaps

| Today | New model |
|---|---|
| `puzzle_symbols` value → `RenderSymbol` | `RenderSpec.clues: {value: CellStyle}` |
| predicate `symbol`/`color`/`background` | `GlyphRule` / `FillRule` |
| `value` field indirection; >9→letters (clues only) | `GlyphRule(value_field=…)` + `glyph_for_value` (uniform) |
| `priority` ints | `Layer` IntEnum + insertion order (any int accepted) |
| `symbol: None` bg-only overlay | `CellFill` (structural) |
| `loop_directions`/`dir1_field`/`dir2_field` | `PathRule` → `CellPath` |
| Stitches paired-cell closure (mutable state) | `LinkRule` → `CellLink` (deterministic) |
| Fillomino/Galaxies `custom_renderer` closures | typed `Colorer` / `RegionFillRule` |
| region_coloring + `_region_colors` stash (Galaxies, Stitches, Starbattle) | `RegionFillRule(FromPredicate|FromClues)` |
| `draw_box`/`rows_per_box`/`cols_per_box` | `Lattice.FRAME` + `RegionBorderRule(by=…)` |
| `join_char` | `SceneStyle.packed` |
| `"."` default dot via `puzzle_symbols` | `SceneStyle.empty` |
| `grid.line_characters` string-concat keys | geometry table keyed by `frozenset[str]` + junction flags |
| preview + solved renders (implicit, incomplete previews) | one pipeline via `build_scene(solution)`; data-driven rules make previews complete; `Provenance` GIVEN/DERIVED typed |
| *(gap)* outside clues never rendered | `OutsideLabel` + `LineLabels` + geometry margins |
| *(gap)* Slitherlink loop invisible | `RegionBoundaryRule` / `EdgeRule` → `EdgeSegment` |
| *(gap)* no edge/vertex notion | canonical `Edge`/`Vertex` + `EdgeSegment`/`VertexMark` |
| *(gap)* no per-backend element choice | `backends: BackendSet` on elements/rules; `Scene.sorted_elements(backend)`/`layout_needs(backend)` filter at one choke point |
| *(gap)* no spreadsheet-paste output for hunt solving | `Backend.SHEET` + `SheetRenderer`/`SheetGeometry` (§6.1): TSV, one grid cell per sheet cell, labels in margin cells |
| *(bug)* `use_colors` not threaded | threaded through `render_puzzle` → `AsciiRenderer` |

---

## 9. Testability — an acceptance criterion, per layer

Every layer must be pinnable by unit tests **in isolation**: the scene/model as pure data with no solver and no terminal; backends against exact expected output from small synthetic scenes; per-grid geometry contracts with no solver; solver specs as pure data with no solving. The seams above were shaped for this — the two adjustments the criterion forced are noted at the end. One concrete test per layer:

**Scene/model (pure data — no solver, no renderer, no ANSI).** Grids need only a `Puzzle()` (module registration), never grounding or solving:

```python
def test_scene_sorting_and_backend_filtering() -> None:
    grid = RectangularGrid(Puzzle(), rows=2, cols=2)
    scene = Scene(grid)
    glyph = CellGlyph(grid.Cell(1, 1), Glyph("5"), provenance=Provenance.GIVEN)
    fill = CellFill(grid.Cell(1, 1), PaletteColor.GREEN)
    loop = EdgeSegment(grid.edge(grid.Cell(1, 1), "e"), backends=SVG_ONLY)
    scene.add(glyph, fill, loop)

    assert scene.sorted_elements(Backend.ASCII) == [fill, glyph]   # FILL < GLYPH; loop hidden
    assert scene.sorted_elements(Backend.SVG) == [fill, loop, glyph]
    assert not scene.layout_needs(Backend.ASCII).edges             # SVG-only edge ⇒ compact layout
```

**ASCII backend (synthetic scene → golden string).** `AsciiRenderer(use_colors=False)` pins characters; a second assertion with `use_colors=True` and an injected two-entry `AsciiTheme` pins SGR placement without depending on the full default palette:

```python
def test_ascii_fill_under_glyph_golden() -> None:
    grid = RectangularGrid(Puzzle(), rows=2, cols=2)
    scene = Scene(grid)
    scene.add(CellFill(grid.Cell(1, 1), PaletteColor.GREEN),
              CellGlyph(grid.Cell(1, 1), Glyph("5")))
    assert AsciiRenderer(use_colors=False).render(scene) == "5 .\n. ."
```

**Per-grid geometry contract (no solver; shared conformance suite).** Pure-Python invariants, plus one grounding-backed diff test per grid class keeping `neighbor()` honest against the ASP facts:

```python
@pytest.mark.parametrize("grid_factory", ALL_GRID_FACTORIES)
def test_edge_canonicalization(grid_factory: Callable[[], Grid]) -> None:
    grid = grid_factory()
    for cell in grid.all_cells():
        for d in grid.orthogonal_direction_names:
            n = grid.neighbor(cell, d)
            if n is not None:
                assert grid.edge(cell, d) == grid.edge(n, grid.opposite_direction(d))
```

The suite also renders one synthetic scene containing *every* element kind through every registered `AsciiGeometry` (asserting no crash and stable goldens), which is what keeps a future hex geometry honest before any solver uses it.

**Solver specs (pure data — construction, no solving).** Instantiating a `Solver` parses config and grid data but grounds nothing; `get_render_spec()` returns inspectable frozen dataclasses, and `build_scene` accepts a hand-written solution dict — so solved-state rendering is testable without clingo in the loop:

```python
def test_sudoku_spec_and_preview_scene() -> None:
    solver = Solver.from_config(load_puzzle_config("sudoku"))
    spec = solver.get_render_spec()
    assert any(isinstance(rule, RegionBorderRule) for rule in spec.atoms)

    preview = solver.build_scene(solution=None)          # no solving
    ascii_els = preview.sorted_elements(Backend.ASCII)
    assert any(isinstance(e, EdgeSegment) for e in ascii_els)        # boxes in preview
    assert all(e.provenance is Provenance.GIVEN for e in ascii_els
               if isinstance(e, CellGlyph))                          # preview = clues only
```

**SVG backend (later, same pattern).** Synthetic scene → assert exact fragments: `'<line' in out`, `'data-provenance="given"' in out`, and a golden file per conformance scene.

Two seams were adjusted to satisfy the criterion: (1) **region coloring must be deterministic** — and clingo's first model, while stable for a fixed binary and config, is not contractually stable across versions or platforms, so `regioncolor.py` is pure Python: first-fit backtracking over a fixed ordering. Identical everywhere, forever; `RegionFillRule` goldens and its unit tests (determinism across runs and insertion orders) are stable, and rendering needs no solver at all. (2) **`AsciiTheme` is constructor-injected** into `AsciiRenderer` (not a module global read at call time), so color-placement tests can use minimal themes. Everything else — grids constructible from a bare `Puzzle()`, `build_scene` as a free function, `Scene` as frozen-dataclass data — already satisfies it. Each migration wave (§10) lands with its layer's tests; a wave without them does not merge.

---

## 10. Migration plan

1. **Land the model**: `aspuzzle/rendering/` (color/glyph/scene/spec + ASCII canvas/theme/renderer) and `RectangularAsciiGeometry` (compact + expanded/lanes) alongside the old path; add `Grid.neighbor/corner_names/corner_across/edge/vertex/all_cells/cell_coords/ascii_geometry`. Land the §9 unit-test suites for scene, canvas/renderer, and rectangular geometry in the same PR (acceptance criterion), including the neighbor-vs-ASP conformance test (ground a small grid, diff `Orthogonal` atoms against `neighbor()`) and the backend-filtering tests (SVG-only edge ⇒ compact layout; hidden label ⇒ no margin).
2. **Golden capture**: record every solver's current `render_puzzle` output (colored and plain) for all `puzzles/*.json` — *both* the preview (`solution=None`) and solved renders, since both flow through the new pipeline. Compact-mode solvers must match byte-for-byte; Sudoku's boxed output may differ only in reviewed junction chars; the new label margins, Slitherlink loop, and uniform >9 letters are intentional, reviewed deltas. Goldens are per-backend from the start (ASCII now; SVG goldens join when it lands). Solution *validation* compares predicate atoms, not rendered text — it cannot break.
3. **Port solvers in three waves**: pure tables (Minesweeper, Tents, Hitori, Cave, Nurikabe, Skyscrapers, Sudoku); rule-based (Numberlink, Slitherlink, Fillomino, Starbattle ×2); region/link (Galaxies, Stitches). Every config is the same size or smaller, statically typed, and three previously-invisible clue families become visible. Each wave adds spec-as-data tests (§9) for its solvers.
4. **Delete** `aspuzzle/grids/rendering.py`, `Grid.render_ascii`, `Grid.line_characters`, `RectangularGrid`'s canvas code, `Solver.get_render_config`/`_preprocess_puzzle_symbols`/`_preprocess_predicates`/`_preprocess_for_rendering`; re-point `region_coloring` to `ColorSpec` and make it deterministic (§9). No dual-path shim: single-author repo, all consumers in-tree, one migration PR per wave.
5. **Hex/tri geometries and the SVG backend** land later as pure additions (grid classes + geometry objects; renderer + themes), each with its conformance-suite membership and golden fragments on day one. Port one solver (Slitherlink or Minesweeper) to a hex instance as the proof of grid-agnosticism — Slitherlink exercises both the shared-edge property and, via §7.6, per-backend selection on a non-rectangular grid.

---

## 11. Risks and open questions

- **`finish()` re-seam — deferred to hex time.** The ASCII geometry's
  `finish(canvas, junctions, cell_fills)` runs run-bridging, fill
  continuity, and junction resolution — none of which are rectangular
  facts; only their inputs are. The deeper cut moves those loops into
  `AsciiPainter` behind protocol primitives (`junction_char(flags,
  heavy)`, lane anchors) and rekeys `cell_fills` by `GridCell` with
  `grid.neighbor` instead of `(row, col+1)` arithmetic. Deferred for the
  same reason `RectangularGeometryBase` was extracted only once two
  backends existed: with one ASCII geometry there is no second
  implementation to check the abstraction against. Do it when
  `HexAsciiGeometry` lands.
- **`CommonGeometry`/`GeometryBase` home + `paint_element` exhaustiveness
  — paired follow-up.** `CommonGeometry` is declared in `painter.py`, so
  geometry modules import the painter for their own contract; it and
  `GeometryBase` belong in one shared `rendering/geometry.py`. Fold in
  `assert_never` on `paint_element`'s dispatch at the same time — both
  are about the shared contract's shape, and the move is an import-graph
  change that deserves its own commit.
  **Trigger: before the sheet renderer lands** — `SheetGeometry` already
  exists and deliberately does not inherit `CommonGeometry`; the sheet
  backend is the next party that must decide its relationship to the
  shared contract, so the contract must be in its own home by then.
- **Accepted cosmetic debt, ride along when the file is next touched**
  (recorded so the drops are deliberate, not forgotten): the
  stringly-typed `"h"|"v"` orientation in `RectangularGeometryBase`
  (a `Literal` alias); the `GeometryBase[GridT]` generic arguably
  redundant next to leaf-level `grid:` annotations; `CommonGeometry`'s
  current placement in `painter.py` (covered by the entry above); the
  ring-has-no-character-form rationale comment lost from the ASCII mark
  path during the AsciiPainter reshape (the SVG `_mark` kept its ring
  handling and rationale); `AsciiPainter` sharing `ascii/renderer.py`
  with `AsciiRenderer` while `SvgPainter` shares `svg/renderer.py` —
  fine or a split, decide when either file next grows; `mark_char`
  public only as a move artifact; `VERTEX_DOT` housed in the protocol
  module `ascii/geometry.py`.

- **ASCII junction fidelity.** The flag-accumulation algorithm must reproduce current Sudoku output; goldens gate it. Mixed NORMAL/HEAVY junctions ship with "heavy wins" before the mixed single/double family (`╞╫…`) is attempted.
- **Lane-collapse edge cases.** A stroked lane adjacent to a collapsed lane must still resolve junctions correctly (single stroked interior lane; strokes touching the frame). Dedicated tests in the geometry conformance suite — which now also covers visibility-induced collapse (all-`SVG_ONLY` edges must yield the compact layout byte-for-byte, §7.6).
- **Glyph width.** Content width is fixed per geometry (1 char rectangular); `glyph_for_value` keeps values single-char, so spacing is stable. Multi-codepoint/emoji width is out of scope (documented; the canvas rejects width>span with a precise error rather than corrupting columns). Note Starbattle's `★` is single-width and unaffected.
- **Hex/tri path-glyph fidelity.** Six-direction `CellPath` in one char is lossy (`{ne,s}` has no good glyph); geometries return best-effort with a documented `*` fallback; SVG is the faithful backend. This risk is now bounded rather than open-ended: any solver that finds the fallback unacceptable opts out per backend (`SVG_ONLY` path + `ASCII_ONLY` stand-in, §3.5/§7.3) — the fallback only ever shows where a solver declined to choose. Prototype the hex geometry early — it is the riskiest unproven piece.
- **Per-backend divergence.** Visibility lets ASCII and SVG legitimately show different element sets, which doubles what goldens must pin and could tempt solvers into gratuitous divergence. Mitigations: goldens are per-backend (§10.2); the default is `ALL_BACKENDS` so divergence is always an explicit, grep-able keyword (`backends=`); convention documented in §6 — `SVG_ONLY` for "too rich for the terminal", `ASCII_ONLY` only for its stand-in, so SVG remains the superset view.
- **Python/ASP double bookkeeping.** `neighbor()`/`all_cells()` restate what the ASP `Cell`/`Orthogonal` facts define. For rectangular grids this is a non-issue by construction: `neighbor()` reads the same `direction_vectors` table that emits the `Direction` facts, so only the trivial bounds check is duplicated, and the conformance test (ground a small instance, diff) is the tripwire. **Decision (July 2026): keep the arithmetic implementation for rectangular; adopt ground-atom extraction only when a grid's boundary makes it earn its keep.** The real skew risk is in-grid *membership* on grids with complicated boundaries (hexagon-shaped hex boards, irregular regions) — and for those, the sanctioned strategy is to extract the `Cell` atoms once and cache them: copy the grid's segment into a fresh `ASPProgram` with the predicates shown (segments are extractable and copyable; hidden atoms can also be read from the solver directly), ground, store the cell set. `neighbor()` then stays shared-table vector arithmetic + a membership lookup, and `all_cells()` reads the same cached set — the boundary is stated exactly once, in ASP. Adjacency itself never needs extracting. The `neighbor()`/`all_cells()` contract is implementation-agnostic, so a grid can switch strategies without touching renderers, scenes, or the conformance suite.
- **Clue layering (decided July 2026): clue glyphs paint at ANNOTATION.** `CellStyle.layer` defaults to `Layer.ANNOTATION`, so a solution atom covering a clue cell cannot repaint the given value in solution colors — Sudoku's clue digits keep their clue color in solved renders. A style may lower it back to `Layer.GLYPH` when the solution's repaint is the desired look: Fillomino does, because its clue color matches its region fill and a persisting clue would vanish into the background. (`Provenance` does not resolve this by itself — it is meaning, not paint order.)
- **Predicate references in rules are `type[Predicate] | str`** (`PredicateRef`). Solution dicts are signature-keyed (`"name/arity"`; migration Step 12, done July 2026), and string references must spell the full signature — `FillRule("wall/1")` — rejected at spec construction otherwise, so a typo or arity mismatch cannot silently match nothing. Classically negated atoms are blanket-dropped from solution dicts at `solve()`: no renderer can draw one, and a positive alias predicate is one ASP line away. Class references derive their signature automatically and isinstance-filter their bucket as belt-and-braces.
- **Field names in rules are strings** (`value_field="size"`). Predicate fields are dynamic per-solver classes; full static typing would mean plumbing `type[Predicate]` generics through rules for marginal benefit. Instead `build_scene` validates field existence eagerly with precise errors. A conscious pragmatic stop.
- **Open: vertex-clue puzzles and the dual grid (decided July 2026: not now, door left open).** Rendering needs only vertex *identity and position*, which the `(cell, corner)` canonicalization supplies for any tessellation from two local facts — deliberately the weakest mechanism that works. Puzzles with vertex entities in their ASP formulation (Slant-class: vertex clues, degree constraints) need far more — a vertex domain, incidence facts — and the canonical construction there is the **dual grid**, added at the ASP layer when the first such solver is written (for a rectangular primal: a second `RectangularGrid` of (rows+1)×(cols+1) plus +0/+1 incidence arithmetic, and a `vertex_cell(vertex) ↔ Vertex` bridge on the grid; the canonical spelling bijects with dual coordinates, so the bridge is mechanical and no scene/geometry API changes). The two mechanisms compose; they were deliberately NOT unified because the dual of a hex grid is a *triangular* grid — first-class dual coordinates would make hex vertex rendering wait on the deferred triangular machinery, when a corner mark needs nothing of the sort. (Slitherlink is the counter-example that cell-centric reformulation often beats native vertex encodings in ASP anyway.)
- **Stacked label rings (`offset > 0`) — deferred.** The `OutsideLabel.offset` field ships as the extension point, but `LineLabels` carries no offset and the rectangular geometry raises if a nonzero offset reaches `_label_span`; `LayoutNeeds.label_margins` is keyed per direction only. Trigger: the first solver needing a second ring (e.g. two clue rows on one side). The known change: `label_margins` keys widen to `(direction, offset)` — worth landing *before* the sheet geometry freezes the narrow shape into a third consumer.
- **`AsciiGeometryBase` extraction — superseded by the common-core rework (July 2026).** Rather than sharing layout privates between two fat per-backend geometries, the rework slimmed the geometry contract (see the §5 amendment): painting moved into the shared `ScenePainter` core, and the cross-backend sharing happens per grid shape in `RectangularGeometryBase` — the structure a `HexGeometryBase` will repeat.
- **Grid-class config resolution for orientation subclasses — decide before hex.** `Solver.create_grid` derives the module name from the class name (`"RectangularGrid"` → `aspuzzle.grids.rectangulargrid`); `"grid_type": "FlatTopHexGrid"` would try to import `aspuzzle.grids.flattophexgrid` and fail, since the plan puts all hex classes in `hexgrid.py`. Options: a registry in `aspuzzle/grids/__init__.py` consulted before the module convention, or one-module-per-concrete-class. Config-format-facing, so it deserves a recorded decision when hex lands.
- **Width-1 glyphs are a spec-level contract, independent of geometry width.** `glyph_for_value`/`_value_glyph` compact values to one char at scene-build time, before any geometry exists — so on a 2-char-wide hex cell, 12 still renders as `C` and 40 as `#` even though the literal digits would fit. Decided: keep it — scene building stays geometry-free, and per-backend `Glyph` variants remain the escape hatch. Revisit only if hex renders prove illegible.
- **Open:** module-contributed spec fragments (`Module.render_rules()` — a SymbolSet knows its symbol names) — additive later. A `ColorMode` (ANSI16/256/truecolor) theme upgrade with `Rgb` passthrough — additive later. JSON-serializing scenes for an interactive HTML viewer — nothing blocks it (a scene is a list of frozen dataclasses, and because visibility filters at query time, a serialized scene carries *all* backends' content). Whether `Provenance` should grow a third member for scaffold/debug overlays — deferred until a consumer exists.

---

## 12. Decisions and rejected alternatives

All three proposals converged on the same skeleton — typed scene between solver and backends, semantic colors, first-class edges/vertices/outside positions, grid-owned character geometry, declarative rule specs, internalized region coloring — which is itself strong evidence for the architecture. Differences were at the joints.

**Skeleton: Proposal 1** (Declarative Scene Model). Its element vocabulary is the most complete (`CellLink` and `OutsideLabel` offset rings exist only there), its `Layer` IntEnum + insertion order is cleaner than raw ints while still accepting them, its single `ColorSpec` with role-by-element-kind avoids a `Style` wrapper layer that added nothing in practice, and its junction-flag resolution is the right unification of Sudoku boxes, Slitherlink loops, and the frame. Its choice to keep `GridCell` atoms as the cell address (shared with Proposal 3) was verified as correct: they are typed, hashable value objects solvers already hold — Proposal 2's `CellRef` coordinate tuples would have forced a conversion at every rule boundary and discarded static typing the codebase already paid for.

**Grafted from Proposal 2** (Geometry-First):
- The **richer geometry surface** (`content_span` with width, `interior_spans` plural) — Proposal 1's single char anchor per cell silently assumed 1-char cells and would not have survived hex.
- **Lane collapsing**, which derives Sudoku's classic look from first principles instead of reproducing `rows_per_box` arithmetic.
- The **concrete hex and triangular char-level layouts** (`__/  \__` tiling, zigzag band) — the only proposal that proved, character by character, that every geometric edge is one shared run. Adopted verbatim as the hex/tri specification.
- **`RegionBorderRule(by=…)`** — strictly better than Proposal 1's `edges_between` inside a `build_scene` override (Sudoku becomes fully declarative and boxes render in previews) and than Proposal 3's `RectangularGrid.block_border_edges` (which was rectangular-specific by construction).
- **`RegionBoundaryRule`** computing Slitherlink's loop in Python from `inside` atoms — chosen over Proposal 1/3's ASP `LoopEdge` extraction as the *recommended* route because it needs zero solver ASP changes and no extra grounding; `EdgeRule` is retained for genuinely ASP-derived edges.
- **`FromClues`** as a region-fill source, which is what actually deletes the side channels in Stitches *and* Starbattle (grid-data regions, not solution predicates — a case Proposal 1's `RegionFillRule` missed).
- The observation that triangular grids make constant-list side/corner vocabularies wrong — retained as the documented signature-widening plan (§5.5), not as shipped generality, once triangular support was deferred.
- The `EdgeWeight` enum and the guardrail test that scene/spec modules import nothing ANSI.

**Grafted from Proposal 3** (Pragmatic Typed Evolution):
- **Whole-set `CustomRule`** (all atoms at once, sorted) — the fix for Stitches' order-dependent colors generalizes to every future escape-hatch use.
- The **`use_colors` threading fix** (its observation; verified: `render_puzzle` never passes it).
- `glyph_for_value` as a shared helper also usable by Sudoku's input remapping, and the observation that today's letters convention is clue-only.
- The framing of **load-bearing vs deferrable**, which shaped the migration plan (SVG protocols frozen now, implemented later; vertex ASCII placement slotted but unexercised).
- Eager **field-name validation with precise errors** in `build_scene`, and the honest note that rule field names remain strings.

**Amendment decisions (owner requirements added after synthesis):**
- **Visibility as element data, filtered at the Scene's query methods** (`sorted_elements(backend)` / `layout_needs(backend)`). Rejected: *per-backend scenes* (two IRs that drift, `build_scene` running twice, and a serialization that captures only one backend — the single-IR constraint exists precisely to prevent this); *filtering at `Scene.add`* (the Scene would need to know its consumer at build time, and a stored scene could never serve a second backend); *renderer-side skip logic* (layout and paint would consult visibility in two places — an SVG-only `EdgeSegment` forcing the expanded ASCII layout is exactly the bug class the single choke point eliminates).
- **`Backend` as a closed enum**, mirroring the closed element union: adding a backend is a conscious decision revisiting every constant and renderer. Rejected: open string tags (typo-prone, un-exhaustive) and per-element booleans like `ascii: bool` (doesn't scale past two backends).
- **Explicit visibility beats geometry fallbacks** — precedence stated in §3.5, not left emergent: the filter runs before geometry ever sees an element, so fallbacks are strictly the no-choice-made safety net. Rejected: capability negotiation (geometry reporting "I render CellPath poorly" and the renderer auto-substituting) — the solver, not the machinery, owns the taste judgment, per Requirement A.
- **`Provenance` as its own enum field**, stamped mechanically by `build_scene`. Rejected: inferring GIVEN/DERIVED from `Layer` (layers are paint order — Sudoku clue and solution digits share `Layer.GLYPH`) and a boolean `is_clue` (a third class of scaffold/debug content is plausible later; an enum leaves the door open).
- **`KW_ONLY` shared base** for `backends`/`provenance` — one declaration, positional construction preserved, per-kind `layer` defaults kept on the subclasses (where they differ).
- **Testability as an acceptance criterion**, with two seam changes it forced: contractually deterministic region coloring (pure-Python backtracking — clingo's first model is not version/platform-stable, and CI goldens must not flap) and constructor-injected `AsciiTheme`. Rejected: treating the §9 suites as follow-up work — each migration wave gates on its tests (§10).
- **Dual rendering stated, not assumed**: preview and solved renders share `build_scene(solution)` by construction; the seams that make previews complete (clues, labels, `by=`-rules, `FromClues` all solution-free) are named and tested (§9's preview-scene test). Rejected: a separate preview path or a `preview: bool` flag threaded through rendering — the solution's presence/absence *is* the distinction, and `Provenance` is its typed residue for backends to style.

**Rejected, with reasons:**
- **A separate `GridTopology` companion class** (P2): grids are already plain Python objects usable without grounding; the topology methods live on `Grid` directly, avoiding a parallel class hierarchy and a second `from_config` path. The conformance test P2 proposed is kept.
- **Coordinate-tuple `CellRef`/opaque-key `EdgeRef`** (P2): loses the typed `GridCell` currency; opaque integer keys would also have pushed canonicalization knowledge into a key-encoding scheme instead of one `Grid.edge` method.
- **`OutsideRef(direction, index, end)`** (P3): the `end` field creates the documented ambiguity (`('s', i, 'start')` ≡ `('n', i, 'start')`) that then needs its own canonicalization. Direction alone already names both ends unambiguously and matches the `Clue(dir=…)` facts solvers write.
- **`Style(fg, bg)` wrapper** (P2/P3): an extra nesting level in every rule for no expressive gain; role-by-element-kind reads better in specs, and `GlyphRule` carries both `color` and `fill` where both are needed. `Emphasis`/bold deferred with it (provenance-driven emphasis now covers the main motivating case at the theme level).
- **Clues painting above atoms by default** (P2's `Layer.CLUE=30`, P3's `clue_layer=10`): verified *contrary to today's behavior* — `_build_render_grid` paints puzzle symbols first and predicates over them. The unified design preserves today's order for golden fidelity and leaves "clues persist" as a per-solver one-liner.
- **Raising on unknown rule predicates** (P3): a predicate absent from a model is legitimate (no mines placed); silent-empty is kept, with typos caught by field validation and goldens.
- **`Chroma.DEFAULT` member** (P3): `color=None` already means "inherit/terminal default"; a sentinel enum member would duplicate it.
- **Deprecation shims / dual-path compatibility**: single-author repo, ~15 in-tree call sites; the old dicts are precisely what is being eliminated.
