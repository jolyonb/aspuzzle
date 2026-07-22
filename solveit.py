#!/usr/bin/env python3
import argparse
import json
import pathlib

from aspalchemy import GroundingError, Predicate
from aspuzzle.solver import Solver


def solve(
    filename: str,
    preview_puzzle: bool = False,
    render: bool = True,
    solve_puzzle: bool = True,
    max_solutions: int = 1000,
    timeout: int = 0,
    display_solutions: bool = True,
    display_stats: bool = True,
    visualize: bool = True,
    validate: bool = True,
    output_file: str | None = None,
    no_output_file: bool = False,
    quiet: bool = False,
    analyze_grounding: bool = False,
    annotate: bool = False,
    svg_file: str | None = None,
) -> None:
    """
    Loads the puzzle from the given filename and solves it based on options.

    Args:
        filename: Path to the puzzle JSON file
        preview_puzzle: Whether to preview the puzzle before solving
        render: Whether to render the ASP program
        solve_puzzle: Whether to solve the puzzle
        max_solutions: Maximum number of solutions to find (0 to enumerate all);
            the default is high enough that an exhausted search proves uniqueness
            for ordinary puzzles
        timeout: Wall-clock limit in seconds (0 for no limit)
        display_solutions: Whether to display found solutions
        display_stats: Whether to display solver statistics
        visualize: Whether to visualize the solution as ASCII
        validate: Whether to validate solutions against expected solutions
        output_file: File to write the ASP program to (defaults to solver_scripts/[puzzle_name].lp)
        no_output_file: Don't write the ASP program to a file
        quiet: Suppress all output except errors
        analyze_grounding: Print the grounding profile (ground-atom counts per
            predicate, joined to the deriving Python lines) and aspif size
        annotate: Additionally write a [name].annotated.lp with "% file:line"
            provenance notes; the canonical .lp stays unannotated
        svg_file: Write an SVG render to this path — the first solution when
            solving, the puzzle preview otherwise (e.g. with --render-only)
    """
    # Find the file to open
    if not filename.endswith(".json"):
        filename += ".json"
    path = pathlib.Path(filename)

    if not path.exists():
        # Try looking in the puzzles directory
        path = path.parent / "puzzles" / filename

    if not path.exists():
        raise FileNotFoundError(f"Could not find puzzle file: {filename}")

    with open(path) as f:
        config = json.load(f)

    # Create the appropriate solver
    solver = Solver.from_config(config)

    # Preview the puzzle if requested
    if preview_puzzle and not quiet:
        print("\n=== Puzzle Preview ===")
        print(solver.render_puzzle())

    # Render the puzzle (constructs the puzzle rules)
    asp_program = solver.render_program()
    if render and not quiet:
        print("\n=== Clingo Script ===")
        print(asp_program)

    # Save the script to file
    if not no_output_file:
        if output_file:
            output_path = pathlib.Path(output_file)
            if not output_path.suffix:
                output_path = output_path.with_suffix(".lp")
        else:
            # Create default output path
            puzzle_name = pathlib.Path(filename).stem
            output_dir = pathlib.Path("solver_scripts")
            output_path = output_dir / f"{puzzle_name}.lp"

        with open(output_path, "w") as f:
            f.write(asp_program)

        if render and not quiet:
            print(f"\n(Script program written to {output_path})")

        # Annotated sidecar: provenance notes churn on unrelated edits, so
        # they never go into the canonical (checked-in) .lp
        if annotate:
            # Append rather than replace the suffix: with_suffix would fold
            # distinct outputs like out.v1/out.v2 onto one sidecar path
            if output_path.suffix == ".lp":
                annotated_path = output_path.with_name(f"{output_path.stem}.annotated.lp")
            else:
                annotated_path = output_path.with_name(f"{output_path.name}.annotated.lp")
            with open(annotated_path, "w") as f:
                f.write(solver.render_program(annotate=True))
            if not quiet:
                print(f"(Annotated program written to {annotated_path})")

    try:
        # Analyze the grounding if requested
        if analyze_grounding and not quiet:
            print("\n=== Recursion Analysis ===")
            print(solver.analyze_recursion())
            grounded = solver.ground()
            print("\n=== Grounding Analysis ===")
            print(grounded.analyze_grounding())
            print("\n=== Statement Analysis ===")
            print(grounded.analyze_statements())
            print(f"\ngrounding time: {grounded.grounding_time:.2f}s")
            print(f"aspif size: {len(grounded.aspif()):,} bytes")

        # Solve the puzzle
        solutions: list[dict[str, list[Predicate]]] = []
        if solve_puzzle:
            grounded = solver.ground()  # cached: separates grounding time from solving time
            solutions, result = solver.solve(models=max_solutions, timeout=timeout)

            # Display solutions
            if display_solutions and not quiet:
                solver.display_results(solutions, result, visualize=visualize)

            # Print statistics
            if display_stats and not quiet:
                if not analyze_grounding:
                    print(f"\nGrounding time: {grounded.grounding_time:.2f}s")
                solver.display_statistics(result)

            # Validate solutions
            if validate and not quiet and "solutions" in config:
                solver.validate_solutions(solutions)

        # Write the SVG render: the first solution when available, else the preview
        if svg_file is not None:
            svg_path = pathlib.Path(svg_file)
            solution = solutions[0] if solutions else None
            svg_path.write_text(solver.render_puzzle_svg(solution))
            if not quiet:
                label = "Solution" if solution is not None else "Preview"
                print(f"({label} SVG written to {svg_path})")
    except GroundingError as e:
        # Already formatted with the offending ASP, a caret, and the
        # "generated by file:line" note back to solver code
        print("\n=== Grounding Error ===")
        print(e)
        raise SystemExit(1) from e


