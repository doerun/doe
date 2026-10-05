# Native ONNX proc-table integration

This bounded prototype runs ONNX Runtime's existing WebGPU operators through
Doe on Vulkan. It preserves the graph, operator implementations and Python
application interface, disables graph optimization and CPU fallback, and checks
outputs against NumPy. It does not use the separate custom Doe operator plugin.
No performance superiority, browser switching, universal Dawn compatibility or
upstream adoption is claimed.

## Execution and ownership

[Doe execution](doe.json) retains changed inputs, exact outputs, operator
placement, actual bridge calls, native identities, the physical context, and
cleanup observations. [The supported published Dawn control](dawn-control.json)
uses the same workload and oracle without an external proc table. Raw operator
profiles are checksum-bound by [the manifest](manifest.json). Cancellation is
before execution, followed by successful session reuse; interrupting submitted
GPU work is not qualified. Native DRM clients are absent after context teardown;
that observation is not a complete allocation census.

[The generated ABI](bridge-build.json) comes from the consumer release's exact
Dawn revision. Shared structure layouts, member offsets, function signatures and
compatible values are admitted before bridge compilation. Differing extension
identities remain explicit and unsupported. The library/table are process-owned;
a second initialization is rejected, and existing GPU objects are never migrated.
Unsupported procs and descriptor chains terminate this internal prototype with
named errors. This is not a production exception-safe adapter.

## Consumer and native corrections

[The source build](source-build.json) identifies both pristine and patched
consumer libraries. The minimal consumer patch admits a paired external instance
and device at the existing default context: ONNX's shared allocators and transfers
use that context. Operators, shaders, precision and graph semantics are unchanged.
The published plugin is a separate incumbent control, not the patched source build.
The prior diagnostic's runtime/plugin pairing was unsupported by plugin metadata;
its observations remain retained, without being upgraded to package qualification.

The [native correction](native-correction.patch) fixes these demonstrated owners:

- Instance-owned pending pipeline obligations prevent `WaitAny` from retiring
  caller callback storage before delivery finishes. Callback reentry does not
  wait for its own return. Completed obligations retain no tombstones.
- Untracked device-loss timed waits return an explicit error; polling remains
  available. General future validation and callback-mode conformance remain open.
- SPIR-V assignment and declaration stores materialize admitted abstract values
  to destination types. Function-local defaults are initialized when each
  declaration executes, including declarations within repeated control flow.

[The original callback control](future-original.json) fails; [the corrected
control](future-corrected.json) passes using the same native library as inference.
[Failed observations](failed-observations.json), driver/callback stacks, rejected
shader bytes and earlier validation failures preserve the causal investigation.
The captured rejected SPIR-V matches the CLI artifact and fails `spirv-val`.
The corrected shader validates and its real ONNX output passes the oracle.

## Transfer and limits

[Zig validation](zig-validation.log) covers combined runtime and compiler suites.
[Public shader/render checks](shader-render-transfer.log) pass on the final native
library. The retained Doppler transfer uses unchanged installed Gemma generation,
its independent token/text/stopping oracle, cancellation/reuse and checkout/network
isolation. Its deferred-destruction warning remains unresolved; no leak-free
Doppler lifecycle claim follows. See [the disposition](disposition.json).

Binary and source custody is local and ignored, with its archive digest and
inventory in [the manifest](manifest.json). The [offline relocated ONNX consumer](offline-installation.json)
and [execution from the extracted final archive](archive-installation.json)
bind the exact archive contents; source-build reproduction is distinct from
installed execution. Distribution to another host remains unqualified.

Reproduction and evidence checks live in
[the existing harness](../../../../bench/external-projects/onnx-webgpu-substitution/README.md#explicit-proc-table-integration).
The earlier generation experiment and rejected performance candidates remain
closed. The Fawn start page is unchanged; Chromium's execution, transport and
presentation integration must be qualified separately.

Component: `doe.runtime`, `doe.runtime.zig.compiler`,
`doe.runtime.zig.dropin`, `doe.runtime.zig.native`, `doe.bench`.
Intent: preserved. Boundary effects: a pinned internal Dawn ABI adapter and a
minimal consumer context patch; no public package export or model mathematics.
