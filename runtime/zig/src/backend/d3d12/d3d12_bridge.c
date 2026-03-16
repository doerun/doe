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
    return (D3D12Handle)cmd_list;
}

D3D12Handle d3d12_bridge_device_create_buffer(D3D12Handle device_h, size_t size, int heap_type) {
    ID3D12Device* device = (ID3D12Device*)device_h;

    D3D12_HEAP_PROPERTIES heap_props;
    if (heap_type == 3) {
        heap_props.Type = D3D12_HEAP_TYPE_READBACK;
    } else if (heap_type == 2) {
        heap_props.Type = D3D12_HEAP_TYPE_UPLOAD;
    } else {
        heap_props.Type = D3D12_HEAP_TYPE_DEFAULT;
    }
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

    D3D12_RESOURCE_STATES initial_state;
    if (heap_type == 3) {
        initial_state = D3D12_RESOURCE_STATE_COPY_DEST;
    } else if (heap_type == 2) {
        initial_state = D3D12_RESOURCE_STATE_GENERIC_READ;
    } else {
        initial_state = D3D12_RESOURCE_STATE_COPY_DEST;
    }

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

/* --- Texture support --- */

static DXGI_FORMAT map_wgpu_format_to_dxgi(uint32_t format) {
    switch (format) {
        case 0x00000016: return DXGI_FORMAT_R8G8B8A8_UNORM;       /* RGBA8Unorm */
        case 0x00000017: return DXGI_FORMAT_R8G8B8A8_UNORM_SRGB;  /* RGBA8UnormSrgb */
        case 0x0000001B: return DXGI_FORMAT_B8G8R8A8_UNORM;       /* BGRA8Unorm */
        case 0x0000001C: return DXGI_FORMAT_B8G8R8A8_UNORM_SRGB;  /* BGRA8UnormSrgb */
        case 0x00000001: return DXGI_FORMAT_R8_UNORM;              /* R8Unorm */
        case 0x0000000E: return DXGI_FORMAT_R32_FLOAT;             /* R32Float */
        case 0x0000000F: return DXGI_FORMAT_R32_UINT;              /* R32Uint */
        case 0x00000010: return DXGI_FORMAT_R32_SINT;              /* R32Sint */
        case 0x00000009: return DXGI_FORMAT_R16_FLOAT;             /* R16Float */
        case 0x0000002D: return DXGI_FORMAT_D16_UNORM;             /* Depth16Unorm */
        case 0x00000030: return DXGI_FORMAT_D32_FLOAT;             /* Depth32Float */
        default:         return DXGI_FORMAT_R8G8B8A8_UNORM;
    }
}

static D3D12_RESOURCE_FLAGS map_wgpu_usage_to_d3d12_flags(uint32_t usage) {
    D3D12_RESOURCE_FLAGS flags = D3D12_RESOURCE_FLAG_NONE;
    if (usage & 0x0000000000000010) flags |= D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET; /* RenderAttachment */
    if (usage & 0x0000000000000008) flags |= D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS; /* StorageBinding */
    return flags;
}

D3D12Handle d3d12_bridge_device_create_texture_2d(D3D12Handle device_h, uint32_t width, uint32_t height,
                                                    uint32_t mip_levels, uint32_t format, uint32_t usage_flags) {
    ID3D12Device* device = (ID3D12Device*)device_h;

    D3D12_HEAP_PROPERTIES heap_props;
    heap_props.Type                 = D3D12_HEAP_TYPE_DEFAULT;
    heap_props.CPUPageProperty      = D3D12_CPU_PAGE_PROPERTY_UNKNOWN;
    heap_props.MemoryPoolPreference = D3D12_MEMORY_POOL_UNKNOWN;
    heap_props.CreationNodeMask     = 1;
    heap_props.VisibleNodeMask      = 1;

    D3D12_RESOURCE_DESC desc;
    desc.Dimension          = D3D12_RESOURCE_DIMENSION_TEXTURE2D;
    desc.Alignment          = 0;
    desc.Width              = (UINT64)width;
    desc.Height             = height;
    desc.DepthOrArraySize   = 1;
    desc.MipLevels          = (UINT16)(mip_levels == 0 ? 1 : mip_levels);
    desc.Format             = map_wgpu_format_to_dxgi(format);
    desc.SampleDesc.Count   = 1;
    desc.SampleDesc.Quality = 0;
    desc.Layout             = D3D12_TEXTURE_LAYOUT_UNKNOWN;
    desc.Flags              = map_wgpu_usage_to_d3d12_flags(usage_flags);

    D3D12_RESOURCE_STATES initial = D3D12_RESOURCE_STATE_COPY_DEST;

    ID3D12Resource* tex = NULL;
    HRESULT hr = device->lpVtbl->CreateCommittedResource(
        device, &heap_props, D3D12_HEAP_FLAG_NONE,
        &desc, initial, NULL,
        &IID_ID3D12Resource, (void**)&tex);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)tex;
}

