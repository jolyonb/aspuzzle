from enum import Enum, auto
from typing import Final


class Backend(Enum):
    """
    The closed set of rendering backends. Closed on purpose, like the
    element union: adding a backend is a conscious cross-cutting decision
    (it revisits every visibility constant, glyph variant slot, renderer,
    and golden).
    """

    ASCII = auto()
    SVG = auto()
    SHEET = auto()  # tab-separated text for spreadsheet paste


type BackendSet = frozenset[Backend]
ALL_BACKENDS: Final[BackendSet] = frozenset(Backend)
ASCII_ONLY: Final[BackendSet] = frozenset({Backend.ASCII})
SVG_ONLY: Final[BackendSet] = frozenset({Backend.SVG})
SHEET_ONLY: Final[BackendSet] = frozenset({Backend.SHEET})
