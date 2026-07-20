"""
The expanded rectangular ASCII layout: lanes, collapsing, junction
resolution, substrate lattices, vertex marks, and outside-label margins —
pinned as exact scene-to-picture pairs (including a captured literal of
the first pipeline's boxed output).
"""

import pytest

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
    EdgeSegment,
    EdgeWeight,
    Glyph,
    Lattice,
    Layer,
    OutsideLabel,
    PaletteColor,
    Scene,
    SceneStyle,
    Vertex,
    VertexMark,
)
from aspuzzle.rendering.ascii import AsciiRenderer


def make_scene(
    rows: int = 2,
    cols: int = 2,
    style: SceneStyle | None = None,
    backend_styles: dict[Backend, SceneStyle] | None = None,
) -> tuple[RectangularGrid, Scene]:
    grid = RectangularGrid(Puzzle(), rows=rows, cols=cols)
    scene = Scene(grid, style=style or SceneStyle(), backend_styles=backend_styles or {})
    return grid, scene


def render(scene: Scene) -> str:
    return AsciiRenderer(use_colors=False).render(scene)


def block_border_edges(grid: RectangularGrid, rows_per_box: int, cols_per_box: int) -> list[EdgeSegment]:
    """Interior box-boundary edges, the shape RegionBorderRule will emit."""
    edges = []
    for row in range(1, grid.rows + 1):
        for col in range(1, grid.cols + 1):
            if row % rows_per_box == 0 and row < grid.rows:
                edges.append(EdgeSegment(grid.edge(grid.Cell(row, col), "s"), layer=Layer.GRID_MARK))
            if col % cols_per_box == 0 and col < grid.cols:
                edges.append(EdgeSegment(grid.edge(grid.Cell(row, col), "e"), layer=Layer.GRID_MARK))
    return edges


def test_frame_only() -> None:
    _, scene = make_scene(style=SceneStyle(lattice=Lattice.FRAME))
    assert render(scene) == "┌───┐\n│. .│\n│. .│\n└───┘"


def test_heavy_frame() -> None:
    _, scene = make_scene(style=SceneStyle(lattice=Lattice.FRAME, frame_weight=EdgeWeight.HEAVY))
    assert render(scene) == "╔═══╗\n║. .║\n║. .║\n╚═══╝"


def test_full_lattice_wireframe() -> None:
    _, scene = make_scene(style=SceneStyle(lattice=Lattice.FULL))
    assert render(scene) == "┌─┬─┐\n│.│.│\n├─┼─┤\n│.│.│\n└─┴─┘"


def test_single_stroked_interior_lane_collapse() -> None:
    """One stroked interior lane materializes; every other lane collapses."""
    grid, scene = make_scene()
    scene.add(
        EdgeSegment(grid.edge(grid.Cell(1, 1), "s")),
        EdgeSegment(grid.edge(grid.Cell(1, 2), "s")),
    )
    assert render(scene) == ". .\n───\n. ."


def test_stroke_meeting_frame() -> None:
    """An interior stroke ending at the frame junctions correctly."""
    grid, scene = make_scene(style=SceneStyle(lattice=Lattice.FRAME))
    scene.add(
        EdgeSegment(grid.edge(grid.Cell(1, 1), "s")),
        EdgeSegment(grid.edge(grid.Cell(1, 2), "s")),
    )
    assert render(scene) == "┌───┐\n│. .│\n├───┤\n│. .│\n└───┘"


def test_closed_loop_with_gap_zero() -> None:
    """A Slitherlink-shaped loop around one cell of a 2x2 grid."""
    grid, scene = make_scene(style=SceneStyle(packed=True))
    for direction in ("n", "e", "s", "w"):
        scene.add(EdgeSegment(grid.edge(grid.Cell(1, 1), direction)))
    assert render(scene) == "┌─┐ \n│.│.\n└─┘ \n . ."


def test_vertex_dots_materialize_all_lanes() -> None:
    _, scene = make_scene(style=SceneStyle(vertex_dots=True))
    assert render(scene) == ". . .\n . . \n. . .\n . . \n. . ."


def test_vertex_mark_element() -> None:
    grid, scene = make_scene()
    scene.add(VertexMark(grid.vertex(grid.Cell(1, 1), "se"), glyph=Glyph("+")))
    assert render(scene) == ". .\n + \n. ."


