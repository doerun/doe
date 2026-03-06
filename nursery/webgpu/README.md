# @simulatte/webgpu

Canonical Doe WebGPU package for browserless benchmarking, CI workflows, and
headless runtime integration.

This directory is the package root for `@simulatte/webgpu`. It contains the
Node provider source, the addon build contract, the Bun FFI entrypoint, and
the CLI helpers used by benchmark and CI workflows.

Current surface maturity is intentionally uneven:

- Node is the primary supported package surface.
- Bun remains a prototype FFI path and is not yet at Node parity.
- Package-surface comparisons should be read through the benchmark cube outputs
  under `bench/out/cube/`, not as a replacement for strict backend reports.

## What Lives Here

- `src/index.js`: default Node provider entrypoint
- `src/node-runtime.js`: compatibility alias for the Node entrypoint
- `src/bun-ffi.js`: Bun prototype FFI path
- `src/runtime_cli.js`: Doe CLI/runtime helpers
- `native/doe_napi.c`: N-API bridge for the in-process Node provider
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
- Node provider comparisons are package/runtime evidence. Backend claim lanes
  remain the canonical performance evidence path.
- On Linux, the default in-process Node path now fails fast with an explicit
  error instead of hanging when only `libdoe_webgpu.so` is present. Use
  `createDoeRuntime()` for Doe CLI/runtime benches until the Linux Node Doe
  path is wired through end-to-end.
- Explicit `DOE_WEBGPU_LIB=.../libwebgpu.so` is diagnostic-only on Linux and
  should not be treated as Doe-native evidence.
- Bun compatibility is still tracked as prototype work until a real compare
  lane and matching artifact coverage exist.
- API details live in `API_CONTRACT.md`.
- Compatibility scope is documented in `COMPAT_SCOPE.md`.
