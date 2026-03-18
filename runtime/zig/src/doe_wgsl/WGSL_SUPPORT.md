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
| Vertex shaders        | Functional          | Entry-point wiring, struct I/O decomposition, builtin inputs/outputs, inter-stage locations, interpolation decorations, `clip_distances` all work across MSL/HLSL/SPIR-V; render pipeline runtime integration still open |
| Fragment shaders      | Functional          | Entry-point wiring, struct I/O decomposition (MRT), builtin inputs (position, front_facing, sample_index), frag_depth output, `primitive_index`, `blend_src`, discard all work across MSL/HLSL/SPIR-V; render pipeline runtime integration still open |
| Robustness transform  | Functional          | Clamps sized arrays/vectors/matrices, runtime-sized array bases (broadened whitelist: global_ref, member, load, local_ref, param_ref, index, call), and texture coordinates for `textureLoad`/`textureStore` (2D/3D/cube/depth/multisampled/storage); Lean proof-driven clamp elision via `Config.elide_proven_bounds`; non-global `arrayLength` and broader backend texture hardening still need follow-up |
| Struct types          | Full (flat)         | Nested structs parsed but not exercised in tests   |
| var\<workgroup\>      | Full                | Workgroup-memory allocation emitted correctly      |
| Override constants    | Full                | Emitted as pipeline-overridable specialization     |
| Enable extensions     | Full (f16, subgrp)  | `enable f16` and `enable subgroups` pass through   |
| Helper functions      | Full                | 702+ helpers in Doppler corpus, all passing        |
| Builtins              | Full (compute set)  | subgroupAdd/Min/Max/ExclusiveAdd, subgroupBroadcast/Shuffle/ShuffleXor, subgroup_size, subgroup_invocation_id, atomicAdd, workgroupBarrier, ~30 math |
| Texture types         | 2D + 3D             | texture_2d, texture_3d; cube/array unsupported     |
| Texture sampling      | Basic               | `textureSample`, `textureSampleLevel`, `textureDimensions`, plus guarded 2D `textureLoad/store` on the current MSL/HLSL path; broader texture/backend parity is still incomplete |
| Matrix types          | Full                | Parsed, IR-lowered, emitted across MSL (`floatMxN`), HLSL, and SPIR-V (`OpTypeMatrix`); robustness transform clamps column indices |
| Pointer parameters    | Parsed, untested    | AST accepts ptr params; backend emit unverified    |
| Switch statements     | Full                | IR switch/case/default emitted across MSL, HLSL, and SPIR-V |
