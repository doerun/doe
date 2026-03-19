#pragma once
#include <stddef.h>
#include <stdint.h>

typedef void* D3D12Handle;

typedef struct {
    uint32_t format;
    uint32_t input_slot;
    uint32_t aligned_byte_offset;
    uint32_t semantic_index;
    uint32_t input_slot_class;
    uint32_t instance_data_step_rate;
} D3D12InputElementDesc;

typedef struct {
    uint32_t target_format;
    uint32_t depth_stencil_format;
    uint32_t sample_count;
    uint32_t topology;
    uint32_t topology_type;
    uint32_t front_face;
    uint32_t cull_mode;
    uint32_t blend_enabled;
    uint32_t color_operation;
    uint32_t color_src_factor;
    uint32_t color_dst_factor;
    uint32_t alpha_operation;
    uint32_t alpha_src_factor;
    uint32_t alpha_dst_factor;
    uint32_t color_write_mask;
    uint32_t depth_compare;
    uint32_t depth_write_enabled;
    uint32_t stencil_front_compare;
    uint32_t stencil_front_fail_op;
    uint32_t stencil_front_depth_fail_op;
    uint32_t stencil_front_pass_op;
    uint32_t stencil_back_compare;
    uint32_t stencil_back_fail_op;
    uint32_t stencil_back_depth_fail_op;
    uint32_t stencil_back_pass_op;
    uint32_t stencil_read_mask;
    uint32_t stencil_write_mask;
    int32_t depth_bias;
    float depth_bias_slope_scale;
    float depth_bias_clamp;
    uint32_t unclipped_depth;
} D3D12GraphicsPipelineDesc;

/* Device and core objects */
D3D12Handle d3d12_bridge_create_device(void);
void        d3d12_bridge_release(D3D12Handle obj);

D3D12Handle d3d12_bridge_device_create_command_queue(D3D12Handle device);
D3D12Handle d3d12_bridge_device_create_fence(D3D12Handle device);
D3D12Handle d3d12_bridge_device_create_command_allocator(D3D12Handle device);
/* Returns an open (recording) command list. Caller must call close when done. */
D3D12Handle d3d12_bridge_device_create_command_list(D3D12Handle device, D3D12Handle allocator);
/* heap_type: 1 = DEFAULT (GPU-local), 2 = UPLOAD (CPU-visible), 3 = READBACK (CPU-readable) */
D3D12Handle d3d12_bridge_device_create_buffer(D3D12Handle device, size_t size, int heap_type);
uint64_t    d3d12_bridge_buffer_get_size(D3D12Handle buffer);

/* Buffer copy */
void d3d12_bridge_command_list_copy_buffer(D3D12Handle cmd_list, D3D12Handle dst, D3D12Handle src, size_t size);
void d3d12_bridge_command_list_close(D3D12Handle cmd_list);

/* Queue execution and synchronization */
void d3d12_bridge_queue_execute_command_list(D3D12Handle queue, D3D12Handle cmd_list);
void d3d12_bridge_queue_signal(D3D12Handle queue, D3D12Handle fence, uint64_t value);
void d3d12_bridge_fence_wait(D3D12Handle fence, uint64_t value);

/* Compute pipeline support */
D3D12Handle d3d12_bridge_device_create_root_signature_empty(D3D12Handle device);
D3D12Handle d3d12_bridge_device_create_compute_pipeline(D3D12Handle device, D3D12Handle root_sig, const void* bytecode, size_t bytecode_size);
void d3d12_bridge_command_list_set_compute_root_signature(D3D12Handle cmd_list, D3D12Handle root_sig);
void d3d12_bridge_command_list_set_pipeline_state(D3D12Handle cmd_list, D3D12Handle pipeline);
void d3d12_bridge_command_list_dispatch(D3D12Handle cmd_list, uint32_t x, uint32_t y, uint32_t z);
/* Reset an allocator so its command list can be re-recorded. */
int d3d12_bridge_command_allocator_reset(D3D12Handle allocator);
int d3d12_bridge_command_list_reset(D3D12Handle cmd_list, D3D12Handle allocator);

