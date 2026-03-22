/* d3d12_bridge_stubs.c — No-op D3D12 bridge for non-Windows platforms.
 *
 * The D3D12 Zig backend is compiled on all platforms but the real bridge
 * is only available on Windows. These stubs allow the exe and test targets
 * to link on macOS/Linux without silent capability fallback: the D3D12
 * backend will initialise to error.Unsupported at runtime, and no GPU work
 * is performed through this path. */

#include <stddef.h>
#include <stdint.h>
#include "d3d12_bridge.h"

/* Device and core objects */
D3D12Handle d3d12_bridge_create_device(void) { return NULL; }
void        d3d12_bridge_release(D3D12Handle obj) { (void)obj; }

D3D12Handle d3d12_bridge_device_create_command_queue(D3D12Handle device) { (void)device; return NULL; }
D3D12Handle d3d12_bridge_device_create_fence(D3D12Handle device) { (void)device; return NULL; }
D3D12Handle d3d12_bridge_device_create_command_allocator(D3D12Handle device) { (void)device; return NULL; }
D3D12Handle d3d12_bridge_device_create_command_list(D3D12Handle device, D3D12Handle allocator) { (void)device; (void)allocator; return NULL; }
D3D12Handle d3d12_bridge_device_create_buffer(D3D12Handle device, size_t size, int heap_type) { (void)device; (void)size; (void)heap_type; return NULL; }
uint64_t    d3d12_bridge_buffer_get_size(D3D12Handle buffer) { (void)buffer; return 0; }

/* Buffer copy */
void d3d12_bridge_command_list_copy_buffer(D3D12Handle cmd_list, D3D12Handle dst, D3D12Handle src, size_t size) { (void)cmd_list; (void)dst; (void)src; (void)size; }
void d3d12_bridge_command_list_close(D3D12Handle cmd_list) { (void)cmd_list; }

/* Queue execution and synchronization */
void d3d12_bridge_queue_execute_command_list(D3D12Handle queue, D3D12Handle cmd_list) { (void)queue; (void)cmd_list; }
void d3d12_bridge_queue_signal(D3D12Handle queue, D3D12Handle fence, uint64_t value) { (void)queue; (void)fence; (void)value; }
void d3d12_bridge_fence_wait(D3D12Handle fence, uint64_t value) { (void)fence; (void)value; }

/* Compute pipeline support */
D3D12Handle d3d12_bridge_device_create_root_signature_empty(D3D12Handle device) { (void)device; return NULL; }
D3D12Handle d3d12_bridge_device_create_compute_pipeline(D3D12Handle device, D3D12Handle root_sig, const void* bytecode, size_t bytecode_size) { (void)device; (void)root_sig; (void)bytecode; (void)bytecode_size; return NULL; }
void d3d12_bridge_command_list_set_compute_root_signature(D3D12Handle cmd_list, D3D12Handle root_sig) { (void)cmd_list; (void)root_sig; }
void d3d12_bridge_command_list_set_pipeline_state(D3D12Handle cmd_list, D3D12Handle pipeline) { (void)cmd_list; (void)pipeline; }
void d3d12_bridge_command_list_dispatch(D3D12Handle cmd_list, uint32_t x, uint32_t y, uint32_t z) { (void)cmd_list; (void)x; (void)y; (void)z; }
int d3d12_bridge_command_allocator_reset(D3D12Handle allocator) { (void)allocator; return -1; }
int d3d12_bridge_command_list_reset(D3D12Handle cmd_list, D3D12Handle allocator) { (void)cmd_list; (void)allocator; return -1; }

