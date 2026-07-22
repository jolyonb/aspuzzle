# ASPuzzle: Logic Puzzle Solver Framework

## Terminology

Do not call aspalchemy a "DSL" (in code, comments, docs, or conversation) — it
is a Python library that builds ASP programs. Describe it in those plain
terms.

## Mental Model

This project sits at the top of a **layered architecture** for solving logic puzzles using Answer Set Programming (ASP):

```
High Level:  aspuzzle    - Puzzle-specific solvers and framework (this repo)
Middle Layer: aspalchemy - Python-to-ASP translation layer (external dependency)
Low Level:    clingo     - ASP solver engine
```

**Core Insight**: The framework transforms high-level puzzle constraints (Python) into low-level logical constraints (ASP) that can be efficiently solved.

The `aspalchemy` package (an object-oriented Python interface to ASP programming: Variable, Predicate, Expression, Choice, Aggregate, coordinated by the `ASPProgram` class) is a normal installed dependency — its internals live in its own repository.

## Architecture Layers

### 1. ASPuzzle Framework (`aspuzzle/`)
**Purpose**: Modular framework for puzzle-specific logic

- **Puzzle Class**: Orchestrates modules and manages ASP program lifecycle
- **Module System**: Composable components (Grid, RegionConstructor, SymbolSet)
- **Grid Abstraction**: Handles coordinate systems, adjacency, rendering
- **Key Insight**: Each puzzle type composes different modules differently

### 2. Solver Implementations (`aspuzzle/solvers/`)
**Purpose**: Concrete puzzle implementations

- **Base Solver**: Common patterns (config loading, validation, rendering)
- **Dynamic Loading**: Solvers discovered by name from configuration
- **Rendering System**: ASCII visualization with customizable symbols/colors
- **Key Pattern**: `construct_puzzle()` method defines puzzle-specific constraints

## Main Interface

### CLI Tool (`solveit.py`)
**Purpose**: Command-line interface that orchestrates the entire solving pipeline

- **Configuration Loading**: Reads JSON puzzle files from `puzzles/` directory
- **Dynamic Solver Creation**: Uses `Solver.from_config()` to instantiate appropriate solver
- **ASP Generation**: Calls `construct_puzzle()` and renders complete ASP program
- **File Management**: Automatically saves generated ASP to `solver_scripts/[puzzle].lp`
- **Solving Pipeline**: Manages clingo execution with timeout/solution limits
- **Rich Output**: Provides puzzle preview, ASCII visualization, statistics, and validation

**Key Usage Patterns**:
```bash
# Basic solving with statistics
python solveit.py minesweeper --stats

# Render ASP program only (for debugging)
python solveit.py sudoku --render-only

# Performance testing with limits
python solveit.py fillomino --max-solutions 10 --timeout 30

# Quiet mode for automation
python solveit.py nurikabe --quiet --no-viz
```

**Optimization Workflow**: Use `solveit.py` repeatedly with different rule implementations to compare performance:
1. Modify constraint logic in solver class
2. Run `python solveit.py puzzle --stats` to get timing/grounding metrics
3. Compare statistics to identify optimal rule formulations
4. Check generated `.lp` files to verify rule efficiency

## Critical Design Patterns

### 1. Module Composition
```python
# Typical puzzle construction
puzzle = Puzzle()
grid = RectangularGrid(puzzle, rows=9, cols=9)
regions = RegionConstructor(puzzle, grid, ...)
symbols = SymbolSet(grid, ...)
# Each module adds its own constraints to the puzzle
```

### 2. Cached Predicates
```python
@property
@cached_predicate  # Only execute initialization once
def SomePredicate(self) -> type[Predicate]:
    # Heavy computation here
    return Predicate.define(...)
```

### 3. Constraint Patterns
```python
# Counting constraints
puzzle.count_constraint(count_over=X, condition=Y, exactly=N)

# Choice rules with cardinality
Choice(element=P(x), condition=Q(x)).exactly(1)

# Region connectivity via RegionConstructor
regions = RegionConstructor(..., contiguous_regionless=True)
```

## Extension Points

### Adding New Puzzle Types
1. **Create solver**: `aspuzzle/solvers/newpuzzle.py`
2. **Inherit from Solver**: Implement `construct_puzzle()` and `get_render_spec()`
3. **Add rules**: `rules/newpuzzle.md`
4. **Add test cases**: `puzzles/newpuzzle.json`

### Adding New Grid Types
1. **Inherit from Grid**: Implement abstract methods in `aspuzzle/grids/`
2. **Define coordinate system**: `cell_class`, `cell_fields`, `direction_vectors`
3. **Implement adjacency and layout**: `add_vector_to_cell()`, `neighbor()`, `ascii_geometry()`

### Adding New Modules
1. **Inherit from Module**: Add to `aspuzzle/`
2. **Use cached predicates**: Define predicates with `@cached_predicate`
3. **Emit rules in `__init__`**, and only use `finalize()` for rules that depend on
   state the module gathers while the puzzle is built (SymbolSet's placement choice
   waits for the solver to finish adding symbols). A finalize() reads only its own
   module's state — see `Module.finalize`

### Complex Framework Extensions
For advanced modifications (non-rectangular grids, novel module types):

**Recommended Approach**: Work in partnership with the project author, using existing implementations as templates:
- **Alternative grid geometries**: Extend `Grid` base class, copy `RectangularGrid` structure
- **Novel module types**: Follow `RegionConstructor`/`SymbolSet` patterns for module organization
- **New ASP constructs**: These belong in the `aspalchemy` package (its own repository), following its `Choice`/`Aggregate` patterns

Given the project's maturity, these extensions are best accomplished by adapting proven templates rather than designing from scratch.

## Performance Considerations

