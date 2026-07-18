import dataclasses

import pytest

from aspuzzle.grids.rectangulargrid import RectangularGrid
from aspuzzle.puzzle import Puzzle
from aspuzzle.rendering import (
    ALL_BACKENDS,
    ASCII_ONLY,
    SHEET_ONLY,
    SVG_ONLY,
    Backend,
    CellFill,
    CellGlyph,
    CellStyle,
    Edge,
    EdgeSegment,
    Glyph,
    Layer,
    OutsideLabel,
    PaletteColor,
    Provenance,
    Scene,
    SceneStyle,
    Vertex,
    VertexMark,
)


def make_grid() -> RectangularGrid:
    return RectangularGrid(Puzzle(), rows=2, cols=2)


def test_scene_sorting_and_backend_filtering() -> None:
    grid = make_grid()
    scene = Scene(grid)
    glyph = CellGlyph(grid.Cell(1, 1), Glyph("5"), provenance=Provenance.GIVEN)
    fill = CellFill(grid.Cell(1, 1), PaletteColor.GREEN)
    loop = EdgeSegment(Edge(grid.Cell(1, 1), "e"), backends=SVG_ONLY)
    scene.add(glyph, fill, loop)

    assert scene.sorted_elements(Backend.ASCII) == [fill, glyph]  # FILL < GLYPH; loop hidden
    assert scene.sorted_elements(Backend.SVG) == [fill, loop, glyph]
    assert not scene.layout_needs(Backend.ASCII).edges  # SVG-only edge => compact layout
    assert scene.layout_needs(Backend.SVG).edges


def test_insertion_order_breaks_layer_ties() -> None:
    grid = make_grid()
    scene = Scene(grid)
    first = CellGlyph(grid.Cell(1, 1), Glyph("a"))
    second = CellGlyph(grid.Cell(1, 2), Glyph("b"))
    scene.add(first, second)
    assert scene.sorted_elements(Backend.ASCII) == [first, second]


def test_sheet_only_element_visible_to_sheet_alone() -> None:
    grid = make_grid()
    scene = Scene(grid)
    wide = CellGlyph(grid.Cell(1, 1), Glyph("10"), backends=SHEET_ONLY)
    everywhere = CellGlyph(grid.Cell(1, 2), Glyph("X"))
    scene.add(wide, everywhere)

    assert scene.sorted_elements(Backend.SHEET) == [wide, everywhere]
    assert scene.sorted_elements(Backend.ASCII) == [everywhere]
    assert scene.sorted_elements(Backend.SVG) == [everywhere]


def test_hidden_label_reserves_no_margin() -> None:
    grid = make_grid()
    scene = Scene(grid)
    scene.add(
        OutsideLabel("s", 1, Glyph("12"), backends=SVG_ONLY),
        OutsideLabel("e", 2, Glyph("3"), backends=ASCII_ONLY),
    )
    ascii_needs = scene.layout_needs(Backend.ASCII)
    assert ascii_needs.label_margins == {"e": 1}  # SVG-only label reserves nothing
    assert scene.layout_needs(Backend.SVG).label_margins == {"s": 2}


def test_label_margin_takes_widest_text_per_direction() -> None:
    grid = make_grid()
    scene = Scene(grid)
    scene.line_labels("s", [1, None, 12])
    labels = scene.sorted_elements(Backend.ASCII)
    assert [(label.index, label.glyph.text) for label in labels if isinstance(label, OutsideLabel)] == [
        (1, "1"),
        (3, "12"),  # 1-based; None skipped
    ]
    assert all(e.provenance is Provenance.GIVEN for e in labels)  # labels are puzzle input
    assert scene.layout_needs(Backend.ASCII).label_margins == {"s": 2}


def test_label_margin_uses_backend_resolved_glyph_width() -> None:
    grid = make_grid()
    scene = Scene(grid)
    # One label whose sheet variant is wider than its character-grid form
    scene.add(OutsideLabel("s", 1, Glyph("A", sheet="10")))
    assert scene.layout_needs(Backend.ASCII).label_margins == {"s": 1}
    assert scene.layout_needs(Backend.SHEET).label_margins == {"s": 2}


def test_vertex_marks_set_vertex_need() -> None:
    grid = make_grid()
    scene = Scene(grid)
    scene.add(VertexMark(Vertex(grid.Cell(1, 1), "nw")))
    needs = scene.layout_needs(Backend.ASCII)
    assert needs.vertices
    assert not needs.edges


def test_defaults_all_backends_and_derived() -> None:
    grid = make_grid()
    element = CellGlyph(grid.Cell(1, 1), Glyph("x"))
    assert element.backends == ALL_BACKENDS
    assert element.provenance is Provenance.DERIVED
    assert set(ALL_BACKENDS) == {Backend.ASCII, Backend.SVG, Backend.SHEET}


def test_elements_are_frozen() -> None:
    grid = make_grid()
    element = CellFill(grid.Cell(1, 1), PaletteColor.RED)
    with pytest.raises(dataclasses.FrozenInstanceError):
        element.color = PaletteColor.BLUE  # type: ignore[misc]


def test_convenience_emitters() -> None:
    grid = make_grid()
    scene = Scene(grid)
    scene.fill(grid.Cell(1, 1), PaletteColor.GREEN)
    scene.glyph(grid.Cell(1, 1), "7", provenance=Provenance.GIVEN)
    fill, glyph = scene.sorted_elements(Backend.ASCII)
    assert isinstance(fill, CellFill)
    assert isinstance(glyph, CellGlyph)
    assert glyph.glyph == Glyph("7")
    assert glyph.provenance is Provenance.GIVEN
    assert fill.layer == Layer.FILL


def test_scene_style_defaults_match_old_pipeline() -> None:
    style = SceneStyle()
    assert style.cell_gap == 1  # old default join_char " "
    assert not style.frame
    assert style.empty == CellStyle(glyph=Glyph("."))