/* Texture support */
D3D12Handle d3d12_bridge_device_create_texture_2d(D3D12Handle device, uint32_t width, uint32_t height, uint32_t mip_levels, uint32_t format, uint32_t usage_flags) { (void)device; (void)width; (void)height; (void)mip_levels; (void)format; (void)usage_flags; return NULL; }
D3D12Handle d3d12_bridge_device_create_texture_2d_layered(D3D12Handle device, uint32_t width, uint32_t height, uint32_t array_layers, uint32_t mip_levels, uint32_t sample_count, uint32_t format, uint32_t usage_flags) { (void)device; (void)width; (void)height; (void)array_layers; (void)mip_levels; (void)sample_count; (void)format; (void)usage_flags; return NULL; }
D3D12Handle d3d12_bridge_device_create_texture_3d(D3D12Handle device, uint32_t width, uint32_t height, uint32_t depth, uint32_t mip_levels, uint32_t format, uint32_t usage_flags) { (void)device; (void)width; (void)height; (void)depth; (void)mip_levels; (void)format; (void)usage_flags; return NULL; }
D3D12Handle d3d12_bridge_texture_create_view(D3D12Handle texture, uint32_t format, uint32_t dimension, uint32_t aspect, uint32_t base_mip, uint32_t mip_count, uint32_t base_array_layer, uint32_t array_layer_count, uint64_t usage_flags) { (void)texture; (void)format; (void)dimension; (void)aspect; (void)base_mip; (void)mip_count; (void)base_array_layer; (void)array_layer_count; (void)usage_flags; return NULL; }
D3D12Handle d3d12_bridge_texture_create_view_swizzled(D3D12Handle texture, uint32_t format, uint32_t dimension, uint32_t aspect, uint32_t base_mip, uint32_t mip_count, uint32_t base_array_layer, uint32_t array_layer_count, uint64_t usage_flags, uint32_t swizzle_r, uint32_t swizzle_g, uint32_t swizzle_b, uint32_t swizzle_a) { (void)texture; (void)format; (void)dimension; (void)aspect; (void)base_mip; (void)mip_count; (void)base_array_layer; (void)array_layer_count; (void)usage_flags; (void)swizzle_r; (void)swizzle_g; (void)swizzle_b; (void)swizzle_a; return NULL; }
void d3d12_bridge_command_list_copy_texture_region(D3D12Handle cmd_list, D3D12Handle dst_texture, D3D12Handle src_buffer, uint64_t src_offset, uint32_t width, uint32_t height, uint32_t bytes_per_row, uint32_t format) { (void)cmd_list; (void)dst_texture; (void)src_buffer; (void)src_offset; (void)width; (void)height; (void)bytes_per_row; (void)format; }
void d3d12_bridge_command_list_copy_texture_region_subresource(D3D12Handle cmd_list, D3D12Handle dst_texture, uint32_t subresource_index, D3D12Handle src_buffer, uint64_t src_offset, uint32_t width, uint32_t height, uint32_t depth, uint32_t bytes_per_row, uint32_t format) { (void)cmd_list; (void)dst_texture; (void)subresource_index; (void)src_buffer; (void)src_offset; (void)width; (void)height; (void)depth; (void)bytes_per_row; (void)format; }

/* Resource barrier */
void d3d12_bridge_command_list_resource_barrier_transition(D3D12Handle cmd_list, D3D12Handle resource, int state_before, int state_after) { (void)cmd_list; (void)resource; (void)state_before; (void)state_after; }
void d3d12_bridge_command_list_resolve_subresource(D3D12Handle cmd_list, D3D12Handle dst_texture, uint32_t dst_subresource, D3D12Handle src_texture, uint32_t src_subresource, uint32_t format) { (void)cmd_list; (void)dst_texture; (void)dst_subresource; (void)src_texture; (void)src_subresource; (void)format; }

/* Sampler descriptor heap */
D3D12Handle d3d12_bridge_device_create_sampler_heap(D3D12Handle device, uint32_t num_descriptors) { (void)device; (void)num_descriptors; return NULL; }
D3D12Handle d3d12_bridge_device_create_sampler(D3D12Handle device, uint32_t min_filter, uint32_t mag_filter, uint32_t mipmap_filter, uint32_t address_mode_u, uint32_t address_mode_v, uint32_t address_mode_w, float lod_min_clamp, float lod_max_clamp, uint32_t compare, uint16_t max_anisotropy) { (void)device; (void)min_filter; (void)mag_filter; (void)mipmap_filter; (void)address_mode_u; (void)address_mode_v; (void)address_mode_w; (void)lod_min_clamp; (void)lod_max_clamp; (void)compare; (void)max_anisotropy; return NULL; }

