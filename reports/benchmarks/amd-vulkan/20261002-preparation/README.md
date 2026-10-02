# Vulkan shader and pipeline preparation investigation

Baseline source: `7b4a5edfc06f727ade50e17ac568038c3634f8f8`. The candidate is the source change accompanying this report. Both libraries were built with Zig 0.15.2, `zig build dropin -Doptimize=ReleaseFast`, on the same AMD RADV Vulkan host. Their SHA-256 values and the focused script hash are in [pipeline-repeat.json](pipeline-repeat.json). This is a bounded preparation investigation, not a release or speed claim.

## Implementation and physical result

Vulkan translation now extracts compact binding sets for each compute entry point from the analyzed WGSL IR. The versioned translation cache owns those sets with the SPIR-V payload. A pipeline without overrides uses the module's retained set; a specialized pipeline uses the set derived from its specialized IR. Non-allocation reflection failures still reach pipeline construction. Cache decoding validates lengths and enum values, and module release frees the metadata. The shared override owner now rejects undeclared pipeline constants, noncanonical numeric IDs, names used for `@id` declarations, and out-of-range integer values at pipeline creation.

[The focused physical script](../../../../bench/vulkan/preparation-physical.mjs) exercises two entry points from one module, repeated pipelines, two override values, failed entry-point construction, invalid override rejection, and device release. Each of twelve fresh processes produced `[8, 8, 14, 21, 28]`. The baseline accepted unknown and incorrectly named `@id` overrides; the candidate rejected them. For 200 repeated pipelines from one module, the warm-run median was **59.83 ms before and 40.10 ms after**. This isolates pipeline preparation; it does not measure complete application speed.

## Unchanged UMAP application

The pinned UMAP SGD workload was not edited. The harness now externalizes both provider modules so Vitest does not transform Doe's source while loading Dawn directly. Each provider completed ten fresh processes with exact within-provider replay and its declared output oracle. The [baseline raw receipt](umap-baseline-10.json.gz) and [candidate raw receipt](umap-candidate-10.json.gz) retain process results, hardware and provider identity, inputs, oracle decisions, and peak process-tree memory. Both cohorts used populated, separate shader-cache homes. The Dawn lane is the pinned comparator in each receipt. Output hashes differ between Doe and Dawn, so these receipts do not assert bitwise cross-provider identity.

| Complete process, median of ten | Baseline | Candidate |
| --- | ---: | ---: |
| Doe | 638.04 ms | 636.87 ms |
| Dawn control | 621.57 ms | 619.00 ms |
| Doe peak process-tree RSS | 283.78 MiB | 283.36 MiB |

The roughly 1 ms candidate difference does not establish a complete-application gain. Doe remains slower than the pinned Dawn control in both cohorts, although its process-tree peak is lower. One-process [empty-cache baseline](umap-baseline-cold.json.gz) and [candidate](umap-candidate-cold.json.gz) runs also passed; those individual timings are diagnostic, not a cold-cache performance conclusion.

The earlier harness transformed Doe source but loaded Dawn externally. Its [baseline](prior-transformed-baseline-10.json.gz) and [candidate](prior-transformed-candidate-10.json.gz) receipts remain intact. They showed Doe medians of 739.95 and 754.05 ms and peaks near 325 MiB. Those rows must not be used as provider-speed evidence after the loading asymmetry was identified.

## Phase attribution

The [diagnostic provider wrapper](../../../../bench/external-projects/umap-gpu/preparation-diagnostic-provider.mjs) ran the unchanged UMAP workload with public API interception. These timings are diagnostic because interception changes execution cost. `import` is a dynamic import inside Vitest; it is not pure native-library initialization. Request calls include promise resolution. `queue.submit` and `queue.onSubmittedWorkDone` record synchronous call cost, not GPU completion. Allocation/upload and shader/pipeline columns are public-call costs; they do not expose internal compiler allocation counts. Execution, readback, and process teardown are not fully separated by this wrapper.

| Cumulative public boundary for one workload process | Doe empty cache | Doe populated cache | Dawn |
| --- | ---: | ---: | ---: |
| Provider import | 9.26 ms | 8.16 ms | 6.30 ms |
| Provider create | 2.07 ms | 1.99 ms | 0.65 ms |
| Adapter request | 43.40 ms | 40.81 ms | 40.59 ms |
| Device request | 16.66 ms | 15.66 ms | 1.98 ms |
| Eight shader-module calls | 1.21 ms | 0.53 ms | 2.12 ms |
| Eight compute-pipeline calls | 4.31 ms | 4.32 ms | 12.78 ms |
| 2,004 queue submits | 52.42 ms | 45.42 ms | 20.89 ms |

The raw phase observations are [Doe empty cache](phase-doe-empty-cache.json), [Doe populated cache](phase-doe-populated-cache.json), and [Dawn](phase-dawn.json). The earlier transformed-source phase observations remain [here](phase-prior-doe-populated-cache.json), with its [empty-cache](phase-prior-doe-empty-cache.json) and [Dawn](phase-prior-dawn.json) peers. A separate ten-process [direct Node import diagnostic](package-import.json) measured 20.16 ms median for Doe and 8.47 ms for Dawn. The corrected Vitest import observations are closer. Device request and queue submission are now the larger public-call differences; their native subphases remain unattributed.

## Validation and remaining work

`zig build test test-full -Doptimize=ReleaseFast --summary all` passed: 4,706 tests, 22 skips across the combined suites. `npm run test:contracts` and `npm run test:smoke` passed for `doe-gpu`. Physical Vulkan output, cold/populated translation-cache use, changed overrides, unknown-key rejection, and the unchanged UMAP oracle passed. The broader `zig build test-wgsl` target still fails to compile in existing CSL, DXIL, and MSL exhaustive expression switches for the `address_of` and `deref` IR tags; this campaign did not modify those emitters. Full WGSL or WebGPU conformance is not established.

The next candidate needs native attribution for Vulkan device request, whose path creates a new instance and selects a physical device after adapter probing already did so. Any lifetime correction must support multiple devices from one adapter and preserve adapter/device identity. Queue submission remains a separate measured difference. Another unchanged-application comparison is required before a speed claim. Compiler allocation counts, native execution/readback breakdown, and teardown attribution remain open. Generated SPIR-V execution optimization follows a closed preparation campaign.

Component: `doe.runtime-zig.compiler.wgsl`, `doe.runtime-zig.native.vulkan`, `doe.bench`, `doe.reports`. Intent: preserved. Acceptance evidence: linked raw receipts, focused physical script, and executed test commands above. Boundary effects: versioned shader translation cache payload and shared pipeline override validation.
