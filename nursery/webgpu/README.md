# @simulatte/webgpu

Canonical Doe WebGPU package for browserless benchmarking, CI workflows, and
headless runtime integration.

This directory is the package root for `@simulatte/webgpu`. It contains the
Doe-native Node provider, the addon build contract, the Bun FFI entrypoint,
and the CLI helpers used by benchmark and CI workflows.

## What Lives Here

- `src/index.js`: default Doe-native Node provider entrypoint
- `src/node-runtime.js`: compatibility alias for the Node entrypoint
- `src/bun-ffi.js`: Bun prototype FFI path
- `src/runtime_cli.js`: Doe CLI/runtime helpers
- `native/doe_napi.c`: N-API bridge that loads `libdoe_webgpu`
- `binding.gyp`: addon build contract
- `bin/fawn-webgpu-bench.js`: command-stream bench wrapper
- `bin/fawn-webgpu-compare.js`: Dawn-vs-Doe compare wrapper

## Quickstart

```bash
cd /home/x/deco/fawn/zig
zig build dropin

cd /home/x/deco/fawn/nursery/webgpu
npm run build:addon
```

Then install from npm or use this checkout directly:

```bash
npm install @simulatte/webgpu
```

## Notes

- This package is for headless benchmarking and CI workflows, not full browser
  parity.
- API details live in `API_CONTRACT.md`.
- Compatibility scope is documented in `COMPAT_SCOPE.md`.