/* RTV descriptor heap and render target views */
D3D12Handle d3d12_bridge_device_create_rtv_heap(D3D12Handle device, uint32_t num_descriptors) { (void)device; (void)num_descriptors; return NULL; }
void d3d12_bridge_device_create_rtv(D3D12Handle device, D3D12Handle resource, D3D12Handle rtv_heap, uint32_t index, uint32_t format) { (void)device; (void)resource; (void)rtv_heap; (void)index; (void)format; }
void d3d12_bridge_device_create_rtv_view(D3D12Handle device, D3D12Handle resource, D3D12Handle rtv_heap, uint32_t index, uint32_t format, uint32_t dimension, uint32_t base_mip_level, uint32_t base_array_layer, uint32_t array_layer_count, uint32_t depth_slice) { (void)device; (void)resource; (void)rtv_heap; (void)index; (void)format; (void)dimension; (void)base_mip_level; (void)base_array_layer; (void)array_layer_count; (void)depth_slice; }

/* Graphics pipeline */
D3D12Handle d3d12_bridge_device_create_graphics_pipeline(D3D12Handle device, D3D12Handle root_sig, const void* vs_bytecode, size_t vs_size, const void* ps_bytecode, size_t ps_size, uint32_t target_format) { (void)device; (void)root_sig; (void)vs_bytecode; (void)vs_size; (void)ps_bytecode; (void)ps_size; (void)target_format; return NULL; }
D3D12Handle d3d12_bridge_device_create_graphics_pipeline_hlsl(D3D12Handle device, D3D12Handle root_sig, const char* vs_source, size_t vs_source_len, const char* vs_entry, const char* ps_source, size_t ps_source_len, const char* ps_entry, const D3D12GraphicsPipelineDesc* desc, const D3D12InputElementDesc* input_elements, uint32_t input_element_count) { (void)device; (void)root_sig; (void)vs_source; (void)vs_source_len; (void)vs_entry; (void)ps_source; (void)ps_source_len; (void)ps_entry; (void)desc; (void)input_elements; (void)input_element_count; return NULL; }

/* Render commands */
void d3d12_bridge_command_list_set_graphics_root_signature(D3D12Handle cmd_list, D3D12Handle root_sig) { (void)cmd_list; (void)root_sig; }
void d3d12_bridge_command_list_set_render_target(D3D12Handle cmd_list, D3D12Handle rtv_heap, uint32_t index) { (void)cmd_list; (void)rtv_heap; (void)index; }
void d3d12_bridge_command_list_set_render_targets(D3D12Handle cmd_list, D3D12Handle rtv_heap, uint32_t rtv_index, D3D12Handle dsv_heap, uint32_t dsv_index) { (void)cmd_list; (void)rtv_heap; (void)rtv_index; (void)dsv_heap; (void)dsv_index; }
void d3d12_bridge_command_list_set_viewport(D3D12Handle cmd_list, float x, float y, float w, float h, float min_depth, float max_depth) { (void)cmd_list; (void)x; (void)y; (void)w; (void)h; (void)min_depth; (void)max_depth; }
void d3d12_bridge_command_list_set_scissor(D3D12Handle cmd_list, int32_t left, int32_t top, int32_t right, int32_t bottom) { (void)cmd_list; (void)left; (void)top; (void)right; (void)bottom; }
void d3d12_bridge_command_list_ia_set_primitive_topology(D3D12Handle cmd_list, int topology) { (void)cmd_list; (void)topology; }
void d3d12_bridge_command_list_set_blend_factor(D3D12Handle cmd_list, const float rgba[4]) { (void)cmd_list; (void)rgba; }
void d3d12_bridge_command_list_set_stencil_ref(D3D12Handle cmd_list, uint32_t reference) { (void)cmd_list; (void)reference; }
void d3d12_bridge_command_list_draw_instanced(D3D12Handle cmd_list, uint32_t vertex_count, uint32_t instance_count, uint32_t start_vertex, uint32_t start_instance) { (void)cmd_list; (void)vertex_count; (void)instance_count; (void)start_vertex; (void)start_instance; }
void d3d12_bridge_command_list_draw_indexed_instanced(D3D12Handle cmd_list, uint32_t index_count, uint32_t instance_count, uint32_t start_index, int32_t base_vertex, uint32_t start_instance) { (void)cmd_list; (void)index_count; (void)instance_count; (void)start_index; (void)base_vertex; (void)start_instance; }

