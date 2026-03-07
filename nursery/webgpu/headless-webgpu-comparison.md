# WebGPU Headless Runtime Comparison Matrix

This document outlines qualitative differences and target use-cases for headless WebGPU workloads in JavaScript environments. It is intentionally scoped as a comparison draft, not a claim report.

| Feature / Trait | **Fawn Doe** (`@simulatte/webgpu`) | **Node WebGPU** (`webgpu`) | **Bun WebGPU** (`bun-webgpu`) |
| :--- | :--- | :--- | :--- |
| **Underlying Engine** | `libwebgpu_doe` (Zig + Lean pipeline) | Google Dawn (C++) | Google Dawn (C++) |
| **Primary Focus** | Deterministic Compute, ML/AI, Verifiability | Browser Parity, Graphics | Browser Parity, Graphics |
| **Binary Footprint** | Smaller targeted runtime expected | Varies by build/distribution | Varies by build/distribution |
| **JS Binding Layer** | Node-API (N-API) / Bun FFI | Node-API (N-API) | Bun FFI (Fast Foreign Function) |
| **Security Model** | Explicit schema/gate discipline in Fawn pipeline | Runtime heuristics + Dawn validation | Runtime heuristics + Dawn validation |
| **Resource Allocation** | Arena-backed, predictable memory | General WebGPU async allocations | General WebGPU async allocations |
| **WebGPU Spec Compliance**| Compute-prioritized subset target | Broad Chromium-aligned coverage | Broad Chromium-aligned coverage |
| **WGSL Shader Support** | Runtime-specific compiler/tooling path | Tint | Tint |
| **Target Use Case** | LLM Inference Testing, Benchmarks, Contracts | E2E Graphics Testing, Headless bots | High-perf TS Server Compute |

## Architectural Takeaways for Fawn

1. Determinism and fail-fast contracts are the intended Doe value proposition for benchmarking workflows.
2. Bun FFI can reduce wrapper overhead versus heavier bridge layers, but end-to-end results must be measured per workload.
3. Distribution size and startup claims must be backed by measured artifacts before release claims.

## Ecosystem reference: official/community competitors and stats

Sorted by GitHub stars (snapshot taken: 2026-03-02).
This list is limited to real WebGPU runtime implementations (not types/tooling).

| Runtime surface | GitHub project | Maintainer signal | Stars |
| :--- | :--- | :--- | ---: |
| `webgpu` (npm) | `dawn-gpu/node-webgpu` | `dawn-gpu` (official Dawn upstream) | 73 |
| `bun-webgpu` (npm) | `kommander/bun-webgpu` | Community maintained | 29 |

Notes:

1. `@simulatte/webgpu` is still pre-publication, so no direct npm star baseline exists in this snapshot yet.
2. This section is for runtime head-to-head comparability only; stars are a popularity signal, not a quality or correctness signal.
3. For this repo’s “official” definition, maintainer/org governance is the gate.

## Scaffolding the Fawn NPM Package

- Doe is exposed through a native C ABI and can be bridged from JS via Bun FFI now.
- Node N-API support now exists in the canonical `@simulatte/webgpu` package.
- Browser API parity is not claimed by this draft package; the current focus is headless benchmarking workflows.
