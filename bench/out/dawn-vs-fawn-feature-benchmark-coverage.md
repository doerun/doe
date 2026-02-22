# Dawn vs Fawn Feature + Benchmark Coverage

- generatedFrom: `config/webgpu-spec-coverage.json` + `bench/workloads.amd.vulkan.extended.json` + `bench/dawn_workload_map.amd.extended.json`
- totals: implemented=22, partial=0, planned=0

| Capability | Status | Priority | Fawn Contract | Benchmark Workloads | Dawn Baseline Filter(s) |
|---|---|---|---|---|---|
| `queue_sync_mode` | `implemented` | `p0` | zig/src/main.zig --queue-sync-mode, zig/src/webgpu_ffi.zig QueueSyncMode | n/a | n/a |
| `render_draw_offsets` | `implemented` | `p0` | zig/src/model.zig RenderDrawCommand first_vertex/first_instance | n/a | n/a |
| `render_draw_indexed` | `implemented` | `p0` | RenderDrawCommand index_data/index_format/index_count/first_index/base_vertex + native DrawIndexed lowering | n/a | n/a |
| `render_core_api_surface` | `implemented` | `p0` | zig/src/wgpu_types.zig Procs + zig/src/wgpu_loader.zig loadProcs + zig/src/wgpu_render_commands.zig executeRe… | n/a | n/a |
| `render_pass_state_bindings` | `implemented` | `p0` | zig/src/wgpu_render_api.zig + zig/src/wgpu_render_commands.zig render-pass state setup | n/a | n/a |
| `render_draw_encode_modes` | `implemented` | `p0` | RenderDrawCommand encode_mode + zig/src/wgpu_render_commands.zig encode branch | n/a | n/a |
| `textured_render_workload_contract` | `implemented` | `p0` | zig/src/wgpu_render_resources.zig + zig/src/wgpu_texture_procs.zig + zig/src/wgpu_render_assets.zig | n/a | n/a |
| `render_bundle_execution` | `implemented` | `p0` | zig/src/wgpu_render_api.zig + zig/src/wgpu_render_commands.zig bundle encode/finish/execute | n/a | n/a |
| `surface_presentation` | `implemented` | `p1` | zig/src/wgpu_surface_procs.zig + zig/src/webgpu_ffi.zig surface methods | n/a | n/a |
| `async_pipeline_diagnostics` | `implemented` | `p1` | zig/src/wgpu_async_procs.zig + zig/src/wgpu_render_commands.zig async pipeline path | n/a | n/a |
| `render_pass_state_space` | `implemented` | `p1` | render_draw pipelineMode/bindGroupMode + target format contract | n/a | n/a |
| `timestamp_query_claimability` | `implemented` | `p1` | executionGpuTimestampTotalNs + executionGpuTimestampAttemptedCount + executionGpuTimestampValidCount trace-me… | n/a | n/a |
| `texture_query_assertions` | `implemented` | `p1` | TextureQueryCommand expected_* fields + native texture query validation | n/a | n/a |
| `p1_capability_introspection_surface` | `implemented` | `p1` | zig/src/wgpu_p1_capability_procs.zig + zig/src/wgpu_capability_runtime.zig + zig/src/webgpu_ffi.zig | `p1_capability_introspection_contract`, `p1_capability_introspection_macro_500` | `ShaderRobustnessPerf.Run/*` |
| `p1_resource_table_immediates_surface` | `implemented` | `p1` | zig/src/wgpu_p1_resource_table_procs.zig + zig/src/wgpu_async_diagnostics_command.zig | `p1_resource_table_immediates_contract`, `p1_resource_table_immediates_macro_500` | `DrawCallPerf.Run/*` |
| `p2_lifecycle_addref_surface` | `implemented` | `p2` | zig/src/wgpu_p2_lifecycle_procs.zig + zig/src/wgpu_async_diagnostics_command.zig + zig/src/wgpu_capability_ru… | `p2_lifecycle_refcount_contract`, `p2_lifecycle_refcount_macro_200` | `DrawCallPerf.Run/*` |
| `p0_buffer_destroy_and_barrier_clear` | `implemented` | `p0` | zig/src/wgpu_p0_procs.zig + zig/src/wgpu_resources.zig + zig/src/wgpu_commands.zig barrier lowering | `p0_resource_lifecycle_contract` | `BufferUploadPerf.Run/*WriteBuffer_BufferSize_4MB` |
| `p0_compute_indirect_async_timestamp` | `implemented` | `p0` | zig/src/wgpu_p0_procs.zig + zig/src/wgpu_resources.zig + zig/src/wgpu_commands.zig | `p0_compute_indirect_timestamp_contract` | `WorkgroupAtomicPerf.Run/*WorkgroupUsageType_WorkgroupTypeAtomic` |
| `p0_query_set_introspection_lifecycle` | `implemented` | `p0` | zig/src/wgpu_p0_procs.zig querySetMatches + destroyQuerySet; compute/render query setup paths | `p0_compute_indirect_timestamp_contract`, `p0_render_multidraw_contract`, `p0_render_multidraw_indexed_contract` | `WorkgroupAtomicPerf.Run/*WorkgroupUsageType_WorkgroupTypeAtomic`<br>`DrawCallPerf.Run/*`<br>`DrawCallPerf.Run/*DynamicVertexBuffer` |
| `p0_render_occlusion_multidraw_timestamp` | `implemented` | `p0` | zig/src/wgpu_render_api.zig + zig/src/wgpu_render_p0.zig + zig/src/wgpu_render_commands.zig + zig/src/webgpu_… | `p0_render_multidraw_contract`, `p0_render_multidraw_indexed_contract` | `DrawCallPerf.Run/*`<br>`DrawCallPerf.Run/*DynamicVertexBuffer` |
| `p0_device_destroy_lifecycle` | `implemented` | `p0` | zig/src/webgpu_ffi.zig deinit | `p0_resource_lifecycle_contract` | `BufferUploadPerf.Run/*WriteBuffer_BufferSize_4MB` |
| `p0_render_pixel_local_storage_barrier` | `implemented` | `p1` | zig/src/wgpu_p0_procs.zig + zig/src/wgpu_render_api.zig + zig/src/wgpu_render_types.zig + zig/src/wgpu_resour… | `p0_render_pixel_local_storage_barrier_contract`, `p0_render_pixel_local_storage_barrier_macro_500` | `DrawCallPerf.Run/*` |
