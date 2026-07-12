from typing import Any

from aspalchemy import ANY, Count, Predicate, RangePool, V
from aspuzzle.grids.rectangulargrid import RectangularGrid
from aspuzzle.grids.rendering import Color, RenderSymbol
from aspuzzle.solvers.base import Solver
from aspuzzle.symbolset import SymbolSet


class Skyscrapers(Solver):
    """Skyscrapers puzzle solver."""

    solver_name = "Skyscrapers puzzle solver"
    supported_symbols = (*range(1, 26), ".")  # Support up to 25x25 grids
    supported_grid_types = (RectangularGrid,)

    def validate_config(self) -> None:
        """Validate the Skyscrapers configuration."""
        grid = self.grid
        assert isinstance(grid, RectangularGrid)

        # Check that the grid is square
        if grid.rows != grid.cols:
            raise ValueError(f"Skyscrapers requires a square grid. Got {grid.rows}x{grid.cols}")

        grid_size = grid.rows

        # Update supported symbols for this grid size
        self.supported_symbols = (*range(1, grid_size + 1), ".")

        # Validate clue arrays if provided
        for direction in ["top_clues", "bottom_clues", "left_clues", "right_clues"]:
            clues = self.config.get(direction)
            if clues is not None:
                if len(clues) != grid_size:
                    raise ValueError(f"{direction} must have exactly {grid_size} elements, got {len(clues)}")
                if not all(1 <= clue <= grid_size for clue in clues):
                    raise ValueError(f"All clues in {direction} must be between 1 and {grid_size}")

    def construct_puzzle(self) -> None:
        """Construct the Skyscrapers puzzle rules."""
        puzzle, grid, config, grid_data = self.unpack_data()
        assert isinstance(grid, RectangularGrid)

        grid_size = grid.rows
        C, N, Idx = V.C, V.N, V.Idx

        # Clues
        clues_seg = puzzle.add_segment("Clues")
        clues_seg.section("Clue constraints")
        Clue = Predicate.define("clue", ["dir", "index", "count"], show=False)
        clue_mapping: list[tuple[str, list[int]]] = [
            ("s", config["top_clues"]),  # Top clues look south (down)
            ("n", config["bottom_clues"]),  # Bottom clues look north (up)
            ("e", config["left_clues"]),  # Left clues look east (right)
            ("w", config["right_clues"]),  # Right clues look west (left)
        ]
        for direction, clues in clue_mapping:
            clues_seg.fact(
                *[Clue(dir=direction, index=idx, count=clue_count) for idx, clue_count in enumerate(clues, 1)]
            )

        # Rule 1: Place heights 1 to grid_size in each cell
        symbols = SymbolSet(grid, fill_all_squares=True)
        symbols.add_range_symbol(name="height", pool=RangePool(1, grid_size), show=True)
        Height = symbols["height"]

        # Rule 2: Each height appears exactly once in each row and column
        puzzle.section("Each height appears exactly once in each row and column")
        puzzle.when(
            Height(loc=C[1], value=N),
            Height(loc=C[2], value=N),
            grid.Line(direction=V.D, index=Idx, loc=C[1]),
            grid.Line(direction=V.D, index=Idx, loc=C[2]),
        ).require(C[1] == C[2])

        # Add any pre-filled heights from grid_data
        if grid_data:
            given = puzzle.add_segment("Given Heights")
            given.fact(*[Height(loc=grid.Cell(*loc), value=value) for loc, value in grid_data])

        # Rule 3: Line-of-sight visibility rules
        puzzle.section("Line-of-sight visibility")
        Dir, Pos, H = V.Dir, V.Pos, V.H
        cell = grid.cell()
        earlier_cell = grid.cell(suffix="prev")

        # Define blocking predicate: a building is blocked if there's a taller building at an earlier position
        Blocked = Predicate.define("blocked", ["dir", "index", "position"], show=False)
        puzzle.when(
            grid.LineOfSight(direction=Dir, index=Idx, position=Pos, loc=cell),
            Height(loc=cell, value=H),
            grid.LineOfSight(direction=Dir, index=Idx, position=Pos["prev"], loc=earlier_cell),
            Pos["prev"] < Pos,
            Height(loc=earlier_cell, value=H["prev"]),
            H["prev"] > H,
        ).derive(Blocked(dir=Dir, index=Idx, position=Pos))

        # Define visible predicate: a building is visible if it's not blocked
        Visible = Predicate.define("visible", ["dir", "index", "position"], show=False)
        puzzle.when(
            grid.LineOfSight(direction=Dir, index=Idx, position=Pos, loc=ANY),
            ~Blocked(dir=Dir, index=Idx, position=Pos),
        ).derive(Visible(dir=Dir, index=Idx, position=Pos))

        # Rule 4: Visible count must match clue
        puzzle.section("Visible count must match clue")
        puzzle.when(Clue(dir=Dir, index=Idx, count=N)).require(
            Count(Pos, condition=Visible(dir=Dir, index=Idx, position=Pos)) == N
        )

    def get_render_config(self) -> dict[str, Any]:
        """
        Get the rendering configuration for the Skyscrapers solver.

        Returns:
            Dictionary with rendering configuration for Skyscrapers
        """
        assert isinstance(self.grid, RectangularGrid)
        grid_size = self.grid.rows

        puzzle_symbols = {
            i: RenderSymbol(
                symbol=str(i) if i <= 9 else chr(ord("A") + i - 10),
                color=Color.GREEN,
            )
            for i in range(1, grid_size + 1)
        }

        return {
            "puzzle_symbols": puzzle_symbols,
            "predicates": {
                "height": {"value": "value", "color": Color.BRIGHT_BLUE},
            },
        }
