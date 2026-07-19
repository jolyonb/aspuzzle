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


def test_thousand_plus_regions_no_recursion_limit() -> None:
    grid = make_grid(rows=35, cols=35)
    regions = {f"r{r}_{c}": [(r, c)] for r in range(1, 36) for c in range(1, 36)}
    colors = color_regions(grid, regions, DEFAULT_REGION_PALETTE)
    assert len(colors) == 35 * 35


def test_disconnected_regions_get_an_honest_error() -> None:
    # K5 via a 2x10 strip: one column per pair of the five ids, so every
    # pair is adjacent — legal input (repeated clue values), not planar
    from itertools import combinations

    grid = make_grid(rows=2, cols=10)
    regions: dict[str, list[tuple[int, int]]] = {name: [] for name in "abcde"}
    for col, (top, bottom) in enumerate(combinations("abcde", 2), 1):
        regions[top].append((1, col))
        regions[bottom].append((2, col))
    with pytest.raises(ValueError, match="larger palette"):
        color_regions(grid, regions, DEFAULT_REGION_PALETTE[:4])
    five = color_regions(grid, regions, DEFAULT_REGION_PALETTE)  # 5 colors suffice for K5
    assert len({five[name] for name in "abcde"}) == 5


def test_budget_fallback_is_complete_and_deterministic() -> None:
    grid = make_grid()
    first = color_regions(grid, FOUR_QUADRANTS, DEFAULT_REGION_PALETTE, search_budget=1)
    second = color_regions(make_grid(), FOUR_QUADRANTS, DEFAULT_REGION_PALETTE, search_budget=1)
    assert set(first) == set(FOUR_QUADRANTS)  # complete despite the tiny budget
    assert first == second
