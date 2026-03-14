# Changelog

All notable changes to `@simulatte/webgpu` are documented in this file.

This changelog is package-facing and release-oriented. Early entries were
retrofitted from package version history and package-surface commits so the npm
package has a conventional release history alongside the broader Fawn status
and process documents.

## [0.3.1] - 2026-03-11

### Changed

- Tightened the published package README wording, section names, and layering
  narrative after the `0.3.0` release.
- Clarified the terminology split between the `Doe runtime` underneath the
  package and the `Doe API` JS convenience surface exposed by the package,
  including the more opinionated `gpu.compute.once(...)` helper within it.
- Fixed the layered README SVG asset so it renders correctly on package
  surfaces.

## [0.3.0] - 2026-03-11

### Changed

- Breaking: redesigned the shared `doe` surface around `await
  doe.requestDevice()`, grouped `gpu.buffer.*`, grouped `gpu.kernel.*`, and
  `gpu.compute.once(...)` instead of the earlier flat bound-helper methods.
- Added `gpu.buffer.like(...)` for buffer-allocation boilerplate reduction and
  `gpu.compute.once(...)` as the first more opinionated one-shot helper inside
  the Doe API.
- Doe helper token values now use camelCase (`storageRead`,
  `storageReadWrite`) and Doe workgroups now accept `[x, y]` in addition to
  `number` and `[x, y, z]`.
- `gpu.compute.once(...)` now rejects raw numeric WebGPU usage flags; use Doe
  usage tokens there or drop to `gpu.buffer.*` / `gpu.kernel.*` for explicit
  raw control.
- Kept the same `doe` shape on `@simulatte/webgpu` and
  `@simulatte/webgpu/compute`; the package split remains the underlying raw
  device surface (`full` vs compute-only facade), not separate helper dialects.
- Updated the package README, API contract, and JSDoc guide to standardize the
  `Direct WebGPU` and `Doe API` model, including the more opinionated
  `gpu.compute.once(...)` helper within the Doe API, and the boundary between
  the headless package lane and `nursery/fawn-browser`.

## [0.2.4] - 2026-03-11

### Changed

- `doe.runCompute()` now infers binding access from Doe helper-created buffer
  usage and fails fast when a bare binding lacks Doe usage metadata or uses a
  non-bindable/ambiguous usage shape.
- Simplified the compute-surface README example to use inferred binding access
  (`bindings: [input, output]`) and the device-bound `doe.bind(await
  requestDevice())` flow directly.
- Clarified the install contract for non-prebuilt platforms: the `node-gyp`
  fallback only builds the native addon and does not bundle `libwebgpu_doe`
  plus the required Dawn sidecar.
- Aligned the published package docs and API contract with the current
  `@simulatte/webgpu`, `@simulatte/webgpu/compute`, and `@simulatte/webgpu/full`
  export surface.

## [0.2.3] - 2026-03-10

### Added

- macOS arm64 (Metal) prebuilds shipped alongside existing Linux x64 (Vulkan).
- "Verify your install" section with `npm run smoke` and `npm test` guidance.
- Added explicit package export surfaces for `@simulatte/webgpu` (default
  full) and `@simulatte/webgpu/compute`, plus the first `doe` ergonomic
  namespace for buffer/readback/compute helpers.
- Added `doe.bind(device)` so the ergonomic helper surface can wrap an existing
  device into the same bound helper object returned by `doe.requestDevice()`.

### Changed

- Restructured the package README around the default full surface,
  `@simulatte/webgpu/compute`, and the `doe` helper surface.
- `doe.runCompute()` now infers binding access from Doe helper-created buffer
  usage and fails fast for bare bindings that do not carry Doe usage metadata.
- Fixed broken README image links to use bundled asset paths instead of dead
  raw GitHub URLs.
- Root Fawn README now directs package users to the package README.
- Fixed 4 Metal benchmark workload contracts with asymmetric repeat accounting;
  all 31 comparable workloads now have symmetric `leftCommandRepeat` /
  `rightCommandRepeat`.

## [0.2.2] - 2026-03-10

### Added

- Added a Linux regression test guarding the drop-in loader against reopening
  `libwebgpu_doe` as its own target WebGPU provider.

### Changed

- Fixed Linux drop-in proc resolution so workspace-local Node and Bun package
  loads resolve Dawn/WebGPU target symbols instead of recursing through the Doe
  drop-in library.
- Validated the package release surface on Linux Vulkan with addon build, smoke,
  Node tests, prebuild assembly, and Bun contract tests.

## [0.2.1] - 2026-03-07

### Added

- Added package repository, homepage, and issue metadata.
- Added packaged README asset generation support and shipped package assets.
- Added additional package-surface contract documents and metadata schemas to
  the published file set.

### Changed

- Refined the package surface around the canonical Doe-backed Node and Bun
  entrypoints.
- Expanded package publishing inputs to include scripts, prebuilds, and package
  documentation needed for reproducible installs.

## [0.2.0] - 2026-03-06

### Added

- Promoted the package to the public `@simulatte/webgpu` name.
- Added Node and Bun entrypoints, benchmark CLI wrappers, and a native addon
  bridge for headless WebGPU execution.
- Added package install, build, test, smoke, and prebuild workflows.

### Changed

- Replaced the earlier placeholder package metadata with a real publishable
  package surface for Doe-backed headless compute and benchmarking.
- Shifted the package from scaffold-only metadata to a documented package with
  explicit published files and package-surface contracts.

## [0.0.1] - 2026-03-01

### Added

- Initial package scaffold for the Doe WebGPU package surface under
  `nursery/webgpu`.
