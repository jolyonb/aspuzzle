from collections.abc import Sequence

from aspalchemy import ANY, Field, Predicate, V
from aspuzzle.grids.base import GridCell
from aspuzzle.grids.rectangulargrid import RectangularGrid
from aspuzzle.regionconstructor import RegionConstructor
from aspuzzle.rendering import (
    CHARACTER_BACKENDS,
    SVG_ONLY,
    CellMark,
    CellStyle,
    CustomRule,
    EdgeMark,
    FromPredicate,
    Glyph,
    Layer,
    Provenance,
    RegionFillRule,
    RenderContext,
    RenderSpec,
    SceneElement,
    SceneStyle,
    VertexMark,
)
from aspuzzle.rendering import PaletteColor as Color
from aspuzzle.solvers.base import Solver


class Center(Predicate, show=False):
    loc: Field[GridCell]
    loc2: Field[GridCell]
    id: Field[int]


class Galaxy(Predicate):
    loc: Field[GridCell]
    id: Field[int]


class Galaxies(Solver):
    """
    This is a galaxies solver on a rectangular grid.

    Because the point symmetry rule is intrinsically tied to the geometry of the grid, we will implement separate
    solvers for different grid geometries.
    """

    solver_name = "Spiral Galaxies solver"
    supported_grid_types = (RectangularGrid,)
    supported_symbols = (".", "o", "<", ">", "^", "v", 1, 2, 3, 4)

    def validate_config(self) -> None:
        """Validate the puzzle configuration."""
        self.process_data()

    def process_data(self) -> list[tuple[tuple[int, int], tuple[int, int], int]]:
        """
        Process the grid data to identify galaxy centers and their positions.

        Returns:
            List of (center_position1, center_position2, region_id) tuples.
            For centers in cells, position1 = position2.
            For centers at edges or corners, position1 and position2 are the adjacent cells that average to the center.
        """
        # Parse the grid to find all markers
        cell_markers = {}
        for r, row in enumerate(self.config["grid"], 1):
            for c, symbol in enumerate(row, 1):
                if symbol != ".":
                    cell_markers[(r, c)] = symbol

        # Process the markers to identify centers
        centers: list[tuple[tuple[int, int], tuple[int, int], int]] = []
        processed = set()
        region_id = 1

        for (r, c), symbol in cell_markers.items():
            if (r, c) in processed:
                continue

            if symbol == "1":
                # For a "1" cell at (r,c), we need to check if "2", "3", and "4" are present
                # in their expected positions
                expected = {
                    "2": (r, c + 1),  # Top-right
                    "3": (r + 1, c),  # Bottom-left
                    "4": (r + 1, c + 1),  # Bottom-right
                }
                valid = not any(
                    pos not in cell_markers or cell_markers[pos] != expected_symbol
                    for expected_symbol, pos in expected.items()
                )
                if not valid:
                    raise ValueError(f"Incomplete vertex definition at cell ({r}, {c})")
                centers.append(((r, c), (r + 1, c + 1), region_id))
                processed.add((r, c))
                processed.add((r, c + 1))
                processed.add((r + 1, c))
                processed.add((r + 1, c + 1))
                region_id += 1

            elif symbol == "<":
                # For a "<" cell at (r,c), we need to check if ">" is present next to it
                if (r, c + 1) not in cell_markers or cell_markers[(r, c + 1)] != ">":
                    raise ValueError(f"Incomplete vertex definition at cell ({r}, {c})")
                centers.append(((r, c), (r, c + 1), region_id))
                processed.add((r, c))
                processed.add((r, c + 1))
                region_id += 1

            elif symbol == "^":
                # For a "^" cell at (r,c), we need to check if "v" is present below it
                if (r + 1, c) not in cell_markers or cell_markers[(r + 1, c)] != "v":
                    raise ValueError(f"Incomplete vertex definition at cell ({r}, {c})")
                centers.append(((r, c), (r + 1, c), region_id))
                processed.add((r, c))
                processed.add((r + 1, c))
                region_id += 1

            elif symbol == "o":
                centers.append(((r, c), (r, c), region_id))
                processed.add((r, c))
                region_id += 1

        # Check for orphaned characters
        if orphaned := set(cell_markers.keys()) - processed:
            orphaned_symbols = {pos: cell_markers[pos] for pos in orphaned}
            raise ValueError(f"Orphaned galaxy markers detected: {orphaned_symbols}")

        return centers

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, _config, _grid_data = self.unpack_data()
        assert isinstance(grid, RectangularGrid)

        # Define clues - the clues contain cells on either side of the center
        clues = puzzle.add_segment("Clues")
        clues.fact(
            *[
                Center(loc=grid.Cell(*loc1), loc2=grid.Cell(*loc2), id=region_id)
                for loc1, loc2, region_id in self.process_data()
            ]
        )

        # Divide the grid into regions using the first cell in each clue as an anchor.
        # Membership domain: a cell can only belong to a center whose mirror image of
        # that cell stays on the board — the symmetry rule forces the mirror into the
        # same galaxy, so an off-board mirror rules the pairing out entirely.
        cell, anchor = grid.cell(), grid.cell(suffix="anchor")
        R2, C2 = V.R2, V.C2
        mirror_row = anchor.row + R2 - cell.row
        mirror_col = anchor.col + C2 - cell.col
        region_constructor = RegionConstructor(
            puzzle=puzzle,
            grid=grid,
            anchor_predicate=Center,
            anchor_fields={"loc2": ANY, "id": ANY},
            allow_regionless=False,
            region_domain=[
                Center(loc=anchor, loc2=grid.Cell(row=R2, col=C2), id=ANY),
                mirror_row >= 1,
                mirror_row <= grid.rows,
                mirror_col >= 1,
                mirror_col <= grid.cols,
            ],
        )

        # Impose the symmetry constraint
        puzzle.section("Symmetry rule")
        R, C = V.R, V.C  # R[1]/C[1] and R[2]/C[2] are the two cells flanking the center
        puzzle.when(
            Center(loc=grid.Cell(R[1], C[1]), loc2=grid.Cell(R[2], C[2]), id=ANY),
            region_constructor.Region(loc=grid.Cell(R, C), anchor=grid.Cell(R[1], C[1])),
        ).require(
            region_constructor.Region(loc=grid.Cell(R[1] + R[2] - R, C[1] + C[2] - C), anchor=grid.Cell(R[1], C[1]))
        )

        # Define a predicate to extract the regions from the puzzle for solution display purposes
        puzzle.section("Solution extraction")
        puzzle.when(
            region_constructor.Region(loc=V.Loc, anchor=V.A),
            Center(loc=V.A, loc2=ANY, id=V.Id),
        ).derive(Galaxy(loc=V.Loc, id=V.Id))

    def get_render_spec(self) -> RenderSpec:
        # The grid symbols are the character-art encoding of the centers
        # (halves and quarters of a marker spread over the flanking cells);
        # backends with real geometry draw ring marks at the true center
        # positions instead
        # Symbol -> art character: the five markers render themselves, the
        # four corner quarters render as slashes
        art: dict[int | str, str] = {symbol: symbol for symbol in ("o", "^", "v", "<", ">")}
        art |= {1: "/", 2: "\\", 3: "\\", 4: "/"}
        clues = {symbol: CellStyle(glyph=Glyph(char), backends=CHARACTER_BACKENDS) for symbol, char in art.items()}

        grid = self.grid
        centers = self.process_data()

        def center_marks(atoms: Sequence[Predicate], context: RenderContext) -> list[SceneElement]:
            # Centers are puzzle input: the marks come from the parsed
            # config, not solution atoms. A center's two flanking cells are
            # equal (cell center), orthogonal (edge midpoint), or diagonal
            # (shared vertex).
            marks: list[SceneElement] = []
            for (r1, c1), (r2, c2), _region in centers:
                cell = grid.Cell(r1, c1)
                dr, dc = r2 - r1, c2 - c1
                if (dr, dc) == (0, 0):
                    marks.append(CellMark(cell, ring=True, layer=Layer.ANNOTATION, provenance=Provenance.GIVEN))
                elif dr != 0 and dc != 0:
                    corner = ("s" if dr > 0 else "n") + ("e" if dc > 0 else "w")
                    marks.append(
                        VertexMark(
                            grid.vertex(cell, corner), ring=True, layer=Layer.ANNOTATION, provenance=Provenance.GIVEN
                        )
                    )
                else:
                    direction = {(1, 0): "s", (-1, 0): "n", (0, 1): "e", (0, -1): "w"}[(dr, dc)]
                    marks.append(
                        EdgeMark(
                            grid.edge(cell, direction), ring=True, layer=Layer.ANNOTATION, provenance=Provenance.GIVEN
                        )
                    )
            return marks

        return RenderSpec(
            clues=clues,
            atoms=[
                RegionFillRule(
                    FromPredicate(Galaxy),
                    palette=(Color.YELLOW, Color.BRIGHT_BLUE, Color.GREEN, Color.RED),
                ),
                CustomRule(make=center_marks, backends=SVG_ONLY),
            ],
            style=SceneStyle(packed=True),
        )
