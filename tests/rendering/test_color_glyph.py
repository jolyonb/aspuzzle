import pytest

from aspuzzle.rendering import Backend, Glyph, PaletteColor, Rgb, glyph_for_value


def test_palette_has_sixteen_semantic_colors() -> None:
    assert len(PaletteColor) == 16
    # Semantic tokens, not ANSI: no member's value is an escape string
    assert all(isinstance(color.value, int) for color in PaletteColor)


def test_rgb_validates_channels() -> None:
    assert Rgb(0, 128, 255) == Rgb(0, 128, 255)
    with pytest.raises(ValueError, match=r"Rgb\.r"):
        Rgb(-1, 0, 0)
    with pytest.raises(ValueError, match=r"Rgb\.g"):
        Rgb(0, 256, 0)
    with pytest.raises(ValueError, match=r"Rgb\.b"):
        Rgb(0, 0, 1000)


def test_glyph_rejects_empty_text() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        Glyph("")


def test_glyph_backend_variants() -> None:
    tent = Glyph("A", svg="⛺")
    assert tent.for_backend(Backend.ASCII) == "A"
    assert tent.for_backend(Backend.SVG) == "⛺"
    assert tent.for_backend(Backend.SHEET) == "A"  # no override: baseline

    plain = Glyph("T")
    assert all(plain.for_backend(b) == "T" for b in Backend)

    with pytest.raises(ValueError, match="svg override"):
        Glyph("A", svg="")


def test_glyph_for_value_digit_letter_convention() -> None:
    assert glyph_for_value(0) == Glyph("0")
    assert glyph_for_value(9) == Glyph("9")
    # 10+ compacts to a letter only where columns are being counted; the
    # backends with room for it get the literal number
    assert glyph_for_value(10) == Glyph("A", svg="10", sheet="10")
    assert glyph_for_value(35) == Glyph("Z", svg="35", sheet="35")
    assert glyph_for_value(10).for_backend(Backend.ASCII) == "A"
    assert glyph_for_value(10).for_backend(Backend.SHEET) == "10"
    assert glyph_for_value(10).for_backend(Backend.SVG) == "10"
    # Past Z a character grid gives up and prints #, but the backends with
    # room keep the number, so every value from 0 up renders
    assert glyph_for_value(36) == Glyph("#", svg="36", sheet="36")
    assert glyph_for_value(294).for_backend(Backend.ASCII) == "#"
    assert glyph_for_value(294).for_backend(Backend.SVG) == "294"
    # Below zero there is nothing to draw
    with pytest.raises(ValueError, match="from 0 up"):
        glyph_for_value(-1)
