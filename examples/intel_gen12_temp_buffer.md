# Worked Example: Intel Gen12 Temporary Buffer Quirk

This example shows one concrete path:

1. upstream signal
2. normalized quirk record
3. Lean sketch (optional/advisory in this case)
4. runtime behavior today (Zig)
5. what branch elimination would require

## 1) Upstream Signal

Source pattern (representative):
- toggles/workaround logic in Dawn around compressed texture copy path
- condition resembles Intel Gen12 + Vulkan branch

## 2) Normalized Record

Record file:
- `fawn/examples/quirks/intel_gen12_temp_buffer.json`

Key decisions:
- `schemaVersion = 2` (strict action contract)
- `verificationMode = lean_preferred` (not release-blocking in v0)
- `proofLevel = guarded` (deterministic guard path active)

## 3) Lean Sketch (Optional/Advisory Path)

Invariant sketch:
- if workaround is enabled then copy alignment must remain >= 4 bytes
- enabling workaround must not relax bounds-check invariants

Pseudo-shape:

```lean
theorem temp_buffer_alignment_safe :
  workaround_enabled -> alignment_bytes >= 4
```

What this means in v0:
- this theorem shape documents the safety property we care about
- it does not, by itself, remove a Zig runtime branch today
- this quirk is `lean_preferred`, so proof is advisory for gates in v0

## 4) Runtime Behavior Today (Zig)

Current runtime behavior is explicit and deterministic:
- profile matching and best-quirk selection happen once at startup
- command-time dispatch applies the selected action explicitly
- for `use_temporary_buffer`, copy commands are rewritten with `uses_temporary_buffer = true` and `temporary_buffer_alignment = bufferAlignmentBytes` from the quirk record

## 5) What Branch Elimination Would Require

To claim true proof-driven elimination for this path, all must be wired:
1. Lean proof execution in build/CI
2. artifact emission that encodes the proven condition
3. deletion of the redundant Zig runtime check/path in the same contract update

Without those three, Lean here is a formal contract/model aid, not an automated branch-removal mechanism.

## 6) Gate Expectations in v0

- Schema gate: must pass (blocking)
- Correctness + replay gate: must pass (blocking)
- Verification gate: advisory for this quirk (`lean_preferred`)
- Performance gate: advisory report only