/* Vertex/index buffer binding */
void d3d12_bridge_command_list_ia_set_vertex_buffers(D3D12Handle cmd_list, uint32_t start_slot, uint32_t num_views, D3D12Handle buffer, uint32_t size_in_bytes, uint32_t stride_in_bytes, uint64_t offset) { (void)cmd_list; (void)start_slot; (void)num_views; (void)buffer; (void)size_in_bytes; (void)stride_in_bytes; (void)offset; }
void d3d12_bridge_command_list_ia_set_index_buffer(D3D12Handle cmd_list, D3D12Handle buffer, uint32_t format, uint32_t size_in_bytes, uint64_t offset) { (void)cmd_list; (void)buffer; (void)format; (void)size_in_bytes; (void)offset; }

/* Indirect execution */
D3D12Handle d3d12_bridge_device_create_command_signature_dispatch(D3D12Handle device, D3D12Handle root_sig) { (void)device; (void)root_sig; return NULL; }
D3D12Handle d3d12_bridge_device_create_command_signature_draw(D3D12Handle device, D3D12Handle root_sig) { (void)device; (void)root_sig; return NULL; }
D3D12Handle d3d12_bridge_device_create_command_signature_draw_indexed(D3D12Handle device, D3D12Handle root_sig) { (void)device; (void)root_sig; return NULL; }
void d3d12_bridge_command_list_execute_indirect(D3D12Handle cmd_list, D3D12Handle command_sig, uint32_t max_count, D3D12Handle arg_buffer, uint64_t arg_offset) { (void)cmd_list; (void)command_sig; (void)max_count; (void)arg_buffer; (void)arg_offset; }

/* Timestamp queries */
D3D12Handle d3d12_bridge_device_create_timestamp_query_heap(D3D12Handle device, uint32_t count) { (void)device; (void)count; return NULL; }
void d3d12_bridge_command_list_end_query(D3D12Handle cmd_list, D3D12Handle query_heap, uint32_t index) { (void)cmd_list; (void)query_heap; (void)index; }
void d3d12_bridge_command_list_resolve_query_data(D3D12Handle cmd_list, D3D12Handle query_heap, uint32_t start_index, uint32_t count, D3D12Handle dst_buffer, uint64_t dst_offset) { (void)cmd_list; (void)query_heap; (void)start_index; (void)count; (void)dst_buffer; (void)dst_offset; }
uint64_t d3d12_bridge_queue_get_timestamp_frequency(D3D12Handle queue) { (void)queue; return 0; }

/* Map/Unmap for readback */
void* d3d12_bridge_resource_map(D3D12Handle resource) { (void)resource; return NULL; }
void  d3d12_bridge_resource_unmap(D3D12Handle resource) { (void)resource; }

/* Device info / adapter queries */
void d3d12_bridge_device_get_adapter_desc(D3D12Handle device, char* desc_out, size_t desc_size, uint32_t* vendor_id_out, uint32_t* device_id_out, uint64_t* dedicated_vram_out) { (void)device; if (desc_out && desc_size > 0) desc_out[0] = '\0'; if (vendor_id_out) *vendor_id_out = 0; if (device_id_out) *device_id_out = 0; if (dedicated_vram_out) *dedicated_vram_out = 0; }

/* Depth/stencil views */
D3D12Handle d3d12_bridge_device_create_dsv_heap(D3D12Handle device, uint32_t num_descriptors) { (void)device; (void)num_descriptors; return NULL; }
void d3d12_bridge_device_create_dsv(D3D12Handle device, D3D12Handle resource, D3D12Handle dsv_heap, uint32_t index, uint32_t format) { (void)device; (void)resource; (void)dsv_heap; (void)index; (void)format; }
void d3d12_bridge_device_create_dsv_view(D3D12Handle device, D3D12Handle resource, D3D12Handle dsv_heap, uint32_t index, uint32_t format, uint32_t dimension, uint32_t base_mip_level, uint32_t base_array_layer, uint32_t array_layer_count, uint32_t read_only_depth, uint32_t read_only_stencil) { (void)device; (void)resource; (void)dsv_heap; (void)index; (void)format; (void)dimension; (void)base_mip_level; (void)base_array_layer; (void)array_layer_count; (void)read_only_depth; (void)read_only_stencil; }
D3D12Handle d3d12_bridge_device_create_depth_texture(D3D12Handle device, uint32_t width, uint32_t height, uint32_t format) { (void)device; (void)width; (void)height; (void)format; return NULL; }

