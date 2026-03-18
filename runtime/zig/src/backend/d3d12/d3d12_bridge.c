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
        case 0x00000005: return DXGI_FORMAT_R16_UNORM;             /* R16Unorm */
        case 0x00000006: return DXGI_FORMAT_R16_SNORM;             /* R16Snorm */
        case 0x00000011: return DXGI_FORMAT_R16G16_UNORM;          /* RG16Unorm */
        case 0x00000012: return DXGI_FORMAT_R16G16_SNORM;          /* RG16Snorm */
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

/* --- Device info / adapter queries --- */

void d3d12_bridge_device_get_adapter_desc(D3D12Handle device_h, char* desc_out, size_t desc_size,
                                           uint32_t* vendor_id_out, uint32_t* device_id_out,
                                           uint64_t* dedicated_vram_out) {
    if (desc_out && desc_size > 0) desc_out[0] = '\0';
    if (vendor_id_out) *vendor_id_out = 0;
    if (device_id_out) *device_id_out = 0;
    if (dedicated_vram_out) *dedicated_vram_out = 0;

    ID3D12Device* device = (ID3D12Device*)device_h;
    LUID luid = device->lpVtbl->GetAdapterLuid(device);

    IDXGIFactory4* factory = NULL;
    if (FAILED(CreateDXGIFactory1(&IID_IDXGIFactory4, (void**)&factory))) return;

    IDXGIAdapter1* adapter = NULL;
    for (UINT i = 0; factory->lpVtbl->EnumAdapters1(factory, i, &adapter) != DXGI_ERROR_NOT_FOUND; i++) {
        DXGI_ADAPTER_DESC1 desc;
        adapter->lpVtbl->GetDesc1(adapter, &desc);
        if (desc.AdapterLuid.LowPart == luid.LowPart && desc.AdapterLuid.HighPart == luid.HighPart) {
            if (desc_out && desc_size > 0) {
                WideCharToMultiByte(CP_UTF8, 0, desc.Description, -1, desc_out, (int)desc_size, NULL, NULL);
                desc_out[desc_size - 1] = '\0';
            }
            if (vendor_id_out) *vendor_id_out = desc.VendorId;
            if (device_id_out) *device_id_out = desc.DeviceId;
            if (dedicated_vram_out) *dedicated_vram_out = (uint64_t)desc.DedicatedVideoMemory;
            adapter->lpVtbl->Release(adapter);
            break;
        }
        adapter->lpVtbl->Release(adapter);
    }
    factory->lpVtbl->Release(factory);
}

/* --- Depth/stencil views --- */

D3D12Handle d3d12_bridge_device_create_dsv_heap(D3D12Handle device_h, uint32_t num_descriptors) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    D3D12_DESCRIPTOR_HEAP_DESC desc;
    desc.Type           = D3D12_DESCRIPTOR_HEAP_TYPE_DSV;
    desc.NumDescriptors = num_descriptors;
    desc.Flags          = D3D12_DESCRIPTOR_HEAP_FLAG_NONE;
    desc.NodeMask       = 0;

    ID3D12DescriptorHeap* heap = NULL;
    HRESULT hr = device->lpVtbl->CreateDescriptorHeap(device, &desc, &IID_ID3D12DescriptorHeap, (void**)&heap);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)heap;
}

static DXGI_FORMAT map_depth_format(uint32_t format) {
    switch (format) {
        case 0x0000002D: return DXGI_FORMAT_D16_UNORM;
        case 0x0000002E: return DXGI_FORMAT_D24_UNORM_S8_UINT;    /* Depth24Plus */
        case 0x0000002F: return DXGI_FORMAT_D24_UNORM_S8_UINT;    /* Depth24PlusStencil8 */
        case 0x00000030: return DXGI_FORMAT_D32_FLOAT;
        case 0x00000031: return DXGI_FORMAT_D32_FLOAT_S8X24_UINT; /* Depth32FloatStencil8 */
        default:         return DXGI_FORMAT_D32_FLOAT;
    }
}

