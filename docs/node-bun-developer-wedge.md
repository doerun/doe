# Node/Bun developer wedge

## Product sentence

`doe-gpu` is the native, receipt-backed WebGPU runtime for Node and Bun.

WebGPU compatibility is the adoption hook. Doe runtime control, receipts,
diagnostics, explicit failure, and measured package performance are the
developer advantage.

## Boundary

This wedge is separate from Fawn and browser-runtime claims.

`doe-gpu` targets JavaScript hosts where the application already controls the
GPU provider boundary:

- Node.js services and local tools
- Bun services and local tools
- Electron applications
- agent runtimes that need local GPU execution
- GPU-heavy JavaScript developer tools

The package may expose Deno and browser compatibility entrypoints, but the first
developer wedge is Node and Bun. Browser replacement evidence belongs to the
Fawn/Chromium lane.

## ICP

Primary buyers and early users:

- local AI application teams
- Electron desktop AI teams
- agent-runtime teams with local execution paths
- embedding/search product teams
- JavaScript tools that need GPU kernels without a browser tab
- CI and release teams that need GPU regression receipts

They already feel the pain directly: runtime opacity, weak backend provenance,
driver-specific failures, noisy performance evidence, hidden fallback, and
missing receipts for what actually ran.

## First product proof

The install-to-first-kernel path must stay boring:

```bash
npm install doe-gpu
node node_modules/doe-gpu/examples/node-first-kernel.mjs
bun node_modules/doe-gpu/examples/bun-first-kernel.mjs
```

Each example must:

- request a real Doe-backed device
- run a real WGSL compute kernel
- print runtime identity from `providerInfo()`
- emit a JSON receipt with workload, kernel hash, input hash, output hash, and
  measured package timing
- fail explicitly when the native addon or Doe runtime library is missing

These examples are smoke artifacts, not performance claims.

Node also has an explicit native-direct package lane for benchmark and advanced
developer proof work:

```js
import { createNativeDirect } from "doe-gpu";

const gpu = createNativeDirect();
const adapter = await gpu.requestAdapter();
const device = await adapter.requestDevice();
```

The default `create()` surface remains the compatibility front door.
`createNativeDirect()` is the measured Node fast lane: it keeps the same WebGPU
shape for the package workloads while reducing wrapper overhead and preserving
receipt identity as `doe-gpu`.

For Bun, keep the public package contract separate from the direct FFI
investigation lane. The public entry now defaults to the Bun FFI backend on
supported native hosts when the library loads, while `DOE_BUN_WEBGPU_BACKEND`
keeps the backend choice explicit for diagnostics. Public Bun readback mode is
workload-scoped by receipt: the buffer upload/readback row stays on `mapAsync`,
and the current image, queue-submit, and vector rows use native
map/read/copy/unmap on the Apple Metal lane. The direct FFI lane still has its
own strict compare and claim artifacts; the public install path needs separate
public-provider evidence before any public Bun speed claim is promoted.

## Benchmark pack

The package benchmark pack should cover workloads a Node/Bun developer already
recognizes as valuable:

- local inference warmup and steady dispatch
- embedding or vector operations
- buffer upload and readback
- shader compile and compute pipeline creation
- image or video transform kernels
- queue submit and completion latency with real GPU work

For each workload, preserve the benchmark taxonomy:

- `surface`: `package`
- `runtimeHost`: `node` or `bun`
- `product`: `doe`, `node_webgpu_package`, `bun_webgpu_package`, or a declared
  Dawn-backed package product
- workload identity: stable name plus config hash
- run artifact before compare report
- queue-wait policy: recorded in trace metadata; Node package readback plans may
  use terminal readback `mapAsync` as the completion wait only when that
  readback structurally follows the last write/copy into the mapped buffer; Bun
  package plans use the same policy for the package benchmark lane

Do not make empty-submit latency a headline workload unless it is clearly labeled
diagnostic. A useful package proof should perform non-zero GPU work and report
dispatch, setup, encode, submit/wait, and readback scopes where available.

Use `bench/tools/package_phase_delta.py` alongside compare and claim reports
when optimizing the package lane. It groups raw setup, binding, submit, write,
and readback receipt fields, normalized by the run receipt divisor when a
workload repeats full plan cycles, so changes can be attributed without moving
claim logic into prose. Package trace metadata also records write-pressure
counts and bytes, split between static file-backed buffer loads and dynamic
writes; phase-delta reports surface those distributions so resident-state
inference work can be defined from receipt evidence instead of inferred from
timing alone.
Use `bench/tools/package_order_sensitivity.py` when a same-runtime comparison
changes direction under swapped execution order. That artifact keeps
order-sensitive package-path measurements diagnostic until the order effect is
controlled.