/* CBV/SRV/UAV descriptor heap */
D3D12Handle d3d12_bridge_device_create_cbv_srv_uav_heap(D3D12Handle device, uint32_t num_descriptors) { (void)device; (void)num_descriptors; return NULL; }
void d3d12_bridge_device_create_cbv(D3D12Handle device, D3D12Handle heap, uint32_t index, D3D12Handle buffer, uint64_t offset, uint32_t size) { (void)device; (void)heap; (void)index; (void)buffer; (void)offset; (void)size; }
void d3d12_bridge_device_create_srv_buffer(D3D12Handle device, D3D12Handle heap, uint32_t index, D3D12Handle buffer, uint32_t num_elements, uint32_t stride) { (void)device; (void)heap; (void)index; (void)buffer; (void)num_elements; (void)stride; }
void d3d12_bridge_device_create_uav_buffer(D3D12Handle device, D3D12Handle heap, uint32_t index, D3D12Handle buffer, uint32_t num_elements, uint32_t stride) { (void)device; (void)heap; (void)index; (void)buffer; (void)num_elements; (void)stride; }
void d3d12_bridge_device_create_srv_texture(D3D12Handle device, D3D12Handle heap, uint32_t index, D3D12Handle texture, uint32_t format) { (void)device; (void)heap; (void)index; (void)texture; (void)format; }
void d3d12_bridge_device_create_srv_texture_2d(D3D12Handle device, D3D12Handle resource, D3D12Handle heap, uint32_t index, uint32_t format, uint32_t aspect, uint32_t base_mip, uint32_t mip_count, uint32_t base_array_layer, uint32_t array_layer_count) { (void)device; (void)resource; (void)heap; (void)index; (void)format; (void)aspect; (void)base_mip; (void)mip_count; (void)base_array_layer; (void)array_layer_count; }
void d3d12_bridge_device_create_srv_texture_cube(D3D12Handle device, D3D12Handle resource, D3D12Handle heap, uint32_t index, uint32_t format, uint32_t aspect, uint32_t base_mip, uint32_t mip_count, uint32_t base_array_layer, uint32_t array_layer_count) { (void)device; (void)resource; (void)heap; (void)index; (void)format; (void)aspect; (void)base_mip; (void)mip_count; (void)base_array_layer; (void)array_layer_count; }
void d3d12_bridge_device_create_srv_texture_3d(D3D12Handle device, D3D12Handle resource, D3D12Handle heap, uint32_t index, uint32_t format, uint32_t aspect, uint32_t base_mip, uint32_t mip_count) { (void)device; (void)resource; (void)heap; (void)index; (void)format; (void)aspect; (void)base_mip; (void)mip_count; }
void d3d12_bridge_device_create_uav_texture_2d(D3D12Handle device, D3D12Handle resource, D3D12Handle heap, uint32_t index, uint32_t format, uint32_t mip_slice) { (void)device; (void)resource; (void)heap; (void)index; (void)format; (void)mip_slice; }
void d3d12_bridge_command_list_set_descriptor_heaps(D3D12Handle cmd_list, D3D12Handle cbv_srv_uav_heap, D3D12Handle sampler_heap) { (void)cmd_list; (void)cbv_srv_uav_heap; (void)sampler_heap; }

/* Root signature */
D3D12Handle d3d12_bridge_device_create_root_signature_with_ranges(D3D12Handle device, uint32_t num_cbv, uint32_t num_srv, uint32_t num_uav, uint32_t num_samplers) { (void)device; (void)num_cbv; (void)num_srv; (void)num_uav; (void)num_samplers; return NULL; }
D3D12Handle d3d12_bridge_device_create_root_signature_with_tables(D3D12Handle device, const D3D12DescriptorRangeDesc* ranges, uint32_t range_count, uint32_t flags) { (void)device; (void)ranges; (void)range_count; (void)flags; return NULL; }

