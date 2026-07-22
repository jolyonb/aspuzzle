from aspalchemy import ANY, Choice, Count, Field, Predicate, RangePool, V
from aspuzzle.grids.base import GridCell
from aspuzzle.grids.rectangulargrid import RectangularGrid
from aspuzzle.rendering import (
    ASCII_ONLY,
    SVG_ONLY,
    FromPredicate,
    RegionBorderRule,
    RegionFillRule,
    RenderSpec,
    SceneStyle,
    digit_clues,
)
from aspuzzle.rendering import PaletteColor as Color
from aspuzzle.solver import Solver


class Clue(Predicate, show=False):
    loc: Field[GridCell]
    area: Field[int]
    id: Field[int]


class Shape(Predicate, show=False):
    area: Field[int]
    height: Field[int]
    width: Field[int]


class Candidate(Predicate, show=False):
    id: Field[int]
    top: Field[int]
    left: Field[int]
    height: Field[int]
    width: Field[int]


class Placement(Predicate, show=False):
    id: Field[int]
    top: Field[int]
    left: Field[int]
    height: Field[int]
    width: Field[int]


class Rectangle(Predicate):
    loc: Field[GridCell]
    id: Field[int]


class Shikaku(Solver[RectangularGrid]):
    """
    Shikaku tiles the grid with one rectangle per clue, of the clued area.

    The rectangle itself is the unknown, so the rectangle is what gets
    guessed: a rectangle of area N covering its clue is fixed by its top-left
    corner and its width, and the rules enumerate those placements before any
    choice is made. Every guess is then a valid rectangle of the right area by
    construction, and the only thing left to solve is how they fit together —
    coverage and overlap.

    RegionConstructor is emphatically the wrong tool here - it constructs regions
    cell by cell, which is much more expensive than just constructing rectangles.
    """

    solver_name = "Shikaku puzzle solver"
    supported_grid_types = (RectangularGrid,)
    supported_symbols = (".", *range(1, 1000))  # Support areas 1-999

    def validate_config(self) -> None:
        """The clued areas must exactly tile the grid."""
        grid = self.grid

        total = sum(area for _loc, area in self.int_grid_data)
        cells = grid.rows * grid.cols
        if total != cells:
            raise ValueError(f"Clue areas sum to {total}, but the grid has {cells} cells")

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, _config, _grid_data = self.unpack_data()

        clues = puzzle.add_segment("Clues")
        clues.section("Define the clued rectangle areas")
        clues.fact(
            *[
                Clue(loc=grid.Cell(*loc), area=area, id=clue_id)
                for clue_id, (loc, area) in enumerate(self.int_grid_data, 1)
            ]
        )

        Idx, T, L, H, W, N = V.Idx, V.T, V.L, V.H, V.W, V.N
        R, C = V.R, V.C
        cell = grid.cell()

        # The shapes an area can take
        puzzle.section("The shapes a clued area can take")
        puzzle.when(
            Clue(loc=ANY, area=N, id=ANY),
            H.in_(RangePool(1, N)),
            W == N // H,
            W * H == N,
            H <= grid.rows,
            W <= grid.cols,
        ).derive(Shape(area=N, height=H, width=W))

        # Every placement of every shape that covers its own clue and stays on
        # the board, less those covering somebody else's clue — a rectangle
        # holds exactly one number. That last filter is implied by the overlap
        # rule (a clue always lies in its own rectangle) but only reachable by
        # search; imposed here the placement never exists.
        puzzle.section("Every rectangle each clue could be")
        clue_row, clue_col = cell["row"], cell["col"]
        other = grid.cell(suffix="other")
        puzzle.when(
            Clue(loc=cell, area=N, id=Idx),
            Shape(area=N, height=H, width=W),
            T.in_(RangePool(clue_row - H + 1, clue_row)),
            L.in_(RangePool(clue_col - W + 1, clue_col)),
            T >= 1,
            L >= 1,
            T + H - 1 <= grid.rows,
            L + W - 1 <= grid.cols,
            Count(
                other,
                condition=[
                    Clue(loc=other, area=ANY, id=ANY),
                    other["row"] >= T,
                    other["row"] <= T + H - 1,
                    other["col"] >= L,
                    other["col"] <= L + W - 1,
                ],
            )
            == 1,
        ).derive(Candidate(id=Idx, top=T, left=L, height=H, width=W))

        puzzle.section("Each clue takes exactly one of its rectangles")
        puzzle.when(Clue(loc=ANY, area=ANY, id=Idx)).choose(
            Choice(
                Placement(id=Idx, top=T, left=L, height=H, width=W),
                condition=Candidate(id=Idx, top=T, left=L, height=H, width=W),
            ).exactly(1)
        )

        puzzle.section("A placed rectangle covers its cells")
        puzzle.when(
            Placement(id=Idx, top=T, left=L, height=H, width=W),
            R.in_(RangePool(T, T + H - 1)),
            C.in_(RangePool(L, L + W - 1)),
        ).derive(Rectangle(loc=grid.Cell(row=R, col=C), id=Idx))

        # Coverage and overlap stated apart, not as one count per cell: each
        # gives the solver a fact it can propagate from directly — this cell
        # is still uncovered, these two rectangles clash — and that halves
        # the search against the single aggregate
        puzzle.section("The rectangles tile the grid")
        puzzle.when(cell).require(Rectangle(loc=cell, id=ANY))
        puzzle.forbid(Rectangle(loc=cell, id=Idx[1]), Rectangle(loc=cell, id=Idx[2]), Idx[1] < Idx[2])

    def get_render_spec(self) -> RenderSpec:
        clues = digit_clues(range(1, 1000))
        return RenderSpec(
            clues=clues,
            atoms=[
                RegionFillRule(FromPredicate(Rectangle), backends=ASCII_ONLY),
                RegionBorderRule(source=FromPredicate(Rectangle), color=Color.BLACK, backends=SVG_ONLY),
            ],
            style=SceneStyle(packed=True),
        )
