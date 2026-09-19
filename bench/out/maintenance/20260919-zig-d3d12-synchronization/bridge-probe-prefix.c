#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include "d3d12_bridge.h"
typedef uint32_t DWORD;
typedef uint64_t UINT64;
typedef int32_t HRESULT;
#define FAILED(value) ((value) < 0)
#define SUCCEEDED(value) ((value) >= 0)
typedef struct ID3D12Fence ID3D12Fence;
typedef struct ID3D12CommandQueue ID3D12CommandQueue;
typedef struct ID3D12Device ID3D12Device;
typedef struct {
    UINT64 (*GetCompletedValue)(ID3D12Fence*);
    HRESULT (*SetEventOnCompletion)(ID3D12Fence*, UINT64, void*);
    HRESULT (*Signal)(ID3D12Fence*, UINT64);
} FenceMethods;
typedef struct { HRESULT (*Signal)(ID3D12CommandQueue*, ID3D12Fence*, UINT64); } QueueMethods;
typedef struct { HRESULT (*GetDeviceRemovedReason)(ID3D12Device*); } DeviceMethods;
struct ID3D12Fence { FenceMethods* lpVtbl; UINT64 completed; };
struct ID3D12CommandQueue { QueueMethods* lpVtbl; };
struct ID3D12Device { DeviceMethods* lpVtbl; };
static int signal_failures, wait_failure, reset_failures, device_lost, lose_during_wait;
static int signal_calls, wait_calls, reset_calls, sleeps, delayed_completion;
static UINT64 queued_value;
static ID3D12Fence* active_fence;
static void Sleep(DWORD milliseconds) {
    assert(milliseconds > 0);
    assert(++sleeps < 20); /* A failing probe cannot hang the test runner. */
    if (delayed_completion && queued_value) active_fence->completed = queued_value;
}
static UINT64 completed(ID3D12Fence* fence) { return fence->completed; }
static HRESULT wait_for_event(ID3D12Fence* fence, UINT64 value, void* event) {
    assert(event == NULL);
    wait_calls++;
    if (device_lost || lose_during_wait) { fence->completed = UINT64_MAX; return -1; }
    if (wait_failure) return -1;
    fence->completed = value;
    return 0;
}
static HRESULT signal_queue(ID3D12CommandQueue* queue, ID3D12Fence* fence, UINT64 value) {
    (void)queue;
    signal_calls++;
    if (device_lost) { fence->completed = UINT64_MAX; return -1; }
    if (signal_failures-- > 0) return -1;
    queued_value = value;
    if (!delayed_completion) fence->completed = value;
    return 0;
}
static HRESULT signal_cpu(ID3D12Fence* fence, UINT64 value) {
    reset_calls++;
    if (reset_failures-- > 0) return -1;
    fence->completed = value;
    return 0;
}
static HRESULT removed(ID3D12Device* device) { (void)device; return device_lost ? -1 : 0; }
static FenceMethods fence_methods = { completed, wait_for_event, signal_cpu };
static QueueMethods queue_methods = { signal_queue };
static DeviceMethods device_methods = { removed };
static ID3D12Fence fence = { &fence_methods, 0 };
static ID3D12CommandQueue queue = { &queue_methods };
static ID3D12Device device = { &device_methods };
static void reset(void) {
    signal_failures = wait_failure = reset_failures = device_lost = lose_during_wait = 0;
    signal_calls = wait_calls = reset_calls = sleeps = delayed_completion = 0;
    queued_value = 0;
    fence.completed = 0;
    active_fence = &fence;
}
