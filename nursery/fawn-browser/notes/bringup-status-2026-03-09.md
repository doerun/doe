# Track A (browser) gate status (2026-03-09)

Track A (browser) diagnostics now have governed macOS promotion evidence in the
core blocking runner.

## Fresh artifacts

### Browser gate report

1. `bench/out/browser-promotion/20260309T015018Z/browser_gate.json`

Result:

1. `ok=true`
2. ownership contract passed
3. smoke contract passed
4. strict layered browser superset contract passed

### Fresh smoke

1. `nursery/fawn-browser/artifacts/20260309T015018Z/dawn-vs-doe.browser.playwright-smoke.diagnostic.json`

Result:

1. `dawn` compute smoke pass = true
2. `dawn` render smoke pass = true
3. `doe` compute smoke pass = true
4. `doe` render smoke pass = true

Notes:

1. browser close warnings were observed after successful test execution
2. the report remains diagnostic by contract and is not a claim artifact

### Fresh strict layered superset

1. `nursery/fawn-browser/artifacts/20260309T015018Z/dawn-vs-doe.browser-layered.superset.diagnostic.json`
2. `nursery/fawn-browser/artifacts/20260309T015018Z/dawn-vs-doe.browser-layered.superset.summary.json`
3. `nursery/fawn-browser/artifacts/20260309T015018Z/dawn-vs-doe.browser-layered.superset.check.json`

Result:

1. `overallRequiredFailures=0`
2. `promotionChecked=true`
3. both `dawn` and `doe` report zero required L1 failures
4. both `dawn` and `doe` report zero required L2 failures

## Promotion state

Track A (browser) scope now has:

1. core blocking gate wiring in `bench/run_blocking_gates.py --with-browser-gate`
2. explicit ownership in `config/browser-ownership.json`
3. explicit browser promotion approvals in `nursery/fawn-browser/bench/workflows/browser-promotion-approvals.json`

This promotes governance and repeatability for M1-M3 on this host. The final
canonical evidence in this note comes from the combined
`bench/run_blocking_gates.py --with-browser-gate --with-modules` pass. The
browser artifacts remain diagnostic rather than claimable until a formal
browser claim lane exists.
