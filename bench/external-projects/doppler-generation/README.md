# Native full-generation application qualification

This repo-only harness drives the installed `doppler-gpu/compat` API with real
Gemma artifacts on native Vulkan. It owns application inputs, the independent
CPU reference, scoped API observations, controls and candidate admission. Model
math and sampling remain Doppler-owned. It grants no browser, rewriting-quality,
package-release or complete numerical-conformance credit.

The [contract](contract.json), [analysis settings](analysis.json) and
[candidate](candidate.json) are frozen inputs. Their fields and retained producer
outputs are described by
[the experiment schema](../../../config/doppler-generation.schema.json).
Current evidence and its exact local archive custody are retained in the
[application report](../../../reports/benchmarks/amd-vulkan/20261004-doppler-generation/README.md).
This candidate is rejected; its runtime patch must not be mistaken for accepted
production code.

## Prepare identical inputs

Use the source commits, dependency lock, model manifest, tokenizer and shard
digests declared in the contract and report. The recorded model conversion's
origin metadata pins the upstream model revision. Re-conversion alone does not
guarantee identical quantized bytes; authenticate the recorded artifacts.

The provider manifest declares installed module paths, provider archives, native
files and build metadata. Build the native library with the existing Zig drop-in
target, rebuild the existing NAPI addon, and archive the explicit provider files.
Authenticate every archive and loaded native file before qualification. Source
metadata on a published Dawn archive is distinct from building Dawn from source.
The recorded Doppler dependency symlink is explicit and prevents isolated-package
qualification claims.

Use the CPU library versions in the retained reference. `reference.py` loads the
exact recorded tensors, upstream GGUF dequantization and Transformers Gemma; it
does not import Doppler inference or sampling. From the repository root:

```bash
python3 bench/external-projects/doppler-generation/reference.py \
  --contract bench/external-projects/doppler-generation/contract.json \
  --out "$RUN/reference.json"
node bench/external-projects/doppler-generation/run-generation.mjs \
  bench/external-projects/doppler-generation/contract.json \
  "$RUN/providers.json" "$RUN/reference.json" dawn "$RUN/dawn-qualification.json"
node bench/external-projects/doppler-generation/run-generation.mjs \
  bench/external-projects/doppler-generation/contract.json \
  "$RUN/providers.json" "$RUN/reference.json" doe "$RUN/doe-qualification.json"
```

`RUN` names an existing scratch directory with the declared provider manifest.
The workload binds the model's absolute host custody path. Preserve that path or
freeze a new contract and reference for another host; changed inputs cannot reuse
these qualifications. The harness fails exact output or stopping mismatches and
requires cancellation settlement followed by a correct fresh generation.

## Profile, then confirm without observers

Invoke `run-generation.mjs` with the final positional mode `profile` to observe
API intervals. Qualification receipts for both providers must exist next to the
output and match its contract and provider manifest. API observations include
overlapping promises and downstream work; they are not pure GPU timestamps.

```bash
node bench/external-projects/doppler-generation/run-cohort.mjs \
  bench/external-projects/doppler-generation/contract.json \
  "$RUN/providers.json" "$RUN/reference.json" "$RUN" baseline
python3 bench/external-projects/doppler-generation/analyze.py \
  --root "$RUN" --contract bench/external-projects/doppler-generation/contract.json \
  --cohort baseline --out "$RUN/baseline-summary.json"
```

The cohort uses sequential physical-GPU processes, frozen balanced provider
ordering, fresh shader-cache directories, resident A/B labels, and no observers.
OS file cache remains uncontrolled. The analysis declares interpolated quantiles
and process-paired control uncertainty; do not substitute another percentile or
pool frames as independent processes. Acquisition, stream, prefill/decode,
completion and cleanup remain separately retained in raw receipts.

Prepare and qualify a candidate in a distinct scratch directory with its own
provider manifest and qualification receipts before calling `run-cohort.mjs`.
Apply unchanged limits with `compare.py --baseline ... --candidate ...
--contract ... --out ...`. Failed admission closes this candidate without
performance promotion. Regression success cannot rescue failed controls or
first-token criteria. `attribute.py` computes interval unions for profiles;
`validate.py` authenticates retained compressed evidence and schema definitions.

The existing public tooling manifest classifies these entrypoints as internal.
They do not publish packages, deploy a browser, or reopen retired comparisons.
