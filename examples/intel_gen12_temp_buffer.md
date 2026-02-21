# Worked Example: Intel Gen12 Temporary Buffer Quirk

This example shows one concrete path:

1. upstream signal
2. normalized quirk record
3. Lean sketch (optional in this case)
4. Zig specialization output shape

## 1) Upstream Signal

Source pattern (representative):
- toggles/workaround logic in Dawn around compressed texture copy path
- condition resembles Intel Gen12 + Vulkan branch

## 2) Normalized Record

Record file:
- `fawn/examples/quirks/intel_gen12_temp_buffer.json`

Key decisions:
- `verificationMode = lean_preferred` (not release-blocking in v0)
- `proofLevel = guarded` (deterministic guard path active)

## 3) Lean Sketch (Optional Path)

Invariant sketch:
- if workaround is enabled then copy alignment must remain >= 4 bytes
- enabling workaround must not relax bounds-check invariants

Pseudo-shape:

```lean
theorem temp_buffer_alignment_safe :
  workaround_enabled -> alignment_bytes >= 4
```

## 4) Zig Specialization Output (Conceptual)

Conceptual output branch:

```zig
if (profile.vendor == .intel and profile.family == .gen12 and profile.api == .vulkan) {
    cfg.use_temp_buffer = true;
    cfg.temp_buffer_alignment = 4;
}
```

## 5) Gate Expectations in v0

- Schema gate: must pass (blocking)
- Correctness + replay gate: must pass (blocking)
- Verification gate: advisory for this quirk (`lean_preferred`)
- Performance gate: advisory report only
