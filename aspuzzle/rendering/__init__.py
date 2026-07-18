"""
The rendering package: a typed, backend-agnostic scene model between
solvers and renderers. Solvers declare WHAT to show (scene elements at
abstract grid locations, semantic colors); grids supply geometry;
renderers (ASCII, SVG, sheet/TSV) paint. This module re-exports the
solver-facing vocabulary.
"""

from aspuzzle.rendering.backend import (
    ALL_BACKENDS,
    ASCII_ONLY,
    SHEET_ONLY,
    SVG_ONLY,
    Backend,
    BackendSet,
)
from aspuzzle.rendering.color import ColorSpec, PaletteColor, Rgb
from aspuzzle.rendering.glyph import Glyph, glyph_for_value
from aspuzzle.rendering.scene import (
    CellFill,
    CellGlyph,
    CellLink,
    CellPath,
    CellStyle,
    Edge,
    EdgeSegment,
    EdgeWeight,
    Layer,
    LayoutNeeds,
    OutsideLabel,
    Provenance,
    Scene,
    SceneElement,
    SceneStyle,
    Vertex,
    VertexMark,
)

__all__ = [
    "ALL_BACKENDS",
    "ASCII_ONLY",
    "SHEET_ONLY",
    "SVG_ONLY",
    "Backend",
    "BackendSet",
    "CellFill",
    "CellGlyph",
    "CellLink",
    "CellPath",
    "CellStyle",
    "ColorSpec",
    "Edge",
    "EdgeSegment",
    "EdgeWeight",
    "Glyph",
    "Layer",
    "LayoutNeeds",
    "OutsideLabel",
    "PaletteColor",
    "Provenance",
    "Rgb",
    "Scene",
    "SceneElement",
    "SceneStyle",
    "Vertex",
    "VertexMark",
    "glyph_for_value",
]
