# Fawn Zig Style Guide

This guide is the canonical style contract for Fawn Zig modules.  
All Zig implementation and generated artifacts in `fawn/` should follow it.

## Core principles

- Prefer explicit data contracts over scattered boolean logic.
- Prefer exhaustive type-based dispatch (`enum` + `switch`) over long `if`/`else` chains.
- Keep policy outside hot-path runtime; runtime should execute validated evidence as data.
- Keep behavior deterministic and auditable via explicit traces and rule IDs.
- Use bounded, explicit memory ownership and fail-fast validation at load time.

## Repository conventions

- Put public surface types and contracts in `model.zig`.
- Put policy/selection logic in `dispatch.zig`.
- Put data normalization/parsing in `ingest.zig`.
- Keep generated/derived artifacts in `generated/` and clearly mark provenance.
- Co-locate tests with module (`*_test.zig`) and keep them deterministic.
- Use `build.zig` for compile-time generation/preprocessing steps where appropriate.

## Formatting and linting

- Run `zig fmt` on every changed `.zig` file before review.
- Use one statement per logical line and keep lines readable before shortening.
- Keep imports explicit and ordered: std first, then local imports.
- Prefer module-local helper functions over wide utility files.

## Naming

- Types (struct/enum/union): `PascalCase`.
- Functions: `snake_case`.
- Error unions: `error{...}` set with clear names (`InvalidPayload`, `UnknownVendor`, `MissingEvidence`).
- Constants: `snake_case` unless exported public constants in API modules (prefer `pub const` with short clear names).

## Control flow

- Use `switch` over enum states:
  - no hidden defaults for closed sets
  - add `else`/`_` only for truly open sets
- Favor guard-style early returns with explicit `try` + `catch`.
- Avoid nested branching. If logic is a decision matrix:
  - define `enum` keys
  - index `comptime`/`std.AutoHashMap` dispatch tables
  - apply ordered rules.

## Error handling

- Return `!T` where recoverability is expected.
- Use explicit `error` unions for known failure modes.
- Propagate parse/validation failures with contextual errors and source path.
- Never swallow parse/execution errors without an emitted trace.
- Emit structured errors at boundaries (CLI/JSON in/out, file load, schema validation).

## Memory and allocation

- Use explicit allocator parameters in constructors and context-aware calls.
- Prefer arena allocators for request-scoped execution.
- Keep long-lived caches and lookup tables explicit owners.
- Close/free resources deterministically; use `defer` for scope cleanup.

## Determinism and traceability

- All outputs must be reproducible for identical inputs and config.
- Include `rule_id`, `candidate_id`, evidence IDs, and decision metadata in runtime output.
- Sort unordered collections before serialization where output order matters.
- Emit machine-consumable traces (`trace_id`, `matched_rule`, `scores`, `feature_vector`, optional snippets).

## JSON/data handling

- Parse external JSON via validated structs and strict decoding.
- Reject unknown top-level fields only if schema version mismatch requires it; otherwise record as passthrough metadata.
- Keep conversions to internal enums centralized (`parse_vendor`, `parse_backend`, etc.).

## Performance

- Avoid dynamic dispatch in hot paths when static dispatch or table lookup suffices.
- Keep hot loops allocation-free after startup.
- Precompute match indexes at compile/initialization time when config is static.
- Prefer contiguous arrays + indexes over nested maps when cardinality is small.

## Testing

- Unit test each contract conversion (`parse_*`, evidence normalization, rule selection).
- Unit test each decision branch in the dispatch matrix.
- Add property-style tests for idempotency of parser/normalization when possible.
- Include regression fixtures for:
  - duplicate change IDs
  - malformed JSON fields
  - unknown enums
  - tie-breakers in dispatch priority
  - empty evidence

## Fawn-specific implementation pattern (anti-if soup)

- Model the quirk problem as:
  - normalized candidate row → `QuirkKey`
  - candidate key lookup -> ordered rule list
  - rule application -> `QuirkAction`
  - evidence emission -> immutable decision record
- Keep the mapping logic as data (`candidate_pack`, generated maps) + `switch` on action variants.
- Treat unrecognized combinations as explicit `unhandled` states, not silent defaults.

## Mandatory checks before merge

- `zig fmt` clean
- `zig test` (at least targeted module tests)
- `fawn/lean` gate/validation path passes for any schema changes consumed by Zig

