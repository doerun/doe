# Direct WGSL output attribution

## Disposition

Keep the unsigned power-of-two rewrite unpromoted. This direct execution check
creates no compiler Worker or shader adapter. It exercises original WGSL, a
passes-disabled round trip through the qualified WASM, and native-emitted WGSL.
Original and disabled bytes are identical. The browser recompiles every variant.

[Environment](environment.json) records browser/adapter identity, configured
sessions and launch arguments. Each fresh context/device runs rotated cohorts
with fresh pipelines and buffers, first with compute timestamps and then without.
Driver caches remain shared; context recreation does not promise cache isolation.
The [particle contract](../../../../packages/doe-gpu/examples/browser-compiler/contract.json)
retains identical state, geometry, steps, precision, rendering and every-component
CPU oracle. Raw session files retain preparation, allocation/upload, CPU record,
submission, completion/readback, GPU compute and full application scopes.

All numerical checks passed. Application timing signs reverse across sessions.
Identical original/disabled text also produces substantial timing differences.
Complete-operation medians remain similar in the uninstrumented sessions; no
repeatable material shader or application benefit is attributable to the rewrite.
This neither proves transformed WGSL inherently slower nor establishes that
runtime delivery alone explains the earlier assisted-path loss.

The unsigned rewrite remains a mechanism fixture. Select the next general
transformation from measured recoverable cost in an independent inference or
rendering application before further optimization work. Do not repair this
performance rejection by expanding packaging or selecting favorable cohorts.

## Reproduce

Use the verified extracted package and installed native emitter:

```sh
DOE_PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs \
DOE_BROWSER_PACKAGE_ROOT=/path/to/extracted/package \
node bench/executors/run-browser-wgsl-output.mjs
```

The desktop session supplies its own display authorization. The
[settings](../../../../config/browser-compiler-output.json) declare browser
arguments, sessions, viewport and output destination. No Worker is instantiated;
source generation and disabled compilation finish before browser measurements.

The initial Node setup took a memory view before WASM allocation grew memory,
which detached the view. [The failure](failed-node-memory-view.log) remains;
the harness now reserves input before taking the view. This occurred before GPU
measurement. [Execution](execution.log) records the corrected run.
[Manifest](manifest.json) binds source, contract, retained shaders and rows.

Component: benchmark/evidence owner.
Intent: preserved. Acceptance evidence: linked raw sessions and independent oracle.
Boundary effects: compiler delivery and package behavior unchanged; browser owns
GPU execution throughout.