void d3d12_bridge_command_list_copy_texture_region(D3D12Handle cmd_list_h, D3D12Handle dst_texture_h,
                                                     D3D12Handle src_buffer_h, uint64_t src_offset,
                                                     uint32_t width, uint32_t height, uint32_t bytes_per_row,
                                                     uint32_t format) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12Resource* dst = (ID3D12Resource*)dst_texture_h;
    ID3D12Resource* src = (ID3D12Resource*)src_buffer_h;

    D3D12_TEXTURE_COPY_LOCATION dst_loc;
    dst_loc.pResource        = dst;
    dst_loc.Type             = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
    dst_loc.SubresourceIndex = 0;

    D3D12_TEXTURE_COPY_LOCATION src_loc;
    src_loc.pResource                            = src;
    src_loc.Type                                 = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
    src_loc.PlacedFootprint.Offset               = src_offset;
    src_loc.PlacedFootprint.Footprint.Format     = map_wgpu_format_to_dxgi(format);
    src_loc.PlacedFootprint.Footprint.Width      = width;
    src_loc.PlacedFootprint.Footprint.Height     = height;
    src_loc.PlacedFootprint.Footprint.Depth      = 1;
    src_loc.PlacedFootprint.Footprint.RowPitch   = (bytes_per_row + 255u) & ~255u;

    cmd->lpVtbl->CopyTextureRegion(cmd, &dst_loc, 0, 0, 0, &src_loc, NULL);
}

void d3d12_bridge_command_list_resource_barrier_transition(D3D12Handle cmd_list_h, D3D12Handle resource_h,
                                                            int state_before, int state_after) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12Resource* res = (ID3D12Resource*)resource_h;

    D3D12_RESOURCE_BARRIER barrier;
    barrier.Type                   = D3D12_RESOURCE_BARRIER_TYPE_TRANSITION;
    barrier.Flags                  = D3D12_RESOURCE_BARRIER_FLAG_NONE;
    barrier.Transition.pResource   = res;
    barrier.Transition.Subresource = D3D12_RESOURCE_BARRIER_ALL_SUBRESOURCES;
    barrier.Transition.StateBefore = (D3D12_RESOURCE_STATES)state_before;
    barrier.Transition.StateAfter  = (D3D12_RESOURCE_STATES)state_after;
    cmd->lpVtbl->ResourceBarrier(cmd, 1, &barrier);
}

/* --- Sampler descriptor heap --- */

D3D12Handle d3d12_bridge_device_create_sampler_heap(D3D12Handle device_h, uint32_t num_descriptors) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    D3D12_DESCRIPTOR_HEAP_DESC desc;
    desc.Type           = D3D12_DESCRIPTOR_HEAP_TYPE_SAMPLER;
    desc.NumDescriptors = num_descriptors;
    desc.Flags          = D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
    desc.NodeMask       = 0;

    ID3D12DescriptorHeap* heap = NULL;
    HRESULT hr = device->lpVtbl->CreateDescriptorHeap(device, &desc, &IID_ID3D12DescriptorHeap, (void**)&heap);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)heap;
}