/* Texture support */
D3D12Handle d3d12_bridge_device_create_texture_2d(D3D12Handle device, uint32_t width, uint32_t height,
                                                    uint32_t mip_levels, uint32_t format, uint32_t usage_flags);
void d3d12_bridge_command_list_copy_texture_region(D3D12Handle cmd_list, D3D12Handle dst_texture,
                                                     D3D12Handle src_buffer, uint64_t src_offset,
                                                     uint32_t width, uint32_t height, uint32_t bytes_per_row,
                                                     uint32_t format);

/* Resource barrier */
void d3d12_bridge_command_list_resource_barrier_transition(D3D12Handle cmd_list, D3D12Handle resource,
                                                            int state_before, int state_after);

/* Sampler descriptor heap */
D3D12Handle d3d12_bridge_device_create_sampler_heap(D3D12Handle device, uint32_t num_descriptors);

/* RTV descriptor heap and render target views */
D3D12Handle d3d12_bridge_device_create_rtv_heap(D3D12Handle device, uint32_t num_descriptors);
void d3d12_bridge_device_create_rtv(D3D12Handle device, D3D12Handle resource, D3D12Handle rtv_heap,
                                     uint32_t index, uint32_t format);

/* Graphics pipeline */
D3D12Handle d3d12_bridge_device_create_graphics_pipeline(D3D12Handle device, D3D12Handle root_sig,
                                                           const void* vs_bytecode, size_t vs_size,
                                                           const void* ps_bytecode, size_t ps_size,
                                                           uint32_t target_format);
D3D12Handle d3d12_bridge_device_create_graphics_pipeline_hlsl(
    D3D12Handle device,
    D3D12Handle root_sig,
    const char* vs_source,
    size_t vs_source_len,
    const char* vs_entry,
    const char* ps_source,
    size_t ps_source_len,
    const char* ps_entry,
    const D3D12GraphicsPipelineDesc* desc,
    const D3D12InputElementDesc* input_elements,
    uint32_t input_element_count);

/* Render commands */
void d3d12_bridge_command_list_set_graphics_root_signature(D3D12Handle cmd_list, D3D12Handle root_sig);
void d3d12_bridge_command_list_set_render_target(D3D12Handle cmd_list, D3D12Handle rtv_heap, uint32_t index);
void d3d12_bridge_command_list_set_render_targets(
    D3D12Handle cmd_list,
    D3D12Handle rtv_heap,
    uint32_t rtv_index,
    D3D12Handle dsv_heap,
    uint32_t dsv_index);
void d3d12_bridge_command_list_set_viewport(D3D12Handle cmd_list, float x, float y, float w, float h,
                                             float min_depth, float max_depth);
void d3d12_bridge_command_list_set_scissor(D3D12Handle cmd_list, int32_t left, int32_t top,
                                            int32_t right, int32_t bottom);
void d3d12_bridge_command_list_ia_set_primitive_topology(D3D12Handle cmd_list, int topology);
void d3d12_bridge_command_list_set_blend_factor(D3D12Handle cmd_list, const float rgba[4]);
void d3d12_bridge_command_list_set_stencil_ref(D3D12Handle cmd_list, uint32_t reference);
void d3d12_bridge_command_list_draw_instanced(D3D12Handle cmd_list, uint32_t vertex_count,
                                               uint32_t instance_count, uint32_t start_vertex,
                                               uint32_t start_instance);
void d3d12_bridge_command_list_draw_indexed_instanced(D3D12Handle cmd_list, uint32_t index_count,
                                                       uint32_t instance_count, uint32_t start_index,
                                                       int32_t base_vertex, uint32_t start_instance);

/* Vertex/index buffer binding for render bundles */
void d3d12_bridge_command_list_ia_set_vertex_buffers(D3D12Handle cmd_list, uint32_t start_slot,
                                                      uint32_t num_views, D3D12Handle buffer,
                                                      uint32_t size_in_bytes, uint32_t stride_in_bytes,
                                                      uint64_t offset);
