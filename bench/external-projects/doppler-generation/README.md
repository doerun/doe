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

## Standalone installed execution

The separate installation check reuses the unchanged generation runner and CPU
oracle. It relocates only model custody and the contract identity into a new
consumer directory. It preserves the original experiment and grants no
performance credit. See the [installation report](../../../reports/benchmarks/amd-vulkan/20261005-installed-generation/README.md).

Prepare on the artifact custodian's Linux x64 Vulkan host:

```bash
python3 bench/external-projects/doppler-generation/installed-generation.py prepare \
  --destination "$CONSUMER" \
  --contract bench/external-projects/doppler-generation/contract.json \
  --providers reports/benchmarks/amd-vulkan/20261004-doppler-generation/providers.json \
  --reference reports/benchmarks/amd-vulkan/20261004-doppler-generation/reference.json
```

`CONSUMER` is a new directory outside the checkouts. Preparation authenticates
the existing archives, installs their declared required dependencies through npm,
checks every shipped file, copies verified model files, and retains a lockfile,
dependency inventory and private npm cache. Optional automatic provider packages
and installation scripts are omitted: these retained provider archives already
contain the exact native library and addon. This is an explicit source-bound
snapshot installation, not qualification of registry platform packages.

Once prepared, the directory can be transferred intact. Run its copied tool:

```bash
python3 "$CONSUMER/harness/installed-generation.py" run --destination "$CONSUMER"
python3 "$CONSUMER/harness/installed-generation.py" verify --destination "$CONSUMER"
```

Execution requires Bubblewrap, Python, Node/npm under `/usr/bin`, and the physical
AMD Vulkan driver/device. The namespace exposes read-only `/usr`, `/lib`,
`/lib64` where present, `/etc`, and `/sys`, plus host `/dev` and private `/proc`.
It hides the workspace and host temporary directories, clears the environment,
and disables external networking. The consumer directory is writable. This is
dependency-isolation evidence, not a hardened sandbox for hostile programs.

Offline `npm ci` first reconstructs the dependency tree from its retained cache.
Fresh Doe runs exercise complete outputs, stopping, cancellation and reuse;
the pinned Dawn control uses the same workload. Native paths are confirmed from
the running process's shared objects. Missing-library, incompatible-package and
missing-model checks must fail at their named boundaries. Original oracle values
are unchanged and rechecked during evidence verification. Timings are incidental
observations, not a renewed optimization experiment.
