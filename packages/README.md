# Packages

`packages/` contains Doe's public JavaScript package surface:

- `packages/doe-gpu/`
  - `doe-gpu`, the merged runtime and helper package

Repo-only operator tooling lives outside `packages/` and is documented in
[`docs/internal-tooling.md`](../docs/internal-tooling.md). The public package
contract is the package exports plus
[`packages/doe-gpu/README.md`](./doe-gpu/README.md), not the scripts under
`bench/`, `browser/`, or `pipeline/`.

Within `doe-gpu`, subpaths such as `compute`, `browser`, and `hybrid` are
subpath entrypoints of one package, not separate products.

## Deprecated

- `@simulatte/webgpu` — legacy npm name, now redirected to `doe-gpu`
- `@simulatte/webgpu-doe` — legacy npm name, now redirected to `doe-gpu`
