# ONNX Vulkan campaign contract

This repository-only campaign qualifies the pinned procedure-table integration
before measuring the unchanged upstream SqueezeNet application. Its frozen policy
is [onnx-vulkan-campaign.json](../config/onnx-vulkan-campaign.json); evidence fields
are versioned separately from policy. [The harness](../bench/external-projects/onnx-vulkan-campaign/README.md)
owns preparation, qualification, independent-process controls and replay.

## Bridge migration

The existing initializer remains explicit and process-owned. Initialization
failure closes the partial library, clears unpublished state, and allows retry;
a live table still rejects rebinding. `doeDawnBridgeTakeError` consumes a nullable
thread-local diagnostic string with static lifetime. Initialization must be
serialized before consumer use. It does not transfer existing GPU objects.

Unsupported descriptor chains return null for nullable object-returning calls,
`WGPUStatus_Error` for status calls, and `WaitAny_Error` for wait calls. Void,
boolean and future-returning calls still fail explicitly when rejection has no
qualified recoverable contract. No future is fabricated, submission silently
dropped, or callback conformance implied. The consumer must handle rejected
handles/statuses before using dependent objects.

`doeDawnBridgeInitializeControl` explicitly selects the pinned source-built Dawn
table behind the same bridge guards and counters. It is a benchmark control,
not fallback selection. Both libraries retain process lifetime.

## Evidence migration

Measurement evidence version 2 adds scoped cache homes and before/after persistent
cache inventories. Version 1 is retained as diagnostic after the cache-path audit;
its raw observations are not rewritten. The compact summary binds the compressed
version 2 cohort, whose complete schema is also enforced by the semantic verifier.
The additive campaign evidence schema admits named safety, application,
preparation, oracle, measurement, deployment, profile and custody records.
Historical proc-adapter records retain their original schemas, source hashes and
verdicts; replay them against their retained source snapshot. Current-source drift
must not be hidden by rewriting the historical manifest.

The semantic verifier checks raw observations against hashes, complete WebGPU
operator placement, native disabling controls, recovery/reuse, release ownership,
frozen-policy statistics and deployment controls. A completed negative performance
decision passes evidence verification without becoming a speed claim. Compiler
compatibility corrections precede measurement and do not consume the allowance
for a measured-owner performance correction.

## Matched conditions

Both arms share the application bytes, core/header ABI, source-built ONNX provider,
context selection, bridge, model, inputs, full validation request, CPU fallback
prohibition and numerical oracle. Source pins and retained build flags bind the
control. The common core is the pinned published binary; it is not described as a
source-built core. Device feature and callback conformance remain bounded by the
actual workload; the matching validation request does not establish universal
resource-safety equivalence.

Each backend performs its own preparation and synchronization. Complete
`Session.Run` timing includes the work required to return the mapped result;
output checking is outside that interval and runs after every invocation.
The CPU regression uses process-clock consumption during the same inference
interval, and RSS is the process high-water observation after inference; neither
is described as a complete initialization/teardown CPU profile.
Cold processes use independent fresh disk caches, including a scoped HOME for
Doe’s translation cache as well as the XDG and Mesa cache roots. Warm processes use separately
preconditioned backend caches and untimed session warmup. Neither discards legitimate
implementation differences nor substitutes native-only timing for application work.

Standalone replay exposes declared host libraries, drivers and device nodes,
but no checkouts or external networking. Native custody remains local. The
report does not establish registry release, another host's reproduction, adoption,
submitted-work interruption, browser backend replacement, Metal or D3D12.
