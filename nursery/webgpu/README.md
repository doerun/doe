# @doe/webgpu

Scaffold package for the full Doe runtime distribution surface.

- This package is the planned target for the `@doe/webgpu` npm package.
- It is currently a scaffold to reserve the package namespace and docs path.
- For the current production headless package, use:
  - `@doe/webgpu-core` (Node/Bun headless + CLI tools)
- Browser/distribution package lives in:
  - `nursery/fawn-browser`

## Scope

`@doe/webgpu` is intended to cover the full native/runtime replacement tier:
- browserless runtime replacement for Node/Bun and native embeddings
- full `webgpu.h` ABI integration
- render+compute parity beyond headless-only paths

## Current status

- Namespace reserved and directory scaffolded.
- API surface is intentionally unavailable in this stage.
- Consumers should treat this as an integration placeholder until runtime surface hardening is complete.

## Planned minimum package entrypoints

- `src/index.js` (package entry)
- `src/node.js` (node-specific implementation hook)
- `src/bun.js` (bun-specific implementation hook)
- `src/package-entry.js` (shared module implementation)
