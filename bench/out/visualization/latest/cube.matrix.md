# Benchmark Cube

Generated: `2026-04-08T22:31:16.973136Z`

Rows: `6`

## Backend Native

Maturity: `primary`. Primary support: `backend`.

| Workload Set | Apple Silicon macOS | AMD Linux Vulkan | Windows D3D12 |
| --- | --- | --- | --- |
| Full Comparable | unimplemented (contract exists, evidence missing) | claimable (4 rows) | unimplemented (contract exists, evidence missing) |
| Uploads | unimplemented (contract exists, evidence missing) | claimable (4 rows) | unimplemented (contract exists, evidence missing) |
| Compute | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |
| Render | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |
| Pipeline | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |
| Texture | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |
| Contracts | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |

- Strict Dawn-vs-Doe backend reports are the canonical claim lane.
- Missing cells indicate unimplemented or unevidenced host coverage, not silent fallback.
- AMD Vulkan strict comparable/release cells must come from native-supported workload contracts and matching Doe/Dawn adapter identity.
- Windows D3D12 strict comparable coverage is currently limited to compute, upload, pipeline, and p0-resource contracts; render and texture rows remain out of scope until native D3D12 coverage expands.

## Node Package

Maturity: `primary`. Primary support: `node`.

| Workload Set | Apple Silicon macOS | Linux x64 | Windows x64 |
| --- | --- | --- | --- |
| Full Comparable | unimplemented (contract exists, evidence missing) | claimable (1 rows) | unimplemented (contract exists, evidence missing) |
| Uploads | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |
| Compute | unimplemented (contract exists, evidence missing) | claimable (1 rows) | unimplemented (contract exists, evidence missing) |
| Dispatch Only | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |
| Pipeline | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |
| Overhead | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |

- Node is the primary supported package surface for doe-gpu.
- Node package comparisons are runtime/package evidence and do not replace strict backend reports.

## Bun Package

Maturity: `prototype`. Primary support: `bun`.

| Workload Set | Apple Silicon macOS | Linux x64 | Windows x64 |
| --- | --- | --- | --- |
| Full Comparable | unimplemented (contract exists, evidence missing) | claimable (1 rows) | unimplemented (contract exists, evidence missing) |
| Uploads | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |
| Compute | unimplemented (contract exists, evidence missing) | claimable (1 rows) | unimplemented (contract exists, evidence missing) |
| Dispatch Only | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |
| Pipeline | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |
| Overhead | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) | unimplemented (contract exists, evidence missing) |

- Bun has API parity with Node through the package-default Bun runtime entry. Canonical compare flow is artifact-first through bench/cli.py compare with the doe_bun_package and bun_webgpu_package executors.
- Do not cite Bun cells as package parity until they are populated by comparable artifacts.

