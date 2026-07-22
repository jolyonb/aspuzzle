"""
Per-solver render specs as pure data: construct the solver from its
checked-in puzzle config (no solving, no clingo), inspect the spec, and
build scenes from hand-written solution dicts.
"""

import json
from pathlib import Path

import pytest

from aspalchemy import Predicate
from aspuzzle.rendering import (
    ASCII_ONLY,
    CHARACTER_BACKENDS,
    SVG_ONLY,
    Backend,
    CellFill,
    CellGlyph,
    CellLink,
    CellMark,
    CustomRule,
    EdgeMark,
    EdgeSegment,
    FillRule,
    FromClues,
    FromPredicate,
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
    VertexMark,
)
from aspuzzle.solver import Solver
from aspuzzle.solvers.fillomino import Number
from aspuzzle.solvers.galaxies import Galaxies, Galaxy
from aspuzzle.solvers.numberlink import CellDirections, EndpointDirection
from aspuzzle.solvers.nurikabe import Stream
from aspuzzle.solvers.shikaku import Rectangle
from aspuzzle.solvers.stitches import Stitch
from aspuzzle.solvers.tents import Tent, TieDestination

PUZZLES = Path(__file__).parents[2] / "puzzles"


def load_solver(name: str) -> Solver:
    with open(PUZZLES / f"{name}.json") as f:
        return Solver.from_config(json.load(f))


# -- Tents --


def test_tents_spec_is_pure_data() -> None:
    spec = load_solver("tents").get_render_spec()
    tree = spec.clues["T"]
    assert tree.glyph is not None
    assert tree.glyph.for_backend(Backend.ASCII) == "T"
    assert tree.glyph.for_backend(Backend.SVG) == "🌳"
    tent_rule, tie_rule = spec.atoms
    assert isinstance(tent_rule, GlyphRule) and tent_rule.predicate is Tent
    assert tent_rule.glyph is not None and tent_rule.glyph.for_backend(Backend.SVG) == "⛺"
    assert isinstance(tie_rule, LinkRule) and tie_rule.predicate is TieDestination
    assert {label.direction for label in spec.labels} == {"e", "s"}
    assert all(isinstance(label, LineLabels) for label in spec.labels)


def test_tents_preview_is_given_only() -> None:
    solver = load_solver("tents")
    preview = solver.build_scene(None)
    elements = list(preview.visible(Backend.ASCII))
    assert elements, "preview must not be empty"
    assert all(element.provenance is Provenance.GIVEN for element in elements)
    assert any(isinstance(element, OutsideLabel) for element in elements)  # counts render pre-solve
    tree_glyphs = [element for element in elements if isinstance(element, CellGlyph)]
    assert len(tree_glyphs) == sum(1 for _, value in solver.grid_data if value == "T")


def test_tents_scene_from_hand_written_solution() -> None:
    solver = load_solver("tents")
    solution: dict[str, list[Predicate]] = {
        "tent/1": [Tent(loc=solver.grid.Cell(1, 5))],
        "tie_destination/2": [TieDestination(tree_loc=solver.grid.Cell(1, 6), tent_loc=solver.grid.Cell(1, 5))],
    }
    scene = solver.build_scene(solution)
    tents = [
        element
        for element in scene.visible(Backend.ASCII)
        if isinstance(element, CellGlyph) and element.provenance is Provenance.DERIVED
    ]
    assert len(tents) == 1
    assert tents[0].glyph.for_backend(Backend.ASCII) == "A"
    links = [element for element in scene.visible(Backend.SVG) if isinstance(element, CellLink)]
    assert len(links) == 1  # the tie connector renders in SVG...
    assert not any(isinstance(element, CellLink) for element in scene.visible(Backend.ASCII))  # ...only


def test_minesweeper_spec() -> None:
    spec = load_solver("minesweeper").get_render_spec()
    assert len(spec.clues) == 9  # digits 0-8
    (mine,) = spec.atoms
    assert isinstance(mine, GlyphRule)
    assert mine.glyph is not None and mine.glyph.for_backend(Backend.SVG) == "💣"


