# Changelog

All notable changes to `@simulatte/webgpu` are documented in this file.

This changelog is package-facing and release-oriented. Early entries were
retrofitted from package version history and package-surface commits so the npm
package has a conventional release history alongside the broader Fawn status
and process documents.

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
