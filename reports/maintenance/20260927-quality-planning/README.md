# Zig quality planning and render ownership

The existing review tool now separates coverage inventory from work selection.
[`config/zig-review-plan.json`](../../../config/zig-review-plan.json) owns bounded
active and ready batches. `review_log.py --next` shows their rationale, outcomes,
acceptance, stopping conditions, environments, and current ledger findings.
It does not execute commands or grant review credit. Priorities can change without
changing source fingerprints; protocol/checker changes retain their existing
invalidation behavior. No historical review entry was rewritten.

The planning view surfaced a retained Vulkan finding that still matched source.
Inline index storage was released when recording returned, before submission.
Render state also unwound after unsuccessful waiting without resolving native
completion. The concrete correction makes render state own inline index storage
and sends failed submission/wait cleanup through the existing retirement owner.
The retirement helper receives typed retirement/device/error dependencies.
Known allocation rejection still permits submission retry. Unknown completion
keeps ownership; confirmed device loss remains failure, not successful rendering.

The repair closes this ownership increment. Remaining bundle error propagation,
query placement, surface synchronization and attachment admission findings stay
open. The current bounded plan selects bundle rejection/cleanup next, with compiler
cache/query ownership ready. File and parent review completion are separate.

## Evidence and reproduction

[Identity and outcomes](identity.json) pins predecessor, planning and runtime
commits, source hashes, test outcomes, and limitations.
[Raw evidence](raw-evidence.tar.gz) retains executed logs, the physical failure
interposer, probe source, build options, indexed-output regression source, and
separate implementation diffs. Library sizes and export identity are recorded in
[libraries.json](libraries.json). The native-library predecessor is the retained
binary from the preceding implementation-quality checkpoint, whose production
source is unchanged at this checkpoint's predecessor.

The indexed regression uses explicit shaders, a full-screen triangle, both index
formats, and independently expected RGBA pixels. The interposer rejects a queue
submission if its bound index buffer was already destroyed; this prevents invalid
commands reaching the driver during reproduction. The predecessor fails that
guard; the correction passes it and the ordinary physical output check.

The completion probe runs real Vulkan work before injecting failed fence or
timeline waits. Destruction hooks detect release while completion knowledge is
withheld. The same expanded source runs against the pinned predecessor and
candidate, including delayed completion, device loss, rejected submission/retry,
and repeated shutdown. It simulates completion knowledge and device-loss results;
it does not reset hardware. A first indexed-fixture attempt lacked replay setup
for readback; that development failure is retained separately and is not evidence
of the ownership defect.

From the repository root:

```bash
python3 -m unittest discover -s runtime/zig/tools -p test_review_log.py -v
python3 runtime/zig/tools/review_log.py --next
python3 runtime/zig/tools/review_log.py --check --base-ref d8a273512
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_doc_link_coverage
```

From `runtime/zig`, run `zig build test --summary all`. The focused physical test
uses `zig build test -Dtest-filter='Vulkan inline index' --summary all`; add the
extracted interposer through `LD_PRELOAD` to enforce the lifetime guard.
Build it with `cc -O2 -shared -fPIC -pthread fault.c -ldl -o libfault.so`.

For the completion probe, temporarily copy extracted `render-probe.zig` to
`runtime/zig/.audit_render_probe.zig`, refusing to overwrite an existing file.
Run the following from `runtime/zig`, substituting absolute extracted paths,
then remove that temporary source:

```bash
zig test -O ReleaseFast --dep build_options -Mroot=.audit_render_probe.zig \
  -Mbuild_options=/absolute/evidence/build-options.zig -lc -lvulkan \
  -L /absolute/evidence -lfault -rpath /absolute/evidence \
  -femit-bin=/absolute/evidence/render-probe --test-no-exec
LD_PRELOAD=/absolute/evidence/libfault.so /absolute/evidence/render-probe
```

The isolated drop-in library was built with `zig build dropin
-Doptimize=ReleaseFast --prefix /absolute/isolated-prefix`. The unchanged package
example and native recorded-compute/texture fixture pass against that library.
No accepted binary was overwritten. No application performance comparison,
Chromium qualification, surface/presentation failure injection, or physical
Metal/D3D12 run was attempted. Build logs and library size are observations;
this batch establishes no build-speed, application-speed, or release claim.

Component: Zig review tooling; Vulkan render ownership
Intent: preserved
Acceptance evidence: identity.json and raw-evidence.tar.gz
Boundary effects: explicit work selection and internal render allocation retirement; public ABI unchanged
