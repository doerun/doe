#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d12.h>
#include <dxgi1_4.h>
#include "d3d12_bridge.h"

D3D12Handle d3d12_bridge_create_device(void) {
    ID3D12Device* device = NULL;
    HRESULT hr = D3D12CreateDevice(NULL, D3D_FEATURE_LEVEL_11_0, &IID_ID3D12Device, (void**)&device);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)device;
}

void d3d12_bridge_release(D3D12Handle obj) {
    if (obj == NULL) return;
    IUnknown* unk = (IUnknown*)obj;
    unk->lpVtbl->Release(unk);
}

D3D12Handle d3d12_bridge_device_create_command_queue(D3D12Handle device_h) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    D3D12_COMMAND_QUEUE_DESC desc;
    desc.Type     = D3D12_COMMAND_LIST_TYPE_DIRECT;
    desc.Priority = D3D12_COMMAND_QUEUE_PRIORITY_NORMAL;
    desc.Flags    = D3D12_COMMAND_QUEUE_FLAG_NONE;
    desc.NodeMask = 0;
    ID3D12CommandQueue* queue = NULL;
    HRESULT hr = device->lpVtbl->CreateCommandQueue(device, &desc, &IID_ID3D12CommandQueue, (void**)&queue);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)queue;
}

D3D12Handle d3d12_bridge_device_create_fence(D3D12Handle device_h) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12Fence* fence = NULL;
    HRESULT hr = device->lpVtbl->CreateFence(device, 0, D3D12_FENCE_FLAG_NONE, &IID_ID3D12Fence, (void**)&fence);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)fence;
}

D3D12Handle d3d12_bridge_device_create_command_allocator(D3D12Handle device_h) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12CommandAllocator* allocator = NULL;
    HRESULT hr = device->lpVtbl->CreateCommandAllocator(device, D3D12_COMMAND_LIST_TYPE_DIRECT, &IID_ID3D12CommandAllocator, (void**)&allocator);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)allocator;
}

D3D12Handle d3d12_bridge_device_create_command_list(D3D12Handle device_h, D3D12Handle allocator_h) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12CommandAllocator* allocator = (ID3D12CommandAllocator*)allocator_h;
    ID3D12GraphicsCommandList* cmd_list = NULL;
    HRESULT hr = device->lpVtbl->CreateCommandList(device, 0, D3D12_COMMAND_LIST_TYPE_DIRECT, allocator, NULL, &IID_ID3D12GraphicsCommandList, (void**)&cmd_list);
    if (FAILED(hr)) return NULL;
    /* CreateCommandList returns an open list; return it as-is for the caller to record into. */
    return (D3D12Handle)cmd_list;
}

D3D12Handle d3d12_bridge_device_create_buffer(D3D12Handle device_h, size_t size, int heap_type) {
    ID3D12Device* device = (ID3D12Device*)device_h;

    D3D12_HEAP_PROPERTIES heap_props;
    heap_props.Type                 = (heap_type == 2) ? D3D12_HEAP_TYPE_UPLOAD : D3D12_HEAP_TYPE_DEFAULT;
    heap_props.CPUPageProperty      = D3D12_CPU_PAGE_PROPERTY_UNKNOWN;
    heap_props.MemoryPoolPreference = D3D12_MEMORY_POOL_UNKNOWN;
    heap_props.CreationNodeMask     = 1;
    heap_props.VisibleNodeMask      = 1;

    D3D12_RESOURCE_DESC resource_desc;
    resource_desc.Dimension          = D3D12_RESOURCE_DIMENSION_BUFFER;
    resource_desc.Alignment          = 0;
    resource_desc.Width              = (UINT64)size;
    resource_desc.Height             = 1;
    resource_desc.DepthOrArraySize   = 1;
    resource_desc.MipLevels          = 1;
    resource_desc.Format             = DXGI_FORMAT_UNKNOWN;
    resource_desc.SampleDesc.Count   = 1;
    resource_desc.SampleDesc.Quality = 0;
    resource_desc.Layout             = D3D12_TEXTURE_LAYOUT_ROW_MAJOR;
    resource_desc.Flags              = D3D12_RESOURCE_FLAG_NONE;

    D3D12_RESOURCE_STATES initial_state = (heap_type == 2)
        ? D3D12_RESOURCE_STATE_GENERIC_READ
        : D3D12_RESOURCE_STATE_COPY_DEST;

    ID3D12Resource* resource = NULL;
    HRESULT hr = device->lpVtbl->CreateCommittedResource(
        device, &heap_props, D3D12_HEAP_FLAG_NONE,
        &resource_desc, initial_state, NULL,
        &IID_ID3D12Resource, (void**)&resource);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)resource;
}

void d3d12_bridge_command_list_copy_buffer(D3D12Handle cmd_list_h, D3D12Handle dst_h, D3D12Handle src_h, size_t size) {
    ID3D12GraphicsCommandList* cmd_list = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12Resource* dst = (ID3D12Resource*)dst_h;
    ID3D12Resource* src = (ID3D12Resource*)src_h;
    cmd_list->lpVtbl->CopyBufferRegion(cmd_list, dst, 0, src, 0, (UINT64)size);
}

