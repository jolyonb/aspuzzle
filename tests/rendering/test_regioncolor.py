import pytest

from aspuzzle.grids.rectangulargrid import RectangularGrid
from aspuzzle.puzzle import Puzzle
from aspuzzle.rendering import PaletteColor
from aspuzzle.rendering.regioncolor import DEFAULT_REGION_PALETTE, color_regions

FOUR_QUADRANTS = {
    "a": [(1, 1)],
    "b": [(1, 2)],
    "c": [(2, 1)],
    "d": [(2, 2)],
}


def make_grid(rows: int = 2, cols: int = 2) -> RectangularGrid:
    return RectangularGrid(Puzzle(), rows=rows, cols=cols)


def test_adjacent_regions_get_distinct_colors() -> None:
    colors = color_regions(make_grid(), FOUR_QUADRANTS, DEFAULT_REGION_PALETTE)
    assert set(colors) == {"a", "b", "c", "d"}
    assert all(color in DEFAULT_REGION_PALETTE for color in colors.values())
    # Orthogonal adjacencies: a-b, a-c, b-d, c-d must all differ
    assert colors["a"] != colors["b"]
    assert colors["a"] != colors["c"]
    assert colors["b"] != colors["d"]
    assert colors["c"] != colors["d"]


def test_deterministic_across_runs_and_insertion_orders() -> None:
    grid = make_grid()
    first = color_regions(grid, FOUR_QUADRANTS, DEFAULT_REGION_PALETTE)
    second = color_regions(make_grid(), FOUR_QUADRANTS, DEFAULT_REGION_PALETTE)
    shuffled = {key: FOUR_QUADRANTS[key] for key in ("d", "b", "a", "c")}
    third = color_regions(make_grid(), shuffled, DEFAULT_REGION_PALETTE)
    assert first == second == third


def test_generic_over_color_type() -> None:
    colors = color_regions(make_grid(), FOUR_QUADRANTS, ["#111", "#222", "#333", "#444"])
    assert all(isinstance(color, str) and color.startswith("#") for color in colors.values())


def test_empty_regions() -> None:
    assert color_regions(make_grid(), {}, DEFAULT_REGION_PALETTE) == {}


def test_small_palette_rejected() -> None:
    with pytest.raises(ValueError, match="at least 4"):
        color_regions(make_grid(), FOUR_QUADRANTS, [PaletteColor.RED, PaletteColor.BLUE])
