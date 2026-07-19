"""
Per-solver render specs as pure data: construct the solver from its
checked-in puzzle config (no solving, no clingo), inspect the spec, and
build scenes from hand-written solution dicts. Grows a section per solver
as each ports to the scene pipeline.
"""

import json
from pathlib import Path

from aspalchemy import Predicate
from aspuzzle.rendering import (
    Backend,
    CellFill,
    CellGlyph,
    CellLink,
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
    RegionBoundaryRule,
    RegionFillRule,
)
from aspuzzle.solvers.base import Solver
from aspuzzle.solvers.fillomino import Number
from aspuzzle.solvers.galaxies import Galaxy
from aspuzzle.solvers.numberlink import CellDirections
from aspuzzle.solvers.nurikabe import Stream
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
        "tent": [Tent(loc=solver.grid.Cell(1, 5))],
        "tie_destination": [TieDestination(tree_loc=solver.grid.Cell(1, 6), tent_loc=solver.grid.Cell(1, 5))],
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


# -- Wave 1 --


def test_minesweeper_spec() -> None:
    spec = load_solver("minesweeper").get_render_spec()
    assert len(spec.clues) == 9  # digits 0-8
    (mine,) = spec.atoms
    assert isinstance(mine, GlyphRule)
    assert mine.glyph is not None and mine.glyph.for_backend(Backend.SVG) == "💣"


def test_hitori_and_cave_and_nurikabe_fill_rules() -> None:
    for name, predicate in (("hitori", "black"), ("cave", "wall")):
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
    assert all(label.color is PaletteColor.BRIGHT_WHITE for label in spec.labels)
    assert spec.style.lattice is Lattice.FRAME


def test_starbattle_shapeless_spec() -> None:
    spec = load_solver("starbattle_shapeless").get_render_spec()
    (star,) = spec.atoms
    assert isinstance(star, GlyphRule)
    assert star.glyph is not None and star.glyph.for_backend(Backend.ASCII) == "★"


def test_sudoku_blocks_render_in_preview() -> None:
    solver = load_solver("sudoku")
    preview = solver.build_scene(None)
    borders = [element for element in preview.visible(Backend.ASCII) if isinstance(element, EdgeSegment)]
    assert borders and all(element.provenance is Provenance.GIVEN for element in borders)
    # 9x9 with 3x3 blocks: two interior boundaries each way, nine cells each
    assert len(borders) == 2 * 9 * 2


# -- Wave 2 --


def test_numberlink_spec() -> None:
    spec = load_solver("numberlink").get_render_spec()
    (path,) = spec.atoms
    assert isinstance(path, PathRule) and path.predicate is CellDirections
    assert spec.style.packed
    assert len(spec.clues) == len({value for _, value in load_solver("numberlink").grid_data})


def test_slitherlink_spec_draws_fill_and_loop() -> None:
    spec = load_solver("slitherlink").get_render_spec()
    fill, boundary = spec.atoms
    assert isinstance(fill, FillRule) and fill.predicate == "inside"
    assert isinstance(boundary, RegionBoundaryRule) and boundary.predicate == "inside"
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
    solution: dict[str, list[Predicate]] = {"number": [Number(loc=solver.grid.Cell(1, 1), size=40)]}
    scene = solver.build_scene(solution)
    glyphs = [
        element
        for element in scene.visible(Backend.ASCII)
        if isinstance(element, CellGlyph) and element.provenance is Provenance.DERIVED
    ]
    assert len(glyphs) == 1
    assert glyphs[0].glyph.for_backend(Backend.ASCII) == "#"
    assert glyphs[0].glyph.for_backend(Backend.SHEET) == "40"


# -- Wave 3 --


def test_galaxies_spec() -> None:
    spec = load_solver("galaxies").get_render_spec()
    (fill,) = spec.atoms
    assert isinstance(fill, RegionFillRule)
    assert isinstance(fill.source, FromPredicate) and fill.source.predicate is Galaxy
    assert spec.clues["o"].color is None  # center markers inherit the terminal default


def test_stitches_spec_and_preview_regions() -> None:
    solver = load_solver("stitches")
    spec = solver.get_render_spec()
    region_fill, link = spec.atoms
    assert isinstance(region_fill, RegionFillRule) and isinstance(region_fill.source, FromClues)
    assert isinstance(link, LinkRule) and link.predicate is Stitch
    assert {label.direction for label in spec.labels} == {"e", "s"}
    # FromClues runs pre-solve: the preview shows the four-colored regions
    preview = solver.build_scene(None)
    fills = [element for element in preview.visible(Backend.ASCII) if isinstance(element, CellFill)]
    assert len(fills) == len(solver.grid_data)
    assert all(element.provenance is Provenance.GIVEN for element in fills)


def test_starbattle_spec() -> None:
    spec = load_solver("starbattle").get_render_spec()
    region_fill, star = spec.atoms
    assert isinstance(region_fill, RegionFillRule) and isinstance(region_fill.source, FromClues)
    assert isinstance(star, GlyphRule)
    assert star.glyph is not None and star.glyph.for_backend(Backend.SVG) == "⭐"
