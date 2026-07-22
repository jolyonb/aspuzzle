from aspalchemy import register_skip_package

# Framework plumbing: statements these modules emit attribute to THEIR callers
# (the puzzle author's lines), so diagnostics — dangling when() reports,
# annotated renders, grounding errors and profiles — name solver code, not
# framework internals. The solvers package is deliberately NOT registered
# wholesale: aspuzzle/solvers/*.py are authored puzzle definitions whose lines
# are exactly what diagnostics should point at.
for _plumbing in (
    "aspuzzle.puzzle",
    "aspuzzle.symbolset",
    "aspuzzle.regionconstructor",
    "aspuzzle.grids",
    "aspuzzle.solver",
):
    register_skip_package(_plumbing)