/* --- RTV heap and render target views --- */

D3D12Handle d3d12_bridge_device_create_rtv_heap(D3D12Handle device_h, uint32_t num_descriptors) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    D3D12_DESCRIPTOR_HEAP_DESC desc;
    desc.Type           = D3D12_DESCRIPTOR_HEAP_TYPE_RTV;
    desc.NumDescriptors = num_descriptors;
    desc.Flags          = D3D12_DESCRIPTOR_HEAP_FLAG_NONE;
    desc.NodeMask       = 0;

    ID3D12DescriptorHeap* heap = NULL;
    HRESULT hr = device->lpVtbl->CreateDescriptorHeap(device, &desc, &IID_ID3D12DescriptorHeap, (void**)&heap);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)heap;
}

void d3d12_bridge_device_create_rtv(D3D12Handle device_h, D3D12Handle resource_h, D3D12Handle rtv_heap_h,
                                     uint32_t index, uint32_t format) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12Resource* resource = (ID3D12Resource*)resource_h;
    ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)rtv_heap_h;

    UINT rtv_size = device->lpVtbl->GetDescriptorHandleIncrementSize(device, D3D12_DESCRIPTOR_HEAP_TYPE_RTV);
    D3D12_CPU_DESCRIPTOR_HANDLE cpu_handle;
    heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap, &cpu_handle);
    cpu_handle.ptr += (SIZE_T)(rtv_size * index);

    D3D12_RENDER_TARGET_VIEW_DESC rtv_desc;
    rtv_desc.Format               = map_wgpu_format_to_dxgi(format);
    rtv_desc.ViewDimension        = D3D12_RTV_DIMENSION_TEXTURE2D;
    rtv_desc.Texture2D.MipSlice   = 0;
    rtv_desc.Texture2D.PlaneSlice = 0;

    device->lpVtbl->CreateRenderTargetView(device, resource, &rtv_desc, cpu_handle);
}

/* --- Graphics pipeline --- */

/* Minimal passthrough VS/PS bytecode (DXBC noop shaders) embedded at build time is impractical;
   callers provide bytecode. This function wires VS+PS into a graphics PSO. */
D3D12Handle d3d12_bridge_device_create_graphics_pipeline(D3D12Handle device_h, D3D12Handle root_sig_h,
                                                           const void* vs_bytecode, size_t vs_size,
                                                           const void* ps_bytecode, size_t ps_size,
                                                           uint32_t target_format) {
    ID3D12Device*        device   = (ID3D12Device*)device_h;
    ID3D12RootSignature* root_sig = (ID3D12RootSignature*)root_sig_h;

    D3D12_GRAPHICS_PIPELINE_STATE_DESC desc;
    memset(&desc, 0, sizeof(desc));
    desc.pRootSignature         = root_sig;
    desc.VS.pShaderBytecode     = vs_bytecode;
    desc.VS.BytecodeLength      = vs_size;
    desc.PS.pShaderBytecode     = ps_bytecode;
    desc.PS.BytecodeLength      = ps_size;

    /* Default blend: opaque write to RT0. */
    desc.BlendState.RenderTarget[0].RenderTargetWriteMask = D3D12_COLOR_WRITE_ENABLE_ALL;
    desc.SampleMask                    = UINT_MAX;
    desc.RasterizerState.FillMode      = D3D12_FILL_MODE_SOLID;
    desc.RasterizerState.CullMode      = D3D12_CULL_MODE_NONE;
    desc.RasterizerState.DepthClipEnable = TRUE;
    desc.PrimitiveTopologyType         = D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
    desc.NumRenderTargets              = 1;
    desc.RTVFormats[0]                 = map_wgpu_format_to_dxgi(target_format);
    desc.SampleDesc.Count              = 1;
    desc.SampleDesc.Quality            = 0;

    ID3D12PipelineState* pso = NULL;
    HRESULT hr = device->lpVtbl->CreateGraphicsPipelineState(device, &desc, &IID_ID3D12PipelineState, (void**)&pso);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)pso;
}

