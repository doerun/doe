#pragma once
#include <stddef.h>
#include <stdint.h>

typedef void* D3D12Handle;

D3D12Handle d3d12_bridge_create_device(void);
void        d3d12_bridge_release(D3D12Handle obj);

D3D12Handle d3d12_bridge_device_create_command_queue(D3D12Handle device);
D3D12Handle d3d12_bridge_device_create_fence(D3D12Handle device);
D3D12Handle d3d12_bridge_device_create_command_allocator(D3D12Handle device);
/* Returns an open (recording) command list. Caller must call close when done. */
D3D12Handle d3d12_bridge_device_create_command_list(D3D12Handle device, D3D12Handle allocator);
/* heap_type: 1 = DEFAULT (GPU-local), 2 = UPLOAD (CPU-visible) */
D3D12Handle d3d12_bridge_device_create_buffer(D3D12Handle device, size_t size, int heap_type);

void d3d12_bridge_command_list_copy_buffer(D3D12Handle cmd_list, D3D12Handle dst, D3D12Handle src, size_t size);
void d3d12_bridge_command_list_close(D3D12Handle cmd_list);

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
