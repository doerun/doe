# Benchmark Cube

Generated: `2026-03-10T19:18:36.994484Z`

Rows: `1081`

## Backend Native

Maturity: `primary`. Primary support: `backend`.

| Workload Set | Apple Silicon macOS | AMD Linux Vulkan | Windows D3D12 |
| --- | --- | --- | --- |
| Full Comparable | comparable (31 rows) | diagnostic (7 rows) | unimplemented (contract exists, evidence missing) |
| Uploads | claimable (8 rows) | diagnostic (7 rows) | unimplemented (contract exists, evidence missing) |
| Compute | claimable (6 rows) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |
| Render | claimable (7 rows) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |
| Pipeline | claimable (1 rows) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |
| Texture | claimable (3 rows) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |
| Contracts | claimable (2 rows) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |

- Strict Dawn-vs-Doe backend reports are the canonical claim lane.
- Missing cells indicate unimplemented or unevidenced host coverage, not silent fallback.
- AMD Vulkan strict comparable/release cells must come from native-supported workload contracts and matching Doe/Dawn adapter identity.
- Windows D3D12 strict comparable coverage is currently limited to compute, upload, pipeline, and p0-resource contracts; render and texture rows remain out of scope until native D3D12 coverage expands.

## Node Package

Maturity: `primary`. Primary support: `node`.

| Workload Set | Apple Silicon macOS | Linux x64 | Windows x64 |
| --- | --- | --- | --- |
| Full Comparable | diagnostic (12 rows) | diagnostic (4 rows) | unimplemented (contract exists, evidence missing) |
| Uploads | claimable (5 rows) | comparable (5 rows) | unimplemented (contract exists, evidence missing) |
| Compute | diagnostic (3 rows) | comparable (3 rows) | unimplemented (contract exists, evidence missing) |
| Dispatch Only | diagnostic (1 rows) | diagnostic (1 rows) | unimplemented (contract exists, evidence missing) |
| Pipeline | diagnostic (1 rows) | diagnostic (1 rows) | unimplemented (contract exists, evidence missing) |
| Overhead | diagnostic (2 rows) | diagnostic (1 rows) | unimplemented (contract exists, evidence missing) |

- Node is the primary supported package surface for @simulatte/webgpu.
- Node package comparisons are runtime/package evidence and do not replace strict backend reports.

## Bun Package

Maturity: `prototype`. Primary support: `bun`.

| Workload Set | Apple Silicon macOS | Linux x64 | Windows x64 |
| --- | --- | --- | --- |
| Full Comparable | diagnostic (12 rows) | diagnostic (11 rows) | unimplemented (contract exists, evidence missing) |
| Uploads | comparable (5 rows) | comparable (5 rows) | unimplemented (contract exists, evidence missing) |
| Compute | comparable (3 rows) | claimable (3 rows) | unimplemented (contract exists, evidence missing) |
| Dispatch Only | diagnostic (1 rows) | diagnostic (1 rows) | unimplemented (contract exists, evidence missing) |
| Pipeline | diagnostic (1 rows) | diagnostic (1 rows) | unimplemented (contract exists, evidence missing) |
| Overhead | diagnostic (2 rows) | diagnostic (1 rows) | unimplemented (contract exists, evidence missing) |

- Bun has API parity with Node through the package-default Bun runtime entry. Compare lane: bench/bun/compare.js against the bun-webgpu package.
- Do not cite Bun cells as package parity until they are populated by comparable artifacts.

