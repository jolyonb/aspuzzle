from typing import Any

from aspalchemy import Choice, ConditionType, Count, Field, Predicate, Term, V
from aspuzzle.grids.base import CellArg, Grid, GridCell
from aspuzzle.grids.rectangulargrid import RectangularGrid
from aspuzzle.puzzle import Module, Puzzle, cached_predicate


# The region vocabulary, typed; cloned per module instance via in_namespace()
class Regionless(Predicate, show=False):
    loc: Field[GridCell]


class Anchor(Predicate, show=False):
    loc: Field[GridCell]


class Connected(Predicate, show=False):
    loc: Field[GridCell]


class Region(Predicate, show=False):
    loc: Field[GridCell]
    anchor: Field[GridCell]


class ConnectsTo(Predicate, show=False):
    loc1: Field[GridCell]
    loc2: Field[GridCell]


class ConnectedRegionless(Predicate, show=False):
    loc: Field[GridCell]


class PossibleRegion(Predicate, show=False):
    loc: Field[GridCell]
    anchor: Field[GridCell]


class RegionConstructor(Module):
    """
    Module for constructing regions in grid-based puzzles.

    This module provides functionality to create and manage regions within a grid,
    supporting both fixed-anchor approaches (e.g., Nurikabe) and dynamic-anchor
    approaches (e.g., Fillomino).

    There is deliberately no RegionSize predicate, natural as it is to reach
    for one: materializing sizes means an assignment-form aggregate
    (Size = #count{...}), which grounds one rule per feasible (anchor, size)
    pair with the anchor's whole domain in each body — and every join against
    the result multiplies that again. Instead:
    - To CONSTRAIN a region's size against a known bound or target, compare
      region_size() inside require() — one bounded constraint per anchor
      (see the min/max rules below).
    - To CONSUME sizes as values, guess the value with a choice rule and pin
      it with region_size() — see Fillomino's number encoding.
    """

    def __init__(
        self,
        puzzle: Puzzle,
        grid: Grid,
        name: str = "regions",
        primary_namespace: bool = True,
        anchor_predicate: type[Predicate] | None = None,
        anchor_fields: dict[str, Any] | None = None,
        allow_regionless: bool = True,
        forbid_regionless_pools: bool = False,
        contiguous_regionless: bool = False,
        non_adjacent_regions: bool = False,
        forbid_region_pools: bool = False,
        min_region_size: int | None = None,
        max_region_size: int | None = None,
        rectangular_regions: bool = False,
        region_domain: list[Term] | None = None,
    ):
        """
        Initialize a RegionConstructor module.

        Args:
            puzzle: The puzzle this module belongs to
            grid: The grid this region constructor operates on
            name: The name of this module (used for the segment)
            primary_namespace: If True, don't add namespace prefixes
            anchor_predicate: Optional predicate defining fixed anchors for regions
                              If None, flexible anchors will be used
            anchor_fields: Optional dictionary of field names to values for filtering specific anchors
            allow_regionless: If True, cells can be outside any region
                            If False, all cells must belong to a region
            forbid_regionless_pools: If True, no regionless pools are allowed (2x2 in rectangular grid)
            contiguous_regionless: If True, regionless cells must be contiguous
            non_adjacent_regions: If True, regions cannot be adjacent to each other
            forbid_region_pools: If True, no pools allowed in any region (2x2 in rectangular grid)
            min_region_size: The global minimum region size allowed
            max_region_size: The global maximum region size allowed
            rectangular_regions: Whether to force regions to be rectangular (grid-dependent meaning)
            region_domain: Optional extra conditions bounding which (cell, anchor) pairs can
                           belong to the same region, written against the canonical terms
                           grid.cell() (the member cell) and grid.cell(suffix="anchor") (the
                           anchor cell). Conditions may join the caller's own predicates.
                           MUST overapproximate: every (cell, anchor) pair realized in any
                           valid solution must satisfy the conditions — then solutions are
                           preserved exactly and grounding shrinks to the possible domain.
                           For size-bounded regions, grid.distance_bound(cell, anchor) is
                           the building block (see the Nurikabe solver's per-clue bound).
                           With dynamic anchors, being an anchor is a solve-time choice, so
                           the domain enumerates every cell as a potential anchor and the
                           conditions read "IF this cell anchors a region, that cell could
                           belong to it"; pairs whose anchor never materializes are inert,
                           since the domain only ever restricts propagation. That enumeration
                           is cells^2, but it is a single filter pass emitting only the
                           surviving pairs, and without it the whole downstream program
                           grounds at cells^2 scale — the pruning it enables is worth the pass.
        """
        super().__init__(puzzle, name, primary_namespace)
        self.grid = grid
        self._anchor_predicate = anchor_predicate
        self._anchor_fields = anchor_fields or {}
        self.dynamic_anchors = anchor_predicate is None
        self.allow_regionless = allow_regionless
        self.forbid_regionless_pools = forbid_regionless_pools
        self.contiguous_regionless = contiguous_regionless
        self.non_adjacent_regions = non_adjacent_regions
        self.forbid_region_pools = forbid_region_pools
        self.min_region_size = min_region_size
        self.max_region_size = max_region_size
        self.rectangular_regions = rectangular_regions
        self.region_domain = region_domain

    @property
    @cached_predicate
    def Regionless(self) -> type[Regionless]:
        """
        Get the Regionless predicate defining cells not in any region.

        Raises:
            ValueError: If allow_regionless is False (all cells must be in a region)
        """
        if not self.allow_regionless:
            raise ValueError("Cannot use Regionless predicate when allow_regionless is False")

        return Regionless.in_namespace(self.namespace)

    @property
    @cached_predicate
    def Anchor(self) -> type[Anchor]:
        """Get the Anchor predicate defining the cells that anchor regions."""
        return Anchor.in_namespace(self.namespace)

    @property
    @cached_predicate
    def Connected(self) -> type[Connected]:
        """Get the Connected predicate defining cells that are connected to regions."""
        return Connected.in_namespace(self.namespace)

    @property
    @cached_predicate
    def Region(self) -> type[Region]:
        """Get the Region predicate defining which cells belong to which regions."""
        return Region.in_namespace(self.namespace)

    @property
    @cached_predicate
    def ConnectsTo(self) -> type[ConnectsTo]:
        """Get the ConnectsTo predicate defining connections between cells in a region."""
        return ConnectsTo.in_namespace(self.namespace)

    def region_size(self, anchor: CellArg) -> Count:
        """
        A Count aggregate over the cells of the region anchored at `anchor`,
        for bounded comparisons inside require(): one ground constraint per
        anchor, no size values ever materialized. The aggregate binds the reserved
        variable RegionSizeCell; using that name in the surrounding rule
        would turn it into a join variable and change the count's meaning.
        """
        Cell = V.RegionSizeCell
        return Count(Cell, condition=self.Region(loc=Cell, anchor=anchor))

    def finalize(self) -> None:
        """
        Called just before rendering in case the module needs to add any rules based on an internal state.
        """
        # We need access to grid.has_outside_border, which we can only do in finalize
        self._construct_rules()

    def _construct_rules(self) -> None:
        """Generate all rules for region construction."""
        # Variables we'll need
        C, N, A = V.C, V.N, V.A
        cell = self.grid.cell()

        # Section 1: Cell Status Assignment
        self.section("Cell Status Assignment")

        # Create a choice rule for cell status assignment
        choice = Choice(self.Connected(loc=cell))
        if self.allow_regionless:
            choice.add(self.Regionless(loc=cell))
        if self.dynamic_anchors:
            choice.add(self.Anchor(loc=cell))
        choice = choice.exactly(1)
        # Apply the choice rule for each valid cell
        conditions: list[Term] = [cell]
        if self.grid.has_outside_border:
            conditions.append(~self.grid.outside_grid())

        self.when(*conditions).choose(choice)

        # For fixed anchors, we need to identify the anchor locations
        if not self.dynamic_anchors:
            # Define anchors based on the provided predicate
            assert self._anchor_predicate is not None
            anchor_args = {**self._anchor_fields, "loc": C}
            anchor_conditions: list[Term] = [self._anchor_predicate(**anchor_args)]
            if self.grid.has_outside_border:
                anchor_conditions.append(~self.grid.OutsideGrid(loc=C))
            self.when(*anchor_conditions).derive(self.Anchor(loc=C))

            # Anchor cells are connected
            self.when(self.Anchor(loc=C)).derive(self.Connected(loc=C))

        # Section 2: Connection Rules
        self.section("Connection Rules")

        # Connected cells can connect to other orthogonal cells
        choice_conditions: list[ConditionType] = [self.grid.Orthogonal(cell1=C, cell2=N)]
        if self.allow_regionless:
            choice_conditions.append(~self.Regionless(loc=N))
        choice = Choice(self.ConnectsTo(loc1=C, loc2=N), condition=choice_conditions)
        if self.dynamic_anchors:
            # Dynamic anchors: connected cells must have at least one connection (as they're not anchors)
            choice = choice.at_least(1)
            # For fixed anchors, no minimum constraint is needed, as connected cells can also be anchors
        self.when(self.Connected(loc=C)).choose(choice)

        # Connections are symmetric (bidirectional)
        self.when(self.ConnectsTo(loc1=C, loc2=N)).derive(self.ConnectsTo(loc1=N, loc2=C))

        # Section 3: Region Propagation
        self.section("Region Propagation")

        # Optional membership domain: an overapproximation of which (cell, anchor)
        # pairs can share a region, from caller-supplied region_domain conditions.
        # Guarding the propagation rule with it shrinks the grounding of
        # everything built on Region — including the recursive connection rules —
        # from cells x anchors down to the possible domain.
        domain_conditions: list[Term] = list(self.region_domain or [])
        anchor_cell = self.grid.cell(suffix="anchor")

        if self.dynamic_anchors:
            # We use domain conditions to demand that Possible(cell, anchor) has anchor <= cell
            # which substantially decreases the space of possibly dynamic anchors
            AnchorLoc = V.AnchorLoc
            domain_conditions += [AnchorLoc == anchor_cell, AnchorLoc <= self.grid.cell()]

        Possible: type[PossibleRegion] | None = None
        if domain_conditions:
            Possible = PossibleRegion.in_namespace(self.namespace)
            # For fixed anchors the domain enumerates real anchors only; for
            # dynamic anchors any cell may anchor, so the cell atom is the domain
            anchor_domain = anchor_cell if self.dynamic_anchors else self.Anchor(loc=anchor_cell)
            self.when(cell, anchor_domain, *domain_conditions).derive(Possible(loc=cell, anchor=anchor_cell))

        # Anchors define their own region
        self.when(self.Anchor(loc=C)).derive(self.Region(loc=C, anchor=C))
        # ... so the domain has to admit that pair, regardless of any other conditions
        if Possible is not None and not self.dynamic_anchors:
            self.when(self.Anchor(loc=C)).derive(Possible(loc=C, anchor=C))
        # Regions propagate through connections
        propagation: list[Term] = [self.ConnectsTo(loc1=N, loc2=C), self.Region(loc=C, anchor=A)]
        if Possible is not None:
            propagation.append(Possible(loc=N, anchor=A))
        self.when(*propagation).derive(self.Region(loc=N, anchor=A))
        # Orthogonal cells in the same region must be connected. Stated as a
        # requirement, not a derivation: deriving ConnectsTo here would place
        # this three-way join inside the recursive Region/ConnectsTo component,
        # where gringo re-evaluates it across the whole fixpoint; the requirement
        # grounds in one pass after the recursion, with the same models.
        self.when(
            self.grid.Orthogonal(cell1=C, cell2=N),
            C < N,  # Only need conditions on one side of the symmetric ConnectsTo
            self.Region(loc=C, anchor=A),
            self.Region(loc=N, anchor=A),
        ).require(self.ConnectsTo(loc1=C, loc2=N))

        # ...and no connection reaches out of a cell's region into a cell
        # the domain bars from it.
        if Possible is not None:
            self.when(
                self.ConnectsTo(loc1=C, loc2=N),
                self.Region(loc=C, anchor=A),
            ).require(Possible(loc=N, anchor=A))

        # Section 4: Integrity Constraints
        self.section("Integrity Constraints")

        # Every in-region cell must have exactly one anchor.
        conditions = [cell]
        if self.allow_regionless:
            conditions.append(~self.Regionless(loc=cell))
        if self.grid.has_outside_border:
            conditions.append(~self.grid.outside_grid())
        self.when(*conditions).require(Count(A, condition=self.Region(loc=cell, anchor=A)) == 1)

        # Optional rules

        # Regionless pools
        if self.forbid_regionless_pools:
            self.section("Forbid regionless pools")
            if isinstance(self.grid, RectangularGrid):
                self.grid.forbid_2x2_blocks(self.Regionless, segment=self.segment)
            else:
                raise ValueError("Don't know how to forbid pools with this grid type")

        # Region pools
        if self.forbid_region_pools:
            self.section("Forbid region pools")
            if isinstance(self.grid, RectangularGrid):
                self.grid.forbid_2x2_blocks(self.Region, segment=self.segment, fixed_fields={"anchor": A})
            else:
                raise ValueError("Don't know how to forbid pools with this grid type")

        # Non-adjacent regions
        if self.non_adjacent_regions:
            self.section("Regions cannot touch")
            # Cheapest to express this as "forbid cells next to a region cell that aren't the same region or regionless"
            # Can write as "if region(C1, A1) and region(C2, A2), then A1 == A2", but that's more expensive to ground
            self.when(
                self.Region(loc=C[1], anchor=A),
                self.grid.Orthogonal(cell1=C[1], cell2=C[2]),
            ).forbid(
                ~self.Region(loc=C[2], anchor=A),
                ~self.Regionless(loc=C[2]),
            )

        # Contiguous regionless area
        if self.contiguous_regionless:
            # Predicate for connectedness
            ConnectedClone = ConnectedRegionless.in_namespace(self.namespace)

            # Create an anchor for the regionless area
            anchor_pred = self.grid.find_anchor_cell(
                condition_predicate=self.Regionless,
                cell_field="loc",
                anchor_name="regionless_anchor",
                segment=self.segment,
            )

            self.section("Contiguity for regionless cells")

            # Mark the anchor as connected
            cell = self.grid.cell()
            self.when(anchor_pred(loc=cell)).derive(ConnectedClone(cell))

            # Propagate connectivity
            C, C_adj = V.C, V.C_adj
            self.when(
                ConnectedClone(loc=C),
                self.grid.Orthogonal(cell1=C, cell2=C_adj),
                self.Regionless(loc=C_adj),
            ).derive(ConnectedClone(loc=C_adj))

            # Every regionless cell must be connected
            self.when(self.Regionless(loc=C)).require(ConnectedClone(loc=C))

        # Min/Max region sizes
        if self.min_region_size or self.max_region_size:
            self.section("Min/Max region sizes")
            AnchorCell = V.Anchor
            if self.min_region_size == self.max_region_size:
                self.when(self.Anchor(loc=AnchorCell)).require(self.region_size(AnchorCell) == self.min_region_size)
            else:
                if self.min_region_size:
                    self.when(self.Anchor(loc=AnchorCell)).require(self.region_size(AnchorCell) >= self.min_region_size)
                if self.max_region_size:
                    self.when(self.Anchor(loc=AnchorCell)).require(self.region_size(AnchorCell) <= self.max_region_size)

        # Rectangular regions
        if self.rectangular_regions:
            self.section("Rectangular region constraints")

            if not isinstance(self.grid, RectangularGrid):
                raise ValueError("Don't know how to force rectangular regions with this grid type")

            # If three corners of a 2x2 are in a region, then the 4th corner
            # must be as well. Where the membership domain bars that fourth
            # corner, the three corners are an impossible configuration, so
            # say so: deriving the barred atom instead would put Region atoms
            # outside the domain, and every rule reading Region then grounds
            # against the inflated set.
            C, R = V.C, V.R
            corners = [(0, 0), (1, 0), (0, 1), (1, 1)]
            for corner in corners:
                head_row, head_col = corner
                body = [
                    self.Region(loc=self.grid.Cell(row=R + row, col=C + col), anchor=A)
                    for row, col in corners
                    if (row, col) != corner
                ]
                head = self.Region(loc=self.grid.Cell(row=R + head_row, col=C + head_col), anchor=A)
                if Possible is None:
                    self.when(*body).derive(head)
                else:
                    domain = Possible(loc=self.grid.Cell(row=R + head_row, col=C + head_col), anchor=A)
                    self.when(*body, domain).derive(head)
                    self.when(*body).require(domain)
