from aspalchemy import ANY, Choice, Count, Field, Predicate, PredicateArg, V
from aspuzzle.grids.base import GridCell
from aspuzzle.rendering import PaletteColor as Color
from aspuzzle.rendering import PathRule, RenderSpec, SceneStyle, symbol_clues, symbol_colorer
from aspuzzle.solvers.base import Solver


class Symbol(Predicate, show=False):
    """A numbered endpoint clue; sym is an opaque label (int or str)."""

    loc: Field[GridCell]
    sym: Field[PredicateArg]


class HasSymbol(Predicate, show=False):
    loc: Field[GridCell]


class PathDegree(Predicate, show=False):
    loc: Field[GridCell]
    degree: Field[int]


class Path(Predicate, show=False):
    loc: Field[GridCell]
    direction: Field[str]


class PropagatedSymbol(Predicate, show=False):
    loc: Field[GridCell]
    sym: Field[PredicateArg]


class Connected(Predicate, show=False):
    loc1: Field[GridCell]
    loc2: Field[GridCell]


class CellDirections(Predicate):
    """A path passes through loc via dir1/dir2; sym carries the pair
    identity so renderers can color each path like its endpoint clues."""

    loc: Field[GridCell]
    dir1: Field[str]
    dir2: Field[str]
    sym: Field[PredicateArg]


class EndpointDirection(Predicate):
    """The single direction a pair's path leaves its endpoint clue in, so
    renderers can draw the path into the numbered cell."""

    loc: Field[GridCell]
    direction: Field[str]
    sym: Field[PredicateArg]


class Numberlink(Solver):
    solver_name = "Numberlink puzzle solver"

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, _config, grid_data = self.unpack_data()

        # Create variables
        Cell, Cell1, Cell2 = V.Cell, V.Cell1, V.Cell2
        D, Sym = V.D, V.Sym

        # Clues
        clues = puzzle.add_segment("Clues")
        clues.section("Define numbered endpoints")
        clues.fact(*[Symbol(loc=grid.Cell(*loc), sym=sym) for loc, sym in grid_data])

        # Define which cells have symbols
        puzzle.section("Identify cells with symbols")
        puzzle.when(Symbol(loc=Cell, sym=ANY)).derive(HasSymbol(loc=Cell))

        # Rule 1: Define how many paths each cell should have
        puzzle.section("Path degree requirements")
        cell = grid.cell()
        puzzle.when(HasSymbol(loc=Cell)).derive(PathDegree(loc=Cell, degree=1))
        puzzle.when(cell, ~HasSymbol(loc=cell)).derive(PathDegree(loc=cell, degree=2))

        # Rule 2: Choose path directions for each cell
        puzzle.section("Path choice constraints")
        puzzle.when(
            PathDegree(loc=cell, degree=V.N),
        ).choose(
            Choice(
                element=Path(loc=cell, direction=D),
                condition=grid.OrthogonalDir(cell1=cell, direction=D, cell2=ANY),
            ).exactly(V.N)
        )

        # Rule 3: If a cell has a path in a direction, the adjacent cell must have a path back
        puzzle.section("Bidirectional path constraint")
        puzzle.when(
            Path(loc=Cell1, direction=D),
            grid.OrthogonalDir(cell1=Cell1, cell2=Cell2, direction=D),
            grid.Opposite(D, V.OppD),
        ).derive(Path(loc=Cell2, direction=V.OppD))

        # Rule 4: Cells with symbols propagate their symbol
        puzzle.section("Symbol propagation")
        puzzle.when(Symbol(loc=Cell, sym=Sym)).derive(PropagatedSymbol(loc=Cell, sym=Sym))

        # Rule 5: Symbols propagate through connected paths
        puzzle.when(
            PropagatedSymbol(loc=Cell1, sym=Sym),
            Path(loc=Cell1, direction=D),
            grid.OrthogonalDir(cell1=Cell1, cell2=Cell2, direction=D),
        ).derive(PropagatedSymbol(loc=Cell2, sym=Sym))

        # Rule 6: Every cell sees exactly one symbol. Scoping this to every cell (not just
        # symbol cells) also rejects stray closed loops, which carry no symbol at all.
        puzzle.section("Every cell sees exactly one symbol: no stray loops, no joined symbols")
        puzzle.when(cell).require(Count(Sym, condition=PropagatedSymbol(loc=cell, sym=Sym)) == 1)

        # Rule 7: Orthogonal cells with the same propagated symbol must be connected via path
        puzzle.section("Define connected relationship")
        puzzle.when(
            Path(loc=Cell1, direction=D),
            grid.OrthogonalDir(cell1=Cell1, cell2=Cell2, direction=D),
        ).derive(Connected(loc1=Cell1, loc2=Cell2))

        puzzle.section("No self-touch constraint")
        puzzle.when(
            grid.OrthogonalDir(cell1=Cell1, direction=ANY, cell2=Cell2),
            Cell1 < Cell2,
            PropagatedSymbol(loc=Cell1, sym=Sym),
            PropagatedSymbol(loc=Cell2, sym=Sym),
        ).require(Connected(loc1=Cell1, loc2=Cell2))

        # Rule 8: Solution extraction - the two directions through each
        # non-symbol cell and the single direction leaving each endpoint,
        # both carrying the pair symbol for rendering
        puzzle.section("Solution extraction")
        D1, D2 = V.D1, V.D2

        # D1 < D2 ensures canonical ordering to avoid duplicates
        puzzle.when(
            cell,
            ~HasSymbol(loc=cell),
            PropagatedSymbol(loc=cell, sym=Sym),
            Path(loc=cell, direction=D1),
            Path(loc=cell, direction=D2),
            D1 < D2,
        ).derive(CellDirections(loc=cell, dir1=D1, dir2=D2, sym=Sym))

        puzzle.when(
            Symbol(loc=Cell, sym=Sym),
            Path(loc=Cell, direction=D),
        ).derive(EndpointDirection(loc=Cell, direction=D, sym=Sym))

    def get_render_spec(self) -> RenderSpec:
        # Symbols are opaque labels (numbers or strings); color them in
        # first-appearance order, cycling the palette
        palette = (
            Color.BLUE,
            Color.GREEN,
            Color.RED,
            Color.MAGENTA,
            Color.CYAN,
            Color.YELLOW,
            Color.BRIGHT_BLUE,
            Color.BRIGHT_GREEN,
            Color.BRIGHT_RED,
        )
        # Paths color like their endpoint clues: same palette, same
        # first-appearance order. The endpoint rule's single-direction
        # stubs draw the path into the numbered cells (in character grids
        # the clue glyph paints over its stub).
        colorer = symbol_colorer(self.grid_data, palette)
        return RenderSpec(
            clues=symbol_clues(self.grid_data, palette),
            atoms=[
                PathRule(CellDirections, color=colorer),
                PathRule(EndpointDirection, direction_fields=("direction",), color=colorer),
            ],
            style=SceneStyle(packed=True),
        )

    def validate_config(self) -> None:
        """Validate the puzzle configuration."""
        # Check that each symbol appears exactly twice
        symbol_counts: dict[int | str, int] = {}
        for _loc, symbol in self.grid_data:
            symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1

        # Check for symbols that don't appear exactly twice
        invalid_symbols: list[str] = []
        invalid_symbols.extend(
            f"'{symbol}' appears {count} times" for symbol, count in symbol_counts.items() if count != 2
        )

        if invalid_symbols:
            raise ValueError(
                f"Each symbol in Numberlink must appear exactly twice. Invalid symbols: {', '.join(invalid_symbols)}"
            )
