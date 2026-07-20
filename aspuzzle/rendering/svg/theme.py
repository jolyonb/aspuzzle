"""
The ColorSpec-to-hex mapping and every visual constant of the SVG backend:
curated palette, provenance styling (black givens, blue solution
values), stroke widths, font sizes. Lengths come in two kinds —
absolute pixels for the substrate strokes (drawn with
vector-effect:non-scaling-stroke so they stay hairlines at any zoom) and
fractions of the renderer's cell_size for everything that should scale
with the drawing.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from aspuzzle.rendering.color import ColorSpec, PaletteColor, Rgb


@dataclass(frozen=True)
class SvgTheme:
    """
    Constructor-injected into SvgRenderer so tests and callers can restyle
    without touching the renderer. PaletteColor maps through the curated
    `palette`; Rgb passes through verbatim as hex.
    """

    palette: Mapping[PaletteColor, str]
    font_family: str = "Tahoma, Verdana, Roboto, sans-serif"
    # Every other color here assumes this behind it (halo, fill_opacity
    # blending, black strokes) — None renders transparent for callers
    # compositing onto their own known-light background
    background_color: str | None = "#ffffff"
    line_color: str = "#000000"  # lattice, frame, substrate dots
    given_color: str = "#000000"  # clue glyphs and uncolored GIVEN strokes
    derived_color: str = "#1d6ae5"  # solution glyphs and uncolored DERIVED strokes
    halo_color: str = "#ffffff"  # glyph halo so text reads over fills
    fill_opacity: float = 0.5  # cell fills stay light enough for glyphs on top

    # -- absolute pixels (vector-effect: non-scaling-stroke) --
    hairline_width: float = 1.0
    frame_width: float = 3.0

    # -- fractions of cell_size --
    path_width: float = 9 / 64
    link_width: float = 6 / 64
    edge_width: float = 3.5 / 64
    heavy_edge_width: float = 7 / 64
    dot_radius: float = 4 / 64  # substrate vertex dots and default marks
    ring_radius: float = 9 / 64  # open-circle marks (ring=True), e.g. Galaxies centers
    ring_width: float = 3.5 / 64
    halo_width: float = 2 / 64
    # Glyph text by rendered length (1 char, 2 chars, 3+), with a small
    # optical baseline nudge per size; emoji render smaller than the
    # largest text size (their ink fills the whole em square)
    font_sizes: tuple[float, float, float] = (48 / 64, 32 / 64, 24 / 64)
    text_nudges: tuple[float, float, float] = (4 / 64, 2 / 64, 1 / 64)
    emoji_size: float = 40 / 64

    def color(self, spec: ColorSpec) -> str:
        """The hex color a ColorSpec renders as."""
        if isinstance(spec, Rgb):
            return f"#{spec.r:02x}{spec.g:02x}{spec.b:02x}"
        return self.palette[spec]


# Curated hex values for the 16 semantic palette colors, seeded from the
# dbpuzzles/SudokuPad line and categorical palettes: normal entries are the
# saturated glyph-and-stroke tones, bright entries the lighter fill-friendly
# companions (fills additionally soften through fill_opacity).
DEFAULT_SVG_PALETTE: Final[Mapping[PaletteColor, str]] = {
    PaletteColor.BLACK: "#000000",
    PaletteColor.RED: "#e6261f",
    PaletteColor.GREEN: "#76b82a",
    PaletteColor.YELLOW: "#e8b004",
    PaletteColor.BLUE: "#1d6ae5",
    PaletteColor.MAGENTA: "#d23be7",
    PaletteColor.CYAN: "#34bbe6",
    PaletteColor.WHITE: "#cfcfcf",
    PaletteColor.BRIGHT_BLACK: "#5f5f5f",
    PaletteColor.BRIGHT_RED: "#ed635e",
    PaletteColor.BRIGHT_GREEN: "#a3e048",
    PaletteColor.BRIGHT_YELLOW: "#f7d038",
    PaletteColor.BRIGHT_BLUE: "#7ca9f2",
    PaletteColor.BRIGHT_MAGENTA: "#eb8cf2",
    PaletteColor.BRIGHT_CYAN: "#7cd7f2",
    PaletteColor.BRIGHT_WHITE: "#ffffff",
}

DEFAULT_SVG_THEME: Final[SvgTheme] = SvgTheme(palette=DEFAULT_SVG_PALETTE)
