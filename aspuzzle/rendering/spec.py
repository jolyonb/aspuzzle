"""
The solver-facing rendering vocabulary: a RenderSpec is a typed,
declarative description of how a puzzle renders — clue styles for input
values, rules mapping solution predicates to scene elements, outside-label
rings, and substrate styles — and build_scene() turns one spec plus a
(possibly absent) solution into a Scene.

One spec serves every backend and both render states. With solution=None,
predicate-sourced rules emit nothing while clue styles, labels, and
data-driven rules (RegionBorderRule(by=...), FromClues sources) still run,
so previews are complete. Provenance is stamped mechanically: puzzle input
emits GIVEN, solution atoms emit DERIVED. Every rule carries a keyword-only
`backends` field stamped onto everything it emits.

Each rule owns its emission: apply(scene, context) sits with the rule's
declaration, and build_scene() is just clue styles, then each rule's
apply, then labels. Structural mistakes (a rule missing its required
argument) raise at spec construction; data mistakes (a bad field name)
raise at build time with a precise message.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import KW_ONLY, dataclass, field, replace
from typing import TYPE_CHECKING

from aspalchemy import Predicate
from aspuzzle.rendering.backend import ALL_BACKENDS, BackendSet
from aspuzzle.rendering.color import ColorSpec
from aspuzzle.rendering.glyph import Glyph, glyph_for_value
from aspuzzle.rendering.regioncolor import DEFAULT_REGION_PALETTE, color_regions
from aspuzzle.rendering.scene import (
    Backend,
    CellFill,
    CellGlyph,
    CellLink,
    CellPath,
    CellStyle,
    EdgeSegment,
    EdgeWeight,
    Layer,
    OutsideLabel,
    Provenance,
    Scene,
    SceneElement,
    SceneStyle,
)

if TYPE_CHECKING:
    from aspuzzle.grids.base import GridCell, GridCellData
    from aspuzzle.rendering.gridview import RenderGrid

type Colorer = Callable[[Predicate], ColorSpec]
type ColorLike = ColorSpec | Colorer

# Rules name their predicate either by the class the solver holds (loud on
# typos, refactorable, and atoms are isinstance-filtered — robust even if a
# solution bucket ever mixes same-named predicates) or by its rendered name
# (matching the name-keyed solution dict).
type PredicateRef = type[Predicate] | str


@dataclass(frozen=True)
class RenderContext:
    """What rule application sees: the grid, the parsed puzzle input, and
    the (possibly empty) solution."""

    grid: RenderGrid
    grid_data: Sequence[GridCellData]
    solution: Mapping[str, list[Predicate]]

    def atoms(self, predicate: str) -> Sequence[Predicate]:
        return self.solution.get(predicate, [])


# -- shared rule machinery --


def _ref_name(ref: PredicateRef) -> str:
    return ref if isinstance(ref, str) else ref.get_name()


def _require_fields(rule: object, ref: PredicateRef, fields: Sequence[str | None], available: Sequence[str]) -> None:
    for name in fields:
        if name is not None and name not in available:
            raise ValueError(
                f"{type(rule).__name__} on predicate {_ref_name(ref)!r}: "
                f"no field {name!r} (available: {', '.join(available)})"
            )


def _check_ref_fields(rule: object, ref: PredicateRef, fields: Sequence[str | None]) -> None:
    """Class references carry their field set, so a bad field name fails at
    spec construction; string references can only be checked against atoms
    at build time."""
    if not isinstance(ref, str):
        _require_fields(rule, ref, fields, ref.field_names())


def _checked_atoms(rule: object, ref: PredicateRef, context: RenderContext, fields: Sequence[str]) -> list[Predicate]:
    """The rule's atoms, sorted for determinism, with the fields it needs
    validated against the first atom (an absent predicate is legitimate
    and returns empty)."""
    atoms = context.atoms(_ref_name(ref))
    if not isinstance(ref, str):
        # Class references disambiguate: only instances of that class count
        atoms = [atom for atom in atoms if isinstance(atom, ref)]
    atoms = sorted(atoms, key=str)
    if atoms:
        _require_fields(rule, ref, fields, atoms[0].field_names())
    return atoms


def _resolve(color: ColorLike | None, atom: Predicate) -> ColorSpec | None:
    return color(atom) if callable(color) else color


def _value_glyph(value: object) -> Glyph:
    """Single-char convention where it applies; ints past it follow the
    overflow-clue convention (# in character grids, the literal number in
    sheets); other values render as their literal text (which renders in
    width-free backends and raises the canvas's precise width error on
    character grids)."""
    if isinstance(value, int):
        if 0 <= value <= 35:
            return glyph_for_value(value)
        return Glyph("#", sheet=str(value))
    return Glyph(str(value))


@dataclass(frozen=True)
class RuleBase:
    """Fields shared by every rule; keyword-only so subclasses keep their
    natural positional fields."""

    _: KW_ONLY
    backends: BackendSet = ALL_BACKENDS


# -- region sources (shared by the region rules) --


@dataclass(frozen=True)
class FromPredicate:
    """Region source: solution atoms carrying (region id, cell)."""

    predicate: PredicateRef
    id_field: str = "id"
    loc_field: str = "loc"

    def __post_init__(self) -> None:
        _check_ref_fields(self, self.predicate, [self.id_field, self.loc_field])


@dataclass(frozen=True)
class FromClues:
    """Region source: the parsed grid data, region id per cell value.
    Runs with or without a solution."""


type RegionSource = FromPredicate | FromClues


def _region_map(source: RegionSource, context: RenderContext) -> dict[object, list[tuple[int, ...]]]:
    """Region id -> cell coordinates, from either source."""
    regions: dict[object, list[tuple[int, ...]]] = {}
    if isinstance(source, FromClues):
        for coords, value in context.grid_data:
            regions.setdefault(value, []).append(coords)
    else:
        atoms = _checked_atoms(source, source.predicate, context, [source.id_field, source.loc_field])
        for atom in atoms:
            regions.setdefault(atom[source.id_field].value, []).append(context.grid.cell_coords(atom[source.loc_field]))
    return regions


# -- the rules --


@dataclass(frozen=True)
class GlyphRule(RuleBase):
    """Solution atoms -> CellGlyph (+ optional CellFill). Exactly one of
    `glyph` (fixed) or `value_field` (glyph from the atom's value; ints go
    through glyph_for_value) must be given."""

    predicate: PredicateRef
    loc_field: str = "loc"
    glyph: Glyph | None = None
    value_field: str | None = None
    color: ColorLike | None = None
    fill: ColorLike | None = None
    layer: int = Layer.GLYPH

    def __post_init__(self) -> None:
        if (self.glyph is None) == (self.value_field is None):
            raise ValueError(f"GlyphRule on {_ref_name(self.predicate)!r}: give exactly one of glyph= or value_field=")
        _check_ref_fields(self, self.predicate, [self.loc_field, self.value_field])

    def apply(self, scene: Scene, context: RenderContext) -> None:
        fields = [self.loc_field] + ([self.value_field] if self.value_field else [])
        for atom in _checked_atoms(self, self.predicate, context, fields):
            if self.glyph is not None:
                glyph = self.glyph
            else:
                assert self.value_field is not None  # __post_init__'s exactly-one check
                glyph = _value_glyph(atom[self.value_field].value)
            scene.add(
                CellGlyph(
                    atom[self.loc_field],
                    glyph,
                    color=_resolve(self.color, atom),
                    layer=self.layer,
                    backends=self.backends,
                )
            )
            if (fill := _resolve(self.fill, atom)) is not None:
                scene.add(CellFill(atom[self.loc_field], fill, backends=self.backends))


@dataclass(frozen=True)
class FillRule(RuleBase):
    """Solution atoms -> CellFill."""

    predicate: PredicateRef
    fill: ColorLike = None  # type: ignore[assignment]  # required; checked in __post_init__
    loc_field: str = "loc"
    layer: int = Layer.FILL

    def __post_init__(self) -> None:
        if self.fill is None:
            raise ValueError(f"FillRule on {_ref_name(self.predicate)!r}: fill= is required")
        _check_ref_fields(self, self.predicate, [self.loc_field])

    def apply(self, scene: Scene, context: RenderContext) -> None:
        for atom in _checked_atoms(self, self.predicate, context, [self.loc_field]):
            fill = _resolve(self.fill, atom)
            assert fill is not None
            scene.add(CellFill(atom[self.loc_field], fill, layer=self.layer, backends=self.backends))


@dataclass(frozen=True)
class PathRule(RuleBase):
    """Solution atoms carrying direction names -> CellPath."""

    predicate: PredicateRef
    loc_field: str = "loc"
    direction_fields: tuple[str, ...] = ("dir1", "dir2")
    color: ColorSpec | None = None
    layer: int = Layer.PATH

    def __post_init__(self) -> None:
        _check_ref_fields(self, self.predicate, [self.loc_field, *self.direction_fields])

    def apply(self, scene: Scene, context: RenderContext) -> None:
        for atom in _checked_atoms(self, self.predicate, context, [self.loc_field, *self.direction_fields]):
            directions = frozenset(atom[name].value for name in self.direction_fields)
            scene.add(
                CellPath(atom[self.loc_field], directions, color=self.color, layer=self.layer, backends=self.backends)
            )


@dataclass(frozen=True)
class EdgeRule(RuleBase):
    """Solution atoms carrying (cell, direction) -> EdgeSegment, for edges
    that are genuinely solver output."""

    predicate: PredicateRef
    loc_field: str = "loc"
    direction_field: str = "direction"
    color: ColorSpec | None = None
    weight: EdgeWeight = EdgeWeight.NORMAL
    layer: int = Layer.PATH

    def __post_init__(self) -> None:
        _check_ref_fields(self, self.predicate, [self.loc_field, self.direction_field])

    def apply(self, scene: Scene, context: RenderContext) -> None:
        for atom in _checked_atoms(self, self.predicate, context, [self.loc_field, self.direction_field]):
            edge = scene.grid.edge(atom[self.loc_field], atom[self.direction_field].value)
            scene.add(EdgeSegment(edge, color=self.color, weight=self.weight, layer=self.layer, backends=self.backends))


@dataclass(frozen=True)
class LinkRule(RuleBase):
    """Solution atoms carrying two cells -> CellLink, palette cycled
    deterministically over the atoms in sorted order."""

    predicate: PredicateRef
    loc_fields: tuple[str, str] = ("loc1", "loc2")
    glyph: Glyph | None = None
    palette: Sequence[ColorSpec] = ()
    layer: int = Layer.PATH

    def __post_init__(self) -> None:
        _check_ref_fields(self, self.predicate, list(self.loc_fields))

    def apply(self, scene: Scene, context: RenderContext) -> None:
        for index, atom in enumerate(_checked_atoms(self, self.predicate, context, list(self.loc_fields))):
            color = self.palette[index % len(self.palette)] if self.palette else None
            scene.add(
                CellLink(
                    atom[self.loc_fields[0]],
                    atom[self.loc_fields[1]],
                    glyph=self.glyph,
                    color=color,
                    layer=self.layer,
                    backends=self.backends,
                )
            )


@dataclass(frozen=True)
class RegionFillRule(RuleBase):
    """A CellFill per region cell, colors chosen by a deterministic
    four-coloring so orthogonal neighbors differ (see regioncolor)."""

    source: RegionSource = field(default_factory=FromClues)
    palette: Sequence[ColorSpec] = ()  # empty -> DEFAULT_REGION_PALETTE
    layer: int = Layer.FILL

    def apply(self, scene: Scene, context: RenderContext) -> None:
        regions = _region_map(self.source, context)
        if not regions:
            return
        palette: Sequence[ColorSpec] = self.palette if self.palette else DEFAULT_REGION_PALETTE
        colors = color_regions(scene.grid, regions, palette)
        provenance = Provenance.GIVEN if isinstance(self.source, FromClues) else Provenance.DERIVED
        for region_id in sorted(regions, key=str):
            for coords in sorted(regions[region_id]):
                scene.add(
                    CellFill(
                        scene.grid.Cell(*coords),
                        colors[region_id],
                        layer=self.layer,
                        backends=self.backends,
                        provenance=provenance,
                    )
                )


@dataclass(frozen=True)
class RegionBorderRule(RuleBase):
    """EdgeSegments wherever a cell classification changes between
    neighbors — block borders, cages, region outlines. Exactly one of
    `by` (a classification of every cell; runs without a solution) or
    `source` must be given. A None classification means regionless: such
    cells draw no edges of their own (edges against classified neighbors
    still draw, charged to the classified side). Boundary edges (neighbor
    off-grid) are included when include_boundary=True (usually the frame
    covers them)."""

    by: Callable[[GridCell], object] | None = None
    source: RegionSource | None = None
    weight: EdgeWeight = EdgeWeight.NORMAL
    color: ColorSpec | None = None
    include_boundary: bool = False
    layer: int = Layer.GRID_MARK

    def __post_init__(self) -> None:
        if (self.by is None) == (self.source is None):
            raise ValueError("RegionBorderRule: give exactly one of by= or source=")

    def _classification(self, context: RenderContext) -> tuple[Callable[[GridCell], object], Provenance] | None:
        """The cell classification and its provenance, or None if the
        source has nothing to classify."""
        if self.by is not None:
            return self.by, Provenance.GIVEN
        assert self.source is not None  # __post_init__'s exactly-one check
        regions = _region_map(self.source, context)
        if not regions:
            return None
        by_coords = {coords: region_id for region_id, cells in regions.items() for coords in cells}
        grid = context.grid
        provenance = Provenance.GIVEN if isinstance(self.source, FromClues) else Provenance.DERIVED
        return (lambda cell: by_coords.get(grid.cell_coords(cell))), provenance

    def apply(self, scene: Scene, context: RenderContext) -> None:
        classification = self._classification(context)
        if classification is None:
            return
        classify, provenance = classification
        grid = scene.grid
        emitted: set[object] = set()
        for cell in grid.all_cells():
            for direction in grid.orthogonal_direction_names:
                neighbor = grid.neighbor(cell, direction)
                if neighbor is None:
                    if not self.include_boundary or classify(cell) is None:
                        continue
                elif classify(cell) == classify(neighbor):
                    continue
                edge = grid.edge(cell, direction)
                if edge not in emitted:
                    emitted.add(edge)
                    scene.add(
                        EdgeSegment(
                            edge,
                            color=self.color,
                            weight=self.weight,
                            layer=self.layer,
                            backends=self.backends,
                            provenance=provenance,
                        )
                    )


@dataclass(frozen=True)
class RegionBoundaryRule(RuleBase):
    """EdgeSegments around the boundary of a cell set: edges between a
    member cell and any non-member or off-grid cell. Draws a closed loop
    from membership atoms with no solver ASP changes."""

    predicate: PredicateRef
    loc_field: str = "loc"
    color: ColorSpec | None = None
    weight: EdgeWeight = EdgeWeight.NORMAL
    layer: int = Layer.PATH

    def __post_init__(self) -> None:
        _check_ref_fields(self, self.predicate, [self.loc_field])

    def apply(self, scene: Scene, context: RenderContext) -> None:
        atoms = _checked_atoms(self, self.predicate, context, [self.loc_field])
        grid = scene.grid
        members = {grid.cell_coords(atom[self.loc_field]) for atom in atoms}
        for atom in atoms:
            cell = atom[self.loc_field]
            for direction in grid.orthogonal_direction_names:
                neighbor = grid.neighbor(cell, direction)
                if neighbor is None or grid.cell_coords(neighbor) not in members:
                    scene.add(
                        EdgeSegment(
                            grid.edge(cell, direction),
                            color=self.color,
                            weight=self.weight,
                            layer=self.layer,
                            backends=self.backends,
                        )
                    )


@dataclass(frozen=True)
class CustomRule(RuleBase):
    """The typed escape hatch: receives ALL atoms of the predicate at once
    (sorted, so whole-set decisions need no hidden state) and the context,
    returns scene elements. The rule's `backends` is applied to emitted
    elements that did not choose their own."""

    predicate: PredicateRef
    make: Callable[[Sequence[Predicate], RenderContext], Iterable[SceneElement]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.make is None:
            raise ValueError(f"CustomRule on {_ref_name(self.predicate)!r}: make= is required")

    def apply(self, scene: Scene, context: RenderContext) -> None:
        for element in self.make(_checked_atoms(self, self.predicate, context, ()), context):
            if self.backends != ALL_BACKENDS and element.backends == ALL_BACKENDS:
                element = replace(element, backends=self.backends)
            scene.add(element)


@dataclass(frozen=True)
class LineLabels(RuleBase):
    """A ring of outside labels from a config array: one label per
    non-None value at (direction, i), 1-based — the shape of the *_clues
    config lists. Labels are puzzle input (GIVEN)."""

    direction: str
    values: Sequence[int | str | None] = ()
    color: ColorSpec | None = None

    def apply(self, scene: Scene, context: RenderContext) -> None:
        for index, value in enumerate(self.values, 1):
            if value is None:
                continue
            scene.add(
                OutsideLabel(
                    self.direction,
                    index,
                    Glyph(str(value)),
                    color=self.color,
                    backends=self.backends,
                    provenance=Provenance.GIVEN,
                )
            )


type AtomRule = (
    GlyphRule
    | FillRule
    | PathRule
    | EdgeRule
    | LinkRule
    | RegionFillRule
    | RegionBorderRule
    | RegionBoundaryRule
    | CustomRule
)


type ClueColor = ColorSpec | Callable[[int], ColorSpec] | None
"""One color for every clue, a per-value callable, or the terminal default."""


def _clue_color(color: ClueColor, value: int) -> ColorSpec | None:
    return color(value) if callable(color) else color


def digit_clues(
    values: Iterable[int], color: ClueColor = None, layer: int = Layer.ANNOTATION
) -> dict[int | str, CellStyle]:
    """The common clue table: each value styled with its single-character
    glyph (glyph_for_value)."""
    return {
        value: CellStyle(glyph=glyph_for_value(value), color=_clue_color(color, value), layer=layer) for value in values
    }


def overflow_clues(
    values: Iterable[int], color: ClueColor = None, layer: int = Layer.ANNOTATION
) -> dict[int | str, CellStyle]:
    """Clue table for values past the single-character range: # on
    character grids, the literal number in sheets."""
    return {
        value: CellStyle(glyph=Glyph("#", sheet=str(value)), color=_clue_color(color, value), layer=layer)
        for value in values
    }


def symbol_clues(grid_data: Sequence[GridCellData], palette: Sequence[ColorSpec]) -> dict[int | str, CellStyle]:
    """Clue table for opaque symbols (Numberlink-style pair labels): each
    distinct grid value styled as its literal text, colored in
    first-appearance order, cycling the palette."""
    symbols: list[int | str] = []
    for _coords, symbol in grid_data:
        if symbol not in symbols:
            symbols.append(symbol)
    return {
        symbol: CellStyle(glyph=Glyph(str(symbol)), color=palette[i % len(palette)]) for i, symbol in enumerate(symbols)
    }


@dataclass(frozen=True)
class RenderSpec:
    """A puzzle's complete, declarative rendering description."""

    clues: Mapping[int | str, CellStyle] = field(default_factory=dict)
    atoms: Sequence[AtomRule] = ()
    labels: Sequence[LineLabels] = ()
    style: SceneStyle = field(default_factory=SceneStyle)  # the substrate every backend gets
    backend_styles: Mapping[Backend, SceneStyle] = field(default_factory=dict)  # whole-style overrides


