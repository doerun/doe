# Full Doppler generation through native Vulkan

## Disposition

The [frozen application contract](../../../../bench/external-projects/doppler-generation/contract.json)
executes real Gemma through Doppler's supported compatibility API and matches an
independent CPU reference for complete generated tokens, decoded stream and
stopping. Both baseline providers and the experimental provider pass cancellation,
completion settlement and subsequent generation. This is a new native application
qualification; retired provider and Electron comparisons grant no credit.

The completed-small-buffer reuse candidate is **rejected**. Its
[decision](disposition.json) records failed first-token material-gain, initial
first-token tail and candidate control requirements. The candidate is absent from
production source and policy. The [patch](candidate.patch.gz), unfavorable samples,
controls and failures remain retained. No Doe superiority is established.

| Executed bytes | Identity | Checks that apply |
| --- | --- | --- |
| Baseline Doe, corresponding to restored source/policy | [Baseline archive and native file hashes](providers.json) | Full oracle/stopping qualification, cancellation/recovery, baseline cohorts and profile |
| Experimental broader reuse | [Candidate archive and native file hashes](candidate-providers.json) | Separate full qualification and cohorts, candidate profile, cache tests, UMAP and rendering correctness |
| Pinned Dawn | [Archive and native file hashes](providers.json) | Full oracle/stopping qualification, cancellation/recovery, both cohorts and baseline profile |

The baseline library remains intact in its recorded archive and installation.
Restoration returns source and policy to the baseline commit; it does not transfer
candidate-only tests to another binary or assert a new rebuilt-package result.

## Bound inputs and independent oracle

The [manifest](manifest.json) binds source commits, physical adapter, driver,
archives, native binaries, dependency lock, retained evidence and rejected patch.
The [provider manifests](providers.json) and
[candidate provider manifest](candidate-providers.json) identify the precise local
archives and loaded native files. Large archives remain in declared local custody;
they are not duplicated in Git or published. This report is not an isolated package
release qualification: installed Doppler explicitly uses its source checkout's
dependency directory. Dawn is a pinned published native binary with npm source
metadata and a digest, not an independently source-built incumbent control.

The [CPU reference](reference.json) reconstructs the exact stored quantized and
floating-point tensors using upstream GGUF dequantization, then executes
Transformers' Gemma implementation with eager attention and full-prefix CPU state.
It uses neither Doppler transformer kernels nor its sampler. Tokenization and chat
formatting are checked against the public pipeline. Its library identities and
minimum-choice margins remain in the reference. This proves selected complete
outputs and stopping, not bitwise logits or universal host interchangeability.

## Complete application observations

The [baseline summary](baseline-summary.json) and
[candidate summary](candidate-summary.json) retain independent process controls,
initial and resident first-token/completion latency, local loading and host peak
RSS. Raw receipts retain every streamed chunk, prefill/decode diagnostics, loader
and tokenizer phase accounting, cancellation and final cleanup. GPU observers are
disabled in these cohorts. OS file caching is uncontrolled; acquisition reads
verified local assets and does not establish origin download performance.

The baseline complete-generation control fails the frozen stability requirement;
the candidate first-token control also fails. Lower complete-generation samples
therefore provide no attributable improvement. Unchanged Dawn is retained in both
balanced cohorts. Candidate and baseline processes belong to separate cohorts,
without artificial process pairing. Host RSS excludes physical GPU residency and
does not establish process-tree or complete native allocation accounting.

The [diagnostic attribution](attribution.json) records API interval unions,
allocation sizes, preparation, submission and overlapping completion promises.
It identifies repeated small-buffer creation as an avoidable host lead. The
candidate reduces observed buffer-creation cost without satisfying the application
acceptance criteria. No wait is removed or moved into readback. These API spans
are not isolated GPU execution or compiler-allocation measurements; nested and
overlapping intervals must not be added across methods.

## Candidate ownership and regressions

The [candidate contract](../../../../bench/external-projects/doppler-generation/candidate.json)
changes admission and per-size retention in the existing completed-allocation
cache while preserving its byte budget. It requires completed ownership, coherent
device-local memory, generation renewal, zero initialization and caller ownership
when metadata allocation fails. This does not reopen the rejected byte-budget
increase or introduce another cache.

Retained [cache boundary tests](checks/candidate-unit-boundaries.log.gz) exercise
reuse, generation, zeroing, failing allocation and count/byte bounds. The original
[architecture gate failure](checks/candidate-unit.log.gz) remains alongside the
final checks. Scoped module-decision hashes were renewed after inspection, without
changing architecture policy; all experimental production and ownership metadata
edits are restored. These checks grant no complete source-review coverage.

[UMAP regression receipts](checks/umap-receipt-summary.json.gz) and
[rendering ownership checks](checks/render.log.gz) pass correctness on the candidate.
These are regression checks, not new performance campaigns or tail qualification.
Harness failures remain under `failures/`: incorrect public load argument shape,
stop-enum mapping, and an attempt to settle capability-probe devices already
destroyed by Doppler. Final qualification tracks live devices explicitly. Earlier
qualification receipts predate the host peak-memory field; timed receipts require
it and preserve their own runner hashes.

## Reproduction and review

Use the [harness runbook](../../../../bench/external-projects/doppler-generation/README.md)
and the artifact paths in [manifest.json](manifest.json). Verify retained evidence
without installing model packages:

```bash
python3 bench/external-projects/doppler-generation/validate.py \
  --report reports/benchmarks/amd-vulkan/20261004-doppler-generation \
  --schema config/doppler-generation.schema.json
```

Add `--local-archives` on the recorded host to authenticate local archive custody.
The manifest hashes the raw receipts and original producer output, including
compressed evidence. Summaries can be recomputed from decompressed cohorts using
the unchanged workload and analysis settings. Never rerun to discard a failed
control or replace an unfavorable cohort.

The bounded native-generation batch closes with this rejection. Vulkan remains
the permitted backend; browser discovery stays closed, Metal follows and D3D12
is deferred. Rewriting quality and typed-judgment product work remain separate
Doppler decisions.

Component: `doe.bench`, `doe.runtime.zig`, `doe.reports`, `doe.docs`.

Intent: preserved.

Acceptance evidence: [manifest](manifest.json), [decision](disposition.json),
compressed qualification, cohort and regression receipts.

Boundary effects: repo-only application qualification and rejected experimental
cache admission; no retained production runtime, model, sampling or public API
change.
