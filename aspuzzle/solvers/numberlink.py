from typing import Any

from aspalchemy import ANY, Choice, Count, Predicate, V
from aspuzzle.grids.rendering import Color, RenderSymbol
from aspuzzle.solvers.base import Solver


class Numberlink(Solver):
    solver_name = "Numberlink puzzle solver"

    def construct_puzzle(self) -> None:
        """Construct the rules of the puzzle."""
        puzzle, grid, _config, grid_data = self.unpack_data()

        # Create variables
        Cell, Cell1, Cell2 = V.Cell, V.Cell1, V.Cell2
        D, Sym = V.D, V.Sym

        # Clues
        Symbol = Predicate.define("symbol", ["loc", "sym"], show=False)
        clues = puzzle.add_segment("Clues")
        clues.section("Define numbered endpoints")
        clues.fact(*[Symbol(loc=grid.Cell(*loc), sym=sym) for loc, sym in grid_data])

        # Define which cells have symbols
        puzzle.section("Identify cells with symbols")
        HasSymbol = Predicate.define("has_symbol", ["loc"], show=False)
        puzzle.when(Symbol(loc=Cell, sym=ANY)).derive(HasSymbol(loc=Cell))

        # Rule 1: Define how many paths each cell should have
        puzzle.section("Path degree requirements")
        cell = grid.cell()
        PathDegree = Predicate.define("path_degree", ["loc", "degree"], show=False)
        puzzle.when(HasSymbol(loc=Cell)).derive(PathDegree(loc=Cell, degree=1))
        puzzle.when(cell, ~HasSymbol(loc=cell)).derive(PathDegree(loc=cell, degree=2))

        # Rule 2: Choose path directions for each cell
        puzzle.section("Path choice constraints")
        Path = Predicate.define("path", ["loc", "direction"], show=False)
        puzzle.when(
            PathDegree(loc=cell, degree=V.N),
        ).derive(
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
        PropagatedSymbol = Predicate.define("propagated_symbol", ["loc", "sym"], show=False)
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
        Connected = Predicate.define("connected", ["loc1", "loc2"], show=False)
        puzzle.when(
            Path(loc=Cell1, direction=D),
            grid.OrthogonalDir(cell1=Cell1, cell2=Cell2, direction=D),
        ).derive(Connected(loc1=Cell1, loc2=Cell2))

        puzzle.section("No self-touch constraint")
        puzzle.forbid(
            grid.OrthogonalDir(cell1=Cell1, direction=ANY, cell2=Cell2),
            PropagatedSymbol(loc=Cell1, sym=Sym),
            PropagatedSymbol(loc=Cell2, sym=Sym),
            ~Connected(loc1=Cell1, loc2=Cell2),
        )

        # Rule 8: Solution extraction - compute the two directions for each non-symbol cell
        puzzle.section("Solution extraction")
        CellDirections = Predicate.define("cell_directions", ["loc", "dir1", "dir2"], show=True)
        D1, D2 = V.D1, V.D2

        # D1 < D2 ensures canonical ordering to avoid duplicates
        puzzle.when(
            cell,
            ~HasSymbol(loc=cell),
            Path(loc=cell, direction=D1),
            Path(loc=cell, direction=D2),
            D1 < D2,
        ).derive(CellDirections(loc=cell, dir1=D1, dir2=D2))

    def get_render_config(self) -> dict[str, Any]:
        """
        Get the rendering configuration for the Numberlink solver.

        Returns:
            Dictionary with rendering configuration for Numberlink
        """
        # Colors for numbers 1-9, cycling for higher numbers
        colors = [
            Color.BLUE,  # 1
            Color.GREEN,  # 2
            Color.RED,  # 3
            Color.MAGENTA,  # 4
            Color.CYAN,  # 5
            Color.YELLOW,  # 6
            Color.BRIGHT_BLUE,  # 7
            Color.BRIGHT_GREEN,  # 8
            Color.BRIGHT_RED,  # 9
        ]

        puzzle_symbols = {
            i: RenderSymbol(
                symbol=str(i) if i <= 9 else "#",
                color=colors[(i - 1) % len(colors)],
            )
            for i in range(1, 100)
        }

        return {
            "puzzle_symbols": puzzle_symbols,
            "predicates": {
                "cell_directions": {"loop_directions": True, "color": Color.CYAN},
            },
            "join_char": "",
        }

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
