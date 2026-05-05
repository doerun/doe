# Loop protocol: building TSIR vs. closing parity

## Purpose

This doc defines the iteration discipline for two concurrent streams of work
on the Doe TSIR pipeline:

- **Loop 2** — builds the compiler machinery.
- **Loop 3** — proves it on real Doppler→Doe→Cerebras legs, one kernel family
  at a time.

`tsir-lowering-plan.md` defines the *architecture* and the *rollout ordering*
(steps 1–12). This doc defines the *cadence* and *gating rules* that govern
how code lands against that architecture — so that partially-built TSIR can
host real parity receipts without the two streams fighting each other.

Loop 1 — end-to-end happy-path bring-up — is not defined here. That work
precedes and produces the current baseline.

## Summary

| | Loop 2 | Loop 3 |
|--|--|--|
| Job | Build TSIR infrastructure | Close one parity leg |
| Scope | Oracle, descriptors, schema, frontend, residency, collectives, emitter | GEMV → RMSNorm → gather, in that order |
| Per-iteration | One committable increment of the lowest-numbered unlanded step | One kernel family, end to end |
| Gating | Green tests + dated status entry; stop at phase boundary | Parity receipt + lowering binding committed |
| Doc output | Status entry in `docs/status/tsir.md` (Loop 2 TSIR work) / `docs/status/cerebras-csl.md` (Cerebras-specific work) | Parity receipt under `reports/parity/` + manifest `integrityExtensions.lowerings[]` entry |

## Loop 2 — TSIR machinery

**Source of truth:** `docs/tsir-lowering-plan.md`.

**Per-iteration protocol:**

1. Re-read `docs/tsir-lowering-plan.md`.
2. Find the lowest-numbered step not fully landed.
3. Land **one committable increment only** of that step.
4. Include tests, schema/contract updates if any, and a dated status entry in
   the relevant `docs/status/*.md`.
5. Stop unless that exact step is fully green. Do **not** start the next step
   in the same iteration.
6. Stop at phase boundaries for review.

**Phase boundaries** (from `tsir-lowering-plan.md` §Step 12):

- Phase A: steps 1–7 plus GEMV/RMSNorm/gather rewrites.
- Phase B: attention (decode + tiled).
- Phase C: remaining kernel families.
- Phase D: autotuning pass on top of the correctness-only planner.

A phase boundary is a mandatory pause. No Loop 2 iteration crosses a phase
without human review.

**Stop-until-green rule:** A Loop 2 iteration that leaves its step partially
landed must be marked as such in the status entry. The next iteration resumes
the same step. No drift to other steps until the current one is green.

## Loop 3 — parity closure per kernel family

**Source of truth:** `docs/tsir-lowering-plan.md` §Step 10 (manifest binding)
plus `bench/tools/doe_parity.py` receipt schema.

**Sequencing (immutable until Phase A completes):**

1. **fused_gemv** — FFN-dominant kernel; proves residency pass end-to-end.
2. **rmsnorm** — cross-PE mean/variance; proves collective synthesis.
3. **gather** — worst per-PE blowup today; unblocks embedding lookup under
   tight residency budget.

Attention enters the Loop 3 sequence only after Phase A is green. It does
*not* go in this list.

**Per-iteration protocol:**

1. Confirm the Loop 2 phase required for this kernel family is landed.
   Minimum prerequisites for each family:
   - **GEMV:** TSIR schema (step 3), frontend (step 4), residency (step 5),
     mechanical emitter (step 7) landed for at least this kernel.
   - **RMSNorm:** add collective synthesis (step 6) landed.
   - **Gather:** same as RMSNorm plus RDRR Merkle-block packaging in place
     for the gathered tensor (cross-repo dependency on Doppler).
2. Capture the shared contract through TSIR semantic + realization on:
   - `webgpu-generic` (target descriptor)
   - `wse3` (target descriptor)
3. Run `bench/tools/doe_parity.py --kernel <family> --class <exactness> …`
   against the reference interpreter.
4. Emit a parity receipt to `reports/parity/` (schema:
   `config/doe-parity-receipt.schema.json`).
