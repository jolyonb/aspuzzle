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
    letters (10 -> 'A', 35 -> 'Z'), keeping values one character wide on
    character grids; values outside 0..35 have no single-character form
    and raise. Values above 9 carry their literal number as the sheet
    variant — a spreadsheet cell wants "10", not "A". SVG keeps the letter
    so the drawn puzzle matches the terminal render; a solver preferring
    numbers in SVG passes its own Glyph(..., svg=...).
    """
    if not 0 <= value <= 35:
        raise ValueError(f"glyph_for_value covers 0..35 (digits, then A-Z), got {value}")
    if value <= 9:
        return Glyph(str(value))
    return Glyph(chr(ord("A") + value - 10), sheet=str(value))