def main() -> None:
    """Main entry point for the solver CLI."""
    parser = argparse.ArgumentParser(
        description="ASPuzzle solver CLI tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("filename", help="Path to puzzle JSON file (with or without .json extension)")

    # Render options
    render_group = parser.add_argument_group("Rendering options")
    render_group.add_argument("--no-preview", action="store_true", help="Suppress the puzzle preview before solving")
    render_exclusive = render_group.add_mutually_exclusive_group()
    render_exclusive.add_argument("--render", action="store_true", help="Render the ASP program (default)")
    render_exclusive.add_argument("--no-render", action="store_true", help="Don't render the ASP program")
    render_exclusive.add_argument(
        "--render-only", action="store_true", help="Only render the ASP program without solving"
    )
    render_group.add_argument(
        "--output-file", "-o", help="Write the ASP program to this file (default: solver_scripts/[puzzle_name].lp)"
    )
    render_group.add_argument("--no-output-file", action="store_true", help="Don't write the ASP program to a file")
    render_group.add_argument(
        "--svg",
        metavar="PATH",
        help="Write an SVG render to PATH (first solution when solving, puzzle preview with --render-only)",
    )
    render_group.add_argument(
        "--annotate",
        action="store_true",
        help="Also write [name].annotated.lp with %% file:line provenance notes (canonical .lp stays unannotated)",
    )

    # Solve options
    solve_group = parser.add_argument_group("Solving options")
    solve_group.add_argument(
        "--max-solutions",
        "-m",
        type=int,
        default=1000,
        help="Maximum number of solutions to find (default 1000, so exhaustion proves uniqueness; 0 enumerates all)",
    )
    solve_group.add_argument(
        "--timeout", "-t", type=int, default=0, help="Wall-clock limit in seconds (0 for no limit)"
    )

    # Display options
    display_group = parser.add_argument_group("Display options")
    display_group.add_argument("--no-solutions", action="store_true", help="Don't display solutions")
    display_group.add_argument("--stats", action="store_true", help="Display solver statistics")
    display_group.add_argument(
        "--analyze-grounding",
        action="store_true",
        help="Print the recursion, grounding, and statement profiles with deriving Python lines, and aspif size",
    )
    display_group.add_argument("--no-viz", action="store_true", help="Don't visualize the solution")
    display_group.add_argument(
        "--no-validation", action="store_true", help="Don't validate solutions against expected solutions"
    )
    display_group.add_argument("--quiet", "-q", action="store_true", help="Suppress all output except errors")

    # Parse arguments
    args = parser.parse_args()

    # Determine rendering option
    render = not args.no_render
    solve_puzzle = not args.render_only

    solve(
        filename=args.filename,
        preview_puzzle=not args.no_preview,
        render=render,
        solve_puzzle=solve_puzzle,
        max_solutions=args.max_solutions,
        timeout=args.timeout,
        display_solutions=not args.no_solutions and not args.quiet,
        display_stats=args.stats and not args.quiet,
        visualize=not args.no_viz and not args.quiet,
        validate=not args.no_validation and not args.quiet,
        output_file=args.output_file,
        no_output_file=args.no_output_file,
        quiet=args.quiet,
        analyze_grounding=args.analyze_grounding,
        annotate=args.annotate,
        svg_file=args.svg,
    )


if __name__ == "__main__":
    main()
