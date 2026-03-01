# WebGPU Headless Runtime Comparison Matrix

This document outlines qualitative differences and target use-cases for headless WebGPU workloads in JavaScript environments. It is intentionally scoped as a comparison draft, not a claim report.

| Feature / Trait | **Fawn Doe** (`@fawn/webgpu-node`) | **Node WebGPU** (`webgpu`) | **Bun WebGPU** (`bun-webgpu`) | **Deno** (Built-in WebGPU) |
| :--- | :--- | :--- | :--- | :--- |
| **Underlying Engine** | `libdoe_webgpu` (Zig + Lean pipeline) | Google Dawn (C++) | Google Dawn (C++) | Mozilla `wgpu-core` (Rust) |
| **Primary Focus** | Deterministic Compute, ML/AI, Verifiability | Browser Parity, Graphics | Browser Parity, Graphics | Web Standard Parity |
| **Binary Footprint** | Smaller targeted runtime expected | Varies by build/distribution | Varies by build/distribution | Bundled with runtime distribution |
| **JS Binding Layer** | Node-API (N-API) / Bun FFI | Node-API (N-API) | Bun FFI (Fast Foreign Function) | V8 Fast API (Rust bindings) |
| **Security Model** | Explicit schema/gate discipline in Fawn pipeline | Runtime heuristics + Dawn validation | Runtime heuristics + Dawn validation | Rust memory safety + wgpu validation |
| **Resource Allocation** | Arena-backed, predictable memory | General WebGPU async allocations | General WebGPU async allocations | General WebGPU async allocations |
| **WebGPU Spec Compliance**| Compute-prioritized subset target | Broad Chromium-aligned coverage | Broad Chromium-aligned coverage | Broad Firefox/wgpu coverage |
| **WGSL Shader Support** | Runtime-specific compiler/tooling path | Tint | Tint | Naga |
| **Target Use Case** | LLM Inference Testing, Benchmarks, Contracts | E2E Graphics Testing, Headless bots | High-perf TS Server Compute | Server-side TS/JS Compute |

## Architectural Takeaways for Fawn

1. Determinism and fail-fast contracts are the intended Doe value proposition for benchmarking workflows.
2. Bun FFI can reduce wrapper overhead versus heavier bridge layers, but end-to-end results must be measured per workload.
3. Distribution size and startup claims must be backed by measured artifacts before release claims.

## Scaffolding the Fawn NPM Package

- Doe is exposed through a native C ABI and can be bridged from JS via Bun FFI now.
- Node N-API support is planned but not implemented in this scaffold.
- Browser API parity is not claimed by this draft package; the current focus is headless benchmarking workflows.
