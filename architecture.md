# Fawn Architecture

## 1. System Shape

Fawn is split into five modules with hard interfaces. In v0 these interfaces are scaffolded and exercised with worked examples, then hardened into runtime code.

1. `agent` (ingestion)
- Input: upstream source diffs.
- Output: normalized quirk candidates.

2. `config/data` (source of truth)
- Input: candidate records.
- Output: versioned quirk records plus metadata hashes.

3. `lean` (verification)
- Input: quirk records and invariant contracts.
- Output: formal model/obligation semantics in v0, plus proof results/validator artifacts when proof execution wiring is enabled.

4. `zig` (execution)
- Input: validated quirk set and validator artifacts.
- Output: specialized runtime outputs and manifests.

5. `bench+trace` (quality and observability)
- Input: runtime outputs.
- Output: correctness verdicts, perf verdicts, replay artifacts.

## 2. Incumbent Baselines

Fawn is benchmarked against external incumbents:

1. Dawn (C++)
2. wgpu (Rust)

These are baseline systems for measurement, not runtime dependencies.

## 3. Verification Boundary (Proof ROI First)

Every quirk maps to:
- one quirk class (`alignment`, `barrier`, `layout`, `driver_toggle`, `memory`)
- one verification mode (`guard_only`, `lean_preferred`, `lean_required`)
- optionally one Lean theorem pack (`WebGPU.Quirks.<Class>`)
- one Zig specialization module target

This keeps proof work proportional to risk and aligned with dev-speed priority.

Lean obligation decision rule:
1. Primary selector: `verificationMode`.
2. Optional stricter selector: `safetyClass` mapping from `fawn/config/gates.json`.
3. Effective requirement: strictest required `proofLevel` from active selectors.

v0 defaults:
1. `guard_only`: no Lean requirement.
2. `lean_preferred`: advisory Lean signal.
3. `lean_required`: blocking requirement (`proofLevel=proven`).
4. `safetyClass` override map is empty by default.

## 4. Runtime Selection Policy

Fawn uses startup profile selection, then avoids hot-path policy branching:
- detect adapter profile once at startup
- bind selected profile table
- execute specialized code paths

## 5. Data Contracts

Quirk record contract is schema-first in `fawn/config/quirks.schema.json`.
Key fields:
- `quirkId`, `scope`, `match`, `action`, `safetyClass`, `verificationMode`, `proofLevel`, `provenance`

`action` (schemaVersion `2`, strict discriminated contract):
- `use_temporary_buffer` with `params.bufferAlignmentBytes`
- `toggle` with `params.toggle`
- `no_op` with no params payload

`verificationMode` (policy):
- `guard_only`
- `lean_preferred`
- `lean_required`

`proofLevel` (status):
- `proven`
- `guarded`
- `rejected`

## 6. Zig Boundary Strategy

Fawn's Zig layer supports two integration modes:

1. Standalone path
- Zig owns runtime selection and specialization end-to-end.

2. Adapter path
- Zig emits artifacts or ABI helpers consumed by C++/Rust runtimes.
- Used for side-by-side validation against incumbent baselines.

When logic belongs in Zig:
1. It is in the latency-critical path (`submit/encode/validation` hot loops).
2. It benefits from compile-time specialization using known quirk/profile data.
3. It requires explicit allocator control or bounded-memory behavior.

When logic should stay out of Zig:
1. Policy-only gate rules (keep in config + Python/Lean boundary tooling).
2. Proof obligations and theorem statements (keep in Lean lane).
3. Non-hot-path orchestration where specialization will not change measured latency.

### Zig-first, then prove-away

1. For runtime behavior that replaces incumbent C++/Rust paths, land a deterministic Zig implementation first.
2. Use benchmark + trace artifacts to identify removable conditions in the actual hot path.
3. Encode those conditions as Lean obligations; when proven, hoist them to bind/build artifacts and delete the corresponding Zig runtime branch.
4. If a condition is not yet provable, keep the Zig branch explicit (no placeholder runtime logic).

Current v0 integration note:
- Lean contract/model files define obligation semantics and parity targets.
- Runtime and gate enforcement of those semantics is currently executed in Zig/Python.
- End-to-end Lean proof execution plus automated branch elimination is a roadmap item, not a completed CI path.

## 7. WASM Notes

For WASM-compatible deployment:

1. preserve deterministic sequencing independent of wall-clock jitter
2. use bounded ring-buffer memory in linear memory
3. export crash/replay artifacts via explicit host bridge APIs
4. keep native and WASM on the same schema/hash contracts

## 8. Build Outputs

A releasable build emits:
- runtime artifact(s)
- `quirkSetHash`
- `validatorHash` (if present)
- benchmark report
- run metadata conforming to `fawn/config/run-metadata.schema.json`
- trace schema version

## 9. Worked Example

See:
- `fawn/examples/intel_gen12_temp_buffer.md`
- `fawn/examples/quirks/intel_gen12_temp_buffer.json`

for one full path from upstream quirk signal to normalized record and specialization output.

## 10. Incumbent Advantage Contract

Fawn only claims advantage over C++/Rust incumbents when all are true:
1. same workload + backend class + comparable device family
2. same metric IDs from `fawn/config/benchmarks.json`
3. reproducible run metadata for both sides
4. comparison status is not `scaffold`

If these are not met, claims are directional only, not substantiated.

## 11. Backend Runtime Decoupling Contract

Backend selection is now represented as a first-class runtime contract:

1. backend identities
- `dawn_oracle`
- `zig_metal`

2. policy contracts
- `config/backend-runtime-policy.json`
- `config/backend-capability-policy.json`
- `config/backend-timing-policy.json`
- `config/backend-cutover-policy.json`

3. telemetry surface
- trace metadata carries backend-lane and selection context:
  - `backendId`
  - `backendSelectionReason`
  - `fallbackUsed`
  - `selectionPolicyHash`
  - optional shader artifact references

4. strict-lane rule
- strict local Metal lanes and cutover lanes are no-fallback by contract
- fallback must be explicit, policy-encoded, and auditable via trace artifacts
