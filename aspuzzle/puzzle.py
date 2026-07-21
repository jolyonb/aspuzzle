from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from functools import wraps
from typing import Any, cast

from aspalchemy import (
    ASPProgram,
    Choice,
    Comparison,
    ConditionalLiteral,
    DefinedConstant,
    GroundedProgram,
    LogLevel,
    NegatedSignature,
    Predicate,
    RecursiveComponent,
    Segment,
    SolveResult,
    SourceLocation,
    Term,
    When,
    capture_location,
    location_override,
)


class StatementSpeaker(ABC):
    """
    The statement-verb surface shared by Puzzle and Module: the statement
    verbs (fact, choose, when, forbid, require) and the formatting verbs
    (comment, blank_line, section), spoken on this speaker's target.
    Defined once here so the two surfaces cannot drift apart.
    """

    @property
    @abstractmethod
    def _statement_target(self) -> ASPProgram | Segment:
        """
        Where this speaker's statements land: a Puzzle speaks on its
        program (whose verbs write to the default segment), a Module on
        its own segment.
        """

    def fact(self, *facts: Predicate) -> None:
        """
        Add unconditional statements: grounded atoms, asserted true.

        Args:
            *facts: Grounded Predicate instances
        """
        self._statement_target.fact(*facts)

    def choose(self, choice: Choice) -> None:
        """
        Add a bare choice rule with no body.

        Args:
            choice: The Choice to state
        """
        self._statement_target.choose(choice)

    def when(self, *conditions: Term) -> When:
        """
        Hold the conditions for a closer; see Segment.when.

        Args:
            *conditions: One or more conditions that must be satisfied

        Returns:
            A pending context completed by exactly one of
            .derive/.choose/.require/.forbid/.penalize
        """
        return self._statement_target.when(*conditions)

    def forbid(self, *conditions: Term) -> None:
        """
        Create a constraint which forbids the specified combination of conditions.

        Args:
            *conditions: One or more conditions that must not be simultaneously satisfied
        """
        self._statement_target.forbid(*conditions)

    def require(self, target: Comparison | Predicate) -> None:
        """
        Require that a comparison or an atom holds in every answer set.
        Takes exactly one target; syntactic sugar for a forbid constraint
        on its flip. See Segment.require.
        """
        self._statement_target.require(target)

    def comment(self, text: str) -> None:
        """
        Add a comment to the program.

        Args:
            text: The comment text
        """
        self._statement_target.comment(text)

    def blank_line(self) -> None:
        """Add a blank line to the program for formatting."""
        self._statement_target.blank_line()

    def section(self, title: str) -> None:
        """
        Add a section header to the program.

        Args:
            title: The section title
        """
        self._statement_target.section(title)


