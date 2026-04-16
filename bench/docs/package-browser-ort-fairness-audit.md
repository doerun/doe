# Package and browser ORT fairness audit

Audience: Doe benchmark operators evaluating Node, Bun, and browser ORT WebGPU comparisons.

## Scope

This audit covers the repo-only ORT WebGPU compare lanes under `bench/native-compare/` and their executor ids in `bench/native_compare_modules/executor_registry.py`:

- Node package lanes comparing `tjs_ort_node_doe` with `tjs_ort_node_webgpu_package`;
- Bun package lanes comparing `tjs_ort_bun_doe` with `tjs_ort_bun_webgpu_package`;
- browser lanes comparing `browser_ort_webgpu_doe` with `browser_ort_webgpu_dawn`.

These are not public `packages/doe-gpu/` contract claims unless a promoted artifact and claim report says so.

## Findings

The current package and browser ORT lanes are narrower than native Apple Metal Dawn-vs-Doe lanes. They compare provider stacks through the host runtime harness and use process-wall timing where the harness contract requires whole-process or host-mediated measurements. The existing artifacts and configs should be treated as local, host-specific evidence unless a claim report passes strict comparability, report-level comparability coherence, structural equivalence, and the claimability gate.

No package or browser ORT lane is allowed to inherit the Apple Metal pipeline archive advantage implicitly. Native Apple Metal default executors now disable the archive by default; package/browser lanes that reach native Metal through Doe must still rely on emitted runtime telemetry and the compare report to prove cache state before a claim can be accepted.

## Residual limits

This audit closes the Linux-side contract review. It does not substitute for new Mac hardware evidence, and it does not promote Node, Bun, or browser ORT results to release-grade claims by itself. Release evidence still needs fresh artifacts from the target host, the configured sample floor, positive tail checks, and the blocking gates that apply to the selected surface.
