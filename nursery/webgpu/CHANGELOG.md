# Changelog

All notable changes to `@simulatte/webgpu` are documented in this file.

This changelog is package-facing and release-oriented. Early entries were
retrofitted from package version history and package-surface commits so the npm
package has a conventional release history alongside the broader Fawn status
and process documents.

## [0.2.3] - 2026-03-10

### Added

- macOS arm64 (Metal) prebuilds shipped alongside existing Linux x64 (Vulkan).
- Monte Carlo pi estimation example in the README, replacing the trivial
  buffer-readback snippet with a real GPU compute demonstration.
- "Verify your install" section with `npm run smoke` and `npm test` guidance.

### Changed

- Restructured package README for consumers: examples, quickstart, and
  verification first; building from source and Fawn developer context at the end.
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