def test_hitori_and_cave_and_nurikabe_fill_rules() -> None:
    for name, predicate in (("hitori", "black/1"), ("cave", "wall/1")):
        (rule,) = load_solver(name).get_render_spec().atoms
        assert isinstance(rule, FillRule) and rule.predicate == predicate
    nurikabe_spec = load_solver("nurikabe").get_render_spec()
    (rule,) = nurikabe_spec.atoms
    assert isinstance(rule, FillRule) and rule.predicate is Stream
    # Clues beyond the single-char convention render as # (number kept for sheets)
    large = nurikabe_spec.clues[40]
    assert large.glyph is not None
    assert large.glyph.for_backend(Backend.ASCII) == "#"
    assert large.glyph.for_backend(Backend.SHEET) == "40"


def test_skyscrapers_labels_all_four_sides() -> None:
    spec = load_solver("skyscrapers").get_render_spec()
    assert {label.direction for label in spec.labels} == {"n", "e", "s", "w"}
    # Bright-white labels are terminal styling; richer backends carry an
    # uncolored twin that takes the provenance default (visible on paper)
    ascii_labels = [label for label in spec.labels if label.backends == CHARACTER_BACKENDS]
    rich_labels = [label for label in spec.labels if label.backends == SVG_ONLY]
    assert len(ascii_labels) == len(rich_labels) == 4
    assert all(label.color is PaletteColor.BRIGHT_WHITE for label in ascii_labels)
    assert all(label.color is None for label in rich_labels)
    assert spec.style.lattice is Lattice.FRAME


def test_starbattle_shapeless_spec() -> None:
    solver = load_solver("starbattle_shapeless")
    spec = solver.get_render_spec()
    (star,) = spec.atoms
    assert isinstance(star, GlyphRule)
    assert star.glyph is not None and star.glyph.for_backend(Backend.ASCII) == "★"
    # The filled-cell convention: character backends keep the '#' glyph,
    # SVG paints the cell solid
    wall = spec.clues["#"]
    assert wall.backends == CHARACTER_BACKENDS and wall.fill_backends == SVG_ONLY
    preview = solver.build_scene(None)
    fills = [element for element in preview.visible(Backend.SVG) if isinstance(element, CellFill)]
    assert len(fills) == sum(1 for _, value in solver.grid_data if value == "#")
    assert all(fill.opacity == 1.0 and fill.provenance is Provenance.GIVEN for fill in fills)
    assert not [element for element in preview.visible(Backend.ASCII) if isinstance(element, CellFill)]


def test_sudoku_blocks_render_in_preview() -> None:
    solver = load_solver("sudoku")
    preview = solver.build_scene(None)
    borders = [element for element in preview.visible(Backend.ASCII) if isinstance(element, EdgeSegment)]
    assert borders and all(element.provenance is Provenance.GIVEN for element in borders)
    # 9x9 with 3x3 blocks: two interior boundaries each way, nine cells each
    assert len(borders) == 2 * 9 * 2


def test_numberlink_spec() -> None:
    solver = load_solver("numberlink")
    spec = solver.get_render_spec()
    paths, endpoints = spec.atoms
    assert isinstance(paths, PathRule) and paths.predicate is CellDirections
    assert isinstance(endpoints, PathRule) and endpoints.predicate is EndpointDirection
    assert endpoints.direction_fields == ("direction",)
    assert spec.style.packed
    assert len(spec.clues) == len({value for _, value in solver.grid_data})
    # Paths color like their clues: the shared colorer resolves each atom's
    # symbol to that clue's color
    assert callable(paths.color) and paths.color is endpoints.color
    (coords, symbol) = solver.grid_data[0]
    atom = CellDirections(loc=solver.grid.Cell(*coords), dir1="e", dir2="s", sym=symbol)
    assert paths.color(atom) == spec.clues[symbol].color


