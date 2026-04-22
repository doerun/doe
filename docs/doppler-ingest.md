# Doppler ingest

This document defines the Doe-owned side of the Doppler portable-program
boundary. Doppler owns the portable program export shape. Doe owns what it
accepts from that export, how it captures supported WebGPU execution, and how
it lowers supported WGSL into backend receipts.

The Doppler-owned export contract lives in
[`../../doppler/docs/integration/program-bundle.md`](../../doppler/docs/integration/program-bundle.md).
The wrapper-level narrative lives in
[`../../ouroboros/docs/integration/doppler-doe-program-contract.md`](../../ouroboros/docs/integration/doppler-doe-program-contract.md).

Doe does not compile arbitrary Doppler JavaScript. Doe accepts a closed,
versioned Doppler Program Bundle that declares its model identity, execution
graph, deterministic WebGPU command-producing entrypoint, WGSL modules and
digests, runtime profile, artifact identities, and reference transcript. Doe
configs select an exported bundle and a backend target; they do not re-declare
the kernels or execution behavior that Doppler already owns.

## Artifact ownership

| Artifact | Owner | Meaning |
| --- | --- | --- |
| Doppler Program Bundle | Doppler | Manifest reference, execution graph reference, deterministic JS entrypoint, WGSL refs and digests, runtime/capture profile, artifact IDs, and reference transcript. |
| WebGPU capture graph | Doe | Observed GPU command graph from running the declared program under a supported provider/capture profile. |
| HostPlan | Doe | Lowered execution, memory, scheduling, stream, and launch contract derived from the declared/captured program surface. |
| CSL bundle and receipts | Doe | Backend output plus SDK compile, simfabric, parity, and hardware validation receipts. |
| Cross-repo CUJ narrative | Ouroboros | Milestone map and proof journey that links repo-local contracts without owning their fields. |

Ouroboros integration docs may link these artifacts into the critical user
journey, but the enforceable contract fields live with the owning repository.

## Version gates

Doe ingest must reject unsupported bundles early. A portable-program ingest
receipt should bind these fields before lowering:

- `programContractVersion`
- `dopplerExecutionGraphVersion`
- `webgpuSubset`
- `wgslSubset`
- `jsSubset`
- `hostPlanVersion`
- `unsupportedFeaturePolicy`

For the Cerebras lane, `unsupportedFeaturePolicy` must be `fail`. A bundle that
requires undeclared dynamic imports, undeclared WGSL modules, hidden provider
fallbacks, or runtime behavior outside the selected subset is not eligible for
CSL promotion.

## JavaScript boundary

The v1 JavaScript subset is deterministic WebGPU command production. Tokenizer
loading, prompt formatting, sampling policy, stopping rules, filesystem
loading, UI/browser concerns, and open-ended generation stay host-side unless a
future program-contract version explicitly admits them.

The first CSL proof target consumes declared token IDs and bounded decode
settings, then validates logits, selected token IDs, generated-token transcript,
and KV/cache evidence through receipts. Tree shaking or bundling may reduce the
program for execution, but it is an implementation detail, not the correctness
contract.

## Ingest modes

The declared Doppler execution graph is the source identity for v1 ingest. A
Doe WebGPU capture graph is evidence that a specific provider run produced the
expected command surface; it is not a replacement source of truth unless a
future contract version explicitly promotes capture-first ingest.

Doe.js remains optional from Doppler's perspective. Browser and Node Doppler
should remain WebGPU-first. Doe.js can act as an optional provider, capture, or
lowering surface for bundles that select Doe-compatible profiles.

## CSL promotion boundary

For a Doppler bundle to promote through Doe CSL, the receipts must show:

- the same manifest, graph, weight, shard, input, and prompt identities as the
  Doppler reference;
- a HostPlan and runtime config derived from the selected bundle, not a
  separate Doe-authored graph;
- SDK compile and simfabric execution from generated CSL/Python/SdkLayout
  artifacts;
- bounded transcript output with matching decode count, stop reason, token IDs,
  per-step logits tolerance, and generated-token sequence;
- observable KV/cache read/write and layer coverage evidence;
- no stub stages, synthetic inputs, synthetic weights, or hidden fallback path.

Hardware packaging starts only after the same bundle passes simfabric transcript
parity.