void d3d12_bridge_command_list_ia_set_index_buffer(D3D12Handle cmd_list, D3D12Handle buffer,
                                                    uint32_t format, uint32_t size_in_bytes,
                                                    uint64_t offset);

/* Indirect execution */
D3D12Handle d3d12_bridge_device_create_command_signature_dispatch(D3D12Handle device, D3D12Handle root_sig);
D3D12Handle d3d12_bridge_device_create_command_signature_draw(D3D12Handle device, D3D12Handle root_sig);
D3D12Handle d3d12_bridge_device_create_command_signature_draw_indexed(D3D12Handle device, D3D12Handle root_sig);
void d3d12_bridge_command_list_execute_indirect(D3D12Handle cmd_list, D3D12Handle command_sig,
                                                 uint32_t max_count, D3D12Handle arg_buffer,
                                                 uint64_t arg_offset);

/* Timestamp queries */
D3D12Handle d3d12_bridge_device_create_timestamp_query_heap(D3D12Handle device, uint32_t count);
void d3d12_bridge_command_list_end_query(D3D12Handle cmd_list, D3D12Handle query_heap, uint32_t index);
void d3d12_bridge_command_list_resolve_query_data(D3D12Handle cmd_list, D3D12Handle query_heap,
                                                    uint32_t start_index, uint32_t count,
                                                    D3D12Handle dst_buffer, uint64_t dst_offset);
uint64_t d3d12_bridge_queue_get_timestamp_frequency(D3D12Handle queue);

/* Map/Unmap for readback */
void* d3d12_bridge_resource_map(D3D12Handle resource);
void  d3d12_bridge_resource_unmap(D3D12Handle resource);

/* Device info / adapter queries */
void d3d12_bridge_device_get_adapter_desc(D3D12Handle device, char* desc_out, size_t desc_size,
                                           uint32_t* vendor_id_out, uint32_t* device_id_out,
                                           uint64_t* dedicated_vram_out);

/* Depth/stencil views */
D3D12Handle d3d12_bridge_device_create_dsv_heap(D3D12Handle device, uint32_t num_descriptors);
void d3d12_bridge_device_create_dsv(D3D12Handle device, D3D12Handle resource, D3D12Handle dsv_heap,
                                     uint32_t index, uint32_t format);
D3D12Handle d3d12_bridge_device_create_depth_texture(D3D12Handle device, uint32_t width,
                                                       uint32_t height, uint32_t format);

/* CBV/SRV/UAV descriptor heap */
D3D12Handle d3d12_bridge_device_create_cbv_srv_uav_heap(D3D12Handle device, uint32_t num_descriptors);
void d3d12_bridge_device_create_cbv(D3D12Handle device, D3D12Handle heap, uint32_t index,
                                     D3D12Handle buffer, uint64_t offset, uint32_t size);
void d3d12_bridge_device_create_srv_buffer(D3D12Handle device, D3D12Handle heap, uint32_t index,
                                            D3D12Handle buffer, uint32_t num_elements, uint32_t stride);
void d3d12_bridge_device_create_uav_buffer(D3D12Handle device, D3D12Handle heap, uint32_t index,
                                            D3D12Handle buffer, uint32_t num_elements, uint32_t stride);
void d3d12_bridge_device_create_srv_texture(D3D12Handle device, D3D12Handle heap, uint32_t index,
                                             D3D12Handle texture, uint32_t format);
void d3d12_bridge_device_create_srv_texture_2d(D3D12Handle device, D3D12Handle resource,
                                                D3D12Handle heap, uint32_t index, uint32_t format,
                                                uint32_t aspect, uint32_t base_mip, uint32_t mip_count);
void d3d12_bridge_device_create_srv_texture_cube(D3D12Handle device, D3D12Handle resource,
                                                  D3D12Handle heap, uint32_t index, uint32_t format,
                                                  uint32_t aspect, uint32_t base_mip, uint32_t mip_count);
void d3d12_bridge_device_create_srv_texture_3d(D3D12Handle device, D3D12Handle resource,
                                                D3D12Handle heap, uint32_t index, uint32_t format,
                                                uint32_t aspect, uint32_t base_mip, uint32_t mip_count);
