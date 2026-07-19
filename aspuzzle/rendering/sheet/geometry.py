"""
The sheet geometry contract: how a grid maps cells and outside labels onto
(sheet_row, sheet_col) spreadsheet coordinates for the TSV renderer.
"""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from aspuzzle.grids.base import GridCell


class SheetGeometry(Protocol):
    """Constructed per render by Grid.sheet_geometry(needs); consumes
    LayoutNeeds so label margins reserve real sheet rows/columns."""

    def size(self) -> tuple[int, int]: ...

    def cell_pos(self, cell: GridCell) -> tuple[int, int]: ...

    def label_pos(self, direction: str, index: int, offset: int) -> tuple[int, int]: ...
