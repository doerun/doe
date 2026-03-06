# Benchmark Cube

Generated: `2026-03-06T20:57:31.061199Z`

Rows: `158`

## Backend Native

Maturity: `primary`. Primary support: `backend`.

| Workload Set | Apple Silicon macOS | AMD Linux Vulkan | Windows D3D12 |
| --- | --- | --- | --- |
| Full Comparable | claimable (30 rows) | comparable (1 rows) | unimplemented |
| Uploads | claimable (8 rows) | comparable (1 rows) | unimplemented |
| Compute | claimable (7 rows) | unimplemented | unimplemented |
| Render | claimable (7 rows) | unimplemented | unimplemented |
| Pipeline | claimable (2 rows) | unimplemented | unimplemented |
| Texture | claimable (3 rows) | unimplemented | unimplemented |
| Contracts | claimable (3 rows) | unimplemented | unimplemented |

- Strict Dawn-vs-Doe backend reports are the canonical claim lane.
- Missing cells indicate unimplemented or unevidenced host coverage, not silent fallback.

## Node Package

Maturity: `primary`. Primary support: `node`.

| Workload Set | Apple Silicon macOS | Linux x64 | Windows x64 |
| --- | --- | --- | --- |
| Full Comparable | diagnostic (11 rows) | diagnostic (11 rows) | unimplemented |
| Uploads | claimable (5 rows) | comparable (5 rows) | unimplemented |
| Compute | diagnostic (4 rows) | diagnostic (4 rows) | unimplemented |
| Pipeline | diagnostic (1 rows) | diagnostic (1 rows) | unimplemented |
| Overhead | diagnostic (1 rows) | diagnostic (1 rows) | unimplemented |

- Node is the primary supported package surface for @simulatte/webgpu.
- Node package comparisons are runtime/package evidence and do not replace strict backend reports.

## Bun Package

Maturity: `prototype`. Primary support: `bun`.

| Workload Set | Apple Silicon macOS | Linux x64 | Windows x64 |
| --- | --- | --- | --- |
| Full Comparable | unimplemented | unimplemented | unimplemented |
| Uploads | unimplemented | unimplemented | unimplemented |
| Compute | unimplemented | unimplemented | unimplemented |
| Pipeline | unimplemented | unimplemented | unimplemented |
| Overhead | unimplemented | unimplemented | unimplemented |

- Bun remains a prototype FFI path until a real compare lane exists.
- Do not cite Bun cells as package parity until they are populated by comparable artifacts.

