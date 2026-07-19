"""
Per-grid geometry implementations, one module per (grid type, backend)
pair: all the grid-specific layout knowledge consumed by the renderers.
Distinct from aspuzzle/grids/ — nothing here emits ASP; each grid class's
geometry factory imports its implementation from this package.
"""
