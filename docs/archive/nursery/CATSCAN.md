# CATSCAN: Nursery archive

Parent: [Documentation](../../CATSCAN.md)

## Target

Retain navigation from historical nursery paths to their current owners without implying product maturity from the directory name.

## Authority

- Owns archive navigation and migration pointers for former nursery surfaces.
- Does not own executable CI surfaces, product strategy, or promoted APIs.

## Scope

- Includes files beneath this directory except child-chartered components, which narrow this authority.

## Contracts

Inputs:
- Nursery boundary: [`README.md`](README.md).
- Tool classification: [`../../../config/tool-surfaces.json`](../../../config/tool-surfaces.json).

Outputs:
- Pointers to current browser integration, CTS tooling, and workflow owners.

## Invariants

- Current executable surfaces remain with their named component owners.
- Incubation state cannot support a promoted product claim.
- Historical evidence retains the paths of its producer checkout.

## Acceptance

- Archive classification and current navigation remain valid.
- Evidence: [`../../../bench/gates/tool_surface_gate.py`](../../../bench/gates/tool_surface_gate.py).

## Non-goals

- A dumping ground for abandoned or unowned code.

## Freedom

Any mechanism is permitted if it preserves these boundaries and passes the acceptance evidence.