def test_slitherlink_spec_draws_fill_and_loop() -> None:
    spec = load_solver("slitherlink").get_render_spec()
    fill, boundary = spec.atoms
    assert isinstance(fill, FillRule) and fill.predicate == "inside/1"
    assert isinstance(boundary, RegionBoundaryRule) and boundary.predicate == "inside/1"
    sheep = spec.clues["S"]
    assert sheep.glyph is not None and sheep.glyph.for_backend(Backend.SVG) == "🐑"


def test_fillomino_spec_cycles_fills_by_size() -> None:
    solver = load_solver("fillomino")
    spec = solver.get_render_spec()
    (rule,) = spec.atoms
    assert isinstance(rule, GlyphRule) and rule.predicate is Number
    assert callable(rule.fill)
    assert rule.fill(Number(loc=solver.grid.Cell(1, 1), size=1)) == rule.fill(
        Number(loc=solver.grid.Cell(2, 2), size=10)
    )
    # every clue value present in the grid has a style (the old config hid the largest)
    assert all(value in spec.clues for _, value in solver.grid_data)


def test_fillomino_large_clues_still_render() -> None:
    config = {
        "puzzle_type": "Fillomino",
        "grid_type": "RectangularGrid",
        "grid": [[40, 0]],
        "grid_params": {"rows": 1, "cols": 2},
    }
    config["grid"] = [[40, "."]]
    solver = Solver.from_config(config)
    spec = solver.get_render_spec()
    big = spec.clues[40]
    assert big.glyph is not None
    assert big.glyph.for_backend(Backend.ASCII) == "#"
    assert big.glyph.for_backend(Backend.SHEET) == "40"


def test_fillomino_large_solution_sizes_follow_the_overflow_convention() -> None:
    """Solved region sizes past the single-char range render as # (with the
    number kept for sheets) instead of crashing the character grid —
    reachable even without a large clue, via hidden regions."""
    solver = load_solver("fillomino")
    solution: dict[str, list[Predicate]] = {"number/2": [Number(loc=solver.grid.Cell(1, 1), size=40)]}
    scene = solver.build_scene(solution)
    glyphs = [
        element
        for element in scene.visible(Backend.ASCII)
        if isinstance(element, CellGlyph) and element.provenance is Provenance.DERIVED
    ]
    assert len(glyphs) == 1
    assert glyphs[0].glyph.for_backend(Backend.ASCII) == "#"
    assert glyphs[0].glyph.for_backend(Backend.SHEET) == "40"


def test_galaxies_spec() -> None:
    solver = load_solver("galaxies")
    assert isinstance(solver, Galaxies)
    spec = solver.get_render_spec()
    fill, centers = spec.atoms
    assert isinstance(fill, RegionFillRule)
    assert isinstance(fill.source, FromPredicate) and fill.source.predicate is Galaxy
    # The character-art center encoding is terminal vocabulary only
    assert spec.clues["o"].color is None  # center markers inherit the terminal default
    assert all(style.backends == CHARACTER_BACKENDS for style in spec.clues.values())
    # SVG draws ring marks at the true center positions: one per center,
    # at cell centers, edge midpoints, and vertices
    assert isinstance(centers, CustomRule) and centers.backends == SVG_ONLY
    scene = solver.build_scene(None)
    marks = [element for element in scene.visible(Backend.SVG) if isinstance(element, (CellMark, EdgeMark, VertexMark))]
    assert len(marks) == len(solver.process_data())
    assert all(mark.ring and mark.provenance is Provenance.GIVEN for mark in marks)
    assert not [
        element for element in scene.visible(Backend.ASCII) if isinstance(element, (CellMark, EdgeMark, VertexMark))
    ]