void d3d12_bridge_device_create_dsv(D3D12Handle device_h, D3D12Handle resource_h, D3D12Handle dsv_heap_h,
                                     uint32_t index, uint32_t format) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12Resource* resource = (ID3D12Resource*)resource_h;
    ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)dsv_heap_h;

    UINT dsv_size = device->lpVtbl->GetDescriptorHandleIncrementSize(device, D3D12_DESCRIPTOR_HEAP_TYPE_DSV);
    D3D12_CPU_DESCRIPTOR_HANDLE cpu_handle;
    heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap, &cpu_handle);
    cpu_handle.ptr += (SIZE_T)(dsv_size * index);

    D3D12_DEPTH_STENCIL_VIEW_DESC dsv_desc;
    memset(&dsv_desc, 0, sizeof(dsv_desc));
    dsv_desc.Format               = map_depth_format(format);
    dsv_desc.ViewDimension        = D3D12_DSV_DIMENSION_TEXTURE2D;
    dsv_desc.Texture2D.MipSlice   = 0;

    device->lpVtbl->CreateDepthStencilView(device, resource, &dsv_desc, cpu_handle);
}

D3D12Handle d3d12_bridge_device_create_depth_texture(D3D12Handle device_h, uint32_t width, uint32_t height, uint32_t format) {
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
    desc.MipLevels          = 1;
    desc.Format             = map_depth_format(format);
    desc.SampleDesc.Count   = 1;
    desc.SampleDesc.Quality = 0;
    desc.Layout             = D3D12_TEXTURE_LAYOUT_UNKNOWN;
    desc.Flags              = D3D12_RESOURCE_FLAG_ALLOW_DEPTH_STENCIL;

    D3D12_CLEAR_VALUE clear_value;
    clear_value.Format               = desc.Format;
    clear_value.DepthStencil.Depth   = 1.0f;
    clear_value.DepthStencil.Stencil = 0;

    ID3D12Resource* tex = NULL;
    HRESULT hr = device->lpVtbl->CreateCommittedResource(
        device, &heap_props, D3D12_HEAP_FLAG_NONE,
        &desc, D3D12_RESOURCE_STATE_DEPTH_WRITE, &clear_value,
        &IID_ID3D12Resource, (void**)&tex);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)tex;
}

/* --- CBV/SRV/UAV descriptor heap --- */

D3D12Handle d3d12_bridge_device_create_cbv_srv_uav_heap(D3D12Handle device_h, uint32_t num_descriptors) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    D3D12_DESCRIPTOR_HEAP_DESC desc;
    desc.Type           = D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV;
    desc.NumDescriptors = num_descriptors;
    desc.Flags          = D3D12_DESCRIPTOR_HEAP_FLAG_SHADER_VISIBLE;
    desc.NodeMask       = 0;

    ID3D12DescriptorHeap* heap = NULL;
    HRESULT hr = device->lpVtbl->CreateDescriptorHeap(device, &desc, &IID_ID3D12DescriptorHeap, (void**)&heap);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)heap;
}

void d3d12_bridge_device_create_cbv(D3D12Handle device_h, D3D12Handle heap_h, uint32_t index,
                                     D3D12Handle buffer_h, uint64_t offset, uint32_t size) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)heap_h;
    ID3D12Resource* buffer = (ID3D12Resource*)buffer_h;

    UINT incr = device->lpVtbl->GetDescriptorHandleIncrementSize(device, D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
    D3D12_CPU_DESCRIPTOR_HANDLE handle;
    heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap, &handle);
    handle.ptr += (SIZE_T)(incr * index);

    D3D12_CONSTANT_BUFFER_VIEW_DESC cbv_desc;
    cbv_desc.BufferLocation = buffer->lpVtbl->GetGPUVirtualAddress(buffer) + offset;
    cbv_desc.SizeInBytes    = (UINT)((size + 255u) & ~255u); /* D3D12 CBV must be 256-byte aligned */

    device->lpVtbl->CreateConstantBufferView(device, &cbv_desc, handle);
}

void d3d12_bridge_device_create_srv_buffer(D3D12Handle device_h, D3D12Handle heap_h, uint32_t index,
                                            D3D12Handle buffer_h, uint32_t num_elements, uint32_t stride) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)heap_h;
    ID3D12Resource* buffer = (ID3D12Resource*)buffer_h;

    UINT incr = device->lpVtbl->GetDescriptorHandleIncrementSize(device, D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
    D3D12_CPU_DESCRIPTOR_HANDLE handle;
    heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap, &handle);
    handle.ptr += (SIZE_T)(incr * index);

    D3D12_SHADER_RESOURCE_VIEW_DESC srv_desc;
    memset(&srv_desc, 0, sizeof(srv_desc));
    srv_desc.Format                     = DXGI_FORMAT_UNKNOWN;
    srv_desc.ViewDimension              = D3D12_SRV_DIMENSION_BUFFER;
    srv_desc.Shader4ComponentMapping    = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
    srv_desc.Buffer.NumElements         = num_elements;
    srv_desc.Buffer.StructureByteStride = stride;

    device->lpVtbl->CreateShaderResourceView(device, buffer, &srv_desc, handle);
}

