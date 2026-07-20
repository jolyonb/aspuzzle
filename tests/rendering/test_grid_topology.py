"""
The grid topology conformance suite: the pure-Python rendering vocabulary
(neighbor, edge/vertex canonicalization) that every grid type must honor.
New grid classes join ALL_GRID_FACTORIES and inherit the whole suite.
"""

from collections.abc import Callable

import pytest

from aspuzzle.grids.base import Grid
from aspuzzle.grids.rectangulargrid import RectangularGrid
from aspuzzle.puzzle import Puzzle
from aspuzzle.rendering import Edge, Vertex


def rect_3x4() -> Grid:
    return RectangularGrid(Puzzle(), rows=3, cols=4)


ALL_GRID_FACTORIES: list[Callable[[], Grid]] = [rect_3x4]


@pytest.mark.parametrize("grid_factory", ALL_GRID_FACTORIES)
def test_edge_canonicalization(grid_factory: Callable[[], Grid]) -> None:
    """The same geometric edge canonicalizes identically from both sides."""
    grid = grid_factory()
    for cell in grid.all_cells():
        for direction in grid.orthogonal_direction_names:
            adjacent = grid.neighbor(cell, direction)
            if adjacent is not None:
                assert grid.edge(cell, direction) == grid.edge(adjacent, grid.opposite_direction(direction))


def test_edge_from_outside_cell_collapses() -> None:
    """An edge spelled from an outside-border cell canonicalizes to its
    in-grid spelling — solution atoms genuinely carry such cells."""
    grid = rect_3x4()
    assert grid.edge(grid.Cell(0, 1), "s") == grid.edge(grid.Cell(1, 1), "n")
    assert grid.edge(grid.Cell(2, 0), "e") == grid.edge(grid.Cell(2, 1), "w")


@pytest.mark.parametrize("grid_factory", ALL_GRID_FACTORIES)
def test_vertex_canonicalization(grid_factory: Callable[[], Grid]) -> None:
    """Every spelling of a shared corner resolves to one canonical Vertex."""
    grid = grid_factory()
    for cell in grid.all_cells():
        for corner in grid.corner_names:
            canonical = grid.vertex(cell, corner)
            for direction in grid.orthogonal_direction_names:
                across = grid.corner_across(corner, direction)
                adjacent = grid.neighbor(cell, direction)
                if across is not None and adjacent is not None:
                    assert grid.vertex(adjacent, across) == canonical


@pytest.mark.parametrize("grid_factory", ALL_GRID_FACTORIES)
def test_distinct_edges_stay_distinct(grid_factory: Callable[[], Grid]) -> None:
    """Canonicalization collapses spellings, not distinct edges: the count
    over all (cell, direction) pairs must match the tessellation's edges."""
    grid = grid_factory()
    directions = grid.orthogonal_direction_names
    edges = {grid.edge(cell, direction) for cell in grid.all_cells() for direction in directions}
    spellings = sum(len(directions) for _ in grid.all_cells())
    interior = sum(
        1 for cell in grid.all_cells() for direction in directions if grid.neighbor(cell, direction) is not None
    )
    # Interior edges have exactly two spellings, boundary edges one
    assert len(edges) == spellings - interior // 2


def test_rect_interior_vertex_has_four_spellings() -> None:
    grid = rect_3x4()
    canonical = grid.vertex(grid.Cell(1, 1), "se")
    assert canonical == grid.vertex(grid.Cell(1, 2), "sw")
    assert canonical == grid.vertex(grid.Cell(2, 1), "ne")
    assert canonical == grid.vertex(grid.Cell(2, 2), "nw")
    # The lexicographically smallest spelling is the canonical one
    assert canonical == Vertex(grid.Cell(1, 1), "se")


def test_rect_edge_prefers_lexicographically_smaller_cell() -> None:
    grid = rect_3x4()
    assert grid.edge(grid.Cell(1, 2), "w") == Edge(grid.Cell(1, 1), "e")
    assert grid.edge(grid.Cell(2, 1), "n") == Edge(grid.Cell(1, 1), "s")


def test_rect_boundary_edge_needs_no_neighbor() -> None:
    grid = rect_3x4()
    assert grid.neighbor(grid.Cell(1, 2), "n") is None
    assert grid.edge(grid.Cell(1, 2), "n") == Edge(grid.Cell(1, 2), "n")


def test_rect_boundary_vertex_spellings() -> None:
    grid = rect_3x4()
    # A corner of the whole grid has exactly one spelling
    assert grid.vertex(grid.Cell(1, 1), "nw") == Vertex(grid.Cell(1, 1), "nw")
    # A top-boundary vertex has two spellings
    assert grid.vertex(grid.Cell(1, 1), "ne") == grid.vertex(grid.Cell(1, 2), "nw")


def test_bad_directions_and_corners_raise() -> None:
    grid = rect_3x4()
    with pytest.raises(ValueError, match="edge direction"):
        grid.edge(grid.Cell(1, 1), "ne")  # diagonal: a direction, not an edge
    with pytest.raises(ValueError, match="edge direction"):
        grid.neighbor(grid.Cell(1, 1), "sideways")
    with pytest.raises(ValueError, match="corner"):
        grid.vertex(grid.Cell(1, 1), "north")
    with pytest.raises(ValueError, match="No opposite"):
        grid.opposite_direction("q")


@pytest.mark.parametrize("grid_factory", ALL_GRID_FACTORIES)
def test_neighbor_matches_asp_orthogonal_facts(grid_factory: Callable[[], Grid]) -> None:
    """The ASP-vs-Python skew check: neighbor() must restate exactly the
    OrthogonalDir facts the grid grounds."""
    grid = grid_factory()
    puzzle = grid.puzzle
    OrthogonalDir = grid.OrthogonalDir
    puzzle.show(OrthogonalDir)

    result = puzzle.solve()
    model = next(iter(result))
    asp_triples = {
        (grid.cell_coords(atom["cell1"]), atom["direction"].value, grid.cell_coords(atom["cell2"]))
        for atom in model.atoms(OrthogonalDir)
    }
    result.close()

    python_triples = {
        (grid.cell_coords(cell), direction, grid.cell_coords(adjacent))
        for cell in grid.all_cells()
        for direction in grid.orthogonal_direction_names
        if (adjacent := grid.neighbor(cell, direction)) is not None
    }

    assert python_triples == asp_triples