5. Bind the TSIR digests into the relevant Doppler manifest's
   `integrityExtensions.lowerings[]` entry (one per (kernelRef, backend) pair).
   Use `findLoweringOrThrow()` from `doppler/src/formats/rdrr/lowerings.js` to
   verify runtime lookup resolves.
6. Commit parity receipt + manifest binding + dated status entry in the same
   commit.
7. Update any current-state claims in cross-repo coordination docs only if
   they changed.
8. **Stop.** Do not start the next family until the current one is green and
   committed.

**Stop-until-green rule:** if the parity receipt for the current family is
`not_implemented` / `deferred` / `failed`, the iteration is not green and the
next family does not begin. A failing parity run is a Loop 2 defect report,
not a license to skip ahead.

## Legacy-path receipts (pre-TSIR)

During Loop 2 bring-up, `doe_parity.py` may emit receipts from the current
classifier/template CSL path, labeled `backend: csl-classifier-legacy`. These
receipts:

- exercise the receipt-schema + report directory plumbing on real WGSL+CSL
  pairs
- do **not** satisfy a Loop 3 iteration
- must not be bound into `integrityExtensions.lowerings[]` (leaving that
  array absent is the correct state for a Doppler artifact with no TSIR-backed
  lowering yet)

A Loop-3-iteration receipt requires `backend: webgpu-generic` or `backend:
wse3` and non-null TSIR digests. Anything else is Loop 2 plumbing evidence.

## Cross-repo handoffs

Loop 3 binds into Doppler artifacts. The touchpoints:

- **Schema:** `doppler/src/formats/rdrr/types.d.ts`
  (`IntegrityExtensionsLowerings`, `IntegrityExtensionsLoweringEntry`).
- **Validator:** `doppler/src/formats/rdrr/validation.js`
  (`validateLoweringsSection`) — shape only; rejection is caller-side.
- **Runtime lookup:** `doppler/src/formats/rdrr/lowerings.js`
  (`findLoweringOrThrow`, `DOPPLER_LOWERING_MISSING`,
  `DOPPLER_LOWERING_REJECTED`).

A Loop 3 iteration that needs a new field on a lowering entry pauses Loop 3,
opens a Doppler schema change as a separate commit, and resumes Loop 3 only
after the schema lands on Doppler `main`.

**Vocabulary drift to resolve before the first Loop 3 close:** Doe's current
`config/doe-parity-receipt.schema.json` uses underscored exactness-class
values (`bit_exact_solo`, `algorithm_exact`, `tolerance_bounded`). RDRR
canonical form (see `doppler/docs/distribution/rdrr-p2p-plan.md` and
`doppler/docs/distribution/collective-transport-contract.md`) is hyphenated
(`bit-exact-solo`, etc.), and the Doppler `IntegrityExtensionsLoweringEntry`
schema uses the hyphenated form. A Loop 3 iteration will need to either
(a) update the Doe receipt schema to the hyphenated form, or (b) translate
in the tool that copies receipt fields into the manifest entry. Option (a) is
preferred — keep RDRR vocabulary verbatim everywhere.

## What does *not* belong in either loop

- **Loop 2 iterations that run parity on real artifacts.** That's Loop 3.
- **Loop 3 iterations that change the compiler.** That's Loop 2.
- **Receipts emitted as side-effects of ad-hoc debug runs.** Only committed
  receipts under `reports/parity/` count toward Loop 3.
- **Attention** until Phase A completes.
- **CI automation.** Per `tsir-lowering-plan.md` §Step 9, the parity harness
  is a manual CLI gate; automation is not in scope for either loop.

## Exit criteria

Loop 2 exits when:

- all 12 steps are landed
- the 16 per-kernel `emit_csl_*.zig` emitters are deleted
- `emit_csl_classify.zig` is reduced to kernel-family hint extraction

Loop 3 exits when:

- GEMV, RMSNorm, and gather each have a committed parity receipt at
  `algorithm-exact` or better against `webgpu-generic` and `wse3`
- the corresponding Doppler manifests carry `integrityExtensions.lowerings[]`
  entries for those (kernelRef, backend) pairs
- Phase A is closed in `docs/status/tsir.md`

Attention and the remaining kernel families begin a new loop sequence
(Phase B / Phase C); their rules are defined when Phase A exits, not earlier.
