# Metal pipeline cache policy

Audience: Doe benchmark operators and contributors.

## Decision

The committed Apple Metal binary archive is a benchmark fixture, not a product runtime contract.

Default Apple Metal Doe-vs-Dawn native compare lanes must run fair-cold. The default executor ids `doe_direct_metal` and `dawn_delegate_metal` pass `--no-pipeline-cache`, and the Apple Metal compare config command templates carry the same flag. Cache-enabled runs must opt in explicitly through `doe_direct_metal_cache`, `dawn_delegate_metal_cache`, or a config template that states the cache intent.

Cache-enabled lanes are cache-specific diagnostics unless the comparison side has an equivalent declared cache path. Do not use them as apples-to-apples Dawn-vs-Doe speed evidence.

## Current fixture placement

The archive files remain under `bench/kernels/` for now because the runtime cache lookup is coupled to the kernel root used by the benchmark executor. Moving the archive to a dedicated fixture directory needs a separate runtime/config contract for cache location. Until that contract exists, the benchmark policy is enforced by the default no-cache executor templates and by `trace_meta.pipelineCache.state` in run receipts.

`DOE_PIPELINE_CACHE_DIR` is not a public customer contract in this repo state. Treat it as an internal runtime override until the package docs and runtime config schema promote it.

## Required artifact evidence

A fair-cold Apple Metal claim run must show all of the following in the emitted artifacts:

- the executor template or command includes `--no-pipeline-cache` on both sides;
- Doe `trace_meta.pipelineCache.state` is `disabled`;
- Doe `trace_meta.pipelineCache.reason` is `cli-flag`;
- comparability does not auto-mark `pathAsymmetry` only because the workload appears in `bench/kernels/doe_pipeline_archive.manifest`;
- report-level comparability coherence passes before any claim gate accepts the report.

Cache opt-in diagnostics should instead state that the binary archive is active and must not be promoted to strict comparable claim evidence.