class Puzzle(StatementSpeaker):
    """
    Coordinates modules and their rules to create a complete ASP program.

    The Puzzle class provides a high-level interface for defining logic puzzles
    using aspalchemy, with support for modular organization.
    """

    finalized: bool = False

    def __init__(self, name: str = "Puzzle", allow_singletons: bool = False, source_locations: bool = True):
        """
        Initialize a new puzzle.

        Args:
            name: A name for this puzzle (for documentation purposes)
            allow_singletons: Switch off the singleton-variable lint
                (see ASPProgram)
            source_locations: Stamp each statement with the authoring Python
                line (see ASPProgram); powers dangling-when() reports,
                render(annotate=True), and grounding diagnostics
        """
        self.name = name
        self._program = ASPProgram(allow_singletons=allow_singletons, source_locations=source_locations)
        self._modules: dict[str, Module] = {}
        # Resolved on first use, not here: segments render in declaration
        # order, so creating this one at construction would place the rules
        # ahead of the grid and every module
        self._rules_segment: Segment | None = None

    @property
    def _statement_target(self) -> ASPProgram:
        return self._program

    def get_module(self, name: str) -> Module:
        """
        Get a module by name.

        Args:
            name: The name of the module to retrieve

        Returns:
            The requested module

        Raises:
            KeyError: If no module with the given name exists
        """
        if name not in self._modules:
            raise KeyError(f"No module named '{name}' is registered")
        return self._modules[name]

    def register_module(self, module: Module) -> Segment:
        """
        Register a module with this puzzle and return the module's segment.

        Args:
            module: The module to register

        Returns:
            The segment created for the module's statements

        Raises:
            ValueError: If a module with the same name is already registered
            RuntimeError: If the puzzle has already been finalized
        """
        if self.finalized:
            raise RuntimeError(
                f"Cannot register module '{module.name}': the puzzle is already finalized, "
                "so the module's finalize() would never run"
            )
        if module.name in self._modules:
            raise ValueError(f"Module with name '{module.name}' is already registered")

        self._modules[module.name] = module
        return self._program.add_segment(module.name)

    def add_segment(self, segment: str | Segment) -> Segment:
        """
        Add a segment to the program and return it: a string pre-declares
        an empty segment, a Segment object attaches it as-is. Statements
        are spoken on the returned handle (module segments are added at
        registration).
        """
        return self._program.add_segment(segment)

    @property
    def rules_segment(self) -> Segment:
        """
        The segment the puzzle's own verbs write to, as a handle: a solver
        speaks its rules through puzzle.when()/fact() and never needs this,
        but a helper that takes a segment (grid.forbid_2x2_blocks, say) does,
        and a puzzle rule belongs among the puzzle's rules.
        """
        if self._rules_segment is None:
            name = self._program.default_segment
            existing = [segment for segment in self._program.segments if segment.name == name]
            self._rules_segment = existing[0] if existing else self._program.add_segment(name)
        return self._rules_segment

    def define_constant(self, name: str, value: int | str) -> DefinedConstant:
        """
        Define a #const constant for the program.

        Args:
            name: The name of the constant
            value: The value of the constant (integer or string)

        Returns:
            A DefinedConstant object that can be used in ASP rules

        Raises:
            ValueError: If the name is invalid or already registered
            TypeError: If the value is not an integer or string
        """
        return self._program.define_constant(name, value)

    def raw_asp(self, text: str, predicates: Sequence[type[Predicate] | NegatedSignature] = ()) -> None:
        """Add a verbatim block of ASP text; see ASPProgram.raw_asp."""
        self._program.raw_asp(text, predicates=predicates)

    def show(self, predicate: type[Predicate]) -> None:
        """Show this predicate in output, overriding its default visibility."""
        self._program.show(predicate)

    def hide(self, predicate: type[Predicate]) -> None:
        """Hide this predicate from output, overriding its default visibility."""
        self._program.hide(predicate)

    def show_when(self, condition: ConditionalLiteral) -> None:
        """Show this predicate only where the condition holds."""
        self._program.show_when(condition)

    @property
    def _finalized_program(self) -> ASPProgram:
        """
        The underlying program, finalized. Every consumer (solving,
        grounding, rendering, analysis) reads the program through this
        accessor — the single place finalization happens — so no entry
        point can reach the solver with module rules missing. The
        statement verbs above build on the raw _program.
        """
        self.finalize()
        return self._program

    def solve(self, timeout: int = 0) -> SolveResult:
        """
        Solve the puzzle, returning a SolveResult that yields Models lazily.

        The stream is unbounded: take the models you need (islice, or a
        for-loop with break); clasp computes only what you consume.

        Args:
            timeout: Wall-clock limit in seconds (0 for no limit); on timeout, models found
                     so far are yielded and 'exhausted' remains False
        """
        return self._finalized_program.solve(timeout=timeout)

    def ground(self, stop_on_log_level: LogLevel = LogLevel.INFO, context: object = None) -> GroundedProgram:
        """
        Finalize and ground the puzzle, returning the immutable grounding
        snapshot: the hub for grounding introspection (ground_text(), aspif(),
        analyze_grounding(), grounding_profile()) and for ground-once,
        solve-many workflows (solve/brave/cautious/optimize with assumptions).

        Args:
            stop_on_log_level: Clingo messages at or above this level raise
                GroundingError (see ASPProgram.ground)
            context: Optional @-function grounding context object
        """
        return self._finalized_program.ground(stop_on_log_level=stop_on_log_level, context=context)

    def recursion_profile(self) -> tuple[RecursiveComponent, ...]:
        """
        The recursive components of the puzzle's predicate dependency
        graph (see ASPProgram.recursion_profile): static analysis, no
        grounding performed. Finalizes first so module-emitted rules
        (RegionConstructor's fixpoints in particular) are visible.
        """
        return self._finalized_program.recursion_profile()

    def analyze_recursion(self) -> str:
        """The recursion profile as prose (see ASPProgram.analyze_recursion)."""
        return self._finalized_program.analyze_recursion()

    def render(self, annotate: bool = False) -> str:
        """
        Render the puzzle as an ASP program.

        Args:
            annotate: Append a "% file:line" provenance note to each statement
                (line numbering is unchanged). Keep checked-in renders
                unannotated — annotations churn on unrelated edits.

        Returns:
            str: The rendered ASP program.
        """
        return self._finalized_program.render(annotate=annotate)

    def finalize(self) -> None:
        """Ensures all modules finalize their code before rendering or solving"""
        if not self.finalized:
            self._program.header = f"{self.name} by ASPuzzle"
            for module in self._modules.values():
                # Rules emitted during a finalize pass have no honest user
                # frame on the stack; attribute them to the solver line that
                # constructed the module
                if module.construction_site is not None:
                    with location_override(module.construction_site):
                        module.finalize()
                else:
                    module.finalize()
            self.finalized = True


