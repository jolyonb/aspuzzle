"""
Renderable text marks. A Glyph carries a width-constrained baseline plus
optional per-backend variants (svg=, sheet=), resolved by each renderer via
for_backend(); glyph_for_value is the single home of the 0-9/A+ digit
convention for character grids.
"""

from dataclasses import dataclass

from aspuzzle.rendering.backend import Backend


@dataclass(frozen=True)
class Glyph:
    """
    A renderable text mark with optional per-backend variants.

    `text` is the baseline every backend falls back to. Keep it one
    grapheme: character-grid geometries enforce their content width (1 char
    on rectangular grids), and emoji are double-width in terminals, which
    breaks column alignment. Richer backends may override — `svg` for
    full-fidelity marks (emoji welcome), `sheet` for spreadsheet cells
    (no width limit) — e.g. Glyph("A", svg="⛺") renders a tent as 'A' in
    the terminal and as the emoji in SVG, from one element.
    """

    text: str
    svg: str | None = None
    sheet: str | None = None

    def __post_init__(self) -> None:
        if not self.text:
            raise ValueError("Glyph text must be non-empty")
        for variant in ("svg", "sheet"):
            override = getattr(self, variant)
            if override == "":
                raise ValueError(f"Glyph {variant} override must be non-empty when given")

    def for_backend(self, backend: Backend) -> str:
        """The text this backend renders: its override if set, else `text`."""
        if backend is Backend.SVG and self.svg is not None:
            return self.svg
        if backend is Backend.SHEET and self.sheet is not None:
            return self.sheet
        return self.text


def glyph_for_value(value: int) -> Glyph:
    """
    The single home of the digit convention: 0-9 as digits, 10-35 as
    letters (10 -> 'A', 35 -> 'Z'), and '#' beyond that — a character grid
    has one column to spend and nothing better to put in it. Both are
    compromises for grids that count columns, so backends that do not take
    the literal number throughout: a spreadsheet cell wants "10" rather
    than "A", and so does a drawn puzzle — SVG sets its own type size by
    rendered length, so a longer number simply comes out smaller.

    Every value from 0 up renders, so a caller with a wide clue range needs
    no second table; overflow_clues remains for solvers that want '#' below
    36 as well (Cave rings its large clues that way).
    """
    if value < 0:
        raise ValueError(f"glyph_for_value covers values from 0 up, got {value}")

    number = str(value)
    if value <= 9:
        character = number
    elif value <= 35:
        character = chr(ord("A") + value - 10)
    else:
        character = "#"

    # A single digit already is the number; a letter or a # is a stand-in for
    # it, and only then do the roomier backends need telling what it stands for
    stands_in = character != number
    return Glyph(character, svg=number if stands_in else None, sheet=number if stands_in else None)