void d3d12_bridge_device_create_uav_buffer(D3D12Handle device_h, D3D12Handle heap_h, uint32_t index,
                                            D3D12Handle buffer_h, uint32_t num_elements, uint32_t stride) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)heap_h;
    ID3D12Resource* buffer = (ID3D12Resource*)buffer_h;

    UINT incr = device->lpVtbl->GetDescriptorHandleIncrementSize(device, D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
    D3D12_CPU_DESCRIPTOR_HANDLE handle;
    heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap, &handle);
    handle.ptr += (SIZE_T)(incr * index);

    D3D12_UNORDERED_ACCESS_VIEW_DESC uav_desc;
    memset(&uav_desc, 0, sizeof(uav_desc));
    uav_desc.Format                      = DXGI_FORMAT_UNKNOWN;
    uav_desc.ViewDimension               = D3D12_UAV_DIMENSION_BUFFER;
    uav_desc.Buffer.NumElements          = num_elements;
    uav_desc.Buffer.StructureByteStride  = stride;

    device->lpVtbl->CreateUnorderedAccessView(device, buffer, NULL, &uav_desc, handle);
}

void d3d12_bridge_device_create_srv_texture_2d(D3D12Handle device_h, D3D12Handle resource_h,
                                                D3D12Handle heap_h, uint32_t index, uint32_t format,
                                                uint32_t base_mip, uint32_t mip_count) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12Resource* resource = (ID3D12Resource*)resource_h;
    ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)heap_h;

    UINT incr = device->lpVtbl->GetDescriptorHandleIncrementSize(device, D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
    D3D12_CPU_DESCRIPTOR_HANDLE handle;
    heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap, &handle);
    handle.ptr += (SIZE_T)(incr * index);

    D3D12_SHADER_RESOURCE_VIEW_DESC srv_desc;
    memset(&srv_desc, 0, sizeof(srv_desc));
    srv_desc.Format                        = map_wgpu_format_to_dxgi(format);
    srv_desc.ViewDimension                 = D3D12_SRV_DIMENSION_TEXTURE2D;
    srv_desc.Shader4ComponentMapping       = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
    srv_desc.Texture2D.MostDetailedMip     = base_mip;
    srv_desc.Texture2D.MipLevels           = mip_count == 0 ? (UINT)-1 : mip_count;

    device->lpVtbl->CreateShaderResourceView(device, resource, &srv_desc, handle);
}

void d3d12_bridge_device_create_srv_texture_cube(D3D12Handle device_h, D3D12Handle resource_h,
                                                  D3D12Handle heap_h, uint32_t index, uint32_t format,
                                                  uint32_t base_mip, uint32_t mip_count) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12Resource* resource = (ID3D12Resource*)resource_h;
    ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)heap_h;

    UINT incr = device->lpVtbl->GetDescriptorHandleIncrementSize(device, D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
    D3D12_CPU_DESCRIPTOR_HANDLE handle;
    heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap, &handle);
    handle.ptr += (SIZE_T)(incr * index);

    D3D12_SHADER_RESOURCE_VIEW_DESC srv_desc;
    memset(&srv_desc, 0, sizeof(srv_desc));
    srv_desc.Format                           = map_wgpu_format_to_dxgi(format);
    srv_desc.ViewDimension                    = D3D12_SRV_DIMENSION_TEXTURECUBE;
    srv_desc.Shader4ComponentMapping          = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
    srv_desc.TextureCube.MostDetailedMip      = base_mip;
    srv_desc.TextureCube.MipLevels            = mip_count == 0 ? (UINT)-1 : mip_count;

    device->lpVtbl->CreateShaderResourceView(device, resource, &srv_desc, handle);
}

