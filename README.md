# ASPuzzle

Copyright Jolyon Bloomfield 2025

`aspuzzle` is a modular framework for solving logic puzzles with Answer Set Programming. Puzzle rules are expressed as composable Python modules (grids, regions, symbol sets), translated to clingo programs via the [`aspalchemy`](https://github.com/jolyonb/aspalchemy) library, and solved by clingo.

## Usage

Puzzle instances live as JSON configs in `puzzles/`. Solve one from the command line:

```bash
python solveit.py sudoku            # solve puzzles/sudoku.json
python solveit.py minesweeper --stats
python solveit.py fillomino --render-only   # just emit the ASP program
```

Generated ASP programs are written to `solver_scripts/`, and human-readable puzzle rules live in `rules/`.

## Development

```bash
uv sync
uv run pytest tests/    # solves the whole puzzle corpus end to end
```
