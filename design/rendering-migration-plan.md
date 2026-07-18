# Rendering Redesign — Migration Plan

Repo: `/Users/jolyon/gitrepos/aspuzzle`. Target: the approved unified design (typed Scene IR, grid geometry objects, `AsciiRenderer`, per-backend visibility, `get_render_spec()`).

**Green criteria, enforced after every step** (the full pre-commit gauntlet — tests are in every tool's include list and are held to the same standard as the package):

```bash
uv run pytest -q          # all tests incl. golden renders
uv run mypy .             # strict config in pyproject
uv run pyright            # include list covers aspuzzle, tests, solveit.py
uv run ruff check
uv run ruff format --check
```

plus eyeballing **both render modes** for the solvers a step touches, using the default-preview form of the CLI (no `--no-preview`, no `--no-viz`):

```bash
python solveit.py <puzzle> --no-render --no-output-file
```

which prints `=== Puzzle Preview ===` (the `render_puzzle(solution=None)` path) *and* `Solution 1:` (the solved path). Both flow through whatever pipeline the solver is on at that step.

**Solver inventory** (14 classes, 19 puzzle configs): cave, fillomino, galaxies, hitori, minesweeper, numberlink (2 configs), nurikabe, skyscrapers, slitherlink, starbattle, starbattle_shapeless, stitches, sudoku (4 configs), tents.

---

## Compatibility-shim decision (stated up front, no hedge)

- **No shim translating old dict configs to `RenderSpec`.** The dicts are the thing being deleted; a translator would have to reimplement `_preprocess_predicates`'s untyped semantics and would be dead code in ~6 PRs. The design (§12) already rejected it; this plan concurs.
- **Yes to a 6-line dispatch bridge** inside `Solver.render_puzzle`, alive only during Steps 7–10:

  ```python
  def render_puzzle(self, solution=None, *, use_colors: bool = True) -> str:
      if type(self).get_render_spec is not Solver.get_render_spec:   # ported solver
          return AsciiRenderer(use_colors=use_colors).render(self.build_scene(solution))
      ...existing old path...                                        # unported solver
  ```

  This is not a compatibility layer — it never converts between models. It is what lets 14 solvers migrate in four reviewable PRs while the repo stays green and every unported solver renders byte-identically. Deleted in Step 11.

Both old and new pipelines coexist untouched from Step 2 through Step 10; Steps 2–6 are purely additive (old pipeline not even called differently).

---

## Step 1 — Golden capture harness (additive; pins today's behavior)

**Create:**
- `tests/conftest.py` — `--update-goldens` pytest option.
- `tests/test_golden_renders.py` — parametrized over puzzle × mode × backend: every `puzzles/*.json`, both modes (`preview` = render with no solution, `solution` = first model's render), and every entry in a `BACKENDS` table mapping backend name → render callable (`ascii` today; `svg`/`tsv` join as one-line additions). Solver construction + solve are cached once per puzzle across parametrizations. Exact-string comparison (ANSI escapes included) against `tests/goldens/<backend>/<puzzle>/<mode>.txt`.
- `tests/goldens/ascii/**` — generated with `uv run pytest tests/test_golden_renders.py --update-goldens`, committed.

**Notes:** goldens are per-backend from day one (`ascii/` directory level). Galaxies/Stitches/Starbattle goldens depend on today's non-contractual `RegionColoring` model order — commit them anyway; they are re-recorded deliberately when those solvers port (Steps 9–10), and the determinism contract lands in Step 6.

**Verify:** `uv run pytest tests/test_golden_renders.py` twice (stability); `python solveit.py sudoku --no-render --no-output-file` unchanged.

## Step 2 — The scene model: `aspuzzle/rendering/` core (additive)

**Create:**
- `aspuzzle/rendering/__init__.py` — re-exports the solver-facing vocabulary.
- `aspuzzle/rendering/color.py` — `PaletteColor` (16 members), `Rgb` (validated in `__post_init__`), `type ColorSpec = PaletteColor | Rgb`.
- `aspuzzle/rendering/backend.py` — `Backend` (ASCII, SVG, SHEET), `BackendSet`/`ALL_BACKENDS`/`ASCII_ONLY`/`SVG_ONLY`/`SHEET_ONLY`. A leaf module so both `glyph.py` and `scene.py` can import it without a cycle.
- `aspuzzle/rendering/glyph.py` — `Glyph` with per-backend variants (`text` baseline + optional `svg`/`sheet` overrides, resolved via `for_backend`; design §3.2 — e.g. `Glyph("A", svg="⛺")` for Tents), `glyph_for_value` (the single home of the 0–9/A+ convention, currently duplicated in `sudoku.py:150` and `skyscrapers.py:139`; ≥10 carries the literal number as its sheet variant).
- `aspuzzle/rendering/scene.py` — `Provenance`, `Layer`, `EdgeWeight`, `Edge`, `Vertex`, `SceneElementBase` (`KW_ONLY` backends/provenance), the seven element dataclasses, `SceneElement` union, `CellStyle`, `SceneStyle`, `AsciiLayoutNeeds`, `Scene` (`add`/`extend`/`glyph`/`fill`/`line_labels`/`visible`/`sorted_elements`/`layout_needs`).
- `tests/rendering/test_scene.py`, `tests/rendering/test_color_glyph.py`.

**Two concrete decisions the design leaves ambiguous, resolved here:**
1. **`CellStyle` lives in `scene.py`, not `spec.py`** (design lists it under `spec.py`, but `SceneStyle.empty: CellStyle` needs it in `scene.py`); `spec.py` and `__init__.py` re-export it.
2. **`AsciiLayoutNeeds` is defined in `scene.py`** (it is pure data — edge/vertex booleans + margin widths, no character knowledge) and re-exported from `ascii/geometry.py`. This is what lets `Scene.layout_needs(backend)` exist without violating the "scene/spec import nothing from `ascii/`" rule.

**Import direction:** `scene.py` imports `GridCell`/`Grid` from `aspuzzle.grids.base` under `TYPE_CHECKING` only; grids will import scene types at runtime (Step 3). No cycle.

**Backend-visibility mechanics land here** — this is the first of three explicit visibility waypoints: `Scene.visible/sorted_elements/layout_needs` filter at the single choke point. **Tests landing with this step:** the design's §9 `test_scene_sorting_and_backend_filtering` verbatim (SVG-only `EdgeSegment` invisible to ASCII sort; `layout_needs(Backend.ASCII).edges is False`; hidden `OutsideLabel` ⇒ no margin in `label_margins`), layer/insertion-order stability, a `SHEET_ONLY` element visible to `Backend.SHEET` and hidden from the other two, `Provenance` defaults, `Rgb` validation, `glyph_for_value` (9→"9", 10→"A").

**Verify:** `uv run pytest tests/rendering/ -q`; nothing else imports the package yet, full suite unchanged.

## Step 3 — Grid topology vocabulary (additive)

**Modify `aspuzzle/grids/base.py`** (`Grid`): add `cell_coords`, abstract `neighbor`, `edge_directions` (default: `orthogonal_direction_names`), abstract `corner_names`, `opposite_direction(d)` helper (from `opposite_directions`), `edge()` and `vertex()` canonical constructors (default implementations per design §3.4), and abstract `ascii_geometry(needs, style)` **declared but raising `NotImplementedError` by default** until Step 4 fills it (keeps this step additive), plus `svg_geometry()` default-raising.

**Modify `aspuzzle/grids/rectangulargrid.py`** (`RectangularGrid`): implement `neighbor` (pure arithmetic on `row`/`col`, off-grid and outside-border ⇒ `None`), `corner_names` (`nw/ne/se/sw`).

**Create `tests/rendering/test_grid_topology.py`:**
- The design's parametrized `test_edge_canonicalization` conformance suite (`ALL_GRID_FACTORIES` starts with one `RectangularGrid` factory — hex/tri join later).
- Vertex canonicalization (`grid.vertex(c,"se") == grid.vertex(se_neighbor,"nw")` etc.).
- **The neighbor-vs-ASP conformance test:** ground a 3×3 `RectangularGrid` via a throwaway `Puzzle`, collect `Orthogonal` atoms, diff against `{(c, d, neighbor(c,d))}` from Python.

**Verify:** full suite + goldens unchanged (nothing calls the new methods outside tests).

## Step 4 — ASCII backend, compact layout + SVG contracts frozen (additive)

**Create:**
- `aspuzzle/rendering/ascii/__init__.py`
- `aspuzzle/rendering/ascii/canvas.py` — `CharPos`, `TextSpan`, `CharCanvas` (`put` transparency rule, `put_text`, `paint_bg`, `to_string(theme, use_colors)`, width>span error).
- `aspuzzle/rendering/ascii/theme.py` — `AsciiTheme` (constructor-injected mapping; `Rgb`→nearest-palette quantization), `DEFAULT_THEME` with **exactly** today's SGR strings from `grids/rendering.py` (`"\033[34m"` etc.) so ported output is byte-identical.
- `aspuzzle/rendering/ascii/geometry.py` — `AsciiGeometry` Protocol (re-exports `AsciiLayoutNeeds`).
- `aspuzzle/rendering/ascii/renderer.py` — `AsciiRenderer` exactly per design §5.1.
- `aspuzzle/grids/rectangular_ascii_geometry.py` — `RectangularAsciiGeometry`, **compact layout only** in this step: cell `(r,c)` → char `(r-1,(c-1)·(1+cell_gap))`, painting `CellFill`/`CellGlyph`/`CellPath`/`CellLink`; the box-drawing table from `RectangularGrid.line_characters` moves here **re-keyed by `frozenset[str]`** (killing the `"ew"/"we"` duplicate keys); `path_glyph` for `CellPath`. (Placement decision: grid-specific character knowledge stays under `grids/`, per the project philosophy; `rendering/ascii/` stays grid-agnostic, matching the design's package layout which lists only the protocol there.)
- `aspuzzle/rendering/svg/__init__.py`, `aspuzzle/rendering/svg/geometry.py` — `Point`, `SvgGeometry` Protocol only (contracts frozen now, renderer later).
- `tests/rendering/test_canvas.py`, `tests/rendering/test_ascii_renderer.py`, `tests/rendering/test_import_boundaries.py`.

**Modify:** `RectangularGrid.ascii_geometry()` returns `RectangularAsciiGeometry(self, needs, style)`.

**Tests landing with this step:** the design's `test_ascii_fill_under_glyph_golden` (`"5 .\n. ."`); `cell_gap=0` joins; fill-preserves-glyph and glyph-preserves-fill on `CharCanvas`; SGR placement with an injected two-entry theme; the **guardrail tests**: `scene.py`/`spec.py`/`color.py`/`glyph.py` import nothing from `aspuzzle.rendering.ascii` (checked via module `__dict__`/AST), and no `"\033"` literal anywhere in `aspuzzle/rendering/` except `ascii/theme.py`.

**Verify:** full suite green; old pipeline untouched.

## Step 5 — Expanded layout: lanes, junctions, edges, vertices, outside labels (additive)

**Modify `aspuzzle/grids/rectangular_ascii_geometry.py`:** layout selection (compact iff `needs` has no edges/vertices, no `style.frame`, no `label_margins`), interleaved edge lanes with **collapsing**, direction-flag stamping for `EdgeSegment`/frame, `resolve_junctions` via the `frozenset[str]` table extended with the heavy family (`━┃┏…`, mixed weight = heavy wins), `VertexMark` placement, `OutsideLabel` margins (`("s", c)` above column c; `("e", r)` left of row r; `offset` rings).

**Create `tests/rendering/test_rect_geometry_expanded.py`:**
- Golden: synthetic frame-only scene; Sudoku-shaped scene (9×9, block-boundary `EdgeSegment`s at `Layer.GRID_MARK` + frame) asserting `┌─┬─┐ / ├─┼─┤` junctions — this pre-verifies Step 8's Sudoku port.
- Lane-collapse edge cases from design §11 (single stroked interior lane; stroke meeting frame).
- Slitherlink-shaped scene: closed `EdgeSegment` loop + fills beneath.
- Label margins: one ring, two rings (`offset=1`), max-width reservation.
- **Visibility × layout (second explicit visibility waypoint):** a scene whose *only* edge elements are `backends=SVG_ONLY` renders **byte-identically to its compact golden** (the §7.6 lever); an `ASCII_ONLY` label reserves a margin, an `SVG_ONLY` label does not.
- Conformance scene containing every element kind rendered through every registered geometry (suite hex/tri will join).

**Verify:** full suite; old pipeline untouched.

## Step 6 — Spec layer, `build_scene`, deterministic region coloring (additive)

**Create:**
- `aspuzzle/rendering/spec.py` — `RenderContext`, `Colorer`, `GlyphRule`, `FillRule`, `PathRule`, `EdgeRule`, `LinkRule`, `FromPredicate`, `FromClues`, `RegionFillRule`, `RegionBorderRule`, `RegionBoundaryRule`, `CustomRule`, `AtomRule`, `LineLabels`, `RenderSpec`, and the free function `build_scene(grid, spec, grid_data, solution)` — clue styles first (paint-below, matching `_build_render_grid`'s order), then atom rules (data-driven rules run with `solution=None`), then labels; provenance and `backends` stamped mechanically; **eager field-name validation with precise errors**.
- `aspuzzle/rendering/regioncolor.py` — the ASP core **moved** from `grids/region_coloring.py` (`Region`/`Adjacent`/`RegionColor` predicates, `RegionColoring._try_coloring`), retyped `BgColor` → `ColorSpec`, plus `DEFAULT_REGION_PALETTE` (≥4 `PaletteColor`s). **Determinism contract:** region ids sorted before fact emission, adjacency facts emitted sorted, first model taken — pinned by a unit test (fixed region map → fixed assignment, run twice). `grids/region_coloring.py` is left untouched (old-path Galaxies/Stitches/Starbattle still import it) until Step 11.
- `tests/rendering/test_spec.py`, `tests/rendering/test_regioncolor.py`.

**Tests landing with this step:** each rule → expected elements from hand-built `Predicate` atoms on a 3×3 `RectangularGrid`; `GlyphRule(value_field=…)` goes through `glyph_for_value` (10 → "A", fixing the multi-char `str()` defect); `RegionBoundaryRule` on a plus-shaped `inside` set yields the exact canonical edge set (boundary closure at grid edge); `RegionBorderRule(by=…)` with `solution=None` (preview completeness); `LinkRule` palette cycling deterministic over sorted atoms; provenance stamping (`FromClues`/`LineLabels`/clues → `GIVEN`, predicate rules → `DERIVED`); **`backends=` stamping from rule → every emitted element (third visibility waypoint — spec level)**; unknown-field error message.

**Verify:** full suite; old pipeline untouched.

## Step 7 — Solver integration + pilot port: Tents (behavior change, Tents only)

**Modify `aspuzzle/solvers/base.py`:** add `Solver.get_render_spec() -> RenderSpec` (default `RenderSpec()`), `Solver.build_scene(solution)`, and the **dispatch bridge** in `render_puzzle` (shown above), threading `use_colors` end-to-end on the new path (fixing the never-threaded parameter; old path left as-is for golden fidelity).

**Modify `aspuzzle/solvers/tents.py`:** delete `get_render_config` (lines 101–115), add `get_render_spec` per design §7.1 (clue `T`, `GlyphRule("tent", glyph=Glyph("A"), color=PaletteColor.YELLOW)`, `LineLabels` for both line directions from `row_clues`/`column_clues`).

**Modify goldens:** regenerate `tests/goldens/ascii/tents/*` — intentional delta: row/column counts appear in margins for the first time, in **both preview and solution**; cell area otherwise identical (default `cell_gap=1` ≡ `join_char=" "`).

**Create `tests/rendering/test_solver_specs.py`** (grows each wave): Tents spec is pure data — two `LineLabels`, one `GlyphRule`; preview scene contains `GIVEN` tree glyphs + labels and zero `DERIVED` elements; solved scene from a hand-written `{"tent": [...]}` dict contains yellow "A" glyphs. No clingo in the loop.

**Verify:** `python solveit.py tents --no-render --no-output-file` — eyeball margins in preview *and* solution; `uv run pytest` (13 solvers' goldens must be untouched — that is the bridge working).

## Step 8 — Wave 1: pure-table solvers (behavior changes only where listed)

One commit per solver (or one PR, per-solver commits), each: delete `get_render_config`, add `get_render_spec`, regenerate that solver's goldens, extend `test_solver_specs.py`.

**Verify per solver:** `python solveit.py <name> --no-render --no-output-file` (preview + solution eyeball), `uv run pytest`. For Sudoku run all four configs (`sudoku`, `sudoku_4x4`, `sudoku_6x6`, `sudoku_16x16` — the last exercises letter glyphs).

## Step 9 — Wave 2: rule-based solvers

Same mechanics. Numberlink verifies with both `numberlink` and `numberlink_letters`. Slitherlink is the big reviewed visual delta (loop drawn via expanded layout). Starbattle's port deletes its `_preprocess_config` override and `_region_colors` attribute.

## Step 10 — Wave 3: region/link solvers

Galaxies (deletes `_preprocess_for_rendering` + `_region_colors` + the `region_renderer` closure and its "shouldn't be reached" fallback) and Stitches (deletes `_preprocess_config`, `_region_colors`, the `color_index=[0]` mutable-cell closure). After this step **no solver overrides the old hooks** and nothing outside `solvers/base.py` + `grids/` imports the old rendering names.

### Per-solver migration table (Steps 7–10)

| Solver | Step | Old config → new spec | Nontrivial? / intentional golden deltas |
|---|---|---|---|
| **Tents** | 7 | `puzzle_symbols{T}` → `clues`; `tent` dict → `GlyphRule`; **+ `LineLabels` ×2** | Easy. Delta: row/col counts newly rendered (preview + solved) |
| **Minesweeper** | 8 | 0–8 `RenderSymbol` → `CellStyle` table; `mine` → `GlyphRule(glyph=Glyph("*"), color=RED)` | Trivial; byte-identical (compact, `cell_gap=1`) |
| **Hitori** | 8 | digit clues → table; `black: {symbol:None, background:WHITE}` → `FillRule("black", fill=PaletteColor.WHITE)` | Trivial; byte-identical (`cell_gap=0`; `CellFill` preserves glyph = old `symbol:None`) |
| **Cave** | 8 | 1–9 digits BRIGHT_BLUE, 10–29 `"#"` RED → `CellStyle` table (keep `"#"`, no letter switch — table expresses it directly); drop the no-op `cave` entry; `wall` → `FillRule(BRIGHT_BLACK)` | Trivial; byte-identical |
| **Nurikabe** | 8 | clues 1–99 → `CellStyle(glyph_for_value(i), BRIGHT_BLUE)`; `stream` → `FillRule(BRIGHT_BLACK)` | Delta: clues ≥10 become letters (today `str(i)` emits 2 chars and breaks columns — reviewed fix) |
| **Skyscrapers** | 8 | letter-map duplicate → `glyph_for_value`; `height` → `GlyphRule(value_field="value")`; **+ `LineLabels` ×4** (`s/n/e/w` per the existing `clue_mapping`), `SceneStyle(frame=True)` per §7.5 | Flagged: edge clues newly rendered; frame added — reviewed delta in both modes |
| **Sudoku** | 8 | `draw_box/rows_per_box/cols_per_box` → `SceneStyle(frame=True)` + `RegionBorderRule(by=block-index lambda over self.block_rows/block_cols)`; letter-map → `glyph_for_value`; `number` → `GlyphRule(value_field="value", GREEN)` | Flagged: boxes now from lane-collapse + junction resolution — target byte-identical to old `├┼┤` output (pre-verified by Step 5's Sudoku-shaped geometry golden); review any junction diffs char-by-char. Boxes render in preview via `by=` (they already do today) |
| **Starbattle_shapeless** | 8 | `"#"` clue → table; `star` → `GlyphRule(glyph=Glyph("★"), color=BRIGHT_RED)` | Trivial; byte-identical (default gap) |
| **Numberlink** | 9 | first-appearance palette loop kept in Python (spec is still code); `cell_directions: {loop_directions:True}` → `PathRule("cell_directions", color=CYAN)` — the `dir1+dir2 → line_characters` lookup leaves `Solver._preprocess_predicates` for the geometry's `frozenset` table | Flagged: `loop_directions` machinery replaced; byte-identical goldens both configs |
| **Slitherlink** | 9 | clue table; `inside: {symbol:None, background:BRIGHT_GREEN}` → `FillRule("inside", BRIGHT_GREEN)` + **new** `RegionBoundaryRule("inside", color=BRIGHT_YELLOW)` | Flagged: loop drawn along edges for the first time; expanded layout ≈ doubles footprint — the design's chosen default (§7.6). Keep the `backends=SVG_ONLY` compact variant as a documented one-keyword option, not the default |
| **Fillomino** | 9 | clue table (unify ≥10 to `glyph_for_value` letters, replacing `"#"` — reviewed); `custom_renderer` lambda → `GlyphRule("number", value_field="size", color=BRIGHT_WHITE, fill=<Colorer cycling REGION_BG>)` | Flagged: closure → typed `Colorer`; solution sizes ≥10 letters (was multi-char `str`) |
| **Starbattle** | 9 | `_preprocess_config` region stash → `RegionFillRule(FromClues(), palette=…)`; `star` → `GlyphRule("★", BRIGHT_YELLOW)` | Flagged: deletes `_preprocess_config`/`_region_colors`; region colors re-rolled under the deterministic contract — reviewed recolor in preview + solved |
| **Galaxies** | 10 | `Color.RESET` centers → `CellStyle(color=None)`; `region_renderer` closure + `_preprocess_for_rendering` stash → `RegionFillRule(FromPredicate("galaxy"), palette=(YELLOW, BRIGHT_BLUE, GREEN, RED))` | Flagged: whole side channel deleted; coloring now inside `build_scene`, deterministic — reviewed recolor |
| **Stitches** | 10 | `_preprocess_config` stash → `RegionFillRule(FromClues())`; `stitch_renderer` + `color_index=[0]` → `LinkRule("stitch", glyph=Glyph("X"), palette=(BRIGHT_MAGENTA, BRIGHT_CYAN, BRIGHT_YELLOW, BRIGHT_GREEN))`; **+ `LineLabels` ×2** | Flagged: stitch colors become sorted-atom-deterministic (may reorder vs today); counts newly rendered; preview now shows four-colored regions + labels |

## Step 11 — Deletion, docs, final sweep (behavior change: none observable)

**Delete:**
- `aspuzzle/grids/rendering.py` entirely (`Color`, `BgColor`, `colorize`, `RenderItem`, `RenderSymbol` — no shim, no re-export).
- `aspuzzle/grids/region_coloring.py` entirely (`RegionColoring`, `assign_region_colors`, `assign_region_colors_from_predicates`, `DEFAULT_PALETTE` — superseded by `rendering/regioncolor.py`).
- From `aspuzzle/grids/base.py`: abstract `render_ascii`, abstract `line_characters`, the `RenderItem` import.
- From `aspuzzle/grids/rectangulargrid.py`: `render_ascii`, `_build_render_grid`, `_render_grid_simple`, `_render_grid_with_boxes`, `_build_horizontal_line`, `_get_column_separator`, `line_characters`, and the `RenderItem`/`RenderSymbol`/`colorize` imports (~185 lines).
- From `aspuzzle/solvers/base.py`: `get_render_config`, `_preprocess_puzzle_symbols`, `_preprocess_predicates`, `_preprocess_for_rendering`, the dispatch bridge (new path becomes the only body of `render_puzzle`), and the `RenderItem`/`RenderSymbol` imports. **`_preprocess_config` survives** (non-render hook; now unused by any in-tree solver but part of the lifecycle).

**Modify docs:** `aspuzzle/grids/CLAUDE.md` (rendering.py/region_coloring.py sections → new architecture), `aspuzzle/solvers/CLAUDE.md` (`get_render_config` → `get_render_spec`), root `CLAUDE.md` (Rendering System line, extension points).

**Verify:** `grep -rn "RenderItem\|RenderSymbol\|BgColor\|get_render_config\|line_characters\|render_ascii\|loop_directions\|draw_box" aspuzzle/ tests/ solveit.py` returns only historical goldens; full suite + mypy + ruff; sweep every config:

```bash
for p in puzzles/*.json; do python solveit.py "$p" --no-render --no-output-file; done
```

eyeballing each preview + solution pair one last time.

---

## Test strategy summary (each layer's tests land with or before the layer)

| Test file | Pins | Lands |
|---|---|---|
| `tests/test_golden_renders.py` + `tests/goldens/ascii/**` | End-to-end preview + solved ASCII per puzzle config, exact bytes incl. ANSI | Step 1 (old pipeline), regenerated per solver in Steps 7–10 |
| `tests/rendering/test_scene.py`, `test_color_glyph.py` | Scene as pure data: layer sort, insertion order, **backend filtering**, `layout_needs` filtering, provenance, `glyph_for_value`, `Rgb` | Step 2 |
| `tests/rendering/test_grid_topology.py` | `edge`/`vertex` canonicalization conformance suite; `neighbor()` vs grounded `Orthogonal` diff | Step 3 |
| `tests/rendering/test_canvas.py`, `test_ascii_renderer.py`, `test_import_boundaries.py` | Canvas transparency rules; synthetic-scene goldens; injected-theme SGR placement; no-ANSI/no-ascii-import guardrails | Step 4 |
| `tests/rendering/test_rect_geometry_expanded.py` | Lanes, collapse, junction table, margins, **SVG_ONLY-edges ⇒ compact byte-identity**, every-element conformance scene | Step 5 |
| `tests/rendering/test_spec.py`, `test_regioncolor.py` | Every rule → elements from hand-built atoms; preview (solution=None) completeness; **rule-level `backends=` stamping**; field-validation errors; deterministic coloring | Step 6 |
| `tests/rendering/test_solver_specs.py` | Per-solver spec-as-data + preview scene + hand-written-solution scene, no clingo | Step 7, grows through Steps 8–10 |
| SVG fragment goldens | `<line`, `data-provenance="given"`, per-conformance-scene golden files | With the SVG backend (follow-on) |

## End state: entry points for the follow-on work

- **Hexagonal/triangular grids:** new `aspuzzle/grids/hexgrid.py` / `trigrid.py` — subclass `Grid`, implement the existing ASP abstract surface plus the Step 3 topology methods (`neighbor`, `corner_names`, per-cell `edge_directions` for triangular), and `ascii_geometry()` returning a new `HexAsciiGeometry` / `TriAsciiGeometry` (per design §5.4–5.5, in sibling `*_ascii_geometry.py` modules). Register the factory in `ALL_GRID_FACTORIES` and the geometry in the conformance scene — the shared suites do the rest. **Zero renderer changes, zero solver changes**; proof: run Slitherlink or Minesweeper on a hex instance.
- **SVG backend:** `aspuzzle/rendering/svg/renderer.py` (`SvgRenderer`, `SvgTheme`) against the protocol frozen in Step 4; `svg_geometry()` overrides per grid (~30 lines each); one `--svg out.svg` flag in `solveit.py` calling `SvgRenderer().render(solver.build_scene(sol))` — previews included for free; `tests/goldens/svg/**` joins the golden harness. **Zero solver edits**, enforced by the Step 4 import-boundary tests.
- **Sheet backend (design §6.1, for mystery-hunt spreadsheet paste):** `aspuzzle/rendering/sheet/{geometry,renderer}.py` (`SheetGeometry` protocol, `SheetRenderer` — TSV, one grid cell per sheet cell, `OutsideLabel`s in margin cells, fills/edges/colors documented no-ops); `sheet_geometry()` per grid (rectangular: identity + margins); `--tsv` flag in `solveit.py`; `tests/goldens/tsv/**`. Smallest of the three follow-ons — it needs only the Step 2 scene and a trivial geometry, so it can land **any time after Step 2** (early landing is a nice end-to-end proof of the multi-backend seam before SVG exists). `Backend.SHEET` is in the enum from Step 2 either way, and the Step 2 filtering tests cover a `SHEET_ONLY` element alongside the ASCII/SVG cases.

## Risks worth watching during execution

1. **Sudoku junction fidelity (Step 8)** — de-risked by the Step 5 Sudoku-shaped geometry golden; if a junction char legitimately differs, review it there, not in the solver PR.
2. **Region recoloring churn (Steps 9–10)** — the deterministic contract re-rolls Galaxies/Stitches/Starbattle colors once, at port time; accepted as one reviewed delta each, never again after.
3. **Step 1 golden fragility for those same three solvers** — tolerable: any pre-port flake is quarantined to three files and disappears at their port.
4. **The bridge lingering** — Step 11's grep list is the exit criterion; the bridge and every old name must be gone in the same PR.
