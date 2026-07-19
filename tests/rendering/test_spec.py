"""
Rule semantics: every RenderSpec rule turned into elements from hand-built
predicate atoms — no clingo in the loop. Covers ordering (clues first),
preview completeness (solution=None), provenance and backends stamping,
deterministic palettes, and eager field validation.
"""

import pytest

from aspalchemy import Predicate
from aspuzzle.grids.base import GridCell
from aspuzzle.grids.rectangulargrid import RectangularGrid
from aspuzzle.puzzle import Puzzle
from aspuzzle.rendering import (
    SVG_ONLY,
    Backend,
    CellFill,
    CellGlyph,
    CellLink,
    CellPath,
    CellStyle,
    CustomRule,
    EdgeRule,
    EdgeSegment,
    FillRule,
    FromClues,
    FromPredicate,
    Glyph,
    GlyphRule,
    Lattice,
    LineLabels,
    LinkRule,
    OutsideLabel,
    PaletteColor,
    PathRule,
    Provenance,
    RegionBorderRule,
    RegionBoundaryRule,
    RegionFillRule,
    RenderSpec,
    SceneStyle,
    build_scene,
)

Star = Predicate.define("star", {"loc": GridCell}, show=True)
Number = Predicate.define("number", {"loc": GridCell, "value": int}, show=True)
Directions = Predicate.define("cell_directions", {"loc": GridCell, "dir1": str, "dir2": str}, show=True)
Stitch = Predicate.define("stitch", {"loc1": GridCell, "loc2": GridCell}, show=True)
Inside = Predicate.define("inside", {"loc": GridCell}, show=True)
Border = Predicate.define("border", {"loc": GridCell, "direction": str}, show=True)
RegionAtom = Predicate.define("region_atom", {"loc": GridCell, "id": int}, show=True)
Bare = Predicate.define("bare", {"id": int}, show=True)


def make_grid(rows: int = 3, cols: int = 3) -> RectangularGrid:
    return RectangularGrid(Puzzle(), rows=rows, cols=cols)


def test_clues_emit_first_and_given() -> None:
    grid = make_grid()
    spec = RenderSpec(
        clues={5: CellStyle(glyph=Glyph("5"), color=PaletteColor.BLUE, fill=PaletteColor.WHITE)},
        atoms=[GlyphRule("star", glyph=Glyph("*"))],
    )
    scene = build_scene(grid, spec, [((1, 1), 5)], {"star": [Star(loc=grid.Cell(1, 1))]})
    elements = list(scene.visible(Backend.ASCII))
    assert isinstance(elements[0], CellGlyph) and elements[0].provenance is Provenance.GIVEN
    assert isinstance(elements[1], CellFill) and elements[1].provenance is Provenance.GIVEN
    assert isinstance(elements[2], CellGlyph) and elements[2].provenance is Provenance.DERIVED


def test_preview_runs_without_solution() -> None:
    grid = make_grid()
    spec = RenderSpec(
        clues={"T": CellStyle(glyph=Glyph("T"))},
        atoms=[
            GlyphRule("star", glyph=Glyph("*")),
            RegionBorderRule(by=lambda cell: grid.cell_coords(cell)[0] <= 1),
        ],
        labels=[LineLabels("s", [1, None, 2])],
    )
    scene = build_scene(grid, spec, [((2, 2), "T")], None)
    elements = list(scene.visible(Backend.ASCII))
    assert all(element.provenance is Provenance.GIVEN for element in elements)
    kinds = {type(element) for element in elements}
    assert kinds == {CellGlyph, EdgeSegment, OutsideLabel}  # clue, borders, labels; no stars


def test_glyph_rule_value_field_and_colorer() -> None:
    grid = make_grid()
    spec = RenderSpec(
        atoms=[
            GlyphRule(
                "number",
                value_field="value",
                color=lambda atom: PaletteColor.RED if atom["value"].value > 9 else PaletteColor.GREEN,
                fill=PaletteColor.BLACK,
            )
        ]
    )
    solution = {"number": [Number(loc=grid.Cell(1, 1), value=7), Number(loc=grid.Cell(1, 2), value=12)]}
    scene = build_scene(grid, spec, [], solution)
    glyphs = [element for element in scene.visible(Backend.ASCII) if isinstance(element, CellGlyph)]
    by_text = {glyph.glyph.for_backend(Backend.ASCII): glyph for glyph in glyphs}
    assert by_text["7"].color is PaletteColor.GREEN
    assert by_text["C"].color is PaletteColor.RED  # 12 compacts to a letter...
    assert by_text["C"].glyph.for_backend(Backend.SHEET) == "12"  # ...but sheets keep the number
    fills = [element for element in scene.visible(Backend.ASCII) if isinstance(element, CellFill)]
    assert len(fills) == 2


