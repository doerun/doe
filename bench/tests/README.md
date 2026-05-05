# bench/tests

Python tests for `bench/` tooling, runners, and gates. Run via:

```
python3 -m unittest discover bench.tests
```

or a specific module:

```
python3 -m unittest bench.tests.test_predict_simfabric_wallclock
```

Categories:

- **Receipt schema tests** — pin receipt shapes against fixture data;
  fail closed on schema drift.
- **Hash-chain tests** — verify manifest / HostPlan / CSL / artifact
  integrity invariants.
- **Gate tests** — exercise each blocking gate's pass/fail/blocked
  branches against curated inputs.
- **Per-kernel byte-identity tests** — assert 1L vs full-depth CSL
  emit byte-identity for the targets that share kernel bodies.
- **Validator binding tests** — bind cross-repo validators (Doppler
  reference fixture, etc.) to model-specific inputs; skip with typed
  pointer when fixtures are absent.
- **Internal helpers** (`_*.py`) — prefixed with `_`; not test
  modules themselves.

Tests must not embed counts, percentages, or benchmark numbers in
assertion messages — reference the artifact path. See the
"Documentation drift prevention" rule in [`CLAUDE.md`](../../CLAUDE.md).