Resident-state inference is an explicit package workload shape, not a hidden
change to prepared decode. Use prepared-session executors with
`--resident-buffer-loads` or the registry ids ending in
`_prepared_resident_buffer_loads` to preload static file-backed buffer loads
before selected timing, record `packageResidentBufferLoadBreakdown`, and skip
those static writes inside the repeated steady loop. Full-cycle prepared decode
keeps timing every static and dynamic `writeBuffer` in the selected loop. The
promoted workload id for this shape is `gemma270m-decode-resident`, with Node
native-direct and Bun configs under
`bench/native-compare/compare.config.apple.metal.gemma270m.node.direct.decode.resident.warm.ir.json`
and
`bench/native-compare/compare.config.apple.metal.gemma270m.bun-package.decode.resident.warm.ir.json`.
Resident mode rejects plans that try to preload a buffer which also receives
dynamic selected-loop writes.

Prepared-session package proof uses
`bench/workloads/workloads.package.developer.prepared.json`. That pack is for
steady-state package execution after setup has been created. It repeats whole
plan cycles inside one timed sample and reports per-cycle normalized timing.
File-backed synthetic inputs are cached within the executor process so the
prepared upload/readback rows measure repeated upload/readback work rather than
re-reading identical asset files inside the timed loop. Static `writeBuffer`
payloads are materialized once per plan step inside the executor invocation, so
repeated prepared cycles do not rebuild the same typed-array payloads.
Shader/module/pipeline creation remains in the cold package-developer pack
because prepared-session timing intentionally excludes setup.

Local inference cold proof uses the existing package inference workload contract
`bench/workloads/workloads.package.inference.json`. Prepared decode proof uses
`bench/workloads/workloads.package.inference.prepared.json`, which repeats the
full decode plan cycle inside each timed sample and reports per-cycle normalized
timing. Node native-direct has cold and prepared Gemma 3 270M decode configs at
`bench/native-compare/compare.config.apple.metal.gemma270m.node.direct.decode.ir.json`
and
`bench/native-compare/compare.config.apple.metal.gemma270m.node.direct.decode.warm.ir.json`.
Bun has matching cold and prepared package decode configs at
`bench/native-compare/compare.config.apple.metal.gemma270m.bun-package.decode.ir.json`
and
`bench/native-compare/compare.config.apple.metal.gemma270m.bun-package.decode.warm.ir.json`.
The 270M shaped plans include matched readback captures: a logits-prefix capture
for prefill and sampled-token captures for decode. Package receipts summarize
readback captures with byte length, SHA-256, semantic phase, and decoded `u32`
values when available. Materialize those plan assets with
`bench/tools/materialize_plan_assets.py` before collecting receipt-first compare
artifacts. The current readback-backed Node native-direct decode claim artifacts
are
`bench/out/apple-metal/20260530T180023Z/gemma270m.node.direct.decode.ir.claim.json`
and
`bench/out/apple-metal/20260530T180733Z/gemma270m.node.direct.decode.warm.ir.claim.json`.
The current async-submit prepared Node native-direct decode artifacts are
`bench/out/apple-metal/20260531T022005Z/gemma270m.node.direct.decode.warm.async-submit.compare.json`
and
`bench/out/apple-metal/20260531T022005Z/gemma270m.node.direct.decode.warm.async-submit.claim.json`,
with phase attribution at
`bench/out/apple-metal/20260531T022005Z/gemma270m.node.direct.decode.warm.async-submit.phase-delta.json`.
The current readback-backed Bun package decode claim artifacts are
`bench/out/apple-metal/20260530T180153Z/gemma270m.bun-package.decode.ir.claim.json`
and
`bench/out/apple-metal/20260530T180815Z/gemma270m.bun-package.decode.warm.ir.claim.json`.
The current async-submit prepared Bun package decode artifacts are
`bench/out/apple-metal/20260531T021923Z/gemma270m.bun-package.decode.warm.async-submit.compare.json`
and
`bench/out/apple-metal/20260531T021923Z/gemma270m.bun-package.decode.warm.async-submit.claim.json`,
with phase attribution at
`bench/out/apple-metal/20260531T021923Z/gemma270m.bun-package.decode.warm.async-submit.phase-delta.json`.
The promoted catalog and generated compare-taxonomy expansion now expose these
Node native-direct and Bun decode profiles as package-surface workloads, so the
front-door compare selector and taxonomy reporting see the same receipt-backed
profiles.

