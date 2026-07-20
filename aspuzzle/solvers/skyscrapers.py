from typing import ClassVar

from aspalchemy import ANY, Count, Field, Predicate, RangePool, V
from aspuzzle.grids.rectangulargrid import RectangularGrid
from aspuzzle.rendering import (
    CHARACTER_BACKENDS,
    SVG_ONLY,
    GlyphRule,
    Lattice,
    LineLabels,
    RenderSpec,
    SceneStyle,
    digit_clues,
)
from aspuzzle.rendering import PaletteColor as Color
from aspuzzle.solvers.base import Solver
from aspuzzle.symbolset import SymbolSet


class Clue(Predicate, show=False):
    dir: Field[str]
    index: Field[int]
    count: Field[int]


class Blocked(Predicate, show=False):
    dir: Field[str]
    index: Field[int]
    position: Field[int]


class Visible(Predicate, show=False):
    dir: Field[str]
    index: Field[int]
    position: Field[int]


class Skyscrapers(Solver):
    """Skyscrapers puzzle solver."""

    solver_name = "Skyscrapers puzzle solver"
    supported_symbols = (*range(1, 26), ".")  # Support up to 25x25 grids
    supported_grid_types = (RectangularGrid,)
    # (line-of-sight direction, config key): the direction is which way the
    # clue looks, not where it sits — a top clue looks south down its column
    CLUE_DIRECTIONS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("s", "top_clues"),
        ("n", "bottom_clues"),
        ("e", "left_clues"),
        ("w", "right_clues"),
    )

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
        clue_mapping = [(direction, config[key]) for direction, key in self.CLUE_DIRECTIONS]
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
        puzzle.when(
            grid.LineOfSight(direction=Dir, index=Idx, position=Pos, loc=cell),
            Height(loc=cell, value=H),
            grid.LineOfSight(direction=Dir, index=Idx, position=Pos["prev"], loc=earlier_cell),
            Pos["prev"] < Pos,
            Height(loc=earlier_cell, value=H["prev"]),
            H["prev"] > H,
        ).derive(Blocked(dir=Dir, index=Idx, position=Pos))

        # Define visible predicate: a building is visible if it's not blocked
        puzzle.when(
            grid.LineOfSight(direction=Dir, index=Idx, position=Pos, loc=ANY),
            ~Blocked(dir=Dir, index=Idx, position=Pos),
        ).derive(Visible(dir=Dir, index=Idx, position=Pos))

        # Rule 4: Visible count must match clue
        puzzle.section("Visible count must match clue")
        puzzle.when(Clue(dir=Dir, index=Idx, count=N)).require(
            Count(Pos, condition=Visible(dir=Dir, index=Idx, position=Pos)) == N
        )

    def get_render_spec(self) -> RenderSpec:
        assert isinstance(self.grid, RectangularGrid)
        grid_size = self.grid.rows
        return RenderSpec(
            clues=digit_clues(range(1, grid_size + 1), Color.GREEN),
            atoms=[GlyphRule("height/2", value_field="value", color=Color.BRIGHT_BLUE)],
            labels=[
                # Bright white reads well on a dark terminal but vanishes
                # on paper (sheets carry no color either way); SVG takes
                # the provenance default
                *(
                    LineLabels(direction, self.config[key], color=Color.BRIGHT_WHITE, backends=CHARACTER_BACKENDS)
                    for direction, key in self.CLUE_DIRECTIONS
                ),
                *(
                    LineLabels(direction, self.config[key], backends=SVG_ONLY)
                    for direction, key in self.CLUE_DIRECTIONS
                ),
            ],
            style=SceneStyle(lattice=Lattice.FRAME),
        )
