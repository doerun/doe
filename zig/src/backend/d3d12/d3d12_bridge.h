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
