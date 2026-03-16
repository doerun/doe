# WGSL compiler support

Quick-reference for doe_wgsl backend and feature status.

## Backend targets

| Backend | Status              | Notes                                              |
|---------|---------------------|----------------------------------------------------|
| MSL     | Native              | Self-contained; no external tools required         |
| SPIR-V  | Native              | Self-contained; no external tools required         |
| HLSL    | Native              | Self-contained; no external tools required         |
| DXIL    | Requires DXC        | Spawns external `dxc`; see `emit_dxil.zig` header  |

## Feature coverage

| Category              | Status              | Notes                                              |
|-----------------------|---------------------|----------------------------------------------------|
| Compute shaders       | Full                | Covers Doppler's full compute feature set          |
| Vertex shaders        | Basic               | Entry-point wiring works; advanced attrs untested  |
| Fragment shaders      | Basic               | Entry-point wiring works; advanced attrs untested  |
| Struct types          | Full (flat)         | Nested structs parsed but not exercised in tests   |
| var\<workgroup\>      | Full                | Workgroup-memory allocation emitted correctly      |
| Override constants    | Full                | Emitted as pipeline-overridable specialization     |
| Enable extensions     | Full (f16, subgrp)  | `enable f16` and `enable subgroups` pass through   |
| Helper functions      | Full                | 702+ helpers in Doppler corpus, all passing        |
| Builtins              | Full (compute set)  | subgroupAdd/Min/Max/ExclusiveAdd, subgroupBroadcast/Shuffle/ShuffleXor, subgroup_size, subgroup_invocation_id, atomicAdd, workgroupBarrier, ~30 math |
| Texture types         | 2D only             | texture_2d parsed; cube/array/3D untested          |
| Texture sampling      | Basic               | `textureSample`, `textureSampleLevel`, `textureDimensions`, `textureLoad/store` on `texture_2d<f32>` / `texture_storage_2d` |
| Matrix types          | Unsupported         | Not present in Doppler corpus; not yet emitted     |
| Pointer parameters    | Parsed, untested    | AST accepts ptr params; backend emit unverified    |
| Switch statements     | Unsupported         | Not present in Doppler corpus; not yet emitted     |
