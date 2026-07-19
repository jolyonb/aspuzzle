"""
The grid-agnostic ASCII renderer: one consumer of the Scene, painting
through whatever AsciiGeometry the scene's grid supplies.
"""

from typing import Final

from aspuzzle.rendering.ascii.canvas import CharCanvas
from aspuzzle.rendering.ascii.theme import DEFAULT_THEME, AsciiTheme
from aspuzzle.rendering.backend import Backend
from aspuzzle.rendering.scene import Scene


class AsciiRenderer:
    """
    The grid-agnostic ASCII painter: asks the scene's grid for a geometry,
    paints the base, then every ASCII-visible element in painter's order,
    resolves junctions, and serializes through the theme. Contains zero
    grid-specific knowledge.
    """

    backend: Final = Backend.ASCII

    def __init__(self, use_colors: bool = True, theme: AsciiTheme = DEFAULT_THEME) -> None:
        self.use_colors = use_colors
        self.theme = theme

    def render(self, scene: Scene) -> str:
        geometry = scene.grid.ascii_geometry(scene.layout_needs(self.backend), scene.style_for(self.backend))
        canvas = CharCanvas(*geometry.size())
        geometry.paint_base(canvas)
        for element in scene.sorted_elements(self.backend):
            geometry.paint(canvas, element)
        geometry.resolve_junctions(canvas)
        return canvas.to_string(self.theme, self.use_colors)