Current package-developer receipt anchors:

- Node compatibility cold package surface:
  `bench/out/apple-metal/20260530T231739Z/apple.metal.package-developer.node.public.parser-clean.compare.json`
  and
  `bench/out/apple-metal/20260530T231739Z/apple.metal.package-developer.node.public.parser-clean.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260530T231739Z/apple.metal.package-developer.node.public.parser-clean.phase-delta.json`
- Node compatibility prepared package surface:
  `bench/out/apple-metal/20260530T231844Z/apple.metal.package-developer.node.public.prepared.parser-clean.compare.json`
  and
  `bench/out/apple-metal/20260530T231844Z/apple.metal.package-developer.node.public.prepared.parser-clean.claim.json`
- Node native-direct cold package surface:
  `bench/out/apple-metal/20260530T223529Z/apple.metal.package-developer.node.native-direct.current.compare.json`
  and
  `bench/out/apple-metal/20260530T223529Z/apple.metal.package-developer.node.native-direct.current.claim.json`
  plus refreshed coverage at
  `bench/out/apple-metal/20260531T011812Z/apple.metal.package-developer.node.native-direct.current-2.compare.json`
  and
  `bench/out/apple-metal/20260531T011812Z/apple.metal.package-developer.node.native-direct.current-2.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T011812Z/apple.metal.package-developer.node.native-direct.current-2.phase-delta.json`
  plus async-submit coverage at
  `bench/out/apple-metal/20260531T021008Z/apple.metal.package-developer.node.native-direct-async-submit.compare.json`
  and
  `bench/out/apple-metal/20260531T021008Z/apple.metal.package-developer.node.native-direct-async-submit.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T021008Z/apple.metal.package-developer.node.native-direct-async-submit.phase-delta.json`
- Node native-direct prepared package surface:
  `bench/out/apple-metal/20260530T223559Z/apple.metal.package-developer.node.native-direct.prepared.current.compare.json`
  and
  `bench/out/apple-metal/20260530T223559Z/apple.metal.package-developer.node.native-direct.prepared.current.claim.json`
- Bun public macOS cold package surface:
  `bench/out/apple-metal/20260531T000734Z/apple.metal.package-developer.bun.public.macos-full.compare.json`
  and
  `bench/out/apple-metal/20260531T000734Z/apple.metal.package-developer.bun.public.macos-full.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T000734Z/apple.metal.package-developer.bun.public.macos-full.phase-delta.json`
  plus async-submit coverage at
  `bench/out/apple-metal/20260531T020936Z/apple.metal.package-developer.bun.public-async-submit.compare.json`
  and
  `bench/out/apple-metal/20260531T020936Z/apple.metal.package-developer.bun.public-async-submit.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T020936Z/apple.metal.package-developer.bun.public-async-submit.phase-delta.json`
- Bun public macOS prepared package surface:
  `bench/out/apple-metal/20260531T000819Z/apple.metal.package-developer.bun.public.macos-full.prepared.compare.json`
  and
  `bench/out/apple-metal/20260531T000819Z/apple.metal.package-developer.bun.public.macos-full.prepared.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T000819Z/apple.metal.package-developer.bun.public.macos-full.prepared.phase-delta.json`
- Bun FFI cold package surface:
  `bench/out/apple-metal/20260531T005759Z/apple.metal.package-developer.bun.ffi-inline-layout.compare.json`
  and
  `bench/out/apple-metal/20260531T005759Z/apple.metal.package-developer.bun.ffi-inline-layout.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T005759Z/apple.metal.package-developer.bun.ffi-inline-layout.phase-delta.json`
- Bun FFI direct-flush cold package surface:
  `bench/out/apple-metal/20260531T011131Z/apple.metal.package-developer.bun.ffi-direct-flush.compare.json`
  and
  `bench/out/apple-metal/20260531T011131Z/apple.metal.package-developer.bun.ffi-direct-flush.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T011131Z/apple.metal.package-developer.bun.ffi-direct-flush.phase-delta.json`
