#pragma once
#include <stddef.h>
#include <stdint.h>

typedef void* D3D12Handle;

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

/* Render commands */
void d3d12_bridge_command_list_set_graphics_root_signature(D3D12Handle cmd_list, D3D12Handle root_sig);
void d3d12_bridge_command_list_set_render_target(D3D12Handle cmd_list, D3D12Handle rtv_heap, uint32_t index);
void d3d12_bridge_command_list_set_viewport(D3D12Handle cmd_list, float x, float y, float w, float h,
                                             float min_depth, float max_depth);
void d3d12_bridge_command_list_set_scissor(D3D12Handle cmd_list, int32_t left, int32_t top,
                                            int32_t right, int32_t bottom);
void d3d12_bridge_command_list_ia_set_primitive_topology(D3D12Handle cmd_list, int topology);
void d3d12_bridge_command_list_draw_instanced(D3D12Handle cmd_list, uint32_t vertex_count,
                                               uint32_t instance_count, uint32_t start_vertex,
                                               uint32_t start_instance);
void d3d12_bridge_command_list_draw_indexed_instanced(D3D12Handle cmd_list, uint32_t index_count,
                                                       uint32_t instance_count, uint32_t start_index,
                                                       int32_t base_vertex, uint32_t start_instance);

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

/* DXGI swap chain (surface) */
D3D12Handle d3d12_bridge_create_swap_chain(D3D12Handle queue, uint32_t width, uint32_t height, uint32_t format);
int  d3d12_bridge_swap_chain_present(D3D12Handle swap_chain, uint32_t sync_interval);
D3D12Handle d3d12_bridge_swap_chain_get_buffer(D3D12Handle swap_chain, uint32_t index);
int  d3d12_bridge_swap_chain_resize(D3D12Handle swap_chain, uint32_t width, uint32_t height, uint32_t format);
