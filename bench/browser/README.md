# bench/browser

Browser-lane gates for the Chromium WebGPU compare surface. Currently
`browser_gate.py` and `browser_claim_gate.py`, which evaluate the
Playwright-driven smoke output at
`browser/chromium/artifacts/.../dawn-vs-doe.browser.playwright-smoke.diagnostic.json`
against gate policy.

Browser executors and harvesters live in
[`bench/executors/`](../executors/) (`run-browser-ort-bench.py`,
`harvest-doppler-browser-*.js`); the Chromium build itself lives under
`browser/chromium/`. Smoke-artifact production is documented in
[`bench/README.md`](../README.md) and the platform-specific
`bench/docs/` pages.

Gate output is consumed by `bench/runners/run_blocking_gates.py`
through [`config/gates.json`](../../config/gates.json).
