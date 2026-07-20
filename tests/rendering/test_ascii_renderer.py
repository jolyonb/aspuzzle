import pytest

from aspuzzle.grids.rectangulargrid import RectangularGrid
from aspuzzle.puzzle import Puzzle
from aspuzzle.rendering import (
    SVG_ONLY,
    CellFill,
    CellGlyph,
    CellLink,
    CellMark,
    CellPath,
    CellStyle,
    Edge,
    EdgeSegment,
    Glyph,
    PaletteColor,
    Scene,
    SceneStyle,
)
from aspuzzle.rendering.ascii import AsciiRenderer


def make_scene(rows: int = 2, cols: int = 2, style: SceneStyle | None = None) -> tuple[RectangularGrid, Scene]:
    grid = RectangularGrid(Puzzle(), rows=rows, cols=cols)
    scene = Scene(grid, style=style if style is not None else SceneStyle())
    return grid, scene


def test_fill_under_glyph_golden() -> None:
    grid, scene = make_scene()
    scene.add(CellFill(grid.Cell(1, 1), PaletteColor.GREEN), CellGlyph(grid.Cell(1, 1), Glyph("5")))
    assert AsciiRenderer(use_colors=False).render(scene) == "5 .\n. ."


def test_packed_cells_touch() -> None:
    grid, scene = make_scene(style=SceneStyle(packed=True))
    scene.add(CellGlyph(grid.Cell(1, 1), Glyph("5")))
    assert AsciiRenderer(use_colors=False).render(scene) == "5.\n.."


def test_path_glyphs_use_box_chars() -> None:
    grid, scene = make_scene(style=SceneStyle(packed=True))
    scene.add(
        CellPath(grid.Cell(1, 1), frozenset({"e", "s"})),
        CellPath(grid.Cell(1, 2), frozenset({"s", "w"})),
        CellPath(grid.Cell(2, 1), frozenset({"e", "n"})),
        CellPath(grid.Cell(2, 2), frozenset({"n", "w"})),
    )
    assert AsciiRenderer(use_colors=False).render(scene) == "┌┐\n└┘"


def test_unknown_path_direction_set_raises() -> None:
    grid, scene = make_scene()
    scene.add(CellPath(grid.Cell(1, 1), frozenset({"ne", "s"})))
    with pytest.raises(ValueError, match="No path glyph"):
        AsciiRenderer(use_colors=False).render(scene)


def test_multi_character_mark_glyph_raises() -> None:
    grid, scene = make_scene()
    scene.add(CellMark(grid.Cell(1, 1), glyph=Glyph("10")))
    with pytest.raises(ValueError, match="one-character mark position"):
        AsciiRenderer(use_colors=False).render(scene)


def test_cell_link_draws_glyph_in_both_cells() -> None:
    grid, scene = make_scene()
    scene.add(CellLink(grid.Cell(1, 1), grid.Cell(1, 2), glyph=Glyph("X"), color=PaletteColor.CYAN))
    assert AsciiRenderer(use_colors=False).render(scene) == "X X\n. ."


def test_out_of_grid_elements_skipped_silently() -> None:
    grid, scene = make_scene()
    scene.add(CellGlyph(grid.Cell(0, 7), Glyph("!")), CellFill(grid.Cell(5, 5), PaletteColor.RED))
    assert AsciiRenderer(use_colors=False).render(scene) == ". .\n. ."


def test_svg_only_edge_keeps_compact_layout() -> None:
    """The §7.6 lever: an SVG-only EdgeSegment must not force the expanded layout."""
    grid, scene = make_scene()
    scene.add(
        CellFill(grid.Cell(1, 1), PaletteColor.GREEN),
        EdgeSegment(Edge(grid.Cell(1, 1), "e"), backends=SVG_ONLY),
    )
    # Fills touch only the background channel, so the uncolored render is the
    # plain compact grid — and no NotImplementedError, proving the hidden
    # edge never reached the geometry
    assert AsciiRenderer(use_colors=False).render(scene) == ". .\n. ."


def test_custom_empty_style() -> None:
    grid, scene = make_scene(style=SceneStyle(empty=CellStyle(glyph=Glyph("·"), color=PaletteColor.BRIGHT_BLACK)))
    scene.add(CellGlyph(grid.Cell(2, 2), Glyph("x")))
    assert AsciiRenderer(use_colors=False).render(scene) == "· ·\n· x"


def test_glyph_backend_variant_resolves_to_ascii_text() -> None:
    grid, scene = make_scene()
    scene.add(CellGlyph(grid.Cell(1, 1), Glyph("A", svg="⛺")))
    assert AsciiRenderer(use_colors=False).render(scene) == "A .\n. ."


def test_wide_glyph_raises_precise_error() -> None:
    grid, scene = make_scene()
    scene.add(CellGlyph(grid.Cell(1, 1), Glyph("10")))
    with pytest.raises(ValueError, match="target span is 1 wide"):
        AsciiRenderer(use_colors=False).render(scene)


def test_single_edge_materializes_one_lane() -> None:
    grid, scene = make_scene()
    scene.add(EdgeSegment(Edge(grid.Cell(1, 1), "e")))
    # The interior vertical lane materializes (replacing the gap); the other
    # boundaries stay collapsed and the second row's lane column is blank
    assert AsciiRenderer(use_colors=False).render(scene) == ".│.\n. ."
