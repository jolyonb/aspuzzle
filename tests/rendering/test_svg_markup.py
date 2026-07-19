"""The SVG markup escape: scene text can contain markup metacharacters
(Galaxies' clue glyphs are < and >), and everything must survive."""

from aspuzzle.rendering.svg import escape


def test_escape_handles_markup_metacharacters() -> None:
    assert escape("<") == "&lt;"
    assert escape(">") == "&gt;"
    assert escape("&") == "&amp;"
    assert escape('"') == "&quot;"
    assert escape("A") == "A"
