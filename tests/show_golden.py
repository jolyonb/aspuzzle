#!/usr/bin/env python3
"""View golden render files in the terminal, optionally against current output.

Goldens store raw ANSI escapes, so printing them to a terminal shows the
colored render exactly as pinned. Usage:

    python -m tests.show_golden                      # list available goldens
    python -m tests.show_golden sudoku               # show sudoku's goldens
    python -m tests.show_golden sudoku --current     # golden vs current render
    python -m tests.show_golden sudoku --mode solution

--current re-renders through the same backend table the golden tests use and
reports match/mismatch per mode (exit code 1 on any mismatch) — the review
tool for deciding whether a change deserves --update-goldens.
"""

import argparse
import sys
from pathlib import Path

from tests.test_golden_renders import BACKENDS, GOLDEN_ROOT, MODES, solver_and_first_solution
from tests.test_puzzles import get_puzzle_files


def list_goldens() -> None:
    if not GOLDEN_ROOT.is_dir():
        print(f"No goldens directory at {GOLDEN_ROOT}")
        print("Generate with: pytest tests/test_golden_renders.py --update-goldens")
        return
    for backend_dir in sorted(p for p in GOLDEN_ROOT.iterdir() if p.is_dir()):
        for puzzle_dir in sorted(p for p in backend_dir.iterdir() if p.is_dir()):
            modes = " ".join(sorted(f.stem for f in puzzle_dir.glob("*.txt")))
            print(f"{backend_dir.name}/{puzzle_dir.name}: {modes}")


def find_puzzle_file(name: str) -> Path:
    matches = [p for p in get_puzzle_files() if p.stem == name]
    if not matches:
        raise SystemExit(f"No puzzle config named '{name}' in puzzles/")
    return matches[0]


def show(puzzle: str, backend: str, modes: list[str], current: bool) -> bool:
    """Print the requested goldens (and current renders); returns True if all match."""
    all_match = True
    for mode in modes:
        golden_path = GOLDEN_ROOT / backend / puzzle / f"{mode}.txt"
        print(f"=== {backend}/{puzzle}/{mode} (golden) ===")
        if golden_path.exists():
            golden = golden_path.read_text()
            print(golden)
        else:
            golden = None
            print("(no golden recorded)")

        if current:
            if backend not in BACKENDS:
                known = ", ".join(sorted(BACKENDS))
                raise SystemExit(f"No renderer registered for backend '{backend}'; known: {known}")
            solver, solution = solver_and_first_solution(find_puzzle_file(puzzle))
            rendered = BACKENDS[backend](solver, solution if mode == "solution" else None)
            matches = rendered == golden
            all_match = all_match and matches
            print(f"=== {backend}/{puzzle}/{mode} (current) {'✓ matches golden' if matches else '✗ DIFFERS'} ===")
            print(rendered)
        print()
    return all_match


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("puzzle", nargs="?", help="Puzzle name (e.g. 'sudoku'); omit to list available goldens")
    parser.add_argument("--backend", default="ascii", help="Backend directory (default: ascii)")
    parser.add_argument("--mode", choices=[*MODES, "both"], default="both", help="Render mode (default: both)")
    parser.add_argument("--current", action="store_true", help="Also render current output and report match/mismatch")
    args = parser.parse_args()

    if args.puzzle is None:
        list_goldens()
        return

    modes = list(MODES) if args.mode == "both" else [args.mode]
    if not show(args.puzzle, args.backend, modes, args.current):
        sys.exit(1)


if __name__ == "__main__":
    main()
