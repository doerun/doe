static HRESULT clock_result = 0;
static UINT64 clock_frequency = 1000;
static HRESULT map_result = 0;
static unsigned unmap_calls = 0;
static uint64_t ticks[2] = {100, 130};
static HRESULT get_frequency(ID3D12CommandQueue* queue, UINT64* frequency) {
    assert(queue != NULL);
    *frequency = clock_frequency;
    return clock_result;
}
static HRESULT map(ID3D12Resource* resource, unsigned index, const D3D12_RANGE* range, void** data) {
    assert(resource != NULL && index == 0);
    assert(range != NULL && range->Begin == 0 && range->End == sizeof(ticks));
    *data = ticks;
    return map_result;
}
static void unmap(ID3D12Resource* resource, unsigned index, const D3D12_RANGE* range) {
    assert(resource != NULL && index == 0);
    assert(range != NULL && range->Begin == 0 && range->End == 0);
    unmap_calls++;
}
int main(void) {
    const QueueVtbl queue_vtable = {get_frequency};
    ID3D12CommandQueue queue = {&queue_vtable};
    uint64_t frequency = 999;
    assert(d3d12_bridge_queue_get_timestamp_frequency_checked(&queue, &frequency) == D3D12_SYNC_OK);
    assert(frequency == clock_frequency);
    clock_result = -1;
    assert(d3d12_bridge_queue_get_timestamp_frequency_checked(&queue, &frequency) == D3D12_SYNC_FAILED);
    assert(frequency == 0);
    clock_result = DXGI_ERROR_DEVICE_REMOVED;
    assert(d3d12_bridge_queue_get_timestamp_frequency_checked(&queue, &frequency) == D3D12_SYNC_DEVICE_LOST);
    assert(frequency == 0);
    clock_result = DXGI_ERROR_DEVICE_RESET;
    assert(d3d12_bridge_queue_get_timestamp_frequency_checked(&queue, &frequency) == D3D12_SYNC_DEVICE_LOST);
    clock_result = 0;
    clock_frequency = 0;
    assert(d3d12_bridge_queue_get_timestamp_frequency_checked(&queue, &frequency) == D3D12_SYNC_FAILED);
    assert(d3d12_bridge_queue_get_timestamp_frequency(&queue) == 0);
    const ResourceVtbl resource_vtable = {map, unmap};
    ID3D12Resource resource = {&resource_vtable};
    assert(d3d12_bridge_resource_map_read(&resource, sizeof(ticks)) == ticks);
    d3d12_bridge_resource_unmap_read(&resource);
    assert(unmap_calls == 1);
    map_result = -1;
    assert(d3d12_bridge_resource_map_read(&resource, sizeof(ticks)) == NULL);
    puts("PASS: clock outcomes preserve unavailable values; read mapping declares reads and no writes");
    return 0;
}