/* Compute/graphics root descriptor table binding */
void d3d12_bridge_command_list_set_compute_root_descriptor_table(D3D12Handle cmd_list, uint32_t root_parameter_index, D3D12Handle heap, uint32_t base_descriptor_index) { (void)cmd_list; (void)root_parameter_index; (void)heap; (void)base_descriptor_index; }
void d3d12_bridge_command_list_set_graphics_root_descriptor_table(D3D12Handle cmd_list, uint32_t root_parameter_index, D3D12Handle heap, uint32_t base_descriptor_index) { (void)cmd_list; (void)root_parameter_index; (void)heap; (void)base_descriptor_index; }

/* Occlusion and pipeline statistics queries */
D3D12Handle d3d12_bridge_device_create_occlusion_query_heap(D3D12Handle device, uint32_t count) { (void)device; (void)count; return NULL; }
D3D12Handle d3d12_bridge_device_create_pipeline_statistics_query_heap(D3D12Handle device, uint32_t count) { (void)device; (void)count; return NULL; }
void d3d12_bridge_command_list_begin_query(D3D12Handle cmd_list, D3D12Handle query_heap, uint32_t index) { (void)cmd_list; (void)query_heap; (void)index; }

/* Hardware capability queries */
int  d3d12_bridge_device_get_shader_model(D3D12Handle device) { (void)device; return -1; }
int  d3d12_bridge_device_get_wave_lane_count_min(D3D12Handle device) { (void)device; return -1; }
int  d3d12_bridge_device_get_wave_lane_count_max(D3D12Handle device) { (void)device; return -1; }
int  d3d12_bridge_device_supports_native_16bit(D3D12Handle device) { (void)device; return 0; }
int  d3d12_bridge_device_supports_color_attachment_blend(D3D12Handle device, uint32_t format) { (void)device; (void)format; return 0; }
int  d3d12_bridge_device_supports_storage_binding(D3D12Handle device, uint32_t format) { (void)device; (void)format; return 0; }
int  d3d12_bridge_device_supports_storage_read_write(D3D12Handle device, uint32_t format) { (void)device; (void)format; return 0; }
int  d3d12_bridge_device_supports_render_target(D3D12Handle device, uint32_t format) { (void)device; (void)format; return 0; }
int  d3d12_bridge_device_supports_texture_component_swizzle(D3D12Handle device) { (void)device; return 0; }
int  d3d12_bridge_device_supports_bc_sliced_3d(D3D12Handle device) { (void)device; return 0; }

/* Write sampler into existing heap at index */
void d3d12_bridge_device_create_sampler_in_heap(D3D12Handle device, D3D12Handle sampler_heap, uint32_t heap_index, uint32_t min_filter, uint32_t mag_filter, uint32_t mipmap_filter, uint32_t address_mode_u, uint32_t address_mode_v, uint32_t address_mode_w, float lod_min_clamp, float lod_max_clamp, uint32_t compare, uint16_t max_anisotropy) { (void)device; (void)sampler_heap; (void)heap_index; (void)min_filter; (void)mag_filter; (void)mipmap_filter; (void)address_mode_u; (void)address_mode_v; (void)address_mode_w; (void)lod_min_clamp; (void)lod_max_clamp; (void)compare; (void)max_anisotropy; }
void d3d12_bridge_command_list_set_graphics_root_sampler_table(D3D12Handle cmd_list, uint32_t root_parameter_index, D3D12Handle sampler_heap, uint32_t base_descriptor_index) { (void)cmd_list; (void)root_parameter_index; (void)sampler_heap; (void)base_descriptor_index; }

/* DXGI swap chain */
D3D12Handle d3d12_bridge_create_swap_chain(D3D12Handle queue, uint32_t width, uint32_t height, uint32_t format, uint32_t alpha_mode, uint32_t tone_mapping_mode) { (void)queue; (void)width; (void)height; (void)format; (void)alpha_mode; (void)tone_mapping_mode; return NULL; }
int  d3d12_bridge_swap_chain_present(D3D12Handle swap_chain, uint32_t sync_interval) { (void)swap_chain; (void)sync_interval; return -1; }
D3D12Handle d3d12_bridge_swap_chain_get_buffer(D3D12Handle swap_chain, uint32_t index) { (void)swap_chain; (void)index; return NULL; }
int  d3d12_bridge_swap_chain_resize(D3D12Handle swap_chain, uint32_t width, uint32_t height, uint32_t format) { (void)swap_chain; (void)width; (void)height; (void)format; return -1; }
