# TSIR manifest lowering entries

These fixtures bind the Phase A bootstrap kernels to schema-valid
`integrityExtensions.lowerings[]` rows — one row per `(kernel, backend)`
pair. Twelve files total, matching the cross-product of the three
bootstrap families and the four Phase A target descriptors:

- `fused_gemv.{webgpu-generic,wse3,msl,spir-v}.json`
- `rms_norm.{webgpu-generic,wse3,msl,spir-v}.json`
- `gather.{webgpu-generic,wse3,msl,spir-v}.json`

## Why they exist

Downstream consumers treat this directory as the canonical source of
TSIR lowering identity for the bootstrap catalog:

- **Manifest binder** (`bench/tools/tsir_manifest_lowering.py`) — loads
  entries from here to produce Doppler manifest `integrityExtensions.lowerings[]`
  arrays. The fixtures are what those bindings are built from, not
  one-off synthetic values.
- **Nightly parity canary** (`bench/gates/nightly_tsir_parity_canary.py`) —
  runs each fixture through the parity CLI, emits a receipt per fixture,
  and verifies each receipt's `loweringIdentity` block exactly matches
  the source fixture.
- **Parity CLI** (`bench/tools/doe_parity.py` with
  `--manifest-lowering-entry`) — copies a fixture's identity block into
  the receipt it produces, so receipts carry the same
  `(tsirSemanticDigest, tsirRealizationDigest, emitterDigest,
  targetDescriptorCorrectnessHash)` tuple the manifest binding declared.

## Invariants the fixture set must hold

Locked by `bench/tests/test_tsir_manifest_lowering.py`:

- Each entry validates against `config/doe-tsir-manifest-lowering.schema.json`.
- Each `(kernelRef, backend)` pair appears exactly once.
- For a given kernel, all backends share the same `tsirSemanticDigest`
  (semantic is target-independent).
- For a given kernel, `webgpu-generic`, `wse3`, `msl`, and `spir-v`
  each produce distinct `tsirRealizationDigest` values (realization is
  target-specific).
- All twelve entries share the same `frontendVersion` and
  `compilerVersion` (the set is a coherent snapshot, not a partial
  regeneration).
- All entries for a given backend share the same
  `targetDescriptorCorrectnessHash` (set agrees on descriptor identity).
- The four backends use four distinct descriptor hashes.

Locked by `bench/tests/test_nightly_tsir_parity_canary.py`:

- Every canary receipt produced from these fixtures carries a
  `loweringIdentity` block with digests byte-identical to the source
  fixture.

Breaking any of these invariants is a cross-artifact contract
violation; the tests are there to catch the break before it reaches
per-kernel-family parity promotion.

## How to regenerate

Any change to the bootstrap WGSL, the WGSL frontend, the TSIR schema,
the planner, the backend emitters, or the target descriptors will
invalidate these fixtures. Regenerate them with:

```sh
env PYTHONDONTWRITEBYTECODE=1 python3 bench/tools/generate_tsir_manifest_fixtures.py
```

The generator lowers the pinned WGSL bootstrap kernels through Doe IR,
TSIR semantic, and target realization planning, then calls the
schema-backed `bench/tools/tsir_manifest_lowering.py` builder to write
the manifest entries.

**Always regenerate all twelve fixtures together.** The uniformity
invariants above assume the set moves as a unit; partial regeneration
(e.g., running the generator against only one kernel after a descriptor
change) leaves the fixture set internally inconsistent in a way that
downstream consumers will silently accept and the test above will catch
only after commit.