def test_edge_color_carries_to_box_chars() -> None:
    grid, scene = make_scene()
    scene.add(EdgeSegment(grid.edge(grid.Cell(1, 1), "e"), color=PaletteColor.BRIGHT_YELLOW))
    colored = AsciiRenderer(use_colors=True).render(scene)
    assert "\033[93m│\033[0m" in colored


def test_mixed_weight_junction_heavy_wins() -> None:
    grid, scene = make_scene()
    scene.add(
        EdgeSegment(grid.edge(grid.Cell(1, 1), "s")),
        EdgeSegment(grid.edge(grid.Cell(1, 2), "s"), weight=EdgeWeight.HEAVY),
    )
    out = render(scene)
    assert "═" in out and "─" in out


def test_outside_labels_reserve_margins() -> None:
    _, scene = make_scene(style=SceneStyle(lattice=Lattice.FRAME))
    scene.add(
        OutsideLabel("s", 1, Glyph("2")),
        OutsideLabel("s", 2, Glyph("1")),
        OutsideLabel("e", 2, Glyph("3")),
    )
    assert render(scene) == "   2 1 \n  ┌───┐\n  │. .│\n3 │. .│\n  └───┘"


def test_svg_only_substrate_keeps_ascii_compact() -> None:
    """A lattice requested for SVG alone must not expand the ASCII layout."""
    _, scene = make_scene(
        backend_styles={Backend.SVG: SceneStyle(lattice=Lattice.FULL, vertex_dots=True)},
    )
    assert render(scene) == ". .\n. ."


def test_conformance_every_element_kind_renders() -> None:
    grid, scene = make_scene(rows=3, cols=3, style=SceneStyle(lattice=Lattice.FRAME))
    scene.add(
        CellGlyph(grid.Cell(1, 1), Glyph("5")),
        EdgeSegment(grid.edge(grid.Cell(2, 2), "n")),
        VertexMark(grid.vertex(grid.Cell(3, 3), "nw"), glyph=Glyph("+")),
        OutsideLabel("s", 2, Glyph("7")),
    )
    out = render(scene)
    assert "5" in out and "7" in out and "+" in out


def test_stacked_label_rings_unsupported() -> None:
    _, scene = make_scene()
    scene.add(OutsideLabel("s", 1, Glyph("2"), offset=1))
    with pytest.raises(NotImplementedError, match="rings"):
        render(scene)


def test_wide_top_labels_widen_pitch_instead_of_crashing() -> None:
    _, scene = make_scene()
    scene.add(OutsideLabel("s", 1, Glyph("12")), OutsideLabel("s", 2, Glyph("10")))
    out = render(scene)
    assert out.splitlines()[0] == "12 10"


def test_wide_top_labels_widen_materialized_lanes_too() -> None:
    """Column pitch honors the label width even when every boundary
    materializes as a lane; padding keeps the wireframe solid."""
    _, scene = make_scene(rows=3, cols=3, style=SceneStyle(lattice=Lattice.FULL))
    for index, value in enumerate((100, 200, 300), start=1):
        scene.add(OutsideLabel("s", index, Glyph(str(value))))
    lines = render(scene).splitlines()
    assert lines[0] == " 100 200 300"
    assert lines[1].rstrip() == "┌──┬───┬──┐"
    assert lines[2].rstrip() == "│. │ . │ .│"


def test_wide_bottom_labels_widen_materialized_lanes_too() -> None:
    _, scene = make_scene(rows=2, cols=3, style=SceneStyle(lattice=Lattice.FULL))
    for index, value in enumerate((111, 222, 333), start=1):
        scene.add(OutsideLabel("n", index, Glyph(str(value))))
    assert render(scene).splitlines()[-1] == " 111 222 333"


def test_wide_labels_stay_separate_across_a_single_materialized_lane() -> None:
    grid, scene = make_scene(rows=2, cols=4)
    scene.add(
        EdgeSegment(grid.edge(grid.Cell(1, 2), "e")),
        EdgeSegment(grid.edge(grid.Cell(2, 2), "e")),
    )
    for index, value in enumerate((10, 20, 30, 40), start=1):
        scene.add(OutsideLabel("s", index, Glyph(str(value))))
    assert render(scene).splitlines()[0] == "10 20 30 40"


