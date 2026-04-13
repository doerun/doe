# Doe package model

## Public package

Doe has one public npm package family today:

- `doe-gpu`

Its package contract is defined by:

- [`packages/doe-gpu/package.json`](../packages/doe-gpu/package.json)
- [`packages/doe-gpu/README.md`](../packages/doe-gpu/README.md)
- [`docs/internal-tooling.md`](./internal-tooling.md)

Repo-only benchmark, browser, and release tooling is not part of the npm
package surface.

## Exported entrypoints

The current public `doe-gpu` exports are:

- `doe-gpu`
  - host-aware default surface
  - Node uses `src/index.js`
  - Bun uses `src/bun.js`
  - Deno uses `src/deno.js`
- `doe-gpu/compute`
  - narrower compute-oriented surface
- `doe-gpu/browser`
  - browser-facing entrypoint
- `doe-gpu/hybrid`
  - browser/host hybrid integration entrypoint

These are subpath entrypoints inside one package family, not separate products.

## Package boundary

`doe-gpu` is the public runtime package.

`doe-gpu` is the JS/package contract. Cross-platform native install support is
provided through optional platform packages:

- `doe-gpu-darwin-arm64`
- `doe-gpu-darwin-x64`
- `doe-gpu-linux-arm64`
- `doe-gpu-linux-x64`
- `doe-gpu-win32-x64`

Repo-local debug fallback prebuilds may still exist under
`packages/doe-gpu/prebuilds/<platform-arch>/`, but those are not the primary
cross-platform npm distribution mechanism.

It does not ship:

- `bench/` compare or claim CLIs
- browser benchmark harnesses under `browser/chromium/`
- release pipeline tooling
- repo-only operator scripts

Advanced helper exports such as `createDoeRuntime()` and
`runDawnVsDoeCompare()` are still part of the package API, but they are helper
surfaces, not the canonical operator front doors.

## Legacy names

The old npm names are compatibility history only:

- `@simulatte/webgpu`
- `@simulatte/webgpu-doe`

They should be treated as redirects/history in docs and migration notes, not as
separate current package families.