### ASP Program Size
- **Grounding explosion**: Complex conditions can create enormous ground programs
- **Mitigation**: O(N^2) grounding is okay (N number of cells), but O(N^3) is not
- **First stop**: `python solveit.py puzzle --render-only --analyze-grounding` —
  four instruments in one flag, every row naming the solver line responsible:
  - **Recursion analysis** (static, before grounding): the components gringo
    grounds as fixpoints, with the statements re-evaluated inside each. A
    derivation in a fixpoint that need not feed the recursion is the classic
    finding — restate it with `.require()` (this fix alone was 95% of a
    100×100 Galaxies grounding). An UNSTRATIFIED component means circular
    rules through `not` — expensive to solve, almost always an accident.
  - **Grounding analysis**: ground-atom counts per signature
  - **Statement analysis**: ground instantiation counts per statement —
    constraints charge their own rows here, which atom counts cannot see
    (a pairwise uniqueness constraint was 92% of that same Galaxies program,
    invisible to the signature profile)
  - **aspif size**: the honest size measure
- **Programmatic**: `solver.ground()` exposes `analyze_grounding()`,
  `analyze_statements()`, `ground_text()`, `aspif()`;
  `puzzle.analyze_recursion()` needs no grounding at all
- **Domain pruning**: when a RegionConstructor grounds at cells×anchors, pass
  `region_domain=` conditions (see Galaxies' mirror bound, Nurikabe's
  per-clue `grid.distance_bound`)

### Module Dependencies
- **Predicate access triggers rule generation**: First access to cached predicate defines all rules
- **Pattern**: Call `finalize()` to ensure all rules are generated

## Debugging Strategy

### 1. Validation Errors
- **Check input symbols**: `supported_symbols` in solver
- **Verify grid dimensions**: Config validation in solver
- **Examine constraints**: Look for overconstrained rules

### 2. No Solutions Found
- **Check generated ASP**: Look at `.lp` files in `solver_scripts/`
- **Remove constraints**: Comment out rules to find conflicting constraints
- **Use smaller instances**: Test with minimal puzzle size first

### 3. Performance Issues - Step-by-Step Debugging
When a puzzle solver is too slow, follow this systematic workflow:

**Step 1: Baseline Performance Check**
```bash
# Get timing statistics for your puzzle
python solveit.py puzzle --stats
```
- **Target**: 10×10 puzzle should solve in < 0.1s in most cases
- If significantly slower, investigate scaling issues

**Step 2: Profile the Grounding**
```bash
python solveit.py puzzle --render-only --analyze-grounding
```
Read the report top-down — the top rows name the guilty solver lines:
- A constraint or rule with an outsized statement count: rethink its joins
  (aggregates instead of pairwise rules; `possible_region`-style domain
  pruning; anonymous variables where a binding is not needed)
- A statement inside a recursive component that need not feed the recursion:
  restate the derivation as a `.require()`
- An UNSTRATIFIED component: a stratum of your encoding folded back on
  itself through `not` — almost certainly unintended; restructure the tower

**Step 3: Scaling Analysis by Grid Size (if the profile is inconclusive)**
Test the same puzzle type at different sizes and compare profiles; counts
should scale roughly O(N²) in cells. Closed forms fall straight out of the
statement counts (e.g. a row growing as (N−2)·A·(A−1) is cells×anchors²).

**Step 4: Direct ASP Testing (Rapid Iteration)**
For fast debugging without Python overhead:
```bash
# Generate ASP file once
python solveit.py puzzle --render-only
# Test modifications directly with clingo
python -m clingo solver_scripts/puzzle.lp -n 0
```
- Edit the .lp file directly to test rule modifications
- Much faster iteration cycle for constraint optimization

**Step 5: Constraint Optimization**
Focus on the profile's top rows:
- Replace multi-variable rules with BOUNDED aggregates:
  `.require(Count(...) == 1)`, never `N == Count(...)` in a body plus
  `.require(N == 1)` — the assignment form makes gringo enumerate every
  feasible count per cell
- Keep derivations out of recursive components when a `.require()` says
  the same thing — a rule inside a fixpoint is re-evaluated across the
  whole iteration
- Use intermediate predicates to break complex conditions
- Restrict region membership with `region_domain=` when anchors are fixed
- Keep the encoding a tower: each stratum negates only settled strata below
- When an aggregate's VALUE is needed (not just a bound on it), guess it with
  a choice rule and pin it with a bounded aggregate, rather than deriving it
  and joining against the result — the join multiplies the assignment form's
  already-quadratic grounding. Fillomino's per-cell numbers work this way:
  guess a number per cell, propagate equality along the region constructor's
  connection edges, verify one bounded count per anchor
- Never guess what the input already fixes: exclude clued cells from the
  choice rule and state their value, so no rejected candidate ever grounds
  (see Fillomino's clues)

**Step 6: Verify Improvement**
```bash
python solveit.py puzzle --stats
```
- Confirm improved scaling with larger grid sizes
- Ensure solution correctness is maintained

### 4. Rendering Problems
- **Check render config**: Verify predicate names match solver output
- **Priority conflicts**: Higher priority items render on top
- **Color issues**: Ensure ANSI codes work in terminal

## File Organization Strategy

- **Generated files**: `solver_scripts/` - Never edit manually
- **Test data**: `puzzles/` - JSON configs with expected solutions
- **Documentation**: `rules/` - Human-readable puzzle rules
- **Framework**: `aspuzzle/` - High-level, extensible puzzle framework
- **Implementations**: `aspuzzle/solvers/` - Growing collection of puzzle types
- **Core library**: `aspalchemy` - external dependency providing the low-level ASP interface

This architecture enables rapid development of new puzzle types while maintaining performance and correctness through the strong typing and validation provided by the ASPAlchemy foundation.
