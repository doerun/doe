# Linux completion checks

This checkpoint closes specific Linux/Vulkan checks from the implementation
milestone in `docs/status/reusable-compute-programs.md`. It does not declare the
whole milestone complete. `baseline.txt`, `source.patch`, and `SHA256SUMS` bind
the source revision, subsequent test changes, and retained records.

Retained-package correctness and identity are established by
`../20260907-texture-copy-regions/README.md` and
`../20260907-texture-copy-regions-qualified/summary.json`. That checkpoint checks
each archive/artifact hash, fresh controlled-host installations, and the public
C copy fixture against the extracted native binary. The subsequent installed
package used here was compared with every archive member before and after the
prolonged fixtures using `bench.lib.compute_program_package`.

## Earlier findings

`earlier-findings.sha256` binds implementation, regression sources, and the exact
retained-package streams inspected for these findings:

- `shader_binding_reflection.zig` publishes ready metadata only after success;
  extraction errors remain typed failures. Allocation-failure tests verify
  cleanup and a subsequent successful zero-binding module. Required source
  retention has a separate systematic allocation-failure test in
  `doe_shader_native.zig`. The package's reflection fixtures distinguish failure
  from valid empty reflection through the native addon.
- Compiler requests own `Diagnostic` values; shader objects own copied messages.
  Compatibility last-error adapters use thread-local snapshots. Canonical tests
  interleave parser, semantic, IR-builder, and successful compilations across
  threads and verify retained context; native adapters have concurrency tests.
- Descriptor version 3 state changes require an assessment bound to the program,
  revision, and exact edit. Package fixtures exercise changed interpretation at
  unchanged size, stale/declined/approved resets, and failed preparation rollback.
  Earlier descriptor versions retain their documented transition behavior.

The canonical Debug and ReleaseFast results covering these tests are retained in
the preceding texture-copy checkpoint. No new claim relies on historical prose
alone.

## Prolonged execution

Existing integration fixtures gained an explicit `--prolonged` mode; ordinary
qualification defaults remain unchanged. The live-frame wait now restarts its
deadline on accepted progress, while stalls retain the configured timeout.
`retained-tests/` contains the exact fixtures with imports redirected to the
installed, verified package. Run each with `node <fixture.mjs> --prolonged` under
an outer process timeout; the commands here used `timeout 900`.

`resource-prolonged.log` checks every returned integer, samples driver-reported
allocation totals, retains closed program objects, requires unchanged post-close
totals through repeated construction, and verifies device/client cleanup. It
covers ordinary, native-recorded, and GPU-recorded execution with and without
timestamp queries. Its elapsed values include assertions and observations and
are not provider performance comparisons.

`live-prolonged.log` checks the running heat simulation against the independent
reference on every frame after edit and reset tests, records sampled worker RSS,
and verifies cancellation, closing, and reopening. Sampled RSS and DRM allocations
are not physical peak residency, full process-tree memory, or forced driver-loss
evidence. Application-level concurrency remains outside these serial checks.

## Compiler and model checks

`emitter-build.log` rebuilds the SPIR-V compiler at this checkpoint. Reproduce the
fresh discovered-source check with:

```sh
python3 bench/gates/spirv_val_gate.py --require --discover-wgsl --require-subgroup-coverage --json-report <new-report.json>
```

`spirv-val.json` and `spirv-val.log` distinguish fresh discovered WGSL compilation
from pre-existing artifact validation. This covers the discovered corpus, not
all downstream shaders or numerical model acceptance.

The first model attempt in `gemma270m-initial.log` rejected a stale preparation
receipt before execution. `gemma-prepare-plan.json` retains the canonical plan;
`bench/out/external-projects/doppler/linux-completion-gemma/preparation.json`
records the refreshed pinned upstream checkout and preparation. The refreshed
pairwise run in `gemma270m/` aborted in Dawn's Electron native cleanup before a
transcript was produced. It is a failed control, not a Doe win. The retained
`run-model-lane.py` reproduces an individual lane with the same application
arguments and explicit provider/library selection, without promoting it to
pairwise qualification. Inspect its result before asserting model acceptance.
The isolated Doe Electron and Node runs produce complete decode transcripts and
nonzero KV data. The Node Dawn control also completes. `gemma-node-oracle.json`
and `gemma-cross-host-oracle.json` preserve numerical failures under the frozen
tolerance; their application-identity checks correctly reject Node as evidence
for the Electron harness. `model-first-differences.txt` locates the earliest
changed attention outputs before the larger downstream normalization and logits
differences. Nonzero model execution alone does not close numerical acceptance.
Pass a second argument `node` to the isolated reproduction script for that
diagnostic host; it does not modify the promoted harness or acceptance oracle.

The separate frozen external application audit is retained at
`../20260907-texture-copy-applications/summary.json`. Its resident Dawn numerical
failure stops comparison admission; failing-output timings cannot establish
equivalent-work superiority. No application speed claim is made here.
`../20260907-linux-application-matrix/summary.json` separately uses the earlier
frozen invocation-local policy with calibrated GPU timing and unrelated-activity
rejection. The activity gate rejected a measurement with observed foreign GPU
work. A fresh retry retains its own directory and cannot replace that failure.
`../20260907-linux-application-matrix-retry/summary.json` completed; the independent
matrix gate passed in `application-verification.log`. Rows remain diagnostic.
The Deno/wgpu ratios trigger the configured suspicious-speedup threshold and
retain their host/polling caveat; they are not accepted as runtime superiority.
The prepared-versus-Dawn rows have favorable observed latency and CPU ratios in
this run, without establishing ordinary-provider leadership or sustained user
benefit. Raw samples, complete-operation timing, preparation, GPU timing, work
receipts, and observed activity are retained in that matrix directory.

Physical Metal and D3D12 testing remain excluded. Model acceptance, further
demonstrated shader failures, fair application measurements, and the resource
limits named above remain open engineering work; adoption is a separate outcome.
