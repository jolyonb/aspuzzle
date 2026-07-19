"""
The ASCII compositing surface: a rows x cols field of styled characters
that geometries paint onto and the renderer serializes. Holds the
transparency rule (None preserves a channel) in exactly one place.
"""

from dataclasses import dataclass

from aspuzzle.rendering.ascii.theme import AsciiTheme
from aspuzzle.rendering.color import ColorSpec


@dataclass(frozen=True)
class CharPos:
    row: int
    col: int


@dataclass(frozen=True)
class TextSpan:
    row: int
    col: int
    width: int


class CharCanvas:
    """
    A styled-character compositing surface: a rows x cols field of
    (char, fg, bg) triples. The transparency rule lives here and only here:
    put() with char=None preserves the character (fill under glyph);
    fg=None / bg=None preserve that color channel.
    """

    def __init__(self, rows: int, cols: int) -> None:
        if rows < 1 or cols < 1:
            raise ValueError(f"Canvas dimensions must be positive, got {rows}x{cols}")
        self.rows = rows
        self.cols = cols
        self._chars: list[list[str]] = [[" "] * cols for _ in range(rows)]
        self._fg: list[list[ColorSpec | None]] = [[None] * cols for _ in range(rows)]
        self._bg: list[list[ColorSpec | None]] = [[None] * cols for _ in range(rows)]

    def _check(self, row: int, col: int) -> None:
        if not (0 <= row < self.rows and 0 <= col < self.cols):
            raise ValueError(f"Position ({row}, {col}) is outside the {self.rows}x{self.cols} canvas")

    def put(
        self,
        pos: CharPos,
        char: str | None = None,
        fg: ColorSpec | None = None,
        bg: ColorSpec | None = None,
    ) -> None:
        """Composite one position; None arguments preserve that channel."""
        self._check(pos.row, pos.col)
        if char is not None:
            if len(char) != 1:
                raise ValueError(f"put() takes a single character, got {char!r}")
            self._chars[pos.row][pos.col] = char
        if fg is not None:
            self._fg[pos.row][pos.col] = fg
        if bg is not None:
            self._bg[pos.row][pos.col] = bg

    def put_text(self, span: TextSpan, text: str, fg: ColorSpec | None = None) -> None:
        """
        Write text into a span, left-aligned. Rejects text wider than the
        span rather than corrupting neighboring columns.
        """
        if len(text) > span.width:
            raise ValueError(
                f"Text {text!r} is {len(text)} chars but the target span is {span.width} wide; "
                f"glyphs must fit their geometry's content width"
            )
        for offset, char in enumerate(text):
            self.put(CharPos(span.row, span.col + offset), char=char, fg=fg)

    def paint_bg(self, span: TextSpan, bg: ColorSpec) -> None:
        """Paint the background channel across a span, preserving chars/fg."""
        for offset in range(span.width):
            self.put(CharPos(span.row, span.col + offset), bg=bg)

    def to_string(self, theme: AsciiTheme, use_colors: bool) -> str:
        """
        Serialize. Each styled character is wrapped fg-code, bg-code, char, reset.
        """
        lines = []
        for row in range(self.rows):
            parts = []
            for col in range(self.cols):
                char = self._chars[row][col]
                fg, bg = self._fg[row][col], self._bg[row][col]
                if use_colors and (fg is not None or bg is not None):
                    prefix = (theme.fg(fg) if fg is not None else "") + (theme.bg(bg) if bg is not None else "")
                    parts.append(f"{prefix}{char}{theme.reset}")
                else:
                    parts.append(char)
            lines.append("".join(parts))
        return "\n".join(lines)