def test_stitches_spec_and_preview_regions() -> None:
    solver = load_solver("stitches")
    spec = solver.get_render_spec()
    region_fill, region_border, ascii_link, rich_link = spec.atoms
    assert isinstance(region_fill, RegionFillRule) and isinstance(region_fill.source, FromClues)
    assert region_fill.backends == ASCII_ONLY
    # The pair idiom: colored blocks in the terminal, thick region borders
    # and black ties where geometry is real
    assert isinstance(region_border, RegionBorderRule) and region_border.backends == SVG_ONLY
    assert isinstance(ascii_link, LinkRule) and ascii_link.predicate is Stitch and ascii_link.palette
    assert isinstance(rich_link, LinkRule) and rich_link.color is PaletteColor.RED
    assert {label.direction for label in spec.labels} == {"e", "s"}
    # FromClues runs pre-solve: the preview shows the four-colored regions
    preview = solver.build_scene(None)
    fills = [element for element in preview.visible(Backend.ASCII) if isinstance(element, CellFill)]
    assert len(fills) == len(solver.grid_data)
    assert all(element.provenance is Provenance.GIVEN for element in fills)
    # ...and the SVG preview the region borders instead
    assert not [element for element in preview.visible(Backend.SVG) if isinstance(element, CellFill)]
    assert [element for element in preview.visible(Backend.SVG) if isinstance(element, EdgeSegment)]


def test_starbattle_spec() -> None:
    spec = load_solver("starbattle").get_render_spec()
    region_fill, region_border, star = spec.atoms
    assert isinstance(region_fill, RegionFillRule) and isinstance(region_fill.source, FromClues)
    assert region_fill.backends == ASCII_ONLY
    assert isinstance(region_border, RegionBorderRule) and region_border.backends == SVG_ONLY
    assert isinstance(star, GlyphRule)
    assert star.glyph is not None and star.glyph.for_backend(Backend.SVG) == "⭐"


def test_shikaku_spec_and_rectangles_come_from_the_solution() -> None:
    solver = load_solver("shikaku")
    spec = solver.get_render_spec()
    region_fill, region_border = spec.atoms
    # The same pair idiom as stitches and starbattle, but the regions are
    # solved rather than given, so both rules read the solution
    assert isinstance(region_fill, RegionFillRule) and isinstance(region_fill.source, FromPredicate)
    assert region_fill.source.predicate is Rectangle and region_fill.backends == ASCII_ONLY
    assert isinstance(region_border, RegionBorderRule) and region_border.backends == SVG_ONLY
    # Nothing to draw before solving beyond the clues themselves
    preview = solver.build_scene(None)
    assert not [element for element in preview.visible(Backend.ASCII) if isinstance(element, CellFill)]
    assert not [element for element in preview.visible(Backend.SVG) if isinstance(element, EdgeSegment)]
    # ...and one fill per cell once solved, since the rectangles tile the grid
    solutions, _result = solver.solve()
    scene = solver.build_scene(solutions[0])
    fills = [element for element in scene.visible(Backend.ASCII) if isinstance(element, CellFill)]
    assert len(fills) == len(list(solver.grid.all_cells()))
    assert all(element.provenance is Provenance.DERIVED for element in fills)


# -- cross-solver guardrails --


def _string_refs(solver: Solver) -> set[str]:
    """Every string predicate reference in the solver's spec (rule
    predicates and FromPredicate sources)."""
    refs: set[str] = set()
    for rule in solver.get_render_spec().atoms:
        predicate = getattr(rule, "predicate", None)
        if isinstance(predicate, str):
            refs.add(predicate)
        source = getattr(rule, "source", None)
        if isinstance(source, FromPredicate) and isinstance(source.predicate, str):
            refs.add(source.predicate)
    return refs


@pytest.mark.parametrize("puzzle_file", sorted(PUZZLES.glob("*.json")), ids=lambda p: p.name)
def test_string_predicate_refs_name_real_solution_predicates(puzzle_file: Path) -> None:
    """A typo'd string reference renders silently empty (an absent
    predicate is legitimate), so every string ref must name a predicate the
    puzzle's expected solutions actually contain."""
    config = json.loads(puzzle_file.read_text())
    if not config.get("solutions"):
        pytest.skip("config carries no expected solutions")
    solver = Solver.from_config(config)
    missing = _string_refs(solver) - set(config["solutions"][0])
    assert not missing, (
        f"{puzzle_file.name}: spec references {sorted(missing)} but the expected solutions never contain them"
    )
