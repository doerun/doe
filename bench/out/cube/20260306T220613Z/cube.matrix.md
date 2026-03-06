# Benchmark Cube

Generated: `2026-03-06T22:06:13.659966Z`

Rows: `379`

## Backend Native

Maturity: `primary`. Primary support: `backend`.

| Workload Set | Apple Silicon macOS | AMD Linux Vulkan | Windows D3D12 |
| --- | --- | --- | --- |
| Full Comparable | claimable (30 rows) | comparable (8 rows) | unimplemented |
| Uploads | claimable (8 rows) | comparable (8 rows) | unimplemented |
| Compute | claimable (7 rows) | diagnostic (1 rows) | unimplemented |
| Render | claimable (7 rows) | unimplemented | unimplemented |
| Pipeline | claimable (2 rows) | diagnostic (1 rows) | unimplemented |
| Texture | claimable (3 rows) | unimplemented | unimplemented |
| Contracts | claimable (3 rows) | diagnostic (2 rows) | unimplemented |

- Strict Dawn-vs-Doe backend reports are the canonical claim lane.
- Missing cells indicate unimplemented or unevidenced host coverage, not silent fallback.
- AMD Vulkan strict comparable/release cells must come from native-supported workload contracts and matching Doe/Dawn adapter identity.

## Node Package

Maturity: `primary`. Primary support: `node`.

| Workload Set | Apple Silicon macOS | Linux x64 | Windows x64 |
| --- | --- | --- | --- |
| Full Comparable | diagnostic (11 rows) | diagnostic (4 rows) | unimplemented |
| Uploads | claimable (5 rows) | comparable (5 rows) | unimplemented |
| Compute | comparable (3 rows) | comparable (3 rows) | unimplemented |
| Dispatch Only | diagnostic (1 rows) | diagnostic (1 rows) | unimplemented |
| Pipeline | diagnostic (1 rows) | diagnostic (1 rows) | unimplemented |
| Overhead | diagnostic (1 rows) | diagnostic (1 rows) | unimplemented |

- Node is the primary supported package surface for @simulatte/webgpu.
- Node package comparisons are runtime/package evidence and do not replace strict backend reports.

## Bun Package

Maturity: `prototype`. Primary support: `bun`.

| Workload Set | Apple Silicon macOS | Linux x64 | Windows x64 |
| --- | --- | --- | --- |
| Full Comparable | unimplemented | diagnostic (11 rows) | unimplemented |
| Uploads | unimplemented | comparable (5 rows) | unimplemented |
| Compute | unimplemented | claimable (3 rows) | unimplemented |
| Dispatch Only | unimplemented | diagnostic (1 rows) | unimplemented |
| Pipeline | unimplemented | diagnostic (1 rows) | unimplemented |
| Overhead | unimplemented | diagnostic (1 rows) | unimplemented |

- Bun has API parity with Node via direct FFI. Compare lane: bench/bun/compare.js against the bun-webgpu package.
- Do not cite Bun cells as package parity until they are populated by comparable artifacts.