void d3d12_bridge_device_create_srv_texture_3d(D3D12Handle device_h, D3D12Handle resource_h,
                                                D3D12Handle heap_h, uint32_t index, uint32_t format,
                                                uint32_t base_mip, uint32_t mip_count) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12Resource* resource = (ID3D12Resource*)resource_h;
    ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)heap_h;

    UINT incr = device->lpVtbl->GetDescriptorHandleIncrementSize(device, D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
    D3D12_CPU_DESCRIPTOR_HANDLE handle;
    heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap, &handle);
    handle.ptr += (SIZE_T)(incr * index);

    D3D12_SHADER_RESOURCE_VIEW_DESC srv_desc;
    memset(&srv_desc, 0, sizeof(srv_desc));
    srv_desc.Format                          = map_wgpu_format_to_dxgi(format);
    srv_desc.ViewDimension                   = D3D12_SRV_DIMENSION_TEXTURE3D;
    srv_desc.Shader4ComponentMapping         = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
    srv_desc.Texture3D.MostDetailedMip       = base_mip;
    srv_desc.Texture3D.MipLevels             = mip_count == 0 ? (UINT)-1 : mip_count;

    device->lpVtbl->CreateShaderResourceView(device, resource, &srv_desc, handle);
}

void d3d12_bridge_device_create_uav_texture_2d(D3D12Handle device_h, D3D12Handle resource_h,
                                                D3D12Handle heap_h, uint32_t index, uint32_t format,
                                                uint32_t mip_slice) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12Resource* resource = (ID3D12Resource*)resource_h;
    ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)heap_h;

    UINT incr = device->lpVtbl->GetDescriptorHandleIncrementSize(device, D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
    D3D12_CPU_DESCRIPTOR_HANDLE handle;
    heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap, &handle);
    handle.ptr += (SIZE_T)(incr * index);

    D3D12_UNORDERED_ACCESS_VIEW_DESC uav_desc;
    memset(&uav_desc, 0, sizeof(uav_desc));
    uav_desc.Format                    = map_wgpu_format_to_dxgi(format);
    uav_desc.ViewDimension             = D3D12_UAV_DIMENSION_TEXTURE2D;
    uav_desc.Texture2D.MipSlice        = mip_slice;

    device->lpVtbl->CreateUnorderedAccessView(device, resource, NULL, &uav_desc, handle);
}

void d3d12_bridge_command_list_set_descriptor_heaps(D3D12Handle cmd_list_h,
                                                     D3D12Handle cbv_srv_uav_heap_h,
                                                     D3D12Handle sampler_heap_h) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    UINT count = 0;
    ID3D12DescriptorHeap* heaps[2];
    if (cbv_srv_uav_heap_h) heaps[count++] = (ID3D12DescriptorHeap*)cbv_srv_uav_heap_h;
    if (sampler_heap_h)     heaps[count++] = (ID3D12DescriptorHeap*)sampler_heap_h;
    if (count > 0) cmd->lpVtbl->SetDescriptorHeaps(cmd, count, heaps);
}

/* --- Root signature with descriptor table parameters --- */