def test_svg_only_empty_style_paints_nothing_in_ascii() -> None:
    _, scene = make_scene(style=SceneStyle(empty=CellStyle(glyph=Glyph("."), backends=SVG_ONLY)))
    assert render(scene).strip() == ""


def test_cell_link_multichar_glyph_raises_the_precise_width_error() -> None:
    grid, scene = make_scene()
    scene.add(CellLink(grid.Cell(1, 1), grid.Cell(1, 2), glyph=Glyph("ab")))
    with pytest.raises(ValueError, match="2 chars but the target span is 1 wide"):
        render(scene)


def test_isolated_edge_covers_only_its_own_cell() -> None:
    grid, scene = make_scene(rows=2, cols=3)
    scene.add(EdgeSegment(grid.edge(grid.Cell(1, 2), "n")))
    assert render(scene).splitlines()[0] == "  ─  "


def test_fills_bridge_gaps_between_equal_neighbors() -> None:
    grid, scene = make_scene(rows=1, cols=2)
    scene.add(
        CellFill(grid.Cell(1, 1), PaletteColor.GREEN),
        CellFill(grid.Cell(1, 2), PaletteColor.GREEN),
        EdgeSegment(grid.edge(grid.Cell(1, 1), "n")),  # materializes a lane: expanded layout
    )
    colored = AsciiRenderer(use_colors=True).render(scene)
    content_row = colored.splitlines()[1]
    # cell, gap, cell — the gap char carries the shared background too
    assert content_row.count("\033[42m") == 3


def test_fills_flood_solid_block_through_full_lattice() -> None:
    grid, scene = make_scene(style=SceneStyle(lattice=Lattice.FULL))
    for row in (1, 2):
        for col in (1, 2):
            scene.add(CellFill(grid.Cell(row, col), PaletteColor.GREEN))
    colored = AsciiRenderer(use_colors=True).render(scene)
    # the interior 3x3 (cells plus every char between them) carries the
    # background; the outer lattice ring has no filled flank and stays bare
    assert colored.count("\033[42m") == 9
    for line in colored.splitlines()[1:4]:
        assert line.count("\033[42m") == 3


def test_vertex_marks_on_frame_and_off_lattice() -> None:
    """Frame vertices are legitimate even when their canonical spelling
    carries an outside cell; only off-lattice vertices skip silently."""
    grid, scene = make_scene(rows=3, cols=3)
    scene.add(
        VertexMark(grid.vertex(grid.Cell(1, 1), "nw"), glyph=Glyph("*")),  # frame corner, in-grid spelling
        VertexMark(grid.vertex(grid.Cell(0, 2), "sw"), glyph=Glyph("#")),  # frame vertex, outside-celled spelling
        VertexMark(Vertex(grid.Cell(0, 7), "nw"), glyph=Glyph("@")),  # off-lattice: skipped
    )
    out = render(scene)
    assert "*" in out and "#" in out
    assert "@" not in out


def test_label_bounds_checked_before_ring_offset() -> None:
    """An out-of-range index skips silently even on an unsupported ring;
    an in-range one still reaches the offset guard."""
    _grid, scene = make_scene(rows=3, cols=3)
    scene.add(OutsideLabel("e", 9, Glyph("7"), offset=1))
    out = render(scene)
    assert "7" not in out
    _grid, scene = make_scene(rows=3, cols=3)
    scene.add(OutsideLabel("e", 1, Glyph("7"), offset=1))
    with pytest.raises(NotImplementedError, match="Stacked label rings"):
        render(scene)


def test_unknown_label_direction_raises_precisely() -> None:
    _grid, scene = make_scene(rows=3, cols=3)
    scene.add(OutsideLabel("ne", 1, Glyph("7")))
    with pytest.raises(ValueError, match="'ne' is not a label direction"):
        render(scene)


def test_singleton_path_renders_stub() -> None:
    grid, scene = make_scene()
    scene.add(CellPath(grid.Cell(1, 1), frozenset({"e"})))
    assert "╶" in render(scene)


def test_label_index_beyond_grid_skipped_silently() -> None:
    _, scene = make_scene()
    scene.add(OutsideLabel("e", 5, Glyph("9")), OutsideLabel("e", 1, Glyph("7")))
    out = render(scene)
    assert "7" in out and "9" not in out
