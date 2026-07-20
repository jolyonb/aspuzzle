"""
The kitchen-sink conformance scene: every element kind, both edge weights,
a full lattice with vertex dots, multi-char outside labels, and an Rgb
color, rendered through every registered geometry and pinned as a golden —
the test that keeps a new grid geometry or backend honest before any
solver uses it.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from aspuzzle.grids.base import Grid
from aspuzzle.rendering import (
    CellFill,
    CellGlyph,
    CellLink,
    CellMark,
    CellPath,
    EdgeMark,
    EdgeSegment,
    EdgeWeight,
    Glyph,
    Lattice,
    OutsideLabel,
    PaletteColor,
    Rgb,
    Scene,
    SceneStyle,
    VertexMark,
)
from aspuzzle.rendering.ascii import AsciiRenderer
from aspuzzle.rendering.svg import SvgRenderer
from tests.rendering.test_grid_topology import ALL_GRID_FACTORIES

GOLDEN_ROOT = Path(__file__).parents[1] / "goldens" / "conformance"

# Renderer and golden-file suffix per backend; svg goldens are .svg so
# they open directly in a browser
BACKENDS: dict[str, tuple[Callable[[Scene], str], str]] = {
    "ascii": (lambda scene: AsciiRenderer(use_colors=True).render(scene), "txt"),
    "svg": (lambda scene: SvgRenderer().render(scene), "svg"),
}


def kitchen_sink_scene(grid: Grid) -> Scene:
    """Every element kind in one scene, built from the grid's own
    vocabulary only, so any registered grid can render it."""
    # FRAME rather than FULL: a full lattice junction-resolves every vertex
    # position, which would paint over the VertexMark below (junctions
    # deliberately win); the frame still exercises heavy strokes and
    # mixed-weight junctions, and vertex dots materialize every lane
    scene = Scene(
        grid,
        style=SceneStyle(lattice=Lattice.FRAME, frame_weight=EdgeWeight.HEAVY, vertex_dots=True),
    )
    cells = list(grid.all_cells())
    directions = grid.orthogonal_direction_names
    scene.add(
        CellFill(cells[0], PaletteColor.GREEN),
        CellFill(cells[1], PaletteColor.GREEN),  # adjacent equal fills: continuity pass
        CellFill(cells[2], Rgb(200, 100, 50)),  # exact color through the quantizer
        CellGlyph(cells[0], Glyph("g", svg="🌟"), color=PaletteColor.BRIGHT_WHITE),
        CellPath(cells[3], frozenset(directions[:2]), color=PaletteColor.CYAN),
        CellLink(cells[4], cells[5], glyph=Glyph("x"), color=PaletteColor.MAGENTA),
        EdgeSegment(grid.edge(cells[0], directions[0]), color=PaletteColor.RED),
        EdgeSegment(grid.edge(cells[5], directions[1]), weight=EdgeWeight.HEAVY),
        # An interior corner: frame corners are junction-flagged, and
        # junction resolution deliberately wins over vertex marks
        VertexMark(grid.vertex(cells[0], grid.corner_names[2]), glyph=Glyph("o")),
        CellMark(cells[7], ring=True),  # shape channel: open ring in SVG, dot char in ASCII
        EdgeMark(grid.edge(cells[8], directions[1])),  # default dot at an edge midpoint
    )
    for index, text in enumerate(("10", "2", "300"), start=1):
        scene.add(OutsideLabel(grid.line_direction_names[0], index, Glyph(text)))
    return scene


@pytest.mark.parametrize("backend", sorted(BACKENDS))
@pytest.mark.parametrize("grid_factory", ALL_GRID_FACTORIES, ids=lambda f: f.__name__)
def test_kitchen_sink_golden(grid_factory: Callable[[], Grid], backend: str, update_goldens: bool) -> None:
    scene = kitchen_sink_scene(grid_factory())
    render, suffix = BACKENDS[backend]
    text = render(scene)

    golden_path = GOLDEN_ROOT / f"{grid_factory.__name__}-{backend}.{suffix}"
    if update_goldens:
        golden_path.parent.mkdir(parents=True, exist_ok=True)
        golden_path.write_text(text)
        return
    assert golden_path.exists(), f"Missing golden {golden_path}; generate with --update-goldens"
    assert text == golden_path.read_text(), (
        f"conformance/{golden_path.name} differs from its golden; if the change is intentional, "
        f"re-bless with: pytest tests/rendering/test_conformance_scene.py --update-goldens"
    )
