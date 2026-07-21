# Legacy encodings: where the earlier work lives

Several puzzle types in this folder were already solved in aspuzzle's
predecessor, [blog_puzzles](https://github.com/jolyonb/blog_puzzles) (local
checkout: `~/gitrepos/blog_puzzles`). Those encodings are clingo written by
hand, not aspalchemy, so nothing here is copy-and-paste — but they settle the
modelling questions, and each ships sourced example puzzles with their
solutions, ready to become `puzzles/*.json` once the solver lands.

Paths below are relative to the blog_puzzles root. A "wrapper" is the Python
CLI that reads the example file and emits the clue facts; the `.pl` holds the
rules. Every wrapper shares `solvers/asp/common.py`.

`~/gitrepos/dbpuzzles` also exists — ignore it. Its `old_solvers/` is a stale
copy of blog_puzzles, its `logicsolvers/` rewrite is all ports, and it is not
under version control.

## Full solvers (wrapper + encoding + rules write-up + examples)

| Puzzle | Encoding | Wrapper | Examples |
|---|---|---|---|
| Yajilin | `solvers/asp/clingo/yajilin.pl` (73), and three variants: `yajilin_fulllane.pl` (74), `yajilin_oneoff.pl` (78), `yajilin_closedloop.pl` (74) | `solvers/asp/yajilin.py` (188) | `examples/yajilin*.txt` — 9x9 and four 13x13, all sourced. Clue value and clue direction are two parallel grids. |
| Statue Park | `solvers/asp/clingo/statue_park.pl` (75) | `solvers/asp/statue_park.py` (209), plus the polyomino library `solvers/asp/shapes.py` (217) | `examples/statue_park.txt` (7x7 tetrominoes), `statue_park_hard.txt` (12x12 pentominoes), `test/nathan_test.txt` |
| Hashi | `solvers/asp/clingo/hashi.pl` (40) | `solvers/asp/hashi.py` (167) | `examples/hashi.txt` (7x7), `hashi_hard.txt` (15x15), and `mh23hashi.txt` — a 31x33 monster, the largest instance in either legacy repo |
| LITS | `solvers/asp/clingo/lits.pl` (70) | `solvers/asp/lits.py` (152) | `examples/lits.txt` (6x6), `lits_hard.txt` (15x15) |
| Shikaku | `solvers/asp/clingo/shikaku.pl` (42) | `solvers/asp/shikaku.py` (146) | `examples/shikaku.txt` (5x5), `shikaku_hard.txt` (15x15) |

Each has a rules write-up alongside at `rules/<puzzle>.md` in blog_puzzles,
which is where this folder's draft for it came from.

Beware: `hashi_hard.txt`'s solution comment was pasted from `hashi.txt` and is
wrong for it. And `examples/lits.txt` carries options (`letters=LITS`,
`reflections=True`) that the wrapper reads.

## Encodings with no wrapper

Complete clingo, each with its puzzle hard-coded as facts, under
`solvers/asp/clingo/in progress/`:

| Puzzle | File | Instance embedded |
|---|---|---|
| Aquarium | `aquarium.pl` (79) | 6x6, no provenance |
| Shakashaka | `shakashaka.pl` (63) | 5x5, tiny — a smoke test at best |
| Nonogram | `nonogram.pl` (69) | 10x10 monochrome |
| Nonogram, multicolour | `nonogram_multi.pl` (89) | 5x10, three colours; handles same- and different-colour block gaps |

Same folder, no draft in this directory: `double-nonogram.pl` (187, two
overlaid images with unassigned clue sets), `sudoku_killer.pl` (113, cages
plus no-adjacent-consecutive — noted as taking over a minute to solve, so a
performance benchmark if killer sudoku ever lands), and `basalt_caves.pl`
(167, a sudoku x cave x fortress hybrid). `yosenabe.pl` is an incomplete
third-party copy — do not port it.

## Sudoku variants

Not a puzzle type but a large constraint surface this repo lacks. The
variant rules are a Jinja template inside `solvers/asp/sudoku.py` (247
lines, template from line 101) rather than in `clingo/sudoku.pl`, which
holds only the base rules. The file's docstring is the reference for the
input format; implemented settings are:

arrows, thermos, renban lines, German whisper lines, palindrome lines,
between lines, killer cages, unique region entries, ratio and consecutive
Kropki dots, clones, consecutive-adjacent restriction, knight's and king's
move restrictions, unique diagonals, odd/even cells, odd/even diagonals,
and diagonal sums. (XSums and sandwich clues are named but unimplemented.)

Two hand-written variant instances sit in `solvers/asp/clingo/`:
`sudoku_horse.pl` (a non-1..9 digit set with knight and consecutive rules,
decoded by `stuff.py`) and `examples/sudoku_arrows.txt`.

## Also there, not drafted here

`solvers/asp/slitherlink_x_minesweeper.py` (114) and its encoding (78) solve
a hybrid, with a 15x15 instance at
`examples/slitherlink_x_minesweeper.txt`. `sltogether.txt` is an
ambiguous-clue slitherlink where each clue is a two-way choice.

Do not port `blog_puzzles/sl1.txt` as a slitherlink instance: it is UNSAT,
being one reading of the ambiguous puzzle in `sltogether.txt`.