void d3d12_bridge_command_list_close(D3D12Handle cmd_list_h) {
    ID3D12GraphicsCommandList* cmd_list = (ID3D12GraphicsCommandList*)cmd_list_h;
    cmd_list->lpVtbl->Close(cmd_list);
}

void d3d12_bridge_queue_execute_command_list(D3D12Handle queue_h, D3D12Handle cmd_list_h) {
    ID3D12CommandQueue* queue = (ID3D12CommandQueue*)queue_h;
    ID3D12GraphicsCommandList* cmd_list = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12CommandList* lists[1];
    lists[0] = (ID3D12CommandList*)cmd_list;
    queue->lpVtbl->ExecuteCommandLists(queue, 1, lists);
}

void d3d12_bridge_queue_signal(D3D12Handle queue_h, D3D12Handle fence_h, uint64_t value) {
    ID3D12CommandQueue* queue = (ID3D12CommandQueue*)queue_h;
    ID3D12Fence* fence = (ID3D12Fence*)fence_h;
    queue->lpVtbl->Signal(queue, fence, value);
}

void d3d12_bridge_fence_wait(D3D12Handle fence_h, uint64_t value) {
    ID3D12Fence* fence = (ID3D12Fence*)fence_h;
    if (fence->lpVtbl->GetCompletedValue(fence) >= value) return;
    HANDLE event = CreateEventW(NULL, FALSE, FALSE, NULL);
    if (event == NULL) return;
    fence->lpVtbl->SetEventOnCompletion(fence, value, event);
    WaitForSingleObject(event, INFINITE);
    CloseHandle(event);
}

D3D12Handle d3d12_bridge_device_create_root_signature_empty(D3D12Handle device_h) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    D3D12_ROOT_SIGNATURE_DESC desc;
    desc.NumParameters     = 0;
    desc.pParameters       = NULL;
    desc.NumStaticSamplers = 0;
    desc.pStaticSamplers   = NULL;
    desc.Flags             = D3D12_ROOT_SIGNATURE_FLAG_NONE;

    ID3DBlob* blob  = NULL;
    ID3DBlob* error = NULL;
    HRESULT hr = D3D12SerializeRootSignature(&desc, D3D_ROOT_SIGNATURE_VERSION_1, &blob, &error);
    if (error) error->lpVtbl->Release(error);
    if (FAILED(hr) || blob == NULL) return NULL;

    ID3D12RootSignature* root_sig = NULL;
    hr = device->lpVtbl->CreateRootSignature(
        device, 0,
        blob->lpVtbl->GetBufferPointer(blob),
        blob->lpVtbl->GetBufferSize(blob),
        &IID_ID3D12RootSignature, (void**)&root_sig);
    blob->lpVtbl->Release(blob);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)root_sig;
}

D3D12Handle d3d12_bridge_device_create_compute_pipeline(D3D12Handle device_h, D3D12Handle root_sig_h,
                                                         const void* bytecode, size_t bytecode_size) {
    ID3D12Device*         device   = (ID3D12Device*)device_h;
    ID3D12RootSignature*  root_sig = (ID3D12RootSignature*)root_sig_h;

    D3D12_COMPUTE_PIPELINE_STATE_DESC desc;
    memset(&desc, 0, sizeof(desc));
    desc.pRootSignature                = root_sig;
    desc.CS.pShaderBytecode            = bytecode;
    desc.CS.BytecodeLength             = bytecode_size;
    desc.NodeMask                      = 0;
    desc.Flags                         = D3D12_PIPELINE_STATE_FLAG_NONE;

    ID3D12PipelineState* pso = NULL;
    HRESULT hr = device->lpVtbl->CreateComputePipelineState(device, &desc, &IID_ID3D12PipelineState, (void**)&pso);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)pso;
}

void d3d12_bridge_command_list_set_compute_root_signature(D3D12Handle cmd_list_h, D3D12Handle root_sig_h) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12RootSignature* root_sig  = (ID3D12RootSignature*)root_sig_h;
    cmd->lpVtbl->SetComputeRootSignature(cmd, root_sig);
}

void d3d12_bridge_command_list_set_pipeline_state(D3D12Handle cmd_list_h, D3D12Handle pso_h) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12PipelineState* pso       = (ID3D12PipelineState*)pso_h;
    cmd->lpVtbl->SetPipelineState(cmd, pso);
}

void d3d12_bridge_command_list_dispatch(D3D12Handle cmd_list_h, uint32_t x, uint32_t y, uint32_t z) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    cmd->lpVtbl->Dispatch(cmd, x, y, z);
}

int d3d12_bridge_command_allocator_reset(D3D12Handle allocator_h) {
    ID3D12CommandAllocator* alloc = (ID3D12CommandAllocator*)allocator_h;
    return SUCCEEDED(alloc->lpVtbl->Reset(alloc)) ? 0 : -1;
}

int d3d12_bridge_command_list_reset(D3D12Handle cmd_list_h, D3D12Handle allocator_h) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12CommandAllocator* alloc  = (ID3D12CommandAllocator*)allocator_h;
    return SUCCEEDED(cmd->lpVtbl->Reset(cmd, alloc, NULL)) ? 0 : -1;
}
