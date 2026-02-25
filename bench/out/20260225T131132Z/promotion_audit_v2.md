# AMD Vulkan Directional->Comparable Promotion Audit (v2)

Date: 2026-02-25
Scope: re-audit of 17 directional candidate workloads for strict comparable-lane promotion.

## Gate Rules Applied

1. Hard domain gate:
- `comparable=true` is rejected for these domains unless `applesToApplesVetted=true`:
  `pipeline-async`, `p1-capability`, `p1-resource-table`, `p1-capability-macro`, `p2-lifecycle`, `p2-lifecycle-macro`, `p0-resource`, `p0-compute`, `p0-render`, `surface`.
- Source: `bench/compare_dawn_vs_fawn.py:65`, `bench/compare_dawn_vs_fawn.py:1390`.

2. Candidate flag gate:
- `comparabilityCandidate.enabled=true` cannot be promoted to `comparable=true` until candidate flag is cleared.
- Source: `bench/compare_dawn_vs_fawn.py:1411`.

3. Wording gates:
- `comparable=true` rejects:
  - descriptions starting with `"Directional "`
  - notes containing `"closest draw-call throughput proxy"`.
- Source: `bench/compare_dawn_vs_fawn.py:1401`, `bench/compare_dawn_vs_fawn.py:1406`.

4. Current project policy:
- strict comparable matrix is the audited 23-workload subset.
- macro diagnostics are explicitly directional/non-claim right now.
- Source: `status.md:684`, `status.md:688`.

## Updated Promotion List

### Class A: Pilot now (lowest-friction)

1. `p1_resource_table_immediates_macro_500`
2. `p0_render_pixel_local_storage_barrier_macro_500`

Why:
- not in the hard-gated domain set;
- `comparabilityCandidate.enabled` is already `false`.

Required edits:
- `comparable: false -> true`
- `benchmarkClass: "directional" -> "comparable"`
- remove `"Directional "` prefix from `description`
- rewrite `comparabilityNotes` to apples-to-apples wording

### Class B: Next wave, moderate friction

1. `render_draw_throughput_macro_200k`
2. `texture_sampler_write_query_destroy_macro_500`

Why:
- not hard-domain gated, but blocked by `comparabilityCandidate.enabled=true`.

Required edits:
- all Class A edits, plus:
- `comparabilityCandidate.enabled: true -> false` (and clear tier/notes if desired)

### Class C: Hard-gated (explicit vetting required)

1. `p1_capability_introspection_contract`
2. `p1_resource_table_immediates_contract`
3. `p2_lifecycle_refcount_contract`
4. `p1_capability_introspection_macro_500`
5. `p2_lifecycle_refcount_macro_200`
6. `p0_resource_lifecycle_contract`
7. `p0_compute_indirect_timestamp_contract`
8. `p0_render_multidraw_contract`
9. `p0_render_multidraw_indexed_contract`
10. `p0_render_pixel_local_storage_barrier_contract`

Why:
- domain is in hard gate set.

Required edits:
- all Class A edits, plus:
- `applesToApplesVetted: false -> true`
- for four workloads also clear candidate flag:
  `p0_resource_lifecycle_contract`, `p0_compute_indirect_timestamp_contract`,
  `p0_render_multidraw_contract`, `p0_render_multidraw_indexed_contract`.

### Class D: Keep directional for now

1. `draw_indexed_render_proxy`
2. `draw_indexed_render_macro_200k`
3. `surface_presentation_contract`

Why:
- `draw_indexed_render_proxy` uses explicit closest-proxy note rejected for comparable workloads.
- both indexed workloads are still candidate-tiered parity placeholders.
- `surface_presentation_contract` is explicitly directional-only in status policy.

## Validation Plan (required before and after flip)

1. Pre-flip diagnostic probe:

```bash
python3 bench/compare_dawn_vs_fawn.py \
  --config bench/compare_dawn_vs_fawn.config.amd.vulkan.directional.json \
  --workload-filter <comma-separated-candidates> \
  --comparability warn \
  --include-noncomparable-workloads \
  --out bench/out/dawn-vs-fawn.amd.vulkan.promotion_probe.v2.json
```

2. After workload-contract edits, strict check:

```bash
python3 bench/compare_dawn_vs_fawn.py \
  --config bench/compare_dawn_vs_fawn.config.amd.vulkan.extended.comparable.json \
  --workload-filter <same-candidates> \
  --out bench/out/dawn-vs-fawn.amd.vulkan.promotion_strict.v2.json
```

3. Gate checks:

```bash
python3 bench/schema_gate.py --report bench/out/dawn-vs-fawn.amd.vulkan.promotion_strict.v2.json
python3 bench/check_correctness.py --report bench/out/dawn-vs-fawn.amd.vulkan.promotion_strict.v2.json
python3 bench/trace_gate.py --report bench/out/dawn-vs-fawn.amd.vulkan.promotion_strict.v2.json
```

4. If promoted workloads are merged into the comparable contract:
- re-run full strict comparable matrix;
- update status/process docs in same change.

