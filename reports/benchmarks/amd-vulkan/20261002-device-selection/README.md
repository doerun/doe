# Vulkan adapter selection preparation

This checkpoint follows the [entry-point reflection and UMAP comparison](../20261002-preparation/README.md). It retains a bounded physical Vulkan preparation correction and diagnostic application comparisons. The [evidence index](selection-evidence.json) binds the changed source, exact native libraries, workload, and raw cohorts by SHA-256.

## First measured boundary

[Temporary native phase instrumentation](device-phases.json) located repeated Vulkan instance creation and physical-device selection in device request after adapter probing had already performed both. The instrumentation was removed from the runtime after profiling. The [public phase observation](phase-intermediate.json) comes from an intermediate reuse candidate, before the compact selection owner. These phase timings identify the mechanism; neither file is an uninstrumented application measurement.

The native adapter now owns a compact selection with its Vulkan instance, physical device, queue family and capabilities. Device creation borrows that instance and creates its own VkDevice and queue. Native device references retain the adapter, so external adapter release cannot destroy the selection while devices still use it. The selection is destroyed with the final adapter reference. The final implementation stores no unused runtime caches in the adapter.

## Physical and application checks

The [native lifetime check](native-lifetime.json) creates devices from one adapter, releases the public instance and adapter references, then verifies adapter identity and another device request after a peer device is released. The [physical shader check](physical-shader.json) verifies entry points, overrides, pipeline reuse, and output. The public shader-semantics suite also passed compute and rendering readback with this library. Combined ReleaseFast Zig suites and package contract/smoke checks passed.

The unchanged UMAP workload and pinned Dawn control passed output oracles and within-provider replay in the [paired old cohort](paired-old-summary.json) and the [exact final-source cohort](final-summary.json). Their full raw receipts are [old](paired-old-raw.json.gz) and [final](final-raw.json.gz). That standalone comparison did not establish a complete-process gain after accounting for the Dawn control.

An alternating old/new/new/old sequence then exercised the same governed workload. Its [cohort summaries](selection-evidence.json) and raw receipts ([old first](interleave-1-old-raw.json.gz), [new first](interleave-2-new-raw.json.gz), [new second](interleave-3-new-raw.json.gz), [old second](interleave-4-old-raw.json.gz)) show a lower Doe-versus-Dawn process median gap in both new cohorts than in either old cohort. The per-cohort summaries are [old first](interleave-1-old-summary.json), [new first](interleave-2-new-summary.json), [new second](interleave-3-new-summary.json), and [old second](interleave-4-old-summary.json). This supports a local median preparation gain with the exact final library; it does not settle tail behavior or a general speed claim. One selected-operation row crossed the harness material threshold, but that result did not repeat and complete-process advantage remains below the declared material criterion. Peak process-tree RSS is lower than Dawn in these cohorts; it is not a GPU-memory measurement.

The public JavaScript adapter currently permits only one device request from a given adapter. The shared-selection lifetime test uses the native ABI to exercise multiple devices; public multiple-device behavior is a separate WebGPU contract question. These observations are from one AMD RADV machine, with populated cache and no physical device-loss injection. They do not establish cross-device behavior, full compiler conformance, or a general speed claim.

## Reproduction and next boundary

Build the native library with `zig build dropin -Doptimize=ReleaseFast`, select Vulkan through `DOE_BACKEND=vulkan`, and pass its absolute path as `DOE_WEBGPU_LIB` to the existing package scripts. The source-bound commands are `python3 bench/vulkan/selection-lifetime.py <library>`, `node bench/vulkan/preparation-physical.mjs --require-override-rejection`, `zig build test test-full -Doptimize=ReleaseFast --summary all`, `npm run test:contracts`, `npm run test:smoke`, and `node bench/external-projects/umap-gpu/run-sgd-benchmark.mjs --clean-process-runs 10 --require-all-pass --run-id <id>`.

Queue submission remains the larger measured public-call difference after device request. Native attribution should identify its owner before any change. A later generated-SPIR-V execution candidate needs a current shader/ISA profile and separate compiler versus generated-program measurements. Compiler allocation counts and complete execution/readback/teardown phase attribution remain open.

Component: `doe.runtime-zig.native.vulkan`, `doe.bench`, `doe.reports`. Intent: preserved. Acceptance evidence: linked artifacts and executed commands above. Boundary effects: native adapter lifetime and borrowed Vulkan instance ownership.
