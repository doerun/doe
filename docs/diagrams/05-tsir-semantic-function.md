# 05 - TSIR: "Body shape where the kernel is semantic"

## Purpose

Show how Doe preserves kernel body shape for the Cerebras slice where TSIR has
coverage.

## Slide content

- One semantic-function box with four required slots:
  - `axes`
  - `bindings`
  - `reduction`
  - `body op`
- Example body op: `rms_norm`.
- Caption: **Backends may differ in memory movement; the semantic body stays
  inspectable.**

## Visual spec

- One large four-slot box in `doe.blue`.
- Use a small code inset with a real `rms_norm` fixture.
- Bindings use role labels: `input`, `weight`, `output`.
- If the body maps to Cerebras fabric, show a small `cerebras.orange` route
  marker next to the reduction slot.

## Scope guard

- TSIR is not Doe's only IR.
- TSIR does not cover every current CSL kernel yet.
- This slide is a compiler-contract claim, not a runtime parity claim.

## Evidence sources

- `runtime/zig/src/tsir/schema.zig`
- `runtime/zig/src/tsir/reference_interpreter.zig`
- `runtime/zig/tests/tsir/real/rmsnorm/`
