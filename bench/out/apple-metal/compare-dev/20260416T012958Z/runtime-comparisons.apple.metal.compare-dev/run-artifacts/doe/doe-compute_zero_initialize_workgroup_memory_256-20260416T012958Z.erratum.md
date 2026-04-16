# Erratum: Apple Metal pipeline-cache asymmetry

Run receipt: `doe-compute_zero_initialize_workgroup_memory_256-20260416T012958Z.run.json`
Workload: `compute_zero_initialize_workgroup_memory_256`
Issued: 2026-04-16

This run receipt belongs to the historical Apple Metal compare-dev run that was reclassified after the Doe-side Metal pipeline cache asymmetry audit. The Doe process may have opened the committed `bench/kernels/doe_pipeline_archive.metallib`, while the paired Dawn run did not have an equivalent prebuilt pipeline archive path.

Do not cite this receipt, or any comparison derived from it, as apples-to-apples Dawn-vs-Doe speed evidence. Treat it as diagnostic history only. The replacement evidence path is the fair-cold Apple Metal lane where both Doe and Dawn executor templates pass `--no-pipeline-cache` and the emitted `trace_meta.pipelineCache.state` is `disabled`.

Status reference: `docs/status/2026-04.md`, 2026-04-16 Apple Metal pipeline-cache asymmetry entries.
