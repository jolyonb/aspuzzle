"""
Region coloring for rendering: assign colors to regions so that no two
orthogonally adjacent regions share one. Pure deterministic Python — a
first-fit backtracking search over a fixed ordering — so results are
identical across runs, platforms, and library versions, with no solver in
the loop. Puzzle region maps are small (tens of regions) and planar, so
the search is instantaneous.
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
    grid: RenderGrid, regions: Mapping[T, Sequence[tuple[int, ...]]], palette: Sequence[C]
) -> dict[T, C]:
    """
    Color regions so orthogonal neighbors differ, using at most the given
    palette (at least 4 colors, per the Four Color Theorem).

    Deterministic by contract: regions are ordered by descending adjacency
    degree (ties broken by id), colors tried in palette order, first
    complete assignment returned.

    Args:
        grid: The grid the regions live on (topology only; nothing is solved)
        regions: Region id -> cell coordinate tuples
        palette: Colors to assign from (any value type)

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
            cell = grid.Cell(*coords)
            for direction in grid.orthogonal_direction_names:
                neighbor = grid.neighbor(cell, direction)
                if neighbor is None:
                    continue
                other = owner.get(grid.cell_coords(neighbor))
                if other is not None and other != region_id:
                    adjacency[region_id].add(other)
                    adjacency[other].add(region_id)

    # Most-constrained-first ordering keeps the backtracking shallow
    order = sorted(ids, key=lambda region_id: (-len(adjacency[region_id]), str(region_id)))
    assignment: dict[T, int] = {}

    def assign(index: int) -> bool:
        if index == len(order):
            return True
        region_id = order[index]
        used = {assignment[other] for other in adjacency[region_id] if other in assignment}
        for color_index in range(len(palette)):
            if color_index in used:
                continue
            assignment[region_id] = color_index
            if assign(index + 1):
                return True
            del assignment[region_id]
        return False

    if not assign(0):
        raise RuntimeError(
            f"Failed to color regions with {len(palette)} colors. "
            "This violates the Four Color Theorem - please report this as a bug!"
        )
    return {region_id: palette[assignment[region_id]] for region_id in ids}
