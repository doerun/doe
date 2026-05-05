# bench/lib

Shared library code imported by `bench/runners/`, `bench/tools/`, and
`bench/gates/`. No CLI entrypoints live here; everything is invoked
through one of those parents.

Notable modules:

- `benchmark_ir.py` — typed in-memory representation of run / compare /
  claim receipts.
- `bench_utils.py` — common path helpers, hashing, JSON IO.
- `comparability_coherence.py` — apples-to-apples checks for
  Dawn-vs-Doe compares (timing-phase symmetry, dispatch-count parity,
  hardware-path asymmetry detection). Enforces non-negotiable #7-#11
  in [`CLAUDE.md`](../../CLAUDE.md).
- `output_paths.py` — canonical-vs-scratch path routing
  (`bench/out/<lane>/` vs `bench/out/scratch/<timestamp>/`).
- `benchmark_cube_*.py` — cube/dashboard rendering for the static
  bench viewer.
- `adhoc_claim_gating.py` — claim-policy evaluation shared between the
  CLI `claim` subcommand and the gate runner.

Library modules must stay deterministic and side-effect-free where
possible; runtime state belongs in the caller.
