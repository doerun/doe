# Zig consistency and build cleanup

This version-1 maintenance record binds the cleanup to predecessor `ded78ed29`.
It is source/build evidence; it does not measure runtime performance or replace
the frozen application calibration.

## Inventory

See [before-counts.tsv](before-counts.tsv) and [after-counts.tsv](after-counts.tsv)
for current counts. The corresponding `*-files.tsv` records classify and hash
every tracked Zig file. Physical lines include blank and comment-only lines;
code lines exclude blank lines and lines whose first non-whitespace bytes are
`//`. Inline comments remain part of code lines. This is a text inventory, not
a statement count or a count of compiled/reachable code.

Tracked `bench/out/` snapshots are separate from the active `runtime/zig/`
tree. Production generated sources come from the existing source-layout
manifest; generated test-suite roots are separate from handwritten tests.
Untracked vendor files, caches, and installed output are outside the inventory.
The predecessor reconstruction asserts that only `build.zig` changed among Zig
files. The TSV header defines each field; paths are repository relative.

Reproduce from the repository root with:

```bash
python3 bench/out/maintenance/20260914-zig-style/count_source.py before
python3 bench/out/maintenance/20260914-zig-style/count_source.py after
```

## Implemented boundary

The build graph shares comparability and drop-in ABI embedding helpers across
its variants, names their existing read limits, and consistently names its
private graphics-configuration helper. Generated declaration order, values,
hashes, read bounds, and missing-file failure order retain their meanings.

`zig build fmt-check` checks owned Zig files without writing. `zig build fmt`
formats the same tree. Vendored sources, the local Zig cache, and installed
outputs are excluded. Default installation and canonical test-suite steps
depend on the check; WGSL CI runs it explicitly before tests. Named standalone
artifact builds do not acquire a new formatting prerequisite.

The style guide distinguishes local values from domain constants, type factories
from ordinary functions, and local naming from foreign/serialized contracts.
It removes duplicated boundary prose and an example that discarded callback
status. Its review workflow separates mechanical enforcement from ownership,
cohesion, naming, and behavioral evidence.

## Acceptance evidence

- [Option comparison](before/options.tsv) and [current options](after/options.tsv)
  bind generated option bytes for the default, compute, and full variants with
  proof embedding enabled and disabled. The probe captures the build graph's
  actual `Options.contents`; both phases use the same temporary build-module
  filename. It does not compile or install a runtime.
- [Configuration failures](config-failures.tsv) compare missing-input order
  against the predecessor in isolated filesystem layouts. Original
  configuration files are never edited.
- [Formatting probes](formatting.tsv) exercise rejection without writes,
  formatting repair, and excluded directories. Temporary probe files are
  removed even on failure.
- [Structural gates](structural-gates.log) cover formatting, import boundaries,
  source layout, production line policy, generated ABI, and test inventory.
  Advisory size observations remain advisory under the existing manifest.
- [Build-parser tests](build-tests.log) exercise decoded strings, invalid
  policy, and allocation failure through the canonical aggregate suite.
- [WGSL tests](wgsl-tests.log) and [proof-enabled WGSL tests](wgsl-lean-tests.log)
  exercise the canonical compiler suite with both build-option selections.
- [Documentation checks](documentation-checks.log) cover local links and
  component routing. [Preserved inputs](preserved-inputs.tsv) bind accepted
  package and command-storage policy bytes.
- `SHA256SUMS` binds the retained evidence and scripts. `source-files.tsv`
  binds changed implementation and documentation inputs.

Reproduce the negative checks from the repository root:

```bash
python3 bench/out/maintenance/20260914-zig-style/verify_formatting.py
python3 bench/out/maintenance/20260914-zig-style/verify_config_failures.py
```

`capture_options.py before` must run against the predecessor build file;
`capture_options.py after` runs against the changed build file. Captured option
files have a `.txt` suffix so they do not inflate the Zig source inventory.

## Component handoff

Component: Zig runtime build/tooling and documentation
Intent: preserved
Acceptance evidence: commands and artifacts above
Boundary effects: build/test formatting enforcement and WGSL CI; no runtime,
compiler, package, serialized contract, or performance-policy change