- Bun FFI direct-flush prepared package surface:
  `bench/out/apple-metal/20260531T011712Z/apple.metal.package-developer.bun.ffi-direct-flush.prepared.compare.json`
  and
  `bench/out/apple-metal/20260531T011712Z/apple.metal.package-developer.bun.ffi-direct-flush.prepared.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T011712Z/apple.metal.package-developer.bun.ffi-direct-flush.prepared.phase-delta.json`
- Bun FFI async-submit prepared package surface:
  `bench/out/apple-metal/20260531T021207Z/apple.metal.package-developer.bun.ffi-async-submit.prepared.compare.json`
  and
  `bench/out/apple-metal/20260531T021207Z/apple.metal.package-developer.bun.ffi-async-submit.prepared.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T021207Z/apple.metal.package-developer.bun.ffi-async-submit.prepared.phase-delta.json`
- Bun FFI batch-attributed prepared package surface:
  `bench/out/apple-metal/20260531T021713Z/apple.metal.package-developer.bun.ffi-batch-breakdown.prepared.compare.json`
  and
  `bench/out/apple-metal/20260531T021713Z/apple.metal.package-developer.bun.ffi-batch-breakdown.prepared.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T021713Z/apple.metal.package-developer.bun.ffi-batch-breakdown.prepared.phase-delta.json`
- Bun FFI direct-write current cold package surface:
  `bench/out/apple-metal/20260531T014904Z/apple.metal.package-developer.bun.ffi-direct-write-rerun.compare.json`
  and
  `bench/out/apple-metal/20260531T014904Z/apple.metal.package-developer.bun.ffi-direct-write-rerun.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T014904Z/apple.metal.package-developer.bun.ffi-direct-write-rerun.phase-delta.json`
- Bun FFI batch-attributed cold package surface:
  `bench/out/apple-metal/20260531T021812Z/apple.metal.package-developer.bun.ffi-batch-breakdown.compare.json`
  and
  `bench/out/apple-metal/20260531T021812Z/apple.metal.package-developer.bun.ffi-batch-breakdown.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T021812Z/apple.metal.package-developer.bun.ffi-batch-breakdown.phase-delta.json`
- Bun FFI current vector isolation:
  `bench/out/apple-metal/20260531T014835Z/apple.metal.package-developer.bun.ffi-current-vector.compare.json`
  and
  `bench/out/apple-metal/20260531T014835Z/apple.metal.package-developer.bun.ffi-current-vector.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T014835Z/apple.metal.package-developer.bun.ffi-current-vector.phase-delta.json`
- Bun FFI current image isolation:
  `bench/out/apple-metal/20260531T015351Z/apple.metal.package-developer.bun.ffi-reverted-image.compare.json`
  and
  `bench/out/apple-metal/20260531T015351Z/apple.metal.package-developer.bun.ffi-reverted-image.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T015351Z/apple.metal.package-developer.bun.ffi-reverted-image.phase-delta.json`
- Bun FFI private Metal buffer diagnostic:
  `bench/out/apple-metal/20260531T014806Z/apple.metal.package-developer.bun.ffi-private-vector.compare.json`
  and
  `bench/out/apple-metal/20260531T014806Z/apple.metal.package-developer.bun.ffi-private-vector.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T014806Z/apple.metal.package-developer.bun.ffi-private-vector.phase-delta.json`
- Node compatibility prefix diagnostics for the current submit path:
  `bench/out/apple-metal/package-prefix-node-compat-parser-clean/vector.doe.json`
  and
  `bench/out/apple-metal/package-prefix-node-compat-parser-clean/pipeline.doe.json`
- Bun public macOS prefix diagnostics for the current package path:
  `bench/out/apple-metal/package-prefix-bun-public-macos-full/vector.doe.json`
  and
  `bench/out/apple-metal/package-prefix-bun-public-macos-full/pipeline.doe.json`
- Bun FFI optimization diagnostics:
  `bench/out/apple-metal/20260531T000140Z/apple.metal.package-developer.bun.public.ffi-readback-flat.compare.json`
  and
  `bench/out/apple-metal/20260531T000140Z/apple.metal.package-developer.bun.public.ffi-readback-flat.claim.json`
  plus
  `bench/out/apple-metal/20260531T000553Z/apple.metal.package-developer.bun.public.ffi-submit-flat.compare.json`
  and
  `bench/out/apple-metal/20260531T000553Z/apple.metal.package-developer.bun.public.ffi-submit-flat.claim.json`