def test_glyph_rule_requires_exactly_one_glyph_source() -> None:
    grid = make_grid()
    with pytest.raises(ValueError, match="exactly one"):
        build_scene(grid, RenderSpec(atoms=[GlyphRule("star")]), [], {"star": [Star(loc=grid.Cell(1, 1))]})
    with pytest.raises(ValueError, match="exactly one"):
        build_scene(
            grid,
            RenderSpec(atoms=[GlyphRule("number", glyph=Glyph("x"), value_field="value")]),
            [],
            {"number": [Number(loc=grid.Cell(1, 1), value=1)]},
        )


def test_class_reference_filters_by_instance() -> None:
    grid = make_grid()
    bare = Bare(id=1)
    # A hand-built bucket whose name matches but whose atoms are another
    # class entirely: a class-referenced rule filters them out silently...
    scene = build_scene(grid, RenderSpec(atoms=[GlyphRule(Star, glyph=Glyph("*"))]), [], {"star": [bare]})
    assert not list(scene.visible(Backend.ASCII))
    # ...while a string-referenced rule takes the bucket at its word and
    # trips field validation
    with pytest.raises(ValueError, match="no field 'loc'"):
        build_scene(grid, RenderSpec(atoms=[GlyphRule("star", glyph=Glyph("*"))]), [], {"star": [bare]})


def test_class_reference_resolves_name() -> None:
    grid = make_grid()
    spec = RenderSpec(atoms=[GlyphRule(Star, glyph=Glyph("*"))])
    scene = build_scene(grid, spec, [], {"star": [Star(loc=grid.Cell(1, 1))]})
    assert len(list(scene.visible(Backend.ASCII))) == 1


def test_unknown_field_error_is_precise() -> None:
    grid = make_grid()
    spec = RenderSpec(atoms=[GlyphRule("star", glyph=Glyph("*"), loc_field="location")])
    with pytest.raises(ValueError, match="no field 'location' \\(available: loc\\)"):
        build_scene(grid, spec, [], {"star": [Star(loc=grid.Cell(1, 1))]})


def test_absent_predicate_emits_nothing() -> None:
    grid = make_grid()
    spec = RenderSpec(atoms=[GlyphRule("star", glyph=Glyph("*")), FillRule("inside", fill=PaletteColor.GREEN)])
    scene = build_scene(grid, spec, [], {"unrelated": []})
    assert not list(scene.visible(Backend.ASCII))


def test_path_rule_builds_direction_sets() -> None:
    grid = make_grid()
    spec = RenderSpec(atoms=[PathRule("cell_directions", color=PaletteColor.CYAN)])
    solution = {"cell_directions": [Directions(loc=grid.Cell(2, 2), dir1="e", dir2="s")]}
    scene = build_scene(grid, spec, [], solution)
    (path,) = scene.visible(Backend.ASCII)
    assert isinstance(path, CellPath)
    assert path.directions == frozenset({"e", "s"})


def test_edge_rule_canonicalizes() -> None:
    grid = make_grid()
    spec = RenderSpec(atoms=[EdgeRule("border")])
    solution = {"border": [Border(loc=grid.Cell(1, 2), direction="w")]}
    scene = build_scene(grid, spec, [], solution)
    (segment,) = scene.visible(Backend.ASCII)
    assert isinstance(segment, EdgeSegment)
    assert segment.edge == grid.edge(grid.Cell(1, 1), "e")  # canonical spelling


def test_link_rule_palette_is_deterministic() -> None:
    grid = make_grid()
    palette = (PaletteColor.RED, PaletteColor.BLUE)
    spec = RenderSpec(atoms=[LinkRule("stitch", glyph=Glyph("X"), palette=palette)])
    atoms = [
        Stitch(loc1=grid.Cell(1, 1), loc2=grid.Cell(1, 2)),
        Stitch(loc1=grid.Cell(2, 1), loc2=grid.Cell(2, 2)),
    ]
    forward = build_scene(grid, spec, [], {"stitch": atoms})
    reversed_input = build_scene(grid, spec, [], {"stitch": list(reversed(atoms))})
    colors_forward = [element.color for element in forward.visible(Backend.ASCII) if isinstance(element, CellLink)]
    colors_reversed = [
        element.color for element in reversed_input.visible(Backend.ASCII) if isinstance(element, CellLink)
    ]
    assert colors_forward == colors_reversed  # sorted-atom order, not input order
    assert set(colors_forward) == set(palette)