void d3d12_bridge_device_create_uav_texture_2d(D3D12Handle device, D3D12Handle resource,
                                                D3D12Handle heap, uint32_t index, uint32_t format,
                                                uint32_t mip_slice);
void d3d12_bridge_command_list_set_descriptor_heaps(D3D12Handle cmd_list,
                                                     D3D12Handle cbv_srv_uav_heap,
                                                     D3D12Handle sampler_heap);

/* Descriptor range for root signature tables — must match Zig DescriptorRangeDesc layout */
typedef struct {
    uint32_t range_type;
    uint32_t num_descriptors;
    uint32_t base_shader_register;
    uint32_t register_space;
} D3D12DescriptorRangeDesc;

/* Root signature with descriptor table parameters (simple count-based, single register space) */
D3D12Handle d3d12_bridge_device_create_root_signature_with_ranges(D3D12Handle device,
                                                                    uint32_t num_cbv, uint32_t num_srv,
                                                                    uint32_t num_uav, uint32_t num_samplers);

/* Root signature from explicit range array (multi-space, used by Zig descriptor module) */
D3D12Handle d3d12_bridge_device_create_root_signature_with_tables(D3D12Handle device,
                                                                     const D3D12DescriptorRangeDesc* ranges,
                                                                     uint32_t range_count, uint32_t flags);

/* Compute/graphics root descriptor table binding */
void d3d12_bridge_command_list_set_compute_root_descriptor_table(D3D12Handle cmd_list,
                                                                   uint32_t root_parameter_index,
                                                                   D3D12Handle heap,
                                                                   uint32_t base_descriptor_index);
void d3d12_bridge_command_list_set_graphics_root_descriptor_table(D3D12Handle cmd_list,
                                                                    uint32_t root_parameter_index,
                                                                    D3D12Handle heap,
                                                                    uint32_t base_descriptor_index);

/* Occlusion and pipeline statistics queries */
D3D12Handle d3d12_bridge_device_create_occlusion_query_heap(D3D12Handle device, uint32_t count);
D3D12Handle d3d12_bridge_device_create_pipeline_statistics_query_heap(D3D12Handle device, uint32_t count);
void d3d12_bridge_command_list_begin_query(D3D12Handle cmd_list, D3D12Handle query_heap, uint32_t index);

/* 3D texture */
D3D12Handle d3d12_bridge_device_create_texture_3d(D3D12Handle device, uint32_t width, uint32_t height,
                                                    uint32_t depth, uint32_t mip_levels,
                                                    uint32_t format, uint32_t usage_flags);

/* Hardware capability queries for runtime feature detection.
 * TODO: On actual Windows hardware these should query:
 *   - D3D12_FEATURE_DATA_D3D12_OPTIONS1 for WaveLaneCountMin/WaveLaneCountMax
 *   - D3D12_FEATURE_DATA_SHADER_MODEL for HighestShaderModel
 *   - D3D12_FEATURE_DATA_D3D12_OPTIONS4 for Native16BitShaderOpsSupported
 * Currently returns conservative defaults for cross-compilation. */
int  d3d12_bridge_device_get_shader_model(D3D12Handle device);
int  d3d12_bridge_device_get_wave_lane_count_min(D3D12Handle device);
int  d3d12_bridge_device_get_wave_lane_count_max(D3D12Handle device);
int  d3d12_bridge_device_supports_native_16bit(D3D12Handle device);

/* DXGI swap chain (surface) */
D3D12Handle d3d12_bridge_create_swap_chain(D3D12Handle queue, uint32_t width, uint32_t height, uint32_t format, uint32_t alpha_mode, uint32_t tone_mapping_mode);
int  d3d12_bridge_swap_chain_present(D3D12Handle swap_chain, uint32_t sync_interval);
D3D12Handle d3d12_bridge_swap_chain_get_buffer(D3D12Handle swap_chain, uint32_t index);
int  d3d12_bridge_swap_chain_resize(D3D12Handle swap_chain, uint32_t width, uint32_t height, uint32_t format);
