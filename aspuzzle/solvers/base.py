import importlib
import json
from abc import ABC, abstractmethod
from collections.abc import Sequence
from functools import wraps
from itertools import islice
from typing import Any, ClassVar, cast

from aspalchemy import GroundedProgram, Predicate, SolveResult
from aspuzzle.grids.base import Grid, GridCellData
from aspuzzle.puzzle import Puzzle
from aspuzzle.rendering import LineLabels, RenderSpec, Scene, build_scene
from aspuzzle.rendering.ascii import AsciiRenderer


class Solver(ABC):
    default_config: ClassVar[dict[str, Any]] = {}
    solver_name: str = "Puzzle solver"
    supported_grid_types: tuple[type] = (Grid,)  # Support all grids by default
    supported_symbols: tuple[
        str | int, ...
    ] = ()  # Symbols allowed in the grid definition; solvers may override per instance
    grid: Grid
    map_grid_to_integers: bool = False  # Whether to map grid symbols to unique integer ids, useful for defining regions
    _grid_data: list[GridCellData] | None = None
    _grounding: GroundedProgram | None = None
    _constructed: bool = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """
        Wrap each subclass's construct_puzzle in a once-per-instance guard.

        The rules must be emitted exactly once no matter which paths reach
        them: an explicit construct_puzzle() call, ground()'s automatic one,
        or both. Subclasses just implement construct_puzzle as usual; the
        guard is applied here so no implementation can forget it.
        """
        super().__init_subclass__(**kwargs)
        construct = cls.__dict__.get("construct_puzzle")
        if construct is None:
            return

        @wraps(construct)
        def guarded(self: Solver) -> None:
            if self._constructed:
                return
            construct(self)
            # Set only after the body completes: an overriding body calling
            # super().construct_puzzle() must still run the parent's rules
            self._constructed = True

        cast(Any, cls).construct_puzzle = guarded

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> Solver:
        """
        Create and return the appropriate Solver subclass instance for the given configuration.

        Args:
            config: The puzzle configuration dictionary

        Returns:
            An initialized Solver subclass instance

        Raises:
            ValueError: If the puzzle_type is missing or invalid
        """
        if "puzzle_type" not in config:
            raise ValueError("Puzzle configuration must include 'puzzle_type'")

        puzzle_type = config["puzzle_type"]

        # Import the solver module dynamically
        try:
            module = importlib.import_module(f"aspuzzle.solvers.{puzzle_type.lower()}")
            puzzle_class = getattr(module, puzzle_type)
        except (ImportError, AttributeError) as e:
            raise ValueError(f"Invalid puzzle type '{puzzle_type}': {e}") from e

        # Verify that the class is a Solver subclass
        if not issubclass(puzzle_class, cls):
            raise ValueError(f"Class '{puzzle_type}' is not a Solver subclass")

        # Initialize and return the solver
        puzzle = puzzle_class(config)
        assert isinstance(puzzle, Solver)
        return puzzle

    def __init__(self, config: dict[str, Any]) -> None:
        self.puzzle = Puzzle()
        self.puzzle.name = self.solver_name
        # Merge default config with instance config
        self.config = {**self.default_config, **config}

        self.create_grid()
        _ = self.grid_data  # Preprocess this so it's ready!
        self.validate()
        self._preprocess_config()

    def create_grid(self) -> None:
        """Create the grid for this puzzle. Can be overridden by subclasses."""
        grid_type_name = self.config.get("grid_type", "RectangularGrid")

        # Import the grid class dynamically
        try:
            grid_module = importlib.import_module(f"aspuzzle.grids.{grid_type_name.lower()}")
            grid_class = getattr(grid_module, grid_type_name)
        except (ImportError, AttributeError) as e:
            raise ValueError(f"Failed to import grid type {grid_type_name}: {e}") from e

        # Check if the imported grid class is supported based on type inheritance
        if not issubclass(grid_class, self.supported_grid_types):
            supported_names = ", ".join(t.__name__ for t in self.supported_grid_types)
            raise ValueError(
                f"Grid type '{grid_type_name}' is not supported by {self.solver_name}. "
                f"Supported types: {supported_names}"
            )

        # Let the grid create itself from the config
        assert issubclass(grid_class, Grid)
        self.grid = grid_class.from_config(self.puzzle, self.config)

    @property
    def grid_data(self) -> list[GridCellData]:
        """
        Get the parsed grid data, using the provided mapping strategy.
        Lazy-loads and caches the data on first access.

        Returns:
            The parsed grid data
        """
        if self._grid_data is None:
            if "grid" not in self.config:
                self._grid_data = []
            else:
                self._grid_data = self.grid.parse_grid(self.config["grid"], map_to_integers=self.map_grid_to_integers)
        assert self._grid_data is not None
        return self._grid_data

    @property
    def int_grid_data(self) -> list[tuple[tuple[int, ...], int]]:
        """
        Grid data with values narrowed to int, for solvers whose grid values
        are integers by construction (numeric clues validated by
        supported_symbols, or map_grid_to_integers). Raises on any
        non-integer value rather than answering quietly.
        """
        for loc, value in self.grid_data:
            if not isinstance(value, int):
                raise TypeError(f"Expected integer grid values, got {value!r} at position {loc}")
        return [(loc, value) for loc, value in self.grid_data if isinstance(value, int)]

    def _preprocess_config(self) -> None:
        """
        Optional preprocessing step after config validation and grid data parsing.

        This method is called after validate_config() and grid_data property access
        in __init__. Subclasses can override this to perform additional preprocessing
        such as region coloring computation.
        """
        pass

    def unpack_data(self) -> tuple[Puzzle, Grid, dict[str, Any], list[GridCellData]]:
        """
        Convenience property to get puzzle, grid, config, and parsed grid data.

        Returns:
            A tuple containing (puzzle, grid, config, grid_data)
        """
        return self.puzzle, self.grid, self.config, self.grid_data

    def validate(self) -> None:
        """
        Validate the puzzle configuration. Config validation runs first:
        it may adjust supported_symbols (or remap grid symbols) based on
        the configuration, e.g. widening the digit range for large Sudokus.
        """
        self.validate_config()
        self.validate_grid_symbols()

    def validate_grid_symbols(self) -> None:
        """Validate that the grid contains only supported symbols."""
        if not self.supported_symbols or "grid" not in self.config:
            return  # Nothing to validate

        # Check each cell against supported symbols
        for loc, symbol in self.grid_data:
            if symbol not in self.supported_symbols:
                raise ValueError(
                    f"Unsupported symbol '{symbol}' at position {loc}. "
                    f"Supported symbols: {', '.join(str(s) for s in self.supported_symbols)}"
                )

    def validate_config(self) -> None:
        """Function to perform extra validation on the puzzle config as needed."""
        pass

    @abstractmethod
    def construct_puzzle(self) -> None:
        """
        Construct the rules of the puzzle. Guarded to run at most once per
        solver (see __init_subclass__); ground() calls it automatically, so
        explicit calls are only needed to emit rules before grounding
        (e.g. to render the program without solving).
        """

    def render_program(self, annotate: bool = False) -> str:
        """
        Construct (if not already constructed), finalize, and render the
        complete ASP program. The rendering entry point at the solver level:
        going to solver.puzzle.render() directly skips construction.

        Args:
            annotate: Append a "% file:line" provenance note to each
                statement (see Puzzle.render)
        """
        self.construct_puzzle()
        return self.puzzle.render(annotate=annotate)

    def analyze_recursion(self) -> str:
        """
        Construct (if not already constructed) and report the recursion
        profile as prose (see Puzzle.analyze_recursion): static analysis,
        no grounding performed.
        """
        self.construct_puzzle()
        return self.puzzle.analyze_recursion()

    def ground(self) -> GroundedProgram:
        """
        Construct (if not already constructed), finalize, and ground the
        puzzle, caching the immutable snapshot: the handle for grounding
        introspection (analyze_grounding(), aspif(), ground_text()) and
        repeated solving.
        """
        if self._grounding is None:
            self.construct_puzzle()
            self._grounding = self.puzzle.ground()
        return self._grounding

    def solve(self, models: int = 1, timeout: int = 0) -> tuple[list[dict[str, list[Predicate]]], SolveResult]:
        """
        Solve the puzzle; returns the collected name-keyed solutions (the shape
        the renderer and expected-solutions files use) and the SolveResult.

        models caps the collection (0 collects every model) — a consumer-side
        limit on the unbounded stream.
        """
        result = self.ground().solve(timeout=timeout)
        stream = islice(result, models) if models else result
        solutions = []
        for model in stream:
            by_name: dict[str, list[Predicate]] = {}
            for atom in model.atoms():
                by_name.setdefault(type(atom).get_name(), []).append(atom)
            solutions.append({name: sorted(atoms, key=str) for name, atoms in by_name.items()})

        # islice stops the LOOP, not the search: the generator stays
        # suspended and its finally (statistics snapshot, native handle
        # cleanup) never runs. Close explicitly so --stats works and no
        # native SolveHandle outlives the collection.
        result.close()
        return solutions, result

    def display_results(self, solutions: list[dict], result: SolveResult, visualize: bool = True) -> None:
        """Display the solving results."""
        print("\n=== Solutions ===")
        if not result.satisfiable:
            print("No solutions found")
        else:
            # Only show full clingo predicates if there isn't a solution in the config
            if "solutions" not in self.config:
                print(json.dumps(solutions[:2], indent=2, default=lambda pred: pred.canonical_str()))
                if len(solutions) > 2:
                    print(f"(... suppressed ({len(solutions) - 2} more)")

            # Visualize the first couple of solutions if requested
            if visualize and solutions:
                for idx, sol in enumerate(solutions[:2]):
                    print(f"\nSolution {idx + 1}:")
                    print(self.render_puzzle(sol))

            # Print solution count
            suffix = "(exhausted)" if result.exhausted else "(not exhausted)"
            if result.models_yielded == 1:
                print(f"\n1 solution found {suffix}")
            else:
                print(f"\n{result.models_yielded} solutions found {suffix}")

    def display_statistics(self, result: SolveResult) -> None:
        """Display statistics after solving."""
        print("\n=== Statistics ===")
        print(result.format_statistics())

    def validate_solutions(self, solutions: list[dict]) -> bool:
        """Validate that solutions found match expected solutions."""
        if "solutions" not in self.config:
            return True

        print("\n=== Solution Validation ===")
        expected_solutions = self.config["solutions"]

        # Convert found solutions to comparable format (sets of frozensets)
        found_solutions_set = set()
        for sol in solutions:
            # Convert each solution to a frozenset of (predicate_name, frozenset of predicates)
            solution_set = frozenset(
                (pred_name, frozenset(pred.canonical_str() for pred in preds)) for pred_name, preds in sol.items()
            )
            found_solutions_set.add(solution_set)

        # Convert expected solutions to the same format
        expected_solutions_set = set()
        for expected_solution in expected_solutions:
            solution_set = frozenset((pred_name, frozenset(preds)) for pred_name, preds in expected_solution.items())
            expected_solutions_set.add(solution_set)

        # Compare the sets
        if found_solutions_set == expected_solutions_set:
            count = len(expected_solutions)
            if count == 1:
                print("✓ The expected solution was found")
            else:
                print(f"✓ All {count} expected solutions were found")
            return True

        print("✗ Solutions do not match expected")

        # Find differences
        missing_solutions = expected_solutions_set - found_solutions_set
        extra_solutions = found_solutions_set - expected_solutions_set

        if missing_solutions:
            self._print_solution_diff(
                missing_solutions,
                count_label="Missing",
                item_label="Missing solution",
            )

        if extra_solutions:
            self._print_solution_diff(
                extra_solutions, count_label="Found", item_label="Extra solution", suffix=" unexpected"
            )

        return False

    @staticmethod
    def _print_solution_diff(solutions: set, count_label: str, item_label: str, suffix: str = "") -> None:
        """Print differences between expected and found solutions."""
        count = len(solutions)
        print(f"  {count_label} {count}{suffix} solution{'s' if count != 1 else ''}")

        # Show up to 2 examples
        for i, sol in enumerate(solutions, 1):
            if i > 2:
                break
            print(f"    {item_label} {i}:")
            # Convert back to readable format
            sol_dict = {pred_name: sorted(preds) for pred_name, preds in sol}
            print(json.dumps(sol_dict, indent=6, default=str))

        # Show suppression message if needed
        if count > 2:
            print(f"    (... suppressed {count - 2} more)")

    def get_render_spec(self) -> RenderSpec:
        """
        The solver's declarative rendering description (see
        aspuzzle.rendering.spec). One spec serves every backend and both
        render states: the preview (no solution) and the solved render.
        Default: a bare grid.
        """
        return RenderSpec()

    def build_scene(self, solution: dict[str, list[Predicate]] | None = None) -> Scene:
        """
        The scene for a solution (or the preview, when None). Override —
        call super(), then scene.add(...) — only for elements the spec
        cannot express.
        """
        return build_scene(self.grid, self.get_render_spec(), self.grid_data, solution)

    def render_puzzle(self, solution: dict[str, list[Predicate]] | None = None, *, use_colors: bool = True) -> str:
        """
        Render the puzzle as ASCII text: the solution when given, the
        clues-only preview when not.
        """
        return AsciiRenderer(use_colors=use_colors).render(self.build_scene(solution))

    def line_clues(self, direction: str) -> Sequence[int | None]:
        """The config clue list for a line direction, per the naming
        convention validate_line_clues enforces ("e" -> row_clues, ...)."""
        clues = self.config[f"{self.grid.line_direction_descriptions[direction]}_clues"]
        assert isinstance(clues, list)
        return clues

    def clue_labels(self) -> list[LineLabels]:
        """Outside labels for every line clue in the config, placed at
        the start of each line."""
        return [LineLabels(direction, self.line_clues(direction)) for direction in self.grid.line_direction_names]

    def validate_line_clues(self) -> None:
        """
        Validates that all expected line clues exist and have the correct length.

        Raises:
            ValueError: If required clue lists are missing or have incorrect length
        """
        grid = self.grid

        for direction in grid.line_direction_names:
            clue_key = f"{grid.line_direction_descriptions[direction]}_clues"

            # Check if clues exist
            if clue_key not in self.config:
                raise ValueError(f"Missing {clue_key} in puzzle configuration")

            # Check if count matches grid size
            expected_count = grid.get_line_count(direction)
            actual_count = len(self.config[clue_key])

            if actual_count != expected_count:
                raise ValueError(f"Expected {expected_count} {clue_key}, got {actual_count}")