def test_region_boundary_rule_traces_the_perimeter() -> None:
    grid = make_grid()
    plus = [(1, 2), (2, 1), (2, 2), (2, 3), (3, 2)]
    solution = {"inside": [Inside(loc=grid.Cell(*coords)) for coords in plus]}
    scene = build_scene(grid, RenderSpec(atoms=[RegionBoundaryRule("inside")]), [], solution)
    segments = [element for element in scene.visible(Backend.ASCII) if isinstance(element, EdgeSegment)]
    assert len(segments) == 12  # the perimeter of a plus pentomino
    assert EdgeSegment(grid.edge(grid.Cell(1, 2), "n")) in segments  # closes at the grid border


def test_region_border_rule_by_classification() -> None:
    grid = make_grid()
    spec = RenderSpec(atoms=[RegionBorderRule(by=lambda cell: grid.cell_coords(cell)[0] <= 1)])
    scene = build_scene(grid, spec, [], None)
    segments = {element.edge for element in scene.visible(Backend.ASCII) if isinstance(element, EdgeSegment)}
    expected = {grid.edge(grid.Cell(1, col), "s") for col in (1, 2, 3)}
    assert segments == expected
    assert all(
        element.provenance is Provenance.GIVEN
        for element in scene.visible(Backend.ASCII)
        if isinstance(element, EdgeSegment)
    )


def test_region_border_rule_requires_one_source() -> None:
    grid = make_grid()
    with pytest.raises(ValueError, match="exactly one"):
        build_scene(grid, RenderSpec(atoms=[RegionBorderRule()]), [], None)


def test_region_fill_rules_from_clues_and_predicate() -> None:
    grid = make_grid(2, 2)
    grid_data = [((1, 1), "a"), ((1, 2), "b"), ((2, 1), "b"), ((2, 2), "a")]
    scene = build_scene(grid, RenderSpec(atoms=[RegionFillRule(FromClues())]), grid_data, None)
    fills = {
        grid.cell_coords(element.cell): element
        for element in scene.visible(Backend.ASCII)
        if isinstance(element, CellFill)
    }
    assert len(fills) == 4
    assert all(element.provenance is Provenance.GIVEN for element in fills.values())
    assert fills[(1, 1)].color != fills[(1, 2)].color  # adjacent regions differ

    solution = {
        "region_atom": [RegionAtom(loc=grid.Cell(*coords), id=1 if value == "a" else 2) for coords, value in grid_data]
    }
    scene2 = build_scene(grid, RenderSpec(atoms=[RegionFillRule(FromPredicate("region_atom"))]), [], solution)
    fills2 = [element for element in scene2.visible(Backend.ASCII) if isinstance(element, CellFill)]
    assert len(fills2) == 4
    assert all(element.provenance is Provenance.DERIVED for element in fills2)


def test_custom_rule_gets_sorted_atoms_and_backend_stamp() -> None:
    grid = make_grid()
    seen: list[str] = []

    def make(atoms, context):  # type: ignore[no-untyped-def]
        seen.extend(str(atom) for atom in atoms)
        assert context.grid is grid
        yield CellGlyph(grid.Cell(1, 1), Glyph("!"))
        yield CellGlyph(grid.Cell(1, 2), Glyph("?"), backends=frozenset({Backend.ASCII}))

    spec = RenderSpec(atoms=[CustomRule("star", make, backends=SVG_ONLY)])
    atoms = [Star(loc=grid.Cell(2, 2)), Star(loc=grid.Cell(1, 1))]
    scene = build_scene(grid, spec, [], {"star": atoms})
    assert seen == sorted(seen)  # delivered in sorted order
    first, second = scene._elements
    assert first.backends == SVG_ONLY  # rule stamp applied to the defaulted element
    assert second.backends == frozenset({Backend.ASCII})  # explicit choice preserved


def test_labels_and_styles_flow_through() -> None:
    grid = make_grid(2, 2)
    svg_style = SceneStyle(lattice=Lattice.FULL)
    spec = RenderSpec(
        labels=[LineLabels("e", [4, None], color=PaletteColor.WHITE, backends=SVG_ONLY)],
        style=SceneStyle(cell_gap=0),
        backend_styles={Backend.SVG: svg_style},
    )
    scene = build_scene(grid, spec, [], None)
    assert scene.style_for(Backend.SVG) is svg_style
    assert scene.style_for(Backend.ASCII).cell_gap == 0
    labels = [element for element in scene.visible(Backend.SVG) if isinstance(element, OutsideLabel)]
    assert len(labels) == 1 and labels[0].index == 1 and labels[0].provenance is Provenance.GIVEN
    assert not list(scene.visible(Backend.ASCII))  # SVG-only labels invisible to ASCII