D3D12Handle d3d12_bridge_device_create_root_signature_with_ranges(D3D12Handle device_h,
                                                                    uint32_t num_cbv, uint32_t num_srv,
                                                                    uint32_t num_uav, uint32_t num_samplers) {
    ID3D12Device* device = (ID3D12Device*)device_h;

    D3D12_DESCRIPTOR_RANGE ranges[4];
    UINT range_count = 0;
    D3D12_ROOT_PARAMETER params[2];
    UINT param_count = 0;

    /* CBV/SRV/UAV table */
    UINT cbv_srv_uav_total = num_cbv + num_srv + num_uav;
    if (cbv_srv_uav_total > 0) {
        UINT ri = 0;
        if (num_cbv > 0) {
            ranges[ri].RangeType          = D3D12_DESCRIPTOR_RANGE_TYPE_CBV;
            ranges[ri].NumDescriptors     = num_cbv;
            ranges[ri].BaseShaderRegister = 0;
            ranges[ri].RegisterSpace      = 0;
            ranges[ri].OffsetInDescriptorsFromTableStart = D3D12_DESCRIPTOR_RANGE_OFFSET_APPEND;
            ri++;
        }
        if (num_srv > 0) {
            ranges[ri].RangeType          = D3D12_DESCRIPTOR_RANGE_TYPE_SRV;
            ranges[ri].NumDescriptors     = num_srv;
            ranges[ri].BaseShaderRegister = 0;
            ranges[ri].RegisterSpace      = 0;
            ranges[ri].OffsetInDescriptorsFromTableStart = D3D12_DESCRIPTOR_RANGE_OFFSET_APPEND;
            ri++;
        }
        if (num_uav > 0) {
            ranges[ri].RangeType          = D3D12_DESCRIPTOR_RANGE_TYPE_UAV;
            ranges[ri].NumDescriptors     = num_uav;
            ranges[ri].BaseShaderRegister = 0;
            ranges[ri].RegisterSpace      = 0;
            ranges[ri].OffsetInDescriptorsFromTableStart = D3D12_DESCRIPTOR_RANGE_OFFSET_APPEND;
            ri++;
        }
        params[param_count].ParameterType                       = D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
        params[param_count].ShaderVisibility                    = D3D12_SHADER_VISIBILITY_ALL;
        params[param_count].DescriptorTable.NumDescriptorRanges = ri;
        params[param_count].DescriptorTable.pDescriptorRanges   = ranges;
        param_count++;
        range_count = ri;
    }

    /* Sampler table */
    if (num_samplers > 0) {
        D3D12_DESCRIPTOR_RANGE* sampler_range = &ranges[range_count];
        sampler_range->RangeType          = D3D12_DESCRIPTOR_RANGE_TYPE_SAMPLER;
        sampler_range->NumDescriptors     = num_samplers;
        sampler_range->BaseShaderRegister = 0;
        sampler_range->RegisterSpace      = 0;
        sampler_range->OffsetInDescriptorsFromTableStart = D3D12_DESCRIPTOR_RANGE_OFFSET_APPEND;

        params[param_count].ParameterType                       = D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
        params[param_count].ShaderVisibility                    = D3D12_SHADER_VISIBILITY_ALL;
        params[param_count].DescriptorTable.NumDescriptorRanges = 1;
        params[param_count].DescriptorTable.pDescriptorRanges   = sampler_range;
        param_count++;
    }

    D3D12_ROOT_SIGNATURE_DESC sig_desc;
    sig_desc.NumParameters     = param_count;
    sig_desc.pParameters       = param_count > 0 ? params : NULL;
    sig_desc.NumStaticSamplers = 0;
    sig_desc.pStaticSamplers   = NULL;
    sig_desc.Flags             = D3D12_ROOT_SIGNATURE_FLAG_NONE;

    ID3DBlob* blob  = NULL;
    ID3DBlob* error = NULL;
    HRESULT hr = D3D12SerializeRootSignature(&sig_desc, D3D_ROOT_SIGNATURE_VERSION_1, &blob, &error);
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

/* --- Occlusion and pipeline statistics queries --- */

D3D12Handle d3d12_bridge_device_create_occlusion_query_heap(D3D12Handle device_h, uint32_t count) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    D3D12_QUERY_HEAP_DESC desc;
    desc.Type     = D3D12_QUERY_HEAP_TYPE_OCCLUSION;
    desc.Count    = count;
    desc.NodeMask = 0;

    ID3D12QueryHeap* heap = NULL;
    HRESULT hr = device->lpVtbl->CreateQueryHeap(device, &desc, &IID_ID3D12QueryHeap, (void**)&heap);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)heap;
}

D3D12Handle d3d12_bridge_device_create_pipeline_statistics_query_heap(D3D12Handle device_h, uint32_t count) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    D3D12_QUERY_HEAP_DESC desc;
    desc.Type     = D3D12_QUERY_HEAP_TYPE_PIPELINE_STATISTICS;
    desc.Count    = count;
    desc.NodeMask = 0;

    ID3D12QueryHeap* heap = NULL;
    HRESULT hr = device->lpVtbl->CreateQueryHeap(device, &desc, &IID_ID3D12QueryHeap, (void**)&heap);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)heap;
}

void d3d12_bridge_command_list_begin_query(D3D12Handle cmd_list_h, D3D12Handle query_heap_h, uint32_t index) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12QueryHeap* heap          = (ID3D12QueryHeap*)query_heap_h;
    cmd->lpVtbl->BeginQuery(cmd, heap, D3D12_QUERY_TYPE_OCCLUSION, index);
}

/* --- 3D Texture --- */

