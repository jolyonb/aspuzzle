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
    CellGlyph,
    CellLink,
    EdgeSegment,
    FillRule,
    GlyphRule,
    Lattice,
    LineLabels,
    LinkRule,
    OutsideLabel,
    PaletteColor,
    Provenance,
)
from aspuzzle.solvers.base import Solver
from aspuzzle.solvers.nurikabe import Stream
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
    (rule,) = load_solver("nurikabe").get_render_spec().atoms
    assert isinstance(rule, FillRule) and rule.predicate is Stream


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