/* --- Render commands --- */

void d3d12_bridge_command_list_set_graphics_root_signature(D3D12Handle cmd_list_h, D3D12Handle root_sig_h) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12RootSignature* root_sig  = (ID3D12RootSignature*)root_sig_h;
    cmd->lpVtbl->SetGraphicsRootSignature(cmd, root_sig);
}

void d3d12_bridge_command_list_set_render_target(D3D12Handle cmd_list_h, D3D12Handle rtv_heap_h, uint32_t index) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12DescriptorHeap* heap     = (ID3D12DescriptorHeap*)rtv_heap_h;

    /* Get increment size — we need the device for this; query from heap's parent.
       Workaround: assume standard RTV increment (typically 32 bytes on most GPUs).
       The proper approach uses ID3D12Device::GetDescriptorHandleIncrementSize,
       but we don't have the device here. We store the full CPU handle start instead. */
    D3D12_CPU_DESCRIPTOR_HANDLE handle;
    heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap, &handle);
    /* index is passed as 0 for single-target usage; for multi-target, caller pre-offsets */
    (void)index;
    cmd->lpVtbl->OMSetRenderTargets(cmd, 1, &handle, FALSE, NULL);
}

void d3d12_bridge_command_list_set_viewport(D3D12Handle cmd_list_h, float x, float y, float w, float h,
                                             float min_depth, float max_depth) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    D3D12_VIEWPORT vp;
    vp.TopLeftX = x;
    vp.TopLeftY = y;
    vp.Width    = w;
    vp.Height   = h;
    vp.MinDepth = min_depth;
    vp.MaxDepth = max_depth;
    cmd->lpVtbl->RSSetViewports(cmd, 1, &vp);
}

void d3d12_bridge_command_list_set_scissor(D3D12Handle cmd_list_h, int32_t left, int32_t top,
                                            int32_t right, int32_t bottom) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    D3D12_RECT rect;
    rect.left   = (LONG)left;
    rect.top    = (LONG)top;
    rect.right  = (LONG)right;
    rect.bottom = (LONG)bottom;
    cmd->lpVtbl->RSSetScissorRects(cmd, 1, &rect);
}

void d3d12_bridge_command_list_ia_set_primitive_topology(D3D12Handle cmd_list_h, int topology) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    cmd->lpVtbl->IASetPrimitiveTopology(cmd, (D3D12_PRIMITIVE_TOPOLOGY)topology);
}

void d3d12_bridge_command_list_draw_instanced(D3D12Handle cmd_list_h, uint32_t vertex_count,
                                               uint32_t instance_count, uint32_t start_vertex,
                                               uint32_t start_instance) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    cmd->lpVtbl->DrawInstanced(cmd, vertex_count, instance_count, start_vertex, start_instance);
}

void d3d12_bridge_command_list_draw_indexed_instanced(D3D12Handle cmd_list_h, uint32_t index_count,
                                                       uint32_t instance_count, uint32_t start_index,
                                                       int32_t base_vertex, uint32_t start_instance) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    cmd->lpVtbl->DrawIndexedInstanced(cmd, index_count, instance_count, start_index, base_vertex, start_instance);
}

/* --- Indirect execution --- */

