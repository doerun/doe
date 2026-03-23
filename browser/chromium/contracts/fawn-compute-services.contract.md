# fawn_compute_services Contract (Draft)

## Status

`draft`

## Goal

Define a deterministic contract for selected Chromium-internal compute workloads running through Fawn/WebGPU.

## Ownership Boundary

Owns:

1. Execution of contract-listed compute kernels/services.
2. Kernel parameter validation and taxonomy errors.
3. Trace and timing artifact emission for compute services.

Does not own:

1. Non-contract workload orchestration.
2. Codec/decode pipeline ownership.
3. OS presentation paths.

## Input Contract (Candidate)

1. `serviceId`
   - typed compute service identifier
2. `kernelId`
   - kernel identifier/version
3. `inputs`
   - typed buffers/textures with format metadata
4. `dispatch`
   - workgroup dimensions
   - repeat/normalization controls
5. `policy`
   - safety class
   - verification mode

## Output Contract (Candidate)

1. `serviceResult`
   - success/failure status
2. `executionStats`
   - dispatch count
   - bytes moved
3. `timingStats`
   - setup/encode/submit/dispatch spans
4. `failureDetails`
   - explicit taxonomy code and context
5. `traceLink`
   - module and hash anchors

## Failure Taxonomy (Draft)

1. `service_id_unknown`
2. `kernel_id_unknown`
3. `input_contract_invalid`
4. `dispatch_contract_invalid`
5. `required_capability_missing`
6. `execution_failure`

## Determinism Rules

1. Identical service request + config -> stable decision envelope.
2. Validation failures are fail-fast and reason-coded.
3. No implicit kernel substitution on unsupported paths.

## Gates

Blocking:

1. Schema gate for request/result artifacts.
2. Correctness gate on canonical service vectors.
3. Trace gate for deterministic execution envelopes.

Advisory:

1. Performance gate by service workload.
2. Verification advisory except explicit policy overrides.

## KPI Candidates

1. Correctness pass rate by service class.
2. Unsupported/failure taxonomy distribution.
3. p50/p95 latency by serviceId.
4. Determinism pass rate under replay.

## Promotion Preconditions

1. Service registry is explicit and versioned.
2. Request/response schemas promoted to config.
3. CI coverage includes canonical service vectors.
