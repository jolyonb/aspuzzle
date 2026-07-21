from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from typing import TYPE_CHECKING, Any

from aspalchemy import (
    ANY,
    ConditionalLiteral,
    DefinedConstant,
    ExplicitPool,
    Expression,
    Field,
    Pool,
    Predicate,
    PredicateArg,
    Segment,
    V,
    Variable,
)
from aspuzzle.puzzle import Module, Puzzle, cached_predicate
from aspuzzle.rendering.scene import Edge, Vertex

if TYPE_CHECKING:
    from aspuzzle.rendering.ascii.geometry import AsciiGeometry
    from aspuzzle.rendering.scene import LayoutNeeds, SceneStyle
    from aspuzzle.rendering.sheet.geometry import SheetGeometry
    from aspuzzle.rendering.svg.geometry import SvgGeometry

# Representing a location and a value
type GridCellData = tuple[tuple[int, ...], int | str]


class GridCell(Predicate, show=False):
    """
    The base for every grid's Cell class. Concrete grids declare a typed
    subclass (e.g. RectangularCell with row/col fields, named "cell") and
    clone it per instance via in_namespace(), so cells are statically typed
    wherever the grid type is known. This base exists so cell-valued fields
    in grid-agnostic code can be typed Field[GridCell] — "must be a grid
    cell" — without knowing any particular grid's shape.
    """

    def __init__(self, *args: PredicateArg, **kwargs: PredicateArg) -> None:
        # Like Predicate's own stub: checkers cannot know a dynamic Cell's
        # fields, and without this they would use the zero-field init
        # synthesized for this (fieldless) base
        super().__init__(*args, **kwargs)


# What a Field[GridCell] slot accepts: a grounded cell, or any term standing
# for one. Narrower than PredicateArg, which admits the ints and strings a
# cell-valued field rejects.
type CellArg = GridCell | Variable | Expression | Pool | DefinedConstant


# The grid vocabulary, typed; each grid instance clones these into its own
# namespace via in_namespace() in the cached predicate properties below
class Direction(Predicate, show=False):
    name: Field[str]
    vector: Field[GridCell]


class Directions(Predicate, show=False):
    name: Field[str]


class Opposite(Predicate, show=False):
    direction1: Field[str]
    direction2: Field[str]


class OrthogonalDirections(Predicate, show=False):
    name: Field[str]


class Orthogonal(Predicate, show=False):
    cell1: Field[GridCell]
    cell2: Field[GridCell]


class OrthogonalDir(Predicate, show=False):
    cell1: Field[GridCell]
    direction: Field[str]
    cell2: Field[GridCell]


class VertexSharing(Predicate, show=False):
    cell1: Field[GridCell]
    cell2: Field[GridCell]


class CellOrder(Predicate, show=False):
    """
    A total order over a grid's cells, given as its immediate-successor
    relation: cell_order(prev, next) holds when `next` follows `prev` with no
    cell between them. The atoms form a single linear chain threading every
    cell exactly once, in ascending clingo term order, built by rules each grid
    type emits in its CellOrder property.

    Exists so that "the first cell satisfying some condition" — the anchor a
    connectivity constraint roots its flood-fill at — can be found by an
    O(cells) sweep along the chain in find_anchor_cell(), instead of the
    O(cells²) all-pairs "smaller than every other candidate" comparison. Both
    pick the lexicographically minimum candidate; the chain just gets there
    without grounding a body literal per pair.

    Invariant every consumer relies on: the chain covers *exactly* the cells a
    candidate can occupy. A candidate lying off the chain has neither a
    predecessor nor a successor, so the sweep can never reach it and it would
    silently become a second anchor — find_anchor_cell() guards against this
    explicitly (see there).
    """

    prev: Field[GridCell]
    next: Field[GridCell]