- Bun FFI one-bind-group cold package diagnostics:
  `bench/out/apple-metal/20260531T001955Z/apple.metal.package-developer.bun.ffi-one-bg.claim-floor.compare.json`
  and
  `bench/out/apple-metal/20260531T001955Z/apple.metal.package-developer.bun.ffi-one-bg.claim-floor.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T001955Z/apple.metal.package-developer.bun.ffi-one-bg.claim-floor.phase-delta.json`
- Bun FFI one-bind-group prepared package surface:
  `bench/out/apple-metal/20260531T002122Z/apple.metal.package-developer.bun.ffi-one-bg.prepared.compare.json`
  and
  `bench/out/apple-metal/20260531T002122Z/apple.metal.package-developer.bun.ffi-one-bg.prepared.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T002122Z/apple.metal.package-developer.bun.ffi-one-bg.prepared.phase-delta.json`
- Bun FFI flat setup plus no create-time shader preflight:
  `bench/out/apple-metal/20260531T004030Z/apple.metal.package-developer.bun.ffi-flat-setup-no-preflight.compare.json`
  and
  `bench/out/apple-metal/20260531T004030Z/apple.metal.package-developer.bun.ffi-flat-setup-no-preflight.claim.json`
  with phase attribution at
  `bench/out/apple-metal/20260531T004030Z/apple.metal.package-developer.bun.ffi-flat-setup-no-preflight.phase-delta.json`
- Bun FFI prefix diagnostics:
  `bench/out/apple-metal/package-prefix-bun-ffi-readback-flat/vector.doe.json`
  and
  `bench/out/apple-metal/package-prefix-bun-ffi-readback-flat/pipeline.doe.json`
  plus
  `bench/out/apple-metal/package-prefix-bun-ffi-submit-flat/vector.doe.json`
  and
  `bench/out/apple-metal/package-prefix-bun-ffi-submit-flat/pipeline.doe.json`
  plus
  `bench/out/apple-metal/package-prefix-bun-ffi-one-bg/vector.doe.json`
  and
  `bench/out/apple-metal/package-prefix-bun-ffi-one-bg/image.doe.json`
- Node package inference prefix diagnostics after materializing synthetic
  assets:
  `bench/out/apple-metal/package-prefix-inference-current/gemma270m-prefill32.doe.json`
  and
  `bench/out/apple-metal/package-prefix-inference-current/gemma270m-prefill32.node-webgpu.json`

Treat these paths as anchors, not prose claims. Read `comparisonStatus`,
`claimStatus`, workload rows, and phase artifacts before making any external
performance statement.

## Competitors

The useful comparison set is:

- `doe-gpu`
- the Node WebGPU package currently used by the repo
- the Bun WebGPU path when available on the host
- a Dawn-backed baseline where the runtime boundary is equivalent
- CPU fallback only as a labeled baseline, never as a GPU competitor

CPU fallback can help a developer understand value over no GPU path. It cannot
support a GPU-runtime speed claim.

## Claim rules

Package claims follow the same comparability discipline as the runtime:

- same hardware
- same backend family
- same workload shape
- same input and output contract
- same timing scopes
- same resident-buffer-load mode for resident-state workloads
- same resident preload count and byte volume for resident-state workloads
- same sample policy
- same cache temperature label
- no hidden fallback
- no skipped GPU work
- no CPU fallback in the GPU competitor set
- runtime identity captured in every artifact

Allowed public shape:

- "Doe is faster on this named package workload, host, backend, hardware, and
  artifact."
- "Doe emits runtime identity and receipts for this package execution path."
- "Doe fails explicitly when the native runtime is unavailable."

Avoid:

- "fastest WebGPU runtime"
- "faster everywhere"
- "drop-in for every Node/Bun GPU use case"
- "browser replacement" in package GTM copy

## Demo pressure

The demos should show developer pull before browser pressure:

- local embedding search in Node
- Bun GPU image transform
- Electron local AI panel
- CI GPU regression receipt
- same WGSL kernel running through `doe-gpu` and Fawn with comparable receipts

The shared-kernel demo is the bridge between the two wedges: `doe-gpu` proves
developer installability, Fawn proves consumer-visible GPU behavior, and both
point back to the same Doe runtime.

## Evidence cadence

Use event-based evidence, not noisy benchmark churn.

- Run a tiny smoke pack for package/runtime changes.
- Run the package benchmark pack for named runtime, package, backend, or
  methodology milestones.
- Promote only reports that pass comparability and claim gates.
- Keep diagnostic runs useful for engineering, but out of public performance
  copy.
