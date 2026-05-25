# Doe status: runtime backends and benchmark lanes

This is a live topical status shard. Follow the shared shard policy in
[`README.md`](README.md).

## 2026-05-25 — Apple Metal copy contracts enter the release claim lane

Apple Metal native Doe-vs-Dawn release evidence has been refreshed after the
copy transfer contracts were strengthened from diagnostic-only rows into
claim-eligible release rows.

- buffer-to-texture and texture-to-texture rows now use the governed release
  repeat/window contract instead of the previous smoke-sized window.
- the default texture-to-texture command fixture now uses the larger transfer
  shape used by the stronger copy fixtures instead of the tiny smoke fixture.
- both sides now run the copy rows with deferred queue sync, so the repeated
  copy stream is encoded as one drained workload unit.
- the release claim policy can still select workload-unit wall timing for copy
  rows whose per-copy operation timing is below the useful measurement floor.

Release artifacts:

- `bench/out/apple-metal/release/20260525T190747Z/runtime-comparisons.apple.metal.release/run-artifacts/doe/`
- `bench/out/apple-metal/release/20260525T190829Z/runtime-comparisons.apple.metal.release/run-artifacts/dawn_delegate/`
- `bench/out/apple-metal/release/20260525T190829Z/dawn-vs-doe.apple.metal.release.compare.json`
- `bench/out/apple-metal/release/20260525T190829Z/dawn-vs-doe.apple.metal.release.claim.json`

The broader local compare lane can still carry diagnostic/non-claim rows for
methodology auditing. Marketing or release claims should cite the release claim
artifact above.

## 2026-05-25 — Apple Metal release claim uses complete operation timing

Apple Metal native Doe-vs-Dawn release evidence has been refreshed after two
timing-scope fixes in the compare harness:

- render macro workloads now keep full operation timing instead of encode-only
  timing; encode-only selection remains limited to render domains where encode
  is the comparable operation scope.
- kernel-dispatch traces now fold host kernel prewarm into selected operation
  timing when the trace actually contains `kernel_dispatch`; non-kernel copy
  and render traces keep their ordinary operation timing source.

Release artifacts:

- `bench/out/apple-metal/release/20260525T184401Z/runtime-comparisons.apple.metal.release/run-artifacts/doe/`
- `bench/out/apple-metal/release/20260525T184443Z/runtime-comparisons.apple.metal.release/run-artifacts/dawn_delegate/`
- `bench/out/apple-metal/release/20260525T184443Z/dawn-vs-doe.apple.metal.release.compare.json`
- `bench/out/apple-metal/release/20260525T184443Z/dawn-vs-doe.apple.metal.release.claim.json`

The broader local compare lane still includes diagnostic/non-claim rows for
methodology auditing. Marketing or release claims should cite the release claim
artifact above, whose selector excludes rows that are not claim-eligible.

## 2026-05-25 — P0 multi-draw fixtures use explicit indirect commands

The `render_multidraw` and `render_multidraw_indexed` fixtures now exercise
the explicit `draw_indirect` / `draw_indexed_indirect` command path instead of
implicitly enabling multi-draw from ordinary direct render draws. The WebGPU
full path now sizes and writes one indirect argument record per requested draw
before using the p0 multi-draw API; if the argument staging write cannot be
prepared, execution falls back to the regular draw loop.

Fresh directional evidence:

- `bench/out/apple-metal/explore/20260525T181045Z/runtime-comparisons.apple.metal.explore/run-artifacts/doe/doe-render_multidraw-20260525T181045Z.run.json`
- `bench/out/apple-metal/explore/20260525T181045Z/runtime-comparisons.apple.metal.explore/run-artifacts/doe/doe-render_multidraw_indexed-20260525T181045Z.run.json`
- `bench/out/apple-metal/explore/20260525T181126Z/runtime-comparisons.apple.metal.explore/run-artifacts/dawn_delegate/dawn_delegate-render_multidraw-20260525T181126Z.run.json`
- `bench/out/apple-metal/explore/20260525T181126Z/runtime-comparisons.apple.metal.explore/run-artifacts/dawn_delegate/dawn_delegate-render_multidraw_indexed-20260525T181126Z.run.json`

The rows remain directional until governed apples-to-apples evidence is
recorded.

## 2026-05-25 — Browser gate now records forced-runtime identity

The Chromium Track A browser gate now validates explicit runtime-selection
evidence for both Dawn and Doe modes. Smoke and layered browser artifacts carry
forced mode, selected runtime, fallback status, selector version, launch-args
hash, and Doe runtime artifact hash for Doe mode.

Current refreshed evidence:

- `browser/chromium/artifacts/20260525T163954Z/dawn-vs-doe.browser.playwright-smoke.diagnostic.json`
- `browser/chromium/artifacts/20260525T163954Z/dawn-vs-doe.browser-layered.superset.diagnostic.json`
- `browser/chromium/artifacts/20260525T163954Z/dawn-vs-doe.browser-layered.superset.summary.json`
- `browser/chromium/artifacts/20260525T163954Z/dawn-vs-doe.browser-layered.superset.check.json`
- `bench/out/browser-promotion/20260525T163954Z/browser_gate.json`

The gate passes with zero failures. The output remains diagnostic; the next
promotion boundary is a formal browser claim lane.

## Current state

- Apple Metal native Doe-vs-Dawn fair-cold compare defaults are in place.
- AMD Vulkan now has Doe-side `VkPipelineCache` support and renewed strict
  compare evidence.
- Apple Metal package lanes and AMD Vulkan package lanes both have current
  narrow claimable surfaces.
- Benchmark reporting is artifact-first; JSON receipts under `bench/out/` are
  the canonical output surface.

## Active blockers

- Backend-wide claim language is still narrower than the existence of isolated
  claimable rows.
- D3D12 claim evidence still requires a suitable Windows host.
- Broader Metal and ORT/WebGPU package claims remain mixed or narrow.

## Landed infrastructure

- Fair-cold compare defaults on Metal
- Vulkan pipeline-cache implementation and optional persistence
- Artifact-first compare/claim/report flows
- Bench output viewer as the single tracked local HTML surface

## Ground truth

- Backend benchmark status is no longer the main source of status-log volume.
- This shard exists so backend and benchmark updates stop crowding compiler and
  Cerebras work into a single giant dated file.

## Use this shard for

- Native backend compare status
- Package-lane status
- Benchmark methodology / claim updates
- Backend-specific performance evidence
