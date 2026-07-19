# aspuzzle/grids/

This module provides grid abstractions and utilities for grid-based puzzles. It defines the interface for different grid types and provides concrete implementations along with rendering utilities.

## Core Grid Framework

### base.py
Abstract base class and utilities for all grid types:

- **`Grid`** - Abstract base class defining the grid interface
  - Inherits from `Module`, so grids are puzzle modules with their own segments
  - Defines abstract properties: `cell_fields`, `direction_vectors`, `line_direction_names`
  - Provides cached predicates: `Cell`, `Direction`, `Orthogonal`, `VertexSharing`, `Line`
  - Abstract methods: `parse_grid()`, `add_vector_to_cell()`, `neighbor()`, `ascii_geometry()`
  - `find_anchor_cell()` utility for finding lexicographically minimum cells

- **Key Predicates Generated:**
  - `Cell` - Defines valid cells in the grid
  - `Direction` - Maps direction names to vector coordinates  
  - `Orthogonal` - Cells sharing an edge
  - `VertexSharing` - Cells sharing any vertex
  - `Line` - Major lines in the grid (rows, columns, etc.)
  - `LineOfSight` - Lines with position indexing

- **`do_not_show_outside()`** - Utility to hide predicates for outside border cells

### rectangulargrid.py
Concrete implementation for rectangular grids with rows and columns:

- **`RectangularGrid`** - Standard rectangular grid implementation
  - Uses 1-based indexing for rows and columns
  - Supports configurable dimensions via `from_config()`
  - 8-directional support (N, NE, E, SE, S, SW, W, NW)
  - Orthogonal directions: N, E, S, W
  - Line directions: E (rows), S (columns)

- **Grid Parsing:**
  - `parse_grid()` - Converts string/list grid data to structured format
  - Ignores "." characters as empty cells
  - Optional integer mapping for region-based puzzles
  - Validates grid dimensions

- **Constraint Utilities:**
  - `forbid_2x2_blocks()` - Prevents 2x2 blocks of a symbol
  - `forbid_checkerboard()` - Prevents disconnecting checkerboard patterns
  - Outside border support with `OutsideGrid` predicate

## Rendering

Grid classes carry a pure-Python topology vocabulary for the rendering
system (`aspuzzle/rendering/`): `neighbor()`, canonical `edge()`/`vertex()`
constructors, `corner_names`/`corner_across`, `all_cells()`, and an
`ascii_geometry()` factory returning the grid's character-layout engine
(per-grid geometries live in `aspuzzle/rendering/grids/`, e.g.
`RectangularAsciiGeometry`). Rendering code types against the `RenderGrid`
protocol, so it can never reach the ASP statement verbs. Region coloring
for visualization is `aspuzzle/rendering/regioncolor.py` — deterministic
pure Python, no solving.

## Key Features

1. **Extensible Architecture**: Abstract Grid class allows new grid types
2. **Rich Adjacency Support**: Orthogonal, vertex-sharing, and directional adjacency
3. **Flexible Parsing**: Handles various input formats with validation
4. **Constraint Helpers**: Common pattern prevention (pools, checkerboards)
5. **Rendering Topology**: Pure-Python neighbor/edge/vertex vocabulary behind the RenderGrid protocol
