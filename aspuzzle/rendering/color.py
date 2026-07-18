from dataclasses import dataclass
from enum import Enum, auto


class PaletteColor(Enum):
    """
    Semantic named colors. Backends map them: the ASCII theme to ANSI SGR
    codes, the SVG theme to designed hex values. The 16 names deliberately
    match terminal capability so ASCII output is never an approximation of
    the model. Foreground vs background is carried by where a color is used
    (a glyph's color vs a fill's color), not by parallel enums; None in a
    color-valued field means "inherit / terminal default".
    """

    BLACK = auto()
    RED = auto()
    GREEN = auto()
    YELLOW = auto()
    BLUE = auto()
    MAGENTA = auto()
    CYAN = auto()
    WHITE = auto()
    BRIGHT_BLACK = auto()
    BRIGHT_RED = auto()
    BRIGHT_GREEN = auto()
    BRIGHT_YELLOW = auto()
    BRIGHT_BLUE = auto()
    BRIGHT_MAGENTA = auto()
    BRIGHT_CYAN = auto()
    BRIGHT_WHITE = auto()


@dataclass(frozen=True)
class Rgb:
    """
    Exact color for backends that support it. The ASCII theme quantizes to
    the nearest PaletteColor (truecolor emission is a later theme extension,
    invisible to solvers).
    """

    r: int
    g: int
    b: int

    def __post_init__(self) -> None:
        for channel in ("r", "g", "b"):
            value = getattr(self, channel)
            if not isinstance(value, int) or not 0 <= value <= 255:
                raise ValueError(f"Rgb.{channel} must be an integer in 0..255, got {value!r}")


type ColorSpec = PaletteColor | Rgb