def _apply_clues(spec: RenderSpec, scene: Scene, grid_data: Sequence[GridCellData]) -> None:
    for coords, value in grid_data:
        style = spec.clues.get(value)
        if style is None:
            continue
        cell = scene.grid.Cell(*coords)
        if style.glyph is not None:
            scene.add(
                CellGlyph(
                    cell,
                    style.glyph,
                    color=style.color,
                    layer=style.layer,
                    backends=style.backends,
                    provenance=Provenance.GIVEN,
                )
            )
        if style.fill is not None:
            scene.add(CellFill(cell, style.fill, backends=style.backends, provenance=Provenance.GIVEN))


def build_scene(
    grid: RenderGrid,
    spec: RenderSpec,
    grid_data: Sequence[GridCellData],
    solution: Mapping[str, list[Predicate]] | None,
) -> Scene:
    """
    Turn a RenderSpec into a Scene: clue styles first (so later rules at
    the same layer paint over clue cells), then each rule's apply in
    order, then labels. An absent predicate emits nothing (a predicate may
    legitimately be empty in a model).
    """
    scene = Scene(grid, style=spec.style, backend_styles=dict(spec.backend_styles))
    context = RenderContext(grid=grid, grid_data=grid_data, solution=solution or {})

    _apply_clues(spec, scene, grid_data)
    for rule in spec.atoms:
        rule.apply(scene, context)
    for label in spec.labels:
        label.apply(scene, context)
    return scene
