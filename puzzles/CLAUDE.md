# puzzles/

This directory contains JSON configuration files that define puzzle instances for testing and validation.

Each JSON file includes the puzzle type, grid data, and expected solutions for verifying solver correctness.

## Provenance

Where a puzzle came from is recorded in two optional keys, placed above `grid`:

- `url` — where the puzzle was found
- `source` — how to identify it there (size, difficulty, puzzle ID)

Solvers ignore both. Record them whenever the puzzle has a source; a puzzle
invented for the test suite has neither.

## Naming

`<puzzle>.json` is the plain instance a rules file illustrates. Larger or
harder instances of the same type get a suffix: `<puzzle>_hard.json`,
`sudoku_16x16.json`, `slitherlink_sheep.json`.

## Renders

`svg/` holds an SVG of each puzzle and of its solution, written by the
all-puzzles test (`tests/test_puzzles.py`) — generated, never hand-edited.