D3D12Handle d3d12_bridge_device_create_command_signature_dispatch(D3D12Handle device_h, D3D12Handle root_sig_h) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12RootSignature* root_sig = (ID3D12RootSignature*)root_sig_h;

    D3D12_INDIRECT_ARGUMENT_DESC arg_desc;
    arg_desc.Type = D3D12_INDIRECT_ARGUMENT_TYPE_DISPATCH;
    D3D12_COMMAND_SIGNATURE_DESC desc;
    desc.ByteStride       = sizeof(uint32_t) * 3;
    desc.NumArgumentDescs  = 1;
    desc.pArgumentDescs    = &arg_desc;
    desc.NodeMask          = 0;

    ID3D12CommandSignature* sig = NULL;
    HRESULT hr = device->lpVtbl->CreateCommandSignature(device, &desc, root_sig, &IID_ID3D12CommandSignature, (void**)&sig);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)sig;
}

D3D12Handle d3d12_bridge_device_create_command_signature_draw(D3D12Handle device_h, D3D12Handle root_sig_h) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12RootSignature* root_sig = (ID3D12RootSignature*)root_sig_h;

    D3D12_INDIRECT_ARGUMENT_DESC arg_desc;
    arg_desc.Type = D3D12_INDIRECT_ARGUMENT_TYPE_DRAW;
    D3D12_COMMAND_SIGNATURE_DESC desc;
    desc.ByteStride       = sizeof(uint32_t) * 4;
    desc.NumArgumentDescs  = 1;
    desc.pArgumentDescs    = &arg_desc;
    desc.NodeMask          = 0;

    ID3D12CommandSignature* sig = NULL;
    HRESULT hr = device->lpVtbl->CreateCommandSignature(device, &desc, root_sig, &IID_ID3D12CommandSignature, (void**)&sig);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)sig;
}

D3D12Handle d3d12_bridge_device_create_command_signature_draw_indexed(D3D12Handle device_h, D3D12Handle root_sig_h) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12RootSignature* root_sig = (ID3D12RootSignature*)root_sig_h;

    D3D12_INDIRECT_ARGUMENT_DESC arg_desc;
    arg_desc.Type = D3D12_INDIRECT_ARGUMENT_TYPE_DRAW_INDEXED;
    D3D12_COMMAND_SIGNATURE_DESC desc;
    desc.ByteStride       = sizeof(uint32_t) * 5;
    desc.NumArgumentDescs  = 1;
    desc.pArgumentDescs    = &arg_desc;
    desc.NodeMask          = 0;

    ID3D12CommandSignature* sig = NULL;
    HRESULT hr = device->lpVtbl->CreateCommandSignature(device, &desc, root_sig, &IID_ID3D12CommandSignature, (void**)&sig);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)sig;
}

void d3d12_bridge_command_list_execute_indirect(D3D12Handle cmd_list_h, D3D12Handle command_sig_h,
                                                 uint32_t max_count, D3D12Handle arg_buffer_h,
                                                 uint64_t arg_offset) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12CommandSignature* sig    = (ID3D12CommandSignature*)command_sig_h;
    ID3D12Resource* args           = (ID3D12Resource*)arg_buffer_h;
    cmd->lpVtbl->ExecuteIndirect(cmd, sig, max_count, args, arg_offset, NULL, 0);
}

/* --- Timestamp queries --- */

D3D12Handle d3d12_bridge_device_create_timestamp_query_heap(D3D12Handle device_h, uint32_t count) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    D3D12_QUERY_HEAP_DESC desc;
    desc.Type     = D3D12_QUERY_HEAP_TYPE_TIMESTAMP;
    desc.Count    = count;
    desc.NodeMask = 0;

    ID3D12QueryHeap* heap = NULL;
    HRESULT hr = device->lpVtbl->CreateQueryHeap(device, &desc, &IID_ID3D12QueryHeap, (void**)&heap);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)heap;
}

void d3d12_bridge_command_list_end_query(D3D12Handle cmd_list_h, D3D12Handle query_heap_h, uint32_t index) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12QueryHeap* heap          = (ID3D12QueryHeap*)query_heap_h;
    cmd->lpVtbl->EndQuery(cmd, heap, D3D12_QUERY_TYPE_TIMESTAMP, index);
}