D3D12Handle d3d12_bridge_device_create_texture_3d(D3D12Handle device_h, uint32_t width, uint32_t height,
                                                    uint32_t depth, uint32_t mip_levels,
                                                    uint32_t format, uint32_t usage_flags) {
    ID3D12Device* device = (ID3D12Device*)device_h;

    D3D12_HEAP_PROPERTIES heap_props;
    heap_props.Type                 = D3D12_HEAP_TYPE_DEFAULT;
    heap_props.CPUPageProperty      = D3D12_CPU_PAGE_PROPERTY_UNKNOWN;
    heap_props.MemoryPoolPreference = D3D12_MEMORY_POOL_UNKNOWN;
    heap_props.CreationNodeMask     = 1;
    heap_props.VisibleNodeMask      = 1;

    D3D12_RESOURCE_DESC desc;
    desc.Dimension          = D3D12_RESOURCE_DIMENSION_TEXTURE3D;
    desc.Alignment          = 0;
    desc.Width              = (UINT64)width;
    desc.Height             = height;
    desc.DepthOrArraySize   = (UINT16)(depth == 0 ? 1 : depth);
    desc.MipLevels          = (UINT16)(mip_levels == 0 ? 1 : mip_levels);
    desc.Format             = map_wgpu_format_to_dxgi(format);
    desc.SampleDesc.Count   = 1;
    desc.SampleDesc.Quality = 0;
    desc.Layout             = D3D12_TEXTURE_LAYOUT_UNKNOWN;
    desc.Flags              = map_wgpu_usage_to_d3d12_flags(usage_flags);

    ID3D12Resource* tex = NULL;
    HRESULT hr = device->lpVtbl->CreateCommittedResource(
        device, &heap_props, D3D12_HEAP_FLAG_NONE,
        &desc, D3D12_RESOURCE_STATE_COPY_DEST, NULL,
        &IID_ID3D12Resource, (void**)&tex);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)tex;
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

/* --- Simple SRV texture (2D, all mip levels) ---
   Matches Zig extern: d3d12_bridge_device_create_srv_texture(device, heap, index, texture, format) */
void d3d12_bridge_device_create_srv_texture(D3D12Handle device_h, D3D12Handle heap_h, uint32_t index,
                                             D3D12Handle texture_h, uint32_t format) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)heap_h;
    ID3D12Resource* texture = (ID3D12Resource*)texture_h;

    UINT incr = device->lpVtbl->GetDescriptorHandleIncrementSize(device, D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
    D3D12_CPU_DESCRIPTOR_HANDLE handle;
    heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap, &handle);
    handle.ptr += (SIZE_T)(incr * index);

    D3D12_SHADER_RESOURCE_VIEW_DESC srv_desc;
    memset(&srv_desc, 0, sizeof(srv_desc));
    srv_desc.Format                        = map_wgpu_format_to_dxgi(format);
    srv_desc.ViewDimension                 = D3D12_SRV_DIMENSION_TEXTURE2D;
    srv_desc.Shader4ComponentMapping       = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
    srv_desc.Texture2D.MostDetailedMip     = 0;
    srv_desc.Texture2D.MipLevels           = (UINT)-1; /* all mip levels */
    srv_desc.Texture2D.ResourceMinLODClamp = 0.0f;

    device->lpVtbl->CreateShaderResourceView(device, texture, &srv_desc, handle);
}

/* --- Root signature from explicit range array ---
   Matches Zig extern: d3d12_bridge_device_create_root_signature_with_tables(device, ranges, range_count, flags)
   Builds one descriptor table root parameter per contiguous run of CBV/SRV/UAV ranges,
   and a separate table for sampler ranges (D3D12 requires separate heaps). */
