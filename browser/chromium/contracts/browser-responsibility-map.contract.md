# Browser responsibility map contract

## Input shape

The browser responsibility map lives in
[`config/browser-responsibility-map.json`](../../../config/browser-responsibility-map.json)
and is validated by
[`config/browser-responsibility-map.schema.json`](../../../config/browser-responsibility-map.schema.json).

Each entry declares:

- stable `entryId`
- CPU/GPU/boundary owner
- scope status from the task-list taxonomy
- rationale for the boundary decision
- claim binding when `scopeStatus=doe_claim_candidate`

Each boundary declares:

- stable `boundaryId`
- source and destination entry IDs
- crossing description
- scope status
- claim binding when the boundary is claimable

## Output artifacts

The map is a contract artifact. It does not change browser behavior by itself.
Browser and runtime evidence may cite it when deciding whether a surface is
Doe-owned, observable, schedulable, claimable, or blocked by browser policy.

## Failure taxonomy

- `missing_entry`: required browser responsibility entry is absent.
- `missing_boundary`: required CPU/GPU crossing is absent.
- `unbound_claim_candidate`: a claim candidate lacks contract, schema,
  workload, gate, or artifact paths.
- `unsafe_claim_binding_path`: a claim binding path is absolute or escapes
  repo-relative resolution.
- `invalid_scope_status`: an entry uses a status outside the task-list taxonomy.
- `stale_reference`: a claim binding points to an absent contract, schema, gate,
  workload, or artifact root.

## Fallback policy

Missing or invalid map entries cannot promote claim language. Browser work may
remain diagnostic, but no new browser responsibility surface may become
claimable until the map validates and the candidate has a claim binding.

## Gate coverage

- Schema validation: `python3 bench/gates/schema_gate.py`
- Contract presence: `config/schema-targets.json`
- Responsibility-map check:
  `python3 bench/tools/check_browser_responsibility_map.py --map config/browser-responsibility-map.json`
- Claim enforcement: downstream browser and benchmark gates must reject
  claimable surfaces whose responsibility map entry is absent or unbound.

## Promotion criteria

A browser surface can move from `doe_observable` to `doe_claim_candidate` only
when the map entry names:

- owning contract
- validating schema
- workload source
- gate entrypoint
- artifact path

Those paths must be repo-relative; absolute paths and parent traversal are not
valid claim bindings.

Runtime-visible behavior still requires the normal Doe stage order and status
update discipline.
