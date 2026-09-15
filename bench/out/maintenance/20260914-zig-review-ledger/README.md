# Hierarchical Zig review ledger validation

This version-1 maintenance record covers the persistent review log and its
derived queue. It does not record completed source reviews beyond the explicit
scope and status in `runtime/zig/reviews/log.json`.

## Verification

- [Checker regressions](tests.log) exercise bottom-up completion, source changes,
  added and deleted files, superseded prerequisites, changed guidance/context,
  lost evidence, malformed completion records, path containment, and append-only
  history both before and after a commit.
- [Queue check](queue-check.log) validates the real log and its generated view.
- [Schema gate](schema-gate.log) validates the registered review schema/data
  alongside the existing schema targets.
- [Documentation checks](docs-checks.log) cover current local links and component
  routing.
- `source-files.tsv` binds the implementation, schema, log, queue, and process
  inputs; `SHA256SUMS` binds this validation record.

Reproduce from the repository root:

```bash
python3 -m unittest discover -s runtime/zig/tools -p test_review_log.py -v
python3 runtime/zig/tools/review_log.py --check
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_doc_link_coverage
python3 bench/gates/catscan_gate.py
```

The recorded test run used a temporary directory under this evidence directory
because the host's `/tmp` rejected a draft write with a quota error. Fixtures
were removed after the tests. The failed draft granted no review credit.

## Coverage limits

The queue derives production boundary candidates from the existing static import
analyzer. Reviewers must add relationships expressed through callbacks,
generators, shared semantics, or application flows. Fingerprints bind examined
inputs, while declared context binds additional consumers, contracts, and tests.
Neither hashes nor passing gates prove that someone read a file or establish
behavioral correctness. Existing architectural keep/merge decisions are not
imported as completed code reviews.

Component: Zig review tooling, configuration schema, and documentation
Intent: preserved
Acceptance evidence: commands and artifacts above
Boundary effects: repository-only review history and coverage; no runtime,
compiler, public API, or performance-policy change
