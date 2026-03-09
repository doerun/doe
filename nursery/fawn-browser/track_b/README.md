# Track B prototype lane

This directory contains executable Track B incubation artifacts for the browser
integration layer.

Scope:

1. schema-backed request fixtures for Track B modules,
2. config-driven deterministic prototype execution,
3. gate output proving fixture validation and deterministic replay.

These prototypes are nursery-only. They do not change core runtime behavior and
they are not promotion evidence by themselves.

Files:

1. `policy.json`
   - config-as-code thresholds and allowed operation sets.
2. `schemas/*.schema.json`
   - request/result contract schemas per Track B module.
3. `fixtures/*.request.json`
   - deterministic prototype requests for each Track B module.

Scripts:

1. `scripts/track_b_prototype.py`
   - validate one request, execute deterministic prototype logic, emit result JSON.
2. `scripts/check_track_b_prototypes.py`
   - run all Track B fixtures, rerun for determinism, emit a gate report.
