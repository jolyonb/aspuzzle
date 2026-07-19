import pytest

from aspuzzle.rendering import PaletteColor
from aspuzzle.rendering.ascii import DEFAULT_THEME, AsciiTheme, CharCanvas, CharPos, TextSpan


def test_put_transparency_rules() -> None:
    canvas = CharCanvas(1, 1)
    pos = CharPos(0, 0)

    canvas.put(pos, char="5", fg=PaletteColor.GREEN)
    canvas.put(pos, bg=PaletteColor.RED)  # fill over glyph: char and fg preserved
    themed = canvas.to_string(DEFAULT_THEME, use_colors=True)
    assert themed == "\033[32m\033[41m5\033[0m"  # fg then bg, char, reset

    canvas.put(pos, char="7")  # glyph without colors: fg/bg preserved
    assert canvas.to_string(DEFAULT_THEME, use_colors=True) == "\033[32m\033[41m7\033[0m"


def test_put_rejects_bad_input() -> None:
    canvas = CharCanvas(2, 2)
    with pytest.raises(ValueError, match="single character"):
        canvas.put(CharPos(0, 0), char="ab")
    with pytest.raises(ValueError, match="outside"):
        canvas.put(CharPos(2, 0), char="x")
    with pytest.raises(ValueError, match="positive"):
        CharCanvas(0, 3)


def test_put_text_rejects_overflow_with_precise_error() -> None:
    canvas = CharCanvas(1, 3)
    with pytest.raises(ValueError, match="2 chars but the target span is 1 wide"):
        canvas.put_text(TextSpan(0, 0, 1), "10")
    # Shorter than the span is fine and leaves the rest untouched
    canvas.put_text(TextSpan(0, 0, 3), "ab")
    assert canvas.to_string(DEFAULT_THEME, use_colors=False) == "ab "


def test_paint_bg_spans_and_uncolored_output() -> None:
    canvas = CharCanvas(1, 3)
    canvas.put(CharPos(0, 0), char="x")
    canvas.paint_bg(TextSpan(0, 0, 2), PaletteColor.BLUE)
    plain = canvas.to_string(DEFAULT_THEME, use_colors=False)
    assert plain == "x  "  # use_colors=False: no escapes at all
    themed = canvas.to_string(DEFAULT_THEME, use_colors=True)
    assert themed == "\033[44mx\033[0m\033[44m \033[0m "


def test_injected_minimal_theme_pins_sgr_placement() -> None:
    theme = AsciiTheme(
        fg_codes={PaletteColor.RED: "<r>"},
        bg_codes={PaletteColor.GREEN: "[G]"},
        reset="<X>",
    )
    canvas = CharCanvas(1, 2)
    canvas.put(CharPos(0, 0), char="a", fg=PaletteColor.RED, bg=PaletteColor.GREEN)
    canvas.put(CharPos(0, 1), char="b")
    assert canvas.to_string(theme, use_colors=True) == "<r>[G]a<X>b"


def test_rgb_quantizes_to_nearest_palette_entry() -> None:
    from aspuzzle.rendering import Rgb

    assert DEFAULT_THEME.fg(Rgb(250, 80, 90)) == DEFAULT_THEME.fg(PaletteColor.BRIGHT_RED)
    assert DEFAULT_THEME.bg(Rgb(5, 5, 5)) == DEFAULT_THEME.bg(PaletteColor.BLACK)