D3D12Handle d3d12_bridge_device_create_root_signature_with_tables(D3D12Handle device_h,
                                                                     const D3D12DescriptorRangeDesc* ranges,
                                                                     uint32_t range_count, uint32_t flags) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    if (range_count == 0) return NULL;

    /* Translate range descs into D3D12_DESCRIPTOR_RANGE, split CBV/SRV/UAV from SAMPLER */
    D3D12_DESCRIPTOR_RANGE d3d_ranges[64];
    D3D12_DESCRIPTOR_RANGE sampler_ranges[16];
    UINT d3d_count = 0;
    UINT sampler_count = 0;

    for (uint32_t i = 0; i < range_count && i < 64; i++) {
        D3D12_DESCRIPTOR_RANGE r;
        r.RangeType          = (D3D12_DESCRIPTOR_RANGE_TYPE)ranges[i].range_type;
        r.NumDescriptors     = ranges[i].num_descriptors;
        r.BaseShaderRegister = ranges[i].base_shader_register;
        r.RegisterSpace      = ranges[i].register_space;
        r.OffsetInDescriptorsFromTableStart = D3D12_DESCRIPTOR_RANGE_OFFSET_APPEND;

        if (ranges[i].range_type == 3) { /* SAMPLER */
            if (sampler_count < 16) sampler_ranges[sampler_count++] = r;
        } else {
            if (d3d_count < 64) d3d_ranges[d3d_count++] = r;
        }
    }

    D3D12_ROOT_PARAMETER params[2];
    UINT param_count = 0;

    if (d3d_count > 0) {
        params[param_count].ParameterType                       = D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
        params[param_count].ShaderVisibility                    = D3D12_SHADER_VISIBILITY_ALL;
        params[param_count].DescriptorTable.NumDescriptorRanges = d3d_count;
        params[param_count].DescriptorTable.pDescriptorRanges   = d3d_ranges;
        param_count++;
    }
    if (sampler_count > 0) {
        params[param_count].ParameterType                       = D3D12_ROOT_PARAMETER_TYPE_DESCRIPTOR_TABLE;
        params[param_count].ShaderVisibility                    = D3D12_SHADER_VISIBILITY_ALL;
        params[param_count].DescriptorTable.NumDescriptorRanges = sampler_count;
        params[param_count].DescriptorTable.pDescriptorRanges   = sampler_ranges;
        param_count++;
    }

    D3D12_ROOT_SIGNATURE_DESC sig_desc;
    sig_desc.NumParameters     = param_count;
    sig_desc.pParameters       = param_count > 0 ? params : NULL;
    sig_desc.NumStaticSamplers = 0;
    sig_desc.pStaticSamplers   = NULL;
    sig_desc.Flags             = (D3D12_ROOT_SIGNATURE_FLAGS)flags;

    ID3DBlob* blob  = NULL;
    ID3DBlob* error = NULL;
    HRESULT hr = D3D12SerializeRootSignature(&sig_desc, D3D_ROOT_SIGNATURE_VERSION_1, &blob, &error);
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

/* --- Compute root descriptor table binding --- */
void d3d12_bridge_command_list_set_compute_root_descriptor_table(D3D12Handle cmd_list_h,
                                                                   uint32_t root_parameter_index,
                                                                   D3D12Handle heap_h,
                                                                   uint32_t base_descriptor_index) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)heap_h;

    UINT incr = 0;
    /* Get increment size from heap type — use CBV/SRV/UAV as default */
    {
        ID3D12Device* device = NULL;
        HRESULT hr = cmd->lpVtbl->GetDevice(cmd, &IID_ID3D12Device, (void**)&device);
        if (SUCCEEDED(hr) && device) {
            incr = device->lpVtbl->GetDescriptorHandleIncrementSize(device, D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
            device->lpVtbl->Release(device);
        }
    }

    D3D12_GPU_DESCRIPTOR_HANDLE gpu_handle;
    heap->lpVtbl->GetGPUDescriptorHandleForHeapStart(heap, &gpu_handle);
    gpu_handle.ptr += (UINT64)(incr * base_descriptor_index);

    cmd->lpVtbl->SetComputeRootDescriptorTable(cmd, root_parameter_index, gpu_handle);
}

/* --- Graphics root descriptor table binding --- */
void d3d12_bridge_command_list_set_graphics_root_descriptor_table(D3D12Handle cmd_list_h,
                                                                    uint32_t root_parameter_index,
                                                                    D3D12Handle heap_h,
                                                                    uint32_t base_descriptor_index) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)heap_h;

    UINT incr = 0;
    {
        ID3D12Device* device = NULL;
        HRESULT hr = cmd->lpVtbl->GetDevice(cmd, &IID_ID3D12Device, (void**)&device);
        if (SUCCEEDED(hr) && device) {
            incr = device->lpVtbl->GetDescriptorHandleIncrementSize(device, D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
            device->lpVtbl->Release(device);
        }
    }

    D3D12_GPU_DESCRIPTOR_HANDLE gpu_handle;
    heap->lpVtbl->GetGPUDescriptorHandleForHeapStart(heap, &gpu_handle);
    gpu_handle.ptr += (UINT64)(incr * base_descriptor_index);

    cmd->lpVtbl->SetGraphicsRootDescriptorTable(cmd, root_parameter_index, gpu_handle);
}