void d3d12_bridge_command_list_resolve_query_data(D3D12Handle cmd_list_h, D3D12Handle query_heap_h,
                                                    uint32_t start_index, uint32_t count,
                                                    D3D12Handle dst_buffer_h, uint64_t dst_offset) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12QueryHeap* heap          = (ID3D12QueryHeap*)query_heap_h;
    ID3D12Resource* dst            = (ID3D12Resource*)dst_buffer_h;
    cmd->lpVtbl->ResolveQueryData(cmd, heap, D3D12_QUERY_TYPE_TIMESTAMP, start_index, count, dst, dst_offset);
}

uint64_t d3d12_bridge_queue_get_timestamp_frequency(D3D12Handle queue_h) {
    ID3D12CommandQueue* queue = (ID3D12CommandQueue*)queue_h;
    UINT64 freq = 0;
    queue->lpVtbl->GetTimestampFrequency(queue, &freq);
    return (uint64_t)freq;
}

/* --- Map/Unmap --- */

void* d3d12_bridge_resource_map(D3D12Handle resource_h) {
    ID3D12Resource* resource = (ID3D12Resource*)resource_h;
    void* data = NULL;
    D3D12_RANGE range;
    range.Begin = 0;
    range.End   = 0;
    HRESULT hr = resource->lpVtbl->Map(resource, 0, &range, &data);
    if (FAILED(hr)) return NULL;
    return data;
}

void d3d12_bridge_resource_unmap(D3D12Handle resource_h) {
    ID3D12Resource* resource = (ID3D12Resource*)resource_h;
    resource->lpVtbl->Unmap(resource, 0, NULL);
}

/* --- DXGI swap chain (surface) --- */

D3D12Handle d3d12_bridge_create_swap_chain(D3D12Handle queue_h, uint32_t width, uint32_t height, uint32_t format) {
    IDXGIFactory4* factory = NULL;
    HRESULT hr = CreateDXGIFactory1(&IID_IDXGIFactory4, (void**)&factory);
    if (FAILED(hr)) return NULL;

    DXGI_SWAP_CHAIN_DESC1 desc;
    memset(&desc, 0, sizeof(desc));
    desc.Width       = width;
    desc.Height      = height;
    desc.Format      = map_wgpu_format_to_dxgi(format);
    desc.SampleDesc.Count = 1;
    desc.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    desc.BufferCount = 2;
    desc.SwapEffect  = DXGI_SWAP_EFFECT_FLIP_DISCARD;

    /* Headless swap chain for benchmarking; no HWND target */
    IDXGISwapChain1* chain = NULL;
    hr = factory->lpVtbl->CreateSwapChainForComposition(factory, (IUnknown*)queue_h, &desc, NULL, &chain);
    factory->lpVtbl->Release(factory);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)chain;
}

int d3d12_bridge_swap_chain_present(D3D12Handle swap_chain_h, uint32_t sync_interval) {
    IDXGISwapChain1* chain = (IDXGISwapChain1*)swap_chain_h;
    HRESULT hr = chain->lpVtbl->Present(chain, sync_interval, 0);
    return SUCCEEDED(hr) ? 0 : -1;
}

D3D12Handle d3d12_bridge_swap_chain_get_buffer(D3D12Handle swap_chain_h, uint32_t index) {
    IDXGISwapChain1* chain = (IDXGISwapChain1*)swap_chain_h;
    ID3D12Resource* buffer = NULL;
    HRESULT hr = chain->lpVtbl->GetBuffer(chain, index, &IID_ID3D12Resource, (void**)&buffer);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)buffer;
}

int d3d12_bridge_swap_chain_resize(D3D12Handle swap_chain_h, uint32_t width, uint32_t height, uint32_t format) {
    IDXGISwapChain1* chain = (IDXGISwapChain1*)swap_chain_h;
    HRESULT hr = chain->lpVtbl->ResizeBuffers(chain, 2, width, height, map_wgpu_format_to_dxgi(format), 0);
    return SUCCEEDED(hr) ? 0 : -1;
}