class Grid(Module, ABC):
    """Abstract base class for all grid types in puzzles."""

    def __init__(
        self,
        puzzle: Puzzle,
        name: str = "grid",
        primary_namespace: bool = True,
    ):
        """Initialize a base grid module."""
        super().__init__(puzzle, name, primary_namespace)
        self._has_outside_border: bool = False
        # Topology memos: grid geometry is immutable after construction, and
        # rendering calls these per scene element, so results are cached
        self._coords_cache: dict[GridCell, tuple[int, ...]] = {}
        self._cell_by_coords: dict[tuple[int, ...], GridCell] | None = None
        self._opposites: dict[str, str] | None = None
        self._vectors: dict[str, tuple[int, ...]] | None = None

    @abstractmethod
    def with_new_puzzle(self, puzzle: Puzzle) -> Grid:
        """Return a copy of this Grid with a new puzzle."""

    @property
    def has_outside_border(self) -> bool:
        """Whether an outside border was included in the grid definition."""
        return self._has_outside_border

    @classmethod
    @abstractmethod
    def from_config(
        cls,
        puzzle: Puzzle,
        config: dict[str, Any],
        name: str = "grid",
        primary_namespace: bool = True,
    ) -> Grid:
        """Create a grid from configuration."""
        pass

    @abstractmethod
    def parse_grid(
        self, grid_data: list[str] | list[list[str | int]], map_to_integers: bool = False
    ) -> list[GridCellData]:
        """
        Parse the grid data into a structured format.

        Args:
            grid_data: The raw grid data as a list of strings, or a list of lists of integers or strings
            map_to_integers: Whether to convert symbols to unique integers

        Returns:
            List of (loc, value) tuples for non-empty cells
        """
        pass

    @property
    @abstractmethod
    def cell_fields(self) -> list[str]:
        """Returns the list of field names associated with the Cell predicate for this grid"""

    @property
    @abstractmethod
    def cell_var_names(self) -> list[str]:
        """Returns the default list of variable names for the Cell predicate for this grid"""

    @property
    @abstractmethod
    def direction_vectors(self) -> list[tuple[str, tuple[int, ...]]]:
        """Returns the list of directions and vectors for this grid"""

    @property
    @abstractmethod
    def opposite_directions(self) -> list[tuple[str, str]]:
        """Returns the list of opposite direction names for this grid"""

    @property
    @abstractmethod
    def orthogonal_direction_names(self) -> list[str]:
        """Returns the list of orthogonal direction names for this grid"""

    @property
    @abstractmethod
    def line_direction_names(self) -> list[str]:
        """Returns the list of line direction names for this grid"""

    @property
    @abstractmethod
    def line_direction_descriptions(self) -> dict[str, str]:
        """Returns human-readable descriptions of line directions"""
        pass

    @abstractmethod
    def get_line_count(self, direction: str) -> int:
        """Returns the number of lines in the specified direction"""
        pass

    @property
    @abstractmethod
    def Cell(self) -> type[GridCell]:
        """Get the Cell predicate for this grid."""

    @property
    @abstractmethod
    def OutsideGrid(self) -> type[Predicate]:
        """Get the OutsideGrid predicate identifying cells in the outside border."""

    @property
    @cached_predicate
    def Direction(self) -> type[Direction]:
        """Get the Direction predicate for this grid, defining all possible directions as vectors."""
        DirectionClone = Direction.in_namespace(self.namespace)

        self.section("Define directions in the grid")

        direction_facts = []
        for name, coords in self.direction_vectors:
            cell_args = dict(zip(self.cell_fields, coords, strict=True))
            direction_facts.append(DirectionClone(name=name, vector=self.Cell(**cell_args)))

        self.fact(*direction_facts)

        return DirectionClone

    @property
    @cached_predicate
    def Directions(self) -> type[Directions]:
        """Get the Directions predicate, identifying all directions."""
        DirectionsClone = Directions.in_namespace(self.namespace)
        self.section("All directions")
        self.when(self.Direction(name=V.N, vector=ANY)).derive(DirectionsClone(name=V.N))
        return DirectionsClone

    @property
    @cached_predicate
    def Opposite(self) -> type[Opposite]:
        """Get the Opposite predicate, which identifies which directions are opposites."""
        OppositeClone = Opposite.in_namespace(self.namespace)
        self.section("Opposite directions")
        for dir1, dir2 in self.opposite_directions:
            self.fact(OppositeClone(dir1, dir2))
        return OppositeClone

    @property
    @cached_predicate
    def OrthogonalDirections(self) -> type[OrthogonalDirections]:
        """Get the OrthogonalDirections predicate, identifying orthogonal directions."""
        OrthogonalDirectionsClone = OrthogonalDirections.in_namespace(self.namespace)
        self.section("Orthogonal directions")
        self.fact(OrthogonalDirectionsClone(ExplicitPool(self.orthogonal_direction_names)))
        return OrthogonalDirectionsClone

    @property
    @cached_predicate
    def Orthogonal(self) -> type[Orthogonal]:
        """Get the orthogonal adjacency predicate (cells that share an edge)."""
        OrthogonalClone = Orthogonal.in_namespace(self.namespace)

        D = V.D
        cell = self.cell()
        vector = self.cell(suffix="vec")
        cell_plus_vector = self.add_vector_to_cell(cell, vector)

        # Initialize predicates that we'll need
        _ = self.Direction
        _ = self.OrthogonalDirections

        self.section("Orthogonal adjacency definition")

        # Define cells that share an edge (orthogonally adjacent).
        # The small direction relations must precede the cell literals: with the
        # vector bound to a constant first, gringo resolves cell_plus_vector by
        # indexed lookup. With the cell literal first, gringo's join planner
        # degrades to scanning all cells per binding — O(cells²) grounding TIME
        # for the same O(cells) ground program (verified byte-identical output,
        # ~20-50x faster grounding on large grids).
        self.when(
            self.OrthogonalDirections(D),
            self.Direction(D, vector=vector),
            cell,
            cell_plus_vector,
        ).derive(OrthogonalClone(cell1=cell, cell2=cell_plus_vector))

        return OrthogonalClone

    @property
    @cached_predicate
    def OrthogonalDir(self) -> type[OrthogonalDir]:
        """Get the orthogonal adjacency + direction predicate (cells that share an edge)."""
        OrthogonalDirClone = OrthogonalDir.in_namespace(self.namespace)

        D = V.D
        cell = self.cell()
        vector = self.cell(suffix="vec")
        cell_plus_vector = self.add_vector_to_cell(cell, vector)

        # Initialize predicates that we'll need
        _ = self.Direction
        _ = self.OrthogonalDirections

        self.section("Orthogonal adjacency with direction definition")

        # Direction literals first: same join-order requirement as Orthogonal
        # (cell-first bodies ground in O(cells²) time; see comment there)
        self.when(
            self.OrthogonalDirections(D),
            self.Direction(D, vector=vector),
            cell,
            cell_plus_vector,
        ).derive(OrthogonalDirClone(cell1=cell, direction=D, cell2=cell_plus_vector))

        return OrthogonalDirClone

    @property
    @cached_predicate
    def VertexSharing(self) -> type[VertexSharing]:
        """Get the vertex-sharing adjacency predicate."""
        VertexSharingClone = VertexSharing.in_namespace(self.namespace)

        cell = self.cell()
        vector = self.cell(suffix="vec")
        cell_plus_vector = self.add_vector_to_cell(cell, vector)

        # Initialize predicates that we'll need
        _ = self.Direction

        self.section("Vertex-sharing adjacency definition")

        # Define cells that share a vertex. Direction literal first: same
        # join-order requirement as Orthogonal (cell-first bodies ground in
        # O(cells²) time; see comment there)
        self.when(
            self.Direction(ANY, vector=vector),
            cell,
            cell_plus_vector,
        ).derive(VertexSharingClone(cell1=cell, cell2=cell_plus_vector))

        return VertexSharingClone

    @property
    def CellOrder(self) -> type[CellOrder]:
        """
        Get the CellOrder predicate: the successor chain over this grid's cells.
        Concrete grids override this as a cached predicate whose rules produce
        a single linear chain visiting exactly the interior cells (never an
        outside border) in ASCENDING clingo term order — the chain-based anchor
        selection in find_anchor_cell() relies on that order to pick the same
        cell a lexicographic minimum would. Grids that cannot express their
        cell ordering leave this unimplemented, and find_anchor_cell falls back
        to its quadratic encoding.
        """
        raise NotImplementedError(f"{type(self).__name__} does not define a cell order chain")

    @property
    @abstractmethod
    def Line(self) -> type[Predicate]:
        """Get the Line predicate defining major lines in the grid."""

    @property
    @abstractmethod
    def LineOfSight(self) -> type[Predicate]:
        """Get the LineOfSight predicate defining major lines in the grid, with position indexing."""

    def find_anchor_cell(
        self,
        condition_predicate: type[Predicate],
        cell_field: str,
        anchor_name: str,
        segment: Segment,
        condition_fields: dict[str, Any] | None = None,
        anchor_fields: list[str] | None = None,
    ) -> type[Predicate]:
        """
        Find the lexicographically minimum cell that satisfies the given condition.

        Args:
            condition_predicate: The predicate class to check
            cell_field: The name of the field that contains the cell location
            anchor_name: Name for the anchor predicate
            segment: Segment to publish these rules to
            condition_fields: Dictionary of field names to values to include in the condition predicate
            anchor_fields: List of field names from condition_fields to include in the anchor predicate

        Returns:
            The anchor predicate class that marks the anchor cell

        Example:
            ```
            # Find anchor for white cells with specific value
            anchor = grid.find_anchor_cell(
                condition_predicate=WhiteCell,
                cell_field="loc",
                anchor_name="white_anchor",
                segment=module.segment,
                condition_fields={"value": 5},  # Only white cells with value=5
                anchor_fields=["value"]         # Include value in anchor predicate
            )
            # Creates: white_anchor(loc=min_cell, value=5)
            ```
        """
        segment.section(f"Find anchor cell for {condition_predicate.get_name()}")

        if condition_fields is None:
            condition_fields = {}
        if anchor_fields is None:
            anchor_fields = []

        # Validate that anchor_fields are actually in condition_fields
        for field in anchor_fields:
            if field not in condition_fields:
                raise ValueError(f"Anchor field '{field}' not found in condition_fields")

        # Define the anchor predicate
        AnchorPred = Predicate.define(
            anchor_name, {cell_field: GridCell, **dict.fromkeys(anchor_fields)}, namespace=self.namespace, show=False
        )

        Cell, Other = V.Cell, V.Other
        anchor_kwargs = {k: v for k, v in condition_fields.items() if k in anchor_fields}

        def candidate(loc: PredicateArg) -> Predicate:
            return condition_predicate(**{cell_field: loc}, **condition_fields)

        try:
            cell_order: type[CellOrder] | None = self.CellOrder
        except NotImplementedError:
            cell_order = None

        if cell_order is not None:
            # ----------------------------------------------------------------
            # Linear encoding of "the first candidate in term order".
            #
            # The declarative one-liner (the fallback branch below) reads
            # perfectly — "the candidate that is <= every candidate" — but it
            # grounds a conditional literal ranging over every candidate inside
            # every candidate's own rule: O(candidates²) body literals. On large
            # grids that dominated whole programs (up to 97% of aspif) while
            # staying invisible to the per-statement profile, because it is all
            # one rule with a huge body rather than many rules.
            #
            # Instead, walk the grid's cell-order chain and take the first
            # candidate on it. This grounds O(cells) literals and, because the
            # chain is ascending term order, elects the *same* lexicographically
            # minimum candidate — so every model, including this hidden anchor
            # scaffolding, is unchanged.
            #
            # `seen(C)` means "some candidate lies at or before C on the chain":
            # seeded at each candidate, then swept forward. The first candidate
            # is then the one whose chain-predecessor is NOT yet seen.
            # ----------------------------------------------------------------
            SeenPred = Predicate.define(
                f"{anchor_name}_seen",
                {cell_field: GridCell, **dict.fromkeys(anchor_fields)},
                namespace=self.namespace,
                show=False,
            )
            Prev = V.Prev

            def seen(loc: PredicateArg) -> Predicate:
                return SeenPred(**{cell_field: loc}, **anchor_kwargs)

            def anchor(loc: PredicateArg) -> Predicate:
                return AnchorPred(**{cell_field: loc}, **anchor_kwargs)

            # (1) Seed: a candidate is "seen" at its own cell.
            segment.when(candidate(Cell)).derive(seen(Cell))
            # (2) Sweep: "seen" propagates forward along the chain.
            segment.when(seen(Prev), cell_order(prev=Prev, next=Cell)).derive(seen(Cell))
            # (3) Interior anchor: the first candidate has a chain-predecessor
            #     that no candidate reached, so its predecessor is not seen.
            segment.when(candidate(Cell), cell_order(prev=Prev, next=Cell), ~seen(Prev)).derive(anchor(Cell))
            # (4) Head anchor: rule (3) needs a predecessor, so the head of the
            #     chain needs its own rule. Requiring `cell_order(prev=Cell)`
            #     — the head HAS a successor — is the guard: an off-chain cell
            #     has no successor either, so it can never masquerade as the head.
            segment.when(candidate(Cell), cell_order(prev=Cell, next=ANY), ~cell_order(prev=ANY, next=Cell)).derive(
                anchor(Cell)
            )
            # (5) Safety net. The whole scheme assumes candidates lie on the
            #     chain. One that does not (neither a predecessor nor a successor
            #     of anything — e.g. an outside-border cell fed to a contiguity
            #     constraint) is unreachable by the sweep and would silently
            #     become a second anchor, weakening "one connected region" to
            #     "every component holds an anchor". Forbid it outright, turning
            #     the misuse into an immediate UNSAT rather than a wrong answer.
            #     (A one-cell grid has an empty chain and trips this too; no real
            #     puzzle runs a contiguity constraint on a single cell.)
            segment.forbid(
                candidate(Cell),
                ~cell_order(prev=Cell, next=ANY),
                ~cell_order(prev=ANY, next=Cell),
            )
        else:
            # Fallback for grids that cannot enumerate their cells into a chain:
            # the anchor is the candidate that compares <= every candidate. Reads
            # beautifully, but grounds O(candidates²) body literals — the cost the
            # chain above exists to avoid, accepted here only when unavoidable.
            segment.when(
                candidate(Cell),
                ConditionalLiteral(Cell <= Other, candidate(Other)),
            ).derive(AnchorPred(**{cell_field: Cell}, **anchor_kwargs))

        return AnchorPred

    def cell(self, suffix: str = "") -> GridCell:
        """Get a cell predicate for this grid with variable values."""
        variables = [Variable(var_name)[suffix] for var_name in self.cell_var_names]
        cell_args = dict(zip(self.cell_fields, variables, strict=True))
        return self.Cell(**cell_args)

    def outside_grid(self, suffix: str = "") -> Predicate:
        """Get an outside_grid predicate for this grid with variable values."""
        return self.OutsideGrid(self.cell(suffix=suffix))

    def distance_bound(self, cell1: GridCell, cell2: GridCell) -> Expression | None:
        """
        A lower bound on the graph distance (orthogonal steps) between two
        cells, as an ASP arithmetic expression — or None if this grid has no
        usable metric. Used to prune rule domains: cells provably further
        apart than some limit can be excluded during grounding.
        """
        return None

    def direction(self, name_suffix: str = "", vector_suffix: str = "vec") -> Predicate:
        """Get a direction predicate including names and vectors."""
        return self.Direction(name=V.N[name_suffix], vector=self.cell(suffix=vector_suffix))

    def directions(self, name_suffix: str = "") -> Predicate:
        """Get a direction predicate, listing the names of all directions."""
        return self.Directions(name=V.N[name_suffix])

    def orthogonal_directions(self, name_suffix: str = "") -> Predicate:
        """Get an orthogonal direction predicate, listing the names of orthogonal directions."""
        return self.OrthogonalDirections(name=V.N[name_suffix])

    def orthogonal(self, suffix_1: str = "", suffix_2: str = "adj") -> Predicate:
        """Get the orthogonal adjacency predicate with variable values."""
        return self.Orthogonal(cell1=self.cell(suffix_1), cell2=self.cell(suffix_2))

    def vertex_sharing(self, suffix_1: str = "", suffix_2: str = "adj") -> Predicate:
        """Get the vertex-sharing adjacency predicate with variable values."""
        return self.VertexSharing(cell1=self.cell(suffix_1), cell2=self.cell(suffix_2))

    def line(self, direction_suffix: str = "", index_suffix: str = "", loc_suffix: str = "") -> Predicate:
        """Get a line predicate for this grid with variable values."""
        return self.Line(
            direction=V.D[direction_suffix],
            index=V.Idx[index_suffix],
            loc=self.cell(suffix=loc_suffix),
        )

    # -- Python-side topology: the rendering vocabulary (no ASP, no grounding) --

    def cell_coords(self, cell: GridCell) -> tuple[int, ...]:
        """Concrete coordinates of a grounded cell, in cell_fields order."""
        coords = self._coords_cache.get(cell)
        if coords is None:
            coords = tuple(cell[field].value for field in self.cell_fields)
            self._coords_cache[cell] = coords
        return coords

    def cell_at(self, coords: tuple[int, ...]) -> GridCell | None:
        """
        The in-grid cell at concrete coordinates (cell_fields order), or
        None when no such cell exists (outside-border cells count as
        off-grid here). Every call returns the same grounded instance, so
        cells obtained this way compare by identity for free.
        """
        if self._cell_by_coords is None:
            self._cell_by_coords = {self.cell_coords(cell): cell for cell in self.all_cells()}
        return self._cell_by_coords.get(coords)

    @abstractmethod
    def neighbor(self, cell: GridCell, direction: str) -> GridCell | None:
        """
        Edge-adjacent neighbor of a grounded cell in `direction`, or None
        if off-grid (outside-border cells count as off-grid here). Must
        agree with the grid's ASP Orthogonal facts — kept honest by a
        conformance test that grounds a small instance and diffs.

        Raises:
            ValueError: If `direction` is not an edge direction of this grid
        """

    @property
    @abstractmethod
    def corner_names(self) -> Sequence[str]:
        """The corner vocabulary of this grid's cells (rectangular: nw/ne/se/sw)."""

    @abstractmethod
    def corner_across(self, corner: str, direction: str) -> str | None:
        """
        The name a cell-corner carries in the neighbor across `direction`,
        or None when that edge is not incident to the corner. Drives the
        generic vertex-canonicalization walk in vertex().
        """

    def direction_vector(self, direction: str) -> tuple[int, ...]:
        """The concrete step vector for a direction name, per direction_vectors."""
        if self._vectors is None:
            self._vectors = dict(self.direction_vectors)
        try:
            return self._vectors[direction]
        except KeyError:
            raise ValueError(f"No vector defined for direction {direction!r}") from None

    def opposite_direction(self, direction: str) -> str:
        """The opposite of `direction`, per opposite_directions."""
        if self._opposites is None:
            self._opposites = dict(self.opposite_directions)
        try:
            return self._opposites[direction]
        except KeyError:
            raise ValueError(f"No opposite defined for direction {direction!r}") from None

    def edge(self, cell: GridCell, direction: str) -> Edge:
        """
        The canonical Edge between `cell` and its `direction`-neighbor,
        valid for boundary edges too (no neighbor required). Of the two
        spellings of an interior edge, the one with the lexicographically
        smaller (cell_coords, direction) key wins, so the same geometric
        edge compares and hashes equal from either side — including when
        spelled from an outside-border cell, where the in-grid neighbor's
        spelling wins outright. The only public Edge constructor.
        """
        if direction not in self.orthogonal_direction_names:
            raise ValueError(f"{direction!r} is not an edge direction of this grid")
        adjacent = self.neighbor(cell, direction)
        if adjacent is None:
            return Edge(cell, direction)
        flipped = self.opposite_direction(direction)
        if self.cell_at(self.cell_coords(cell)) is None:
            # neighbor() only returns in-grid cells, so this spelling's
            # cell is the outside one: collapse to the in-grid spelling
            return Edge(adjacent, flipped)
        if (self.cell_coords(cell), direction) <= (self.cell_coords(adjacent), flipped):
            return Edge(cell, direction)
        return Edge(adjacent, flipped)

    def vertex(self, cell: GridCell, corner: str) -> Vertex:
        """
        The canonical Vertex for a cell corner: every spelling of the same
        geometric point (found by walking corner_across through neighbors)
        collapses to the lexicographically smallest (cell_coords, corner).
        The only public Vertex constructor.
        """
        if corner not in self.corner_names:
            raise ValueError(f"{corner!r} is not a corner name of this grid")
        best_key = (self.cell_coords(cell), corner)
        best = (cell, corner)
        seen = {best_key}
        frontier: list[tuple[GridCell, str]] = [best]
        while frontier:
            current_cell, current_corner = frontier.pop()
            for direction in self.orthogonal_direction_names:
                across = self.corner_across(current_corner, direction)
                if across is None:
                    continue
                adjacent = self.neighbor(current_cell, direction)
                if adjacent is None:
                    continue
                key = (self.cell_coords(adjacent), across)
                if key in seen:
                    continue
                seen.add(key)
                frontier.append((adjacent, across))
                if key < best_key:
                    best_key = key
                    best = (adjacent, across)
        return Vertex(*best)

    @abstractmethod
    def all_cells(self) -> Iterator[GridCell]:
        """Every in-grid cell as a grounded Cell instance (no outside border)."""

    @property
    def cell_count(self) -> int:
        """
        How many cells the grid holds. Counts all_cells() unless a grid knows
        the answer from its dimensions, which it should override to say —
        all_cells() builds a Cell instance per cell, and counting is a common
        enough bound (a region can be no larger than the grid) to be worth
        answering without them.
        """
        return sum(1 for _ in self.all_cells())

    # -- geometry factories consumed by renderers --

    @abstractmethod
    def ascii_geometry(self, needs: LayoutNeeds, style: SceneStyle) -> AsciiGeometry:
        """The ASCII geometry realizing this grid's cells/edges/vertices as
        canvas characters, sized for the given layout needs and style."""

    def svg_geometry(self) -> SvgGeometry:
        """The SVG geometry for this grid; grids without one raise NotImplementedError."""
        raise NotImplementedError(f"{type(self).__name__} has no SVG geometry yet")

    def sheet_geometry(self, needs: LayoutNeeds) -> SheetGeometry:
        """The sheet (TSV) geometry for this grid; grids without one raise NotImplementedError."""
        raise NotImplementedError(f"{type(self).__name__} has no sheet geometry yet")

    @abstractmethod
    def add_vector_to_cell(self, cell_pred: GridCell, vector_pred: GridCell) -> GridCell:
        """
        Add a vector to a cell, returning the new cell location.

        Args:
            cell_pred: The starting cell predicate
            vector_pred: The vector predicate (as defined in Direction)

        Returns:
            A new Cell predicate with the vector added
        """


def do_not_show_outside(pred: Predicate, grid: Grid) -> None:
    """
    Show this predicate only for cells inside the grid.
    The predicate must be instantiated with the grid.cell() location.
    """
    grid.puzzle.show_when(ConditionalLiteral(pred, [pred, ~grid.outside_grid()]))
