"""
The ColorSpec-to-ANSI mapping — the only module in the system permitted to
contain escape codes (enforced by the import-boundary tests).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from aspuzzle.rendering.color import ColorSpec, PaletteColor, Rgb

# Reference sRGB values for the 16-color terminal palette (classic VGA),
# used only to quantize Rgb requests to the nearest palette entry.
_PALETTE_RGB: Final[Mapping[PaletteColor, tuple[int, int, int]]] = {
    PaletteColor.BLACK: (0, 0, 0),
    PaletteColor.RED: (170, 0, 0),
    PaletteColor.GREEN: (0, 170, 0),
    PaletteColor.YELLOW: (170, 85, 0),
    PaletteColor.BLUE: (0, 0, 170),
    PaletteColor.MAGENTA: (170, 0, 170),
    PaletteColor.CYAN: (0, 170, 170),
    PaletteColor.WHITE: (170, 170, 170),
    PaletteColor.BRIGHT_BLACK: (85, 85, 85),
    PaletteColor.BRIGHT_RED: (255, 85, 85),
    PaletteColor.BRIGHT_GREEN: (85, 255, 85),
    PaletteColor.BRIGHT_YELLOW: (255, 255, 85),
    PaletteColor.BRIGHT_BLUE: (85, 85, 255),
    PaletteColor.BRIGHT_MAGENTA: (255, 85, 255),
    PaletteColor.BRIGHT_CYAN: (85, 255, 255),
    PaletteColor.BRIGHT_WHITE: (255, 255, 255),
}


def _nearest_palette(color: Rgb) -> PaletteColor:
    return min(
        _PALETTE_RGB,
        key=lambda p: (
            (_PALETTE_RGB[p][0] - color.r) ** 2
            + (_PALETTE_RGB[p][1] - color.g) ** 2
            + (_PALETTE_RGB[p][2] - color.b) ** 2
        ),
    )


@dataclass(frozen=True)
class AsciiTheme:
    """
    The ColorSpec-to-ANSI mapping — the only place in the system where
    escape codes exist. Constructor-injected into AsciiRenderer so tests
    can pin SGR placement with minimal themes. Rgb quantizes to the
    nearest palette entry.
    """

    fg_codes: Mapping[PaletteColor, str]
    bg_codes: Mapping[PaletteColor, str]
    reset: str = "\033[0m"
    # Ink for an uncolored character sitting on a cell fill. The terminal's
    # own default is no use there: it is dark on a light-background profile
    # and light on a dark one, while the fill under it is neither, so one of
    # the two profiles always loses. Picking by the fill's luminance instead
    # reads on both. A character with no fill keeps the inherited default,
    # which is the one case that does adapt to the profile by itself.
    ink_on_dark_fill: PaletteColor = PaletteColor.BRIGHT_WHITE
    ink_on_light_fill: PaletteColor = PaletteColor.BLACK

    def fg(self, color: ColorSpec) -> str:
        if isinstance(color, Rgb):
            color = _nearest_palette(color)
        return self.fg_codes[color]

    def bg(self, color: ColorSpec) -> str:
        if isinstance(color, Rgb):
            color = _nearest_palette(color)
        return self.bg_codes[color]

    def ink_on(self, fill: ColorSpec) -> PaletteColor:
        """The ink an uncolored character takes when it sits on `fill`,
        by the fill's perceived brightness."""
        if isinstance(fill, Rgb):
            fill = _nearest_palette(fill)
        red, green, blue = _PALETTE_RGB[fill]
        luminance = 0.299 * red + 0.587 * green + 0.114 * blue
        return self.ink_on_light_fill if luminance > 140 else self.ink_on_dark_fill


def _sgr(code: int) -> str:
    return f"\033[{code}m"


# The standard 16-color SGR code tables.
DEFAULT_THEME: Final[AsciiTheme] = AsciiTheme(
    fg_codes={
        PaletteColor.BLACK: _sgr(30),
        PaletteColor.RED: _sgr(31),
        PaletteColor.GREEN: _sgr(32),
        PaletteColor.YELLOW: _sgr(33),
        PaletteColor.BLUE: _sgr(34),
        PaletteColor.MAGENTA: _sgr(35),
        PaletteColor.CYAN: _sgr(36),
        PaletteColor.WHITE: _sgr(37),
        PaletteColor.BRIGHT_BLACK: _sgr(90),
        PaletteColor.BRIGHT_RED: _sgr(91),
        PaletteColor.BRIGHT_GREEN: _sgr(92),
        PaletteColor.BRIGHT_YELLOW: _sgr(93),
        PaletteColor.BRIGHT_BLUE: _sgr(94),
        PaletteColor.BRIGHT_MAGENTA: _sgr(95),
        PaletteColor.BRIGHT_CYAN: _sgr(96),
        PaletteColor.BRIGHT_WHITE: _sgr(97),
    },
    bg_codes={
        PaletteColor.BLACK: _sgr(40),
        PaletteColor.RED: _sgr(41),
        PaletteColor.GREEN: _sgr(42),
        PaletteColor.YELLOW: _sgr(43),
        PaletteColor.BLUE: _sgr(44),
        PaletteColor.MAGENTA: _sgr(45),
        PaletteColor.CYAN: _sgr(46),
        PaletteColor.WHITE: _sgr(47),
        PaletteColor.BRIGHT_BLACK: _sgr(100),
        PaletteColor.BRIGHT_RED: _sgr(101),
        PaletteColor.BRIGHT_GREEN: _sgr(102),
        PaletteColor.BRIGHT_YELLOW: _sgr(103),
        PaletteColor.BRIGHT_BLUE: _sgr(104),
        PaletteColor.BRIGHT_MAGENTA: _sgr(105),
        PaletteColor.BRIGHT_CYAN: _sgr(106),
        PaletteColor.BRIGHT_WHITE: _sgr(107),
    },
)
