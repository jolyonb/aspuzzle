from collections.abc import Callable, Sequence
from functools import wraps
from typing import Any, TypeVar, cast

from aspalchemy import (
    ASPProgram,
    Choice,
    Comparison,
    ConditionalLiteral,
    DefinedConstant,
    NegatedSignature,
    Predicate,
    Segment,
    SolveResult,
    Term,
    When,
)


class Puzzle:
    """
    Coordinates modules and their rules to create a complete ASP program.

    The Puzzle class provides a high-level interface for defining logic puzzles
    using aspalchemy, with support for modular organization.
    """

    finalized: bool = False

    def __init__(self, name: str = "Puzzle", allow_singletons: bool = False):
        """
        Initialize a new puzzle.

        Args:
            name: A name for this puzzle (for documentation purposes)
            allow_singletons: Switch off the singleton-variable lint
                (see ASPProgram)
        """
        self.name = name
        self._program = ASPProgram(allow_singletons=allow_singletons)
        self._modules: dict[str, Module] = {}

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
        """
        if module.name in self._modules:
            raise ValueError(f"Module with name '{module.name}' is already registered")

        self._modules[module.name] = module
        return self._program.add_segment(module.name)

    # Forward statement verbs to the program's default segment
    def fact(self, *facts: Predicate) -> None:
        """
        Add unconditional statements: grounded atoms, asserted true.

        Args:
            *facts: Grounded Predicate instances
        """
        self._program.fact(*facts)

    def choose(self, choice: Choice) -> None:
        """
        Add a bare choice rule to the program's default segment.

        Args:
            choice: The Choice to state, with no body
        """
        self._program.choose(choice)

    def when(self, *conditions: Term) -> When:
        """
        Hold the conditions for a closer; see Segment.when.

        Args:
            *conditions: One or more conditions that must be satisfied

        Returns:
            A pending context completed by exactly one of
            .derive/.choose/.require/.forbid/.penalize
        """
        return self._program.when(*conditions)

    def forbid(self, *conditions: Term) -> None:
        """
        Create a constraint which forbids the specified combination of conditions.

        Args:
            *conditions: One or more conditions that must not be simultaneously satisfied
        """
        self._program.forbid(*conditions)

    def require(self, target: Comparison | Predicate) -> None:
        """
        Require that a comparison or an atom holds in every answer set.
        Takes exactly one target; syntactic sugar for a forbid constraint
        on its flip. See Segment.require.
        """
        self._program.require(target)

    def add_segment(self, segment: str | Segment) -> Segment:
        """
        Add a segment to the program and return it: a string pre-declares
        an empty segment, a Segment object attaches it as-is. Statements
        are spoken on the returned handle (module segments are added at
        registration).
        """
        return self._program.add_segment(segment)

    def comment(self, text: str) -> None:
        """
        Add a comment to the program.

        Args:
            text: The comment text
        """
        self._program.comment(text)

    def blank_line(self) -> None:
        """Add a blank line to the program for formatting."""
        self._program.blank_line()

    def section(self, title: str) -> None:
        """
        Add a section header to the program.

        Args:
            title: The section title
        """
        self._program.section(title)

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

    def solve(self, timeout: int = 0) -> SolveResult:
        """
        Solve the puzzle, returning a SolveResult that yields Models lazily.

        The stream is unbounded: take the models you need (islice, or a
        for-loop with break); clasp computes only what you consume.

        Args:
            timeout: Wall-clock limit in seconds (0 for no limit); on timeout, models found
                     so far are yielded and 'exhausted' remains False
        """
        return self._program.solve(timeout=timeout)

    def render(self) -> str:
        """
        Render the puzzle as an ASP program.

        Returns:
            str: The rendered ASP program.
        """
        self.finalize()
        self._program.header = f"{self.name} by ASPuzzle"
        return self._program.render()

    def finalize(self) -> None:
        """Ensures all modules finalize their code before rendering or solving"""
        if not self.finalized:
            for module in self._modules.values():
                module.finalize()
            self.finalized = True


class Module:
    """
    Base class for puzzle modules.

    Modules provide organization and domain-specific logic for different
    components of a puzzle. Each module has its own namespace in the ASP program.
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

        # Register with the puzzle, capturing this module's segment
        self._segment = puzzle.register_module(self)

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

    # Statement verbs spoken on this module's segment

    def fact(self, *predicates: Predicate) -> None:
        """
        Add unconditional statements to this module's segment.

        Args:
            *predicates: Grounded predicate instances
        """
        self._segment.fact(*predicates)

    def choose(self, choice: Choice) -> None:
        """
        Add a bare choice rule to this module's segment.

        Args:
            choice: The Choice to state, with no body
        """
        self._segment.choose(choice)

    def when(self, *conditions: Term) -> When:
        """
        Hold conditions for a closer, in this module's segment.

        Args:
            *conditions: One or more conditions that must be satisfied

        Returns:
            A pending context completed by exactly one of
            .derive/.choose/.require/.forbid/.penalize
        """
        return self._segment.when(*conditions)

    def forbid(self, *conditions: Term) -> None:
        """
        Create a constraint in this module's segment.

        Args:
            *conditions: One or more conditions that must not be simultaneously satisfied
        """
        self._segment.forbid(*conditions)

    def require(self, target: Comparison | Predicate) -> None:
        """
        Require that a comparison or an atom holds, in this module's
        segment. Takes exactly one target; syntactic sugar for a forbid
        constraint on its flip. See Segment.require.
        """
        self._segment.require(target)

    def comment(self, text: str) -> None:
        """
        Add a comment to this module's segment.

        Args:
            text: The comment text
        """
        self._segment.comment(text)

    def blank_line(self) -> None:
        """Add a blank line to this module's segment for formatting."""
        self._segment.blank_line()

    def section(self, title: str) -> None:
        """
        Add a section header to this module's segment.

        Args:
            title: The section title
        """
        self._segment.section(title)

    def finalize(self) -> None:
        """
        Called just before rendering in case the module needs to add any rules based on an internal state.
        """
        pass


T = TypeVar("T")


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
