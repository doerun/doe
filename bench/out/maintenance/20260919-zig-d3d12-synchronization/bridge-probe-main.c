int main(void) {
    reset(); signal_failures = 1;
    assert(d3d12_bridge_queue_signal_checked(&queue, &fence, 7) == D3D12_SYNC_FAILED);
    assert(fence.completed == 0);
    reset(); wait_failure = 1;
    assert(d3d12_bridge_fence_wait_checked(&fence, 7) == D3D12_SYNC_FAILED);
    assert(wait_calls == 1 && fence.completed == 0);
    reset(); fence.completed = UINT64_MAX;
    assert(d3d12_bridge_fence_wait_checked(&fence, 7) == D3D12_SYNC_DEVICE_LOST);
    assert(wait_calls == 0);
    reset(); device_lost = 1;
    assert(d3d12_bridge_queue_signal_checked(&queue, &fence, 7) == D3D12_SYNC_DEVICE_LOST);
    reset(); device_lost = 1;
    assert(d3d12_bridge_fence_wait_checked(&fence, 7) == D3D12_SYNC_DEVICE_LOST);
    reset(); fence.completed = 7;
    assert(d3d12_bridge_fence_wait_checked(&fence, 7) == D3D12_SYNC_OK);
    assert(wait_calls == 0);
    reset(); signal_failures = 2; reset_failures = 2; delayed_completion = 1; wait_failure = 1;
    assert(d3d12_bridge_queue_drain(&device, &queue, &fence) == D3D12_SYNC_OK);
    assert(signal_calls == 3 && reset_calls == 3 && wait_calls == 1 && sleeps == 5);
    assert(fence.completed == 1);
    /* Reuse resets a private completed fence; an old marker cannot satisfy this drain. */
    queued_value = 0; sleeps = 0;
    assert(d3d12_bridge_queue_drain(&device, &queue, &fence) == D3D12_SYNC_OK);
    assert(sleeps == 1 && reset_calls == 4 && fence.completed == 1);
    reset(); device_lost = 1;
    assert(d3d12_bridge_queue_drain(&device, &queue, &fence) == D3D12_SYNC_DEVICE_LOST);
    assert(signal_calls == 0 && reset_calls == 0 && wait_calls == 0);
    reset(); delayed_completion = 1; lose_during_wait = 1;
    assert(d3d12_bridge_queue_drain(&device, &queue, &fence) == D3D12_SYNC_DEVICE_LOST);
    assert(wait_calls == 1 && fence.completed == UINT64_MAX);
    puts("PASS: actual bridge synchronization bodies; injected COM outcomes, no Windows/GPU execution");
    return 0;
}
