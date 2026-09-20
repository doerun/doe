# CATSCAN: Doe

Parent: none

## Target

Earn adoption through ordinary WebGPU, then safe reuse on another application,
using one portable compiler/runtime. DoeProof evaluates impartially; browser
distribution is optional.

## Authority

- Owns execution, evidence, and component-boundary law.
- Does not own application planning, browser policy, model selection, or external hardware governance.

## Scope

- Includes this tree; child charters narrow authority.

## Contracts

Inputs:
- Strategic goals: [`GOALS.md`](GOALS.md).
- System intent and invariants: [`INTENT.md`](INTENT.md).
- Product strategy: [`docs/thesis.md`](docs/thesis.md).
- Process law: [`docs/process.md`](docs/process.md).

Outputs:
- Package, runtime, compiler, and qualification artifacts.
- Component authority index: [`docs/component-index.md`](docs/component-index.md).

## Invariants

- Provider, backend, program, hardware, fallback, and result identities remain explicit.
- Unsupported or unproved behavior fails closed at its declared boundary.
- Package, native, browser, simulator, and hardware evidence cannot inherit claims.
- Runtime ownership requires governed comparison.
- Receipts do not prove adoption or become prerequisites for ordinary execution.
- Exact program/resource identity authorizes reuse; affected changes invalidate prepared state.
- Unknown completion retains ownership; timeout never authorizes unsafe reuse.
- Compiler meaning, runtime execution, and offline improvement have distinct owners.

## Acceptance

- Component charters and their generated index pass the blocking CATSCAN gate.
- Behavioral evidence must satisfy [INTENT.md](INTENT.md) and [GOALS.md](GOALS.md).
- Evidence: [`bench/gates/catscan_gate.py`](bench/gates/catscan_gate.py).

## Non-goals

- Universal WebGPU compatibility, universal Dawn replacement, or a general agent framework without separately promoted evidence.

## Freedom

Implementation freedom requires these boundaries and acceptance evidence.
