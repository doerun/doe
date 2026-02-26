# 30 New WebGPU benchmark/workload ideas (implementation-ready plan)

Source constraints:

- vendor/api/runtime shape follows current AMD Vulkan lane conventions:
  `vendor=amd`, `api=vulkan`, `family=gfx11`, `driver=24.0.0`,
  `quirksPath=examples/quirks/amd_radv_noop_list.json`
- No code changes yet. This is a rollout plan with exact field targets, not a live patch set.
- `dawnFilter` values are placeholders until a matching Dawn perf filter is wired.

| # | Workload id | Phase | Command kind(s) | Comparable posture | commandsPath | leftCommandRepeat | leftIgnoreFirstOps | leftTimingDivisor | comparabilityNotes | dawnFilter |
|---|---|---|---|---|---|---|---|---|---|
| 1 | buffer_map_readback_1kb | A | `buffer_map` (read) | directional candidate | `examples/buffer_map_readback_1kb_commands.json` | 240 | 2 | 240 | One-shot map-readback op at 1KB per op, map/read/unmap per loop; validate same read window and deterministic source generation. | pending-map-readback-1kb |
| 2 | buffer_map_readback_64kb | A | `buffer_map` (read) | directional candidate | `examples/buffer_map_readback_64kb_commands.json` | 200 | 1 | 200 | Same shape as #1 with 64KB window to cover staging/memory path variance. | pending-map-readback-64kb |
| 3 | buffer_map_write_1kb | A | `buffer_map` (write) | directional candidate | `examples/buffer_map_write_1kb_commands.json` | 240 | 2 | 240 | One-shot map-write-unmap loop at 1KB; writes are deterministic and scoped to one range. | pending-map-write-1kb |
| 4 | buffer_map_write_64kb | A | `buffer_map` (write) | directional candidate | `examples/buffer_map_write_64kb_commands.json` | 200 | 1 | 200 | Same geometry as #3 with larger mapped region for larger staging write-path branch behavior. | pending-map-write-64kb |
| 5 | buffer_map_partial_read_4kb | A | `buffer_map` (read, subrange) | directional candidate | `examples/buffer_map_partial_read_4kb_commands.json` | 300 | 1 | 300 | Subrange map/read path with fixed offset/length to lock contract around partial mapping semantics. | pending-map-partial-read-4kb |
| 6 | buffer_map_partial_write_64kb | A | `buffer_map` (write, subrange) | directional candidate | `examples/buffer_map_partial_write_64kb_commands.json` | 220 | 1 | 220 | Subrange write path with explicit offset/length pattern; validates range checking and validation-surface parity. | pending-map-partial-write-64kb |
| 7 | buffer_map_double_request_guard | B | `buffer_map`, error scope | directional | `examples/buffer_map_double_request_guard_commands.json` | 120 | 0 | 120 | Second map before unmap should deterministically error; keep explicit error-scope assertion per iteration. | pending-map-double-request-guard |
| 8 | buffer_map_unmap_storm_macro | B | `buffer_map` mixed read/write | comparable candidate | `examples/buffer_map_unmap_storm_macro_commands.json` | 40 | 2 | 80 | Macro command emits 2 map/unmap ops per iteration; divisor normalizes per map-op so timing compares to operation unit. | pending-map-storm-macro |
| 9 | dispatch_indirect_1 | A | `dispatch_indirect` | comparable candidate | `examples/dispatch_indirect_1_commands.json` | 500 | 0 | 500 | Pure `dispatchWorkgroupsIndirect` parity contract with one indirect args shape and one pipeline. | pending-dispatch-indirect-1 |
| 10 | dispatch_indirect_live_args | B | `dispatch_indirect` + `buffer_write` | directional candidate | `examples/dispatch_indirect_live_args_commands.json` | 240 | 0 | 240 | Same dispatch shape as #9 while updating args buffer between calls; validates live-indirect-update behavior. | pending-dispatch-indirect-live-args |
| 11 | dispatch_indirect_large_args | B | `dispatch_indirect` + `buffer_write` | directional candidate | `examples/dispatch_indirect_large_args_commands.json` | 120 | 0 | 120 | Stress arg-buffer size and boundary checks with legal dispatches and explicit validation fences. | pending-dispatch-indirect-large-args |
| 12 | dispatch_workgroups_2d_sweep | A | `dispatch` | comparable candidate | `examples/dispatch_workgroups_2d_sweep_commands.json` | 320 | 0 | 320 | Deterministic 2D dispatch-grid sweep around fixed total work; isolates 2D workgroup decomposition. | pending-dispatch-2d-sweep |
| 13 | dispatch_workgroups_3d_sweep | B | `dispatch` | directional candidate | `examples/dispatch_workgroups_3d_sweep_commands.json` | 240 | 0 | 240 | 3D workgroup geometry sweep with fixed total work and deterministic z-plane ordering. | pending-dispatch-3d-sweep |
| 14 | dispatch_workgroups_indirect_pipeline_switch | C | `dispatch_indirect` + pipeline swap | directional candidate | `examples/dispatch_workgroups_indirect_pipeline_switch_commands.json` | 200 | 0 | 200 | Indirect dispatch fixed args with alternating pipeline handles each submission. | pending-dispatch-indirect-pipeline-switch |
| 15 | kernel_dispatch_macro_1000 | C | `kernel_dispatch` | directional candidate | `examples/kernel_dispatch_macro_1000_commands.json` | 20 | 0 | 20000 | Macro stream includes `repeat:1000` in command object; divisor = workload repeat × inner repeat for per-dispatch timing. | pending-kernel-dispatch-macro-1000 |
| 16 | draw_indexed_indirect_u16 | B | `draw_indexed_indirect` | directional candidate | `examples/draw_indexed_indirect_u16_commands.json` | 500 | 0 | 500 | Indexed indirect render path with U16 index format; validates indexed-arg decoding + draw command queueing shape. | pending-draw-indexed-indirect-u16 |
| 17 | draw_indexed_indirect_u32 | B | `draw_indexed_indirect` | directional candidate | `examples/draw_indexed_indirect_u32_commands.json` | 500 | 0 | 500 | Same as #16 with U32 indices to isolate format branch cost. | pending-draw-indexed-indirect-u32 |
| 18 | draw_indirect_legacy_equivalent | C | `draw_indirect` | directional candidate | `examples/draw_indirect_legacy_equivalent_commands.json` | 800 | 0 | 800 | Non-indexed indirect draw proxy aligned to existing render-draw-style workloads. | pending-draw-indirect-legacy |
| 19 | render_pass_loadops_clear_load | A | `render_pass` | comparable candidate | `examples/render_pass_loadops_clear_load_commands.json` | 240 | 0 | 240 | Fixed render pass with clear/load boundary variants; isolate render pass attachment load-op overhead. | pending-render-loadops-clear-load |
| 20 | render_pass_storeops_discard | A | `render_pass` | comparable candidate | `examples/render_pass_storeops_discard_commands.json` | 240 | 0 | 240 | Fixed geometry with store discard/retain toggles to isolate storeOp handling. | pending-render-storeops-discard |
| 21 | render_pass_depth_stencil | B | `render_pass` | directional candidate | `examples/render_pass_depth_stencil_commands.json` | 200 | 0 | 200 | Depth/stencil attachments plus explicit clear order and deterministic depth test config. | pending-render-depth-stencil |
| 22 | render_pass_stencil_ref_sweep | C | `render_pass` | directional candidate | `examples/render_pass_stencil_ref_sweep_commands.json` | 160 | 0 | 160 | Mid-stream stencil-ref transitions inside command stream to stress attachment state propagation and depth/stencil behavior. | pending-render-stencil-ref-sweep |
| 23 | render_pass_multisample_resolve | C | `render_pass` | directional candidate | `examples/render_pass_multisample_resolve_commands.json` | 180 | 0 | 180 | Deterministic MSAA color/depth resolve path with fixed sample count and attachment formats. | pending-render-msaa-resolve |
| 24 | render_pass_dynamic_viewport_scissor | B | `render_pass` | directional candidate | `examples/render_pass_dynamic_viewport_scissor_commands.json` | 250 | 0 | 250 | Frequent viewport/scissor updates under fixed pipeline/bind state to isolate dynamic-state encoding cost. | pending-render-dynamic-viewport-scissor |
| 25 | copy_buffer_to_buffer_4kb | A | `copy_buffer_to_buffer` | comparable candidate | `examples/copy_buffer_to_buffer_4kb_commands.json` | 600 | 0 | 600 | Baseline direct copy path with 4KB ranges and stable usage flags. | pending-copy-b2b-4kb |
| 26 | copy_buffer_to_buffer_overlap | B | `copy_buffer_to_buffer` | directional candidate | `examples/copy_buffer_to_buffer_overlap_commands.json` | 360 | 0 | 360 | Intentional overlapping ranges and controlled bounds cases; keep legality and deterministic outcomes. | pending-copy-b2b-overlap |
| 27 | copy_buffer_to_texture_tight_pitch | B | `copy_buffer_to_texture` | comparable candidate | `examples/copy_buffer_to_texture_tight_pitch_commands.json` | 320 | 0 | 320 | Tight rows-per-row and compact pitch for layout-path validation. | pending-copy-b2t-tight-pitch |
| 28 | copy_texture_to_buffer_padded | B | `copy_texture_to_buffer` | comparable candidate | `examples/copy_texture_to_buffer_padded_commands.json` | 280 | 0 | 280 | Padded `bytesPerRow`/`rowsPerImage` with legal format handling and deterministic geometry. | pending-copy-t2b-padded |
| 29 | copy_texture_to_texture_subresource | B | `copy_texture_to_texture` | directional candidate | `examples/copy_texture_to_texture_subresource_commands.json` | 220 | 0 | 220 | Layered/subresource copy geometry with fixed mip transitions and explicit region coordinates. | pending-copy-t2t-subresource |
| 30 | copy_texture_to_texture_stress_macro | C | `copy_texture_to_texture` | directional candidate | `examples/copy_texture_to_texture_stress_macro_commands.json` | 60 | 0 | 6000 | Macro command includes 100 copies per workload repeat, thus divisor=60×100 for per-copy normalization. | pending-copy-t2t-stress-macro |

Phase roll-up:

- Phase A: 1, 2, 3, 4, 5, 6, 9, 12, 19, 20, 25, 27, 28 (highest comparable readiness with bounded command semantics)
- Phase B: 7, 8, 10, 11, 13, 14, 16, 17, 18, 21, 22, 23, 24, 26, 29
- Phase C: 15, 30

Contract template for each new workload:

- Start with `comparable=false`, `benchmarkClass: directional`, `default:false`.
- Add:
  - `leftTimingDivisor` as per above
  - `comparabilityNotes` with explicit shape parity and timing normalization rationale
  - `dawnFilter` once mapped (`@autodiscover` or explicit filter)
- Add:
  - `comparabilityCandidate` once command-kind/runtime support exists and we need comparability promotion tracking:
  - `enabled: true`
  - `tier: targeted-dawn-parity`
  - `notes: "Promotable once Dawn side has command-shape-equivalent test coverage and execution-shape obligations pass."`

