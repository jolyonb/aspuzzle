"""
Markup safety for the SVG backend: every piece of scene text (glyphs,
labels) must pass through escape() on its way into markup — Galaxies'
clue glyphs are literally "<" and ">".
"""

from xml.sax.saxutils import escape as _xml_escape


def escape(text: str) -> str:
    """Escape text for SVG element content and attribute values."""
    return _xml_escape(text, {'"': "&quot;", "'": "&apos;"})
