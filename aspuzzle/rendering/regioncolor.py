"""
Region coloring for rendering: assign colors to regions so that no two
orthogonally adjacent regions share one. Pure deterministic Python — a
first-fit backtracking search over a fixed ordering — so results are
identical across runs, platforms, and library versions, with no solver in
the loop. Ordinary puzzle region maps (small, connected regions) color
instantly; a step budget guards the adversarial cases.
"""

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Final

from aspuzzle.rendering.color import PaletteColor

if TYPE_CHECKING:
    from aspuzzle.rendering.gridview import RenderGrid

DEFAULT_REGION_PALETTE: Final[tuple[PaletteColor, ...]] = (
    PaletteColor.BLUE,
    PaletteColor.GREEN,
    PaletteColor.RED,
    PaletteColor.YELLOW,
    PaletteColor.CYAN,
)


def color_regions[T, C](
    grid: RenderGrid,
    regions: Mapping[T, Sequence[tuple[int, ...]]],
    palette: Sequence[C],
    *,
    search_budget: int = 100_000,
) -> dict[T, C]:
    """
    Color regions so orthogonal neighbors differ, using at most the given
    palette (at least 4 colors, per the Four Color Theorem — which
    guarantees success for connected regions; disconnected regions sharing
    an id may need a fifth color).

    Deterministic by contract: regions are ordered by descending adjacency
    degree (ties broken by id), colors tried in palette order, first
    complete assignment returned. If the search exceeds `search_budget`
    steps (possible only for adversarial disconnected-region maps), a
    deterministic greedy fallback returns a complete best-effort coloring.

    Args:
        grid: The grid the regions live on (topology only; nothing is solved)
        regions: Region id -> cell coordinate tuples
        palette: Colors to assign from (any value type)
        search_budget: Backtracking step limit before the greedy fallback

    Returns:
        Region id -> palette entry
    """
    if not regions:
        return {}
    if len(palette) < 4:
        raise ValueError(f"Color palette must have at least 4 colors (Four Color Theorem), got {len(palette)}")

    ids = sorted(regions, key=str)
    owner: dict[tuple[int, ...], T] = {}
    for region_id in ids:
        for coords in regions[region_id]:
            owner[coords] = region_id

    adjacency: dict[T, set[T]] = {region_id: set() for region_id in ids}
    for region_id in ids:
        for coords in regions[region_id]:
            cell = grid.cell_class(*coords)
            for direction in grid.orthogonal_direction_names:
                neighbor = grid.neighbor(cell, direction)
                if neighbor is None:
                    continue
                other = owner.get(grid.cell_coords(neighbor))
                if other is not None and other != region_id:
                    adjacency[region_id].add(other)
                    adjacency[other].add(region_id)

    # Most-constrained-first ordering keeps the backtracking shallow.
    # Iterative (no recursion limit at region counts a big Fillomino
    # reaches) and budgeted: region maps may legally contain DISCONNECTED
    # regions (repeated clue values), whose adjacency graph need not be
    # planar — a small palette can then make exhaustive search explode.
    order = sorted(ids, key=lambda region_id: (-len(adjacency[region_id]), str(region_id)))
    assignment: dict[T, int] = {}
    next_color = [0] * len(order)
    index = 0
    steps = 0
    while index < len(order):
        steps += 1
        if steps > search_budget:
            return _greedy_min_conflict(order, adjacency, ids, palette)
        region_id = order[index]
        used = {assignment[other] for other in adjacency[region_id] if other in assignment}
        color = next_color[index]
        while color < len(palette) and color in used:
            color += 1
        if color == len(palette):
            if index == 0:
                raise ValueError(
                    f"Could not color the regions with {len(palette)} colors. Disconnected regions "
                    "sharing an id (e.g. repeated clue values) can exceed the Four Color Theorem's "
                    "planar guarantee; use a larger palette."
                )
            next_color[index] = 0
            index -= 1
            del assignment[order[index]]
            continue
        assignment[region_id] = color
        next_color[index] = color + 1
        index += 1
    return {region_id: palette[assignment[region_id]] for region_id in ids}


def _greedy_min_conflict[T, C](
    order: Sequence[T], adjacency: Mapping[T, set[T]], ids: Sequence[T], palette: Sequence[C]
) -> dict[T, C]:
    """Budget-exhausted fallback: deterministic and complete, minimizing
    (but not guaranteeing zero) same-color adjacencies."""
    assignment: dict[T, int] = {}
    for region_id in order:
        neighbor_colors = [assignment[other] for other in adjacency[region_id] if other in assignment]
        assignment[region_id] = min(range(len(palette)), key=lambda c: (neighbor_colors.count(c), c))
    return {region_id: palette[assignment[region_id]] for region_id in ids}