class Module(StatementSpeaker):
    """
    Base class for puzzle modules.

    Modules provide organization and domain-specific logic for different
    components of a puzzle. Each module has its own namespace in the ASP
    program, and its statement verbs speak on its own segment.
    """

    def __init__(self, puzzle: Puzzle, name: str, primary_namespace: bool = False):
        """
        Initialize a module.

        Args:
            puzzle: The puzzle this module belongs to
            name: The name of this module (used as the segment name)
            primary_namespace: If True, then do not add namespace prefixes for this module
        """
        if type(self) is Module:
            raise ValueError("Cannot instantiate an abstract Module object")

        self._puzzle = puzzle
        if not all(c.isalnum() for c in name) or not name[0].isalpha():
            raise ValueError(f"Bad name {name}; must be alphanumeric and start with a letter")
        self._name = name.lower()
        self._namespace = "" if primary_namespace else f"{self._name}"

        # The solver line constructing this module: rules the module emits
        # during finalize() are attributed here (see Puzzle.finalize)
        self._construction_site = capture_location()

        # Register with the puzzle, capturing this module's segment
        self._segment = puzzle.register_module(self)

    @property
    def _statement_target(self) -> Segment:
        return self._segment

    @property
    def construction_site(self) -> SourceLocation | None:
        """The solver line that constructed this module, if captured."""
        return self._construction_site

    @property
    def name(self) -> str:
        """Get the name of this module."""
        return self._name

    @property
    def namespace(self) -> str:
        """Get the namespace for this module."""
        return self._namespace

    @property
    def puzzle(self) -> Puzzle:
        """Get the puzzle this module belongs to."""
        return self._puzzle

    @property
    def segment(self) -> Segment:
        """Get this module's segment in the ASP program."""
        return self._segment

    def finalize(self) -> None:
        """
        Called just before rendering in case the module needs to add any rules based on an internal state.
        """
        pass


def cached_predicate[T](init_func: Callable[[Any], T]) -> Callable[[Any], T]:
    """
    Decorator for caching predicates in Module classes.

    This decorator will cache predicate definitions and only execute their initialization
    logic the first time they are accessed.

    Args:
        init_func: The property function that initializes and returns the predicate

    Returns:
        A wrapped property that caches the predicate after first access
    """
    attr_name = f"_{init_func.__name__}"

    @wraps(init_func)
    def getter(self: Any) -> T:
        # Check if the predicate has already been initialized
        if not hasattr(self, attr_name) or getattr(self, attr_name) is None:
            # Initialize the predicate and store it
            setattr(self, attr_name, init_func(self))

        # Return the cached predicate
        return cast(T, getattr(self, attr_name))

    return getter
