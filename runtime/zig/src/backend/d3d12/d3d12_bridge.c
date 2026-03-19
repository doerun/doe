#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d12.h>
#include <d3dcompiler.h>
#include <dxgi1_4.h>
#include <string.h>
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

uint64_t d3d12_bridge_buffer_get_size(D3D12Handle buffer_h) {
    ID3D12Resource* buffer = (ID3D12Resource*)buffer_h;
    if (buffer == NULL) return 0;
    D3D12_RESOURCE_DESC desc = buffer->lpVtbl->GetDesc(buffer);
    return (uint64_t)desc.Width;
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
        case 0x00000001: return DXGI_FORMAT_R8_UNORM;              /* R8Unorm */
        case 0x00000002: return DXGI_FORMAT_R8_SNORM;              /* R8Snorm */
        case 0x00000005: return DXGI_FORMAT_R16_UNORM;             /* R16Unorm */
        case 0x00000006: return DXGI_FORMAT_R16_SNORM;             /* R16Snorm */
        case 0x00000007: return DXGI_FORMAT_R16_UINT;              /* R16Uint */
        case 0x00000008: return DXGI_FORMAT_R16_SINT;              /* R16Sint */
        case 0x00000009: return DXGI_FORMAT_R16_FLOAT;             /* R16Float */
        case 0x0000000A: return DXGI_FORMAT_R8G8_UNORM;            /* RG8Unorm */
        case 0x0000000B: return DXGI_FORMAT_R8G8_SNORM;            /* RG8Snorm */
        case 0x0000000C: return DXGI_FORMAT_R8G8_UINT;             /* RG8Uint */
        case 0x0000000D: return DXGI_FORMAT_R8G8_SINT;             /* RG8Sint */
        case 0x0000000E: return DXGI_FORMAT_R32_FLOAT;             /* R32Float */
        case 0x0000000F: return DXGI_FORMAT_R32_UINT;              /* R32Uint */
        case 0x00000010: return DXGI_FORMAT_R32_SINT;              /* R32Sint */
        case 0x00000011: return DXGI_FORMAT_R16G16_UNORM;          /* RG16Unorm */
        case 0x00000012: return DXGI_FORMAT_R16G16_SNORM;          /* RG16Snorm */
        case 0x00000013: return DXGI_FORMAT_R16G16_UINT;           /* RG16Uint */
        case 0x00000014: return DXGI_FORMAT_R16G16_SINT;           /* RG16Sint */
        case 0x00000015: return DXGI_FORMAT_R16G16_FLOAT;          /* RG16Float */
        case 0x00000016: return DXGI_FORMAT_R8G8B8A8_UNORM;        /* RGBA8Unorm */
        case 0x00000017: return DXGI_FORMAT_R8G8B8A8_UNORM_SRGB;   /* RGBA8UnormSrgb */
        case 0x00000018: return DXGI_FORMAT_R8G8B8A8_SNORM;        /* RGBA8Snorm */
        case 0x00000019: return DXGI_FORMAT_R8G8B8A8_UINT;         /* RGBA8Uint */
        case 0x0000001A: return DXGI_FORMAT_R8G8B8A8_SINT;         /* RGBA8Sint */
        case 0x0000001B: return DXGI_FORMAT_B8G8R8A8_UNORM;        /* BGRA8Unorm */
        case 0x0000001C: return DXGI_FORMAT_B8G8R8A8_UNORM_SRGB;   /* BGRA8UnormSrgb */
        case 0x0000001D: return DXGI_FORMAT_R10G10B10A2_UINT;      /* RGB10A2Uint */
        case 0x0000001E: return DXGI_FORMAT_R10G10B10A2_UNORM;     /* RGB10A2Unorm */
        case 0x0000001F: return DXGI_FORMAT_R11G11B10_FLOAT;       /* RG11B10Ufloat */
        case 0x00000020: return DXGI_FORMAT_R9G9B9E5_SHAREDEXP;    /* RGB9E5Ufloat */
        case 0x00000021: return DXGI_FORMAT_R32G32_FLOAT;          /* RG32Float */
        case 0x00000022: return DXGI_FORMAT_R32G32_UINT;           /* RG32Uint */
        case 0x00000023: return DXGI_FORMAT_R32G32_SINT;           /* RG32Sint */
        case 0x00000024: return DXGI_FORMAT_R16G16B16A16_UINT;     /* RGBA16Uint */
        case 0x00000025: return DXGI_FORMAT_R16G16B16A16_SINT;     /* RGBA16Sint */
        case 0x00000026: return DXGI_FORMAT_R16G16B16A16_FLOAT;    /* RGBA16Float */
        case 0x00000027: return DXGI_FORMAT_R32G32B32A32_FLOAT;    /* RGBA32Float */
        case 0x00000028: return DXGI_FORMAT_R32G32B32A32_UINT;     /* RGBA32Uint */
        case 0x00000029: return DXGI_FORMAT_R32G32B32A32_SINT;     /* RGBA32Sint */
        case 0x0000002A: return DXGI_FORMAT_R16G16B16A16_UNORM;    /* RGBA16Unorm */
        case 0x0000002B: return DXGI_FORMAT_R16G16B16A16_SNORM;    /* RGBA16Snorm */
        case 0x0000002C: return DXGI_FORMAT_R24G8_TYPELESS;         /* Stencil8 */
        case 0x0000002D: return DXGI_FORMAT_R16_TYPELESS;           /* Depth16Unorm */
        case 0x0000002E: return DXGI_FORMAT_R32_TYPELESS;           /* Depth24Plus */
        case 0x0000002F: return DXGI_FORMAT_R24G8_TYPELESS;         /* Depth24PlusStencil8 */
        case 0x00000030: return DXGI_FORMAT_R32_TYPELESS;           /* Depth32Float */
        case 0x00000031: return DXGI_FORMAT_R32G8X24_TYPELESS;      /* Depth32FloatStencil8 */
        case 0x00000032: return DXGI_FORMAT_BC1_UNORM;            /* BC1RGBAUnorm */
        case 0x00000033: return DXGI_FORMAT_BC1_UNORM_SRGB;       /* BC1RGBAUnormSrgb */
        case 0x00000034: return DXGI_FORMAT_BC2_UNORM;            /* BC2RGBAUnorm */
        case 0x00000035: return DXGI_FORMAT_BC2_UNORM_SRGB;       /* BC2RGBAUnormSrgb */
        case 0x00000036: return DXGI_FORMAT_BC3_UNORM;            /* BC3RGBAUnorm */
        case 0x00000037: return DXGI_FORMAT_BC3_UNORM_SRGB;       /* BC3RGBAUnormSrgb */
        case 0x00000038: return DXGI_FORMAT_BC4_UNORM;            /* BC4RUnorm */
        case 0x00000039: return DXGI_FORMAT_BC4_SNORM;            /* BC4RSnorm */
        case 0x0000003A: return DXGI_FORMAT_BC5_UNORM;            /* BC5RGUnorm */
        case 0x0000003B: return DXGI_FORMAT_BC5_SNORM;            /* BC5RGSnorm */
        case 0x0000003C: return DXGI_FORMAT_BC6H_UF16;            /* BC6HRGBUfloat */
        case 0x0000003D: return DXGI_FORMAT_BC6H_SF16;            /* BC6HRGBFloat */
        case 0x0000003E: return DXGI_FORMAT_BC7_UNORM;            /* BC7RGBAUnorm */
        case 0x0000003F: return DXGI_FORMAT_BC7_UNORM_SRGB;       /* BC7RGBAUnormSrgb */
        default:         return DXGI_FORMAT_UNKNOWN;
    }
}

static DXGI_FORMAT map_wgpu_format_to_dxgi_view(uint32_t format, uint32_t aspect) {
    switch (format) {
        case 0x0000002C: /* Stencil8 */
            return DXGI_FORMAT_X24_TYPELESS_G8_UINT;
        case 0x0000002D: /* Depth16Unorm */
            return DXGI_FORMAT_R16_UNORM;
        case 0x0000002E: /* Depth24Plus */
            return DXGI_FORMAT_R32_FLOAT;
        case 0x0000002F: /* Depth24PlusStencil8 */
            return aspect == 0x00000002 ? DXGI_FORMAT_X24_TYPELESS_G8_UINT : DXGI_FORMAT_R24_UNORM_X8_TYPELESS;
        case 0x00000030: /* Depth32Float */
            return DXGI_FORMAT_R32_FLOAT;
        case 0x00000031: /* Depth32FloatStencil8 */
            return aspect == 0x00000002 ? DXGI_FORMAT_X32_TYPELESS_G8X24_UINT : DXGI_FORMAT_R32_FLOAT_X8X24_TYPELESS;
        default:
            return map_wgpu_format_to_dxgi(format);
    }
}

static D3D12_RESOURCE_FLAGS map_wgpu_usage_to_d3d12_flags(uint32_t format, uint32_t usage) {
    D3D12_RESOURCE_FLAGS flags = D3D12_RESOURCE_FLAG_NONE;
    if (usage & 0x0000000000000010) {
        if (format == 0x0000002C ||
            format == 0x0000002D ||
            format == 0x0000002E ||
            format == 0x0000002F ||
            format == 0x00000030 ||
            format == 0x00000031) {
            flags |= D3D12_RESOURCE_FLAG_ALLOW_DEPTH_STENCIL;
        } else {
            flags |= D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET; /* RenderAttachment */
        }
    }
    if (usage & 0x0000000000000008) flags |= D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS; /* StorageBinding */
    return flags;
}

D3D12Handle d3d12_bridge_device_create_texture_2d(D3D12Handle device_h, uint32_t width, uint32_t height,
                                                    uint32_t mip_levels, uint32_t format, uint32_t usage_flags) {
    return d3d12_bridge_device_create_texture_2d_layered(
        device_h,
        width,
        height,
        1,
        mip_levels,
        1,
        format,
        usage_flags);
}

D3D12Handle d3d12_bridge_device_create_texture_2d_layered(
    D3D12Handle device_h,
    uint32_t width,
    uint32_t height,
    uint32_t array_layers,
    uint32_t mip_levels,
    uint32_t sample_count,
    uint32_t format,
    uint32_t usage_flags) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    const uint32_t resolved_layers = array_layers == 0 ? 1 : array_layers;
    const uint32_t resolved_samples = sample_count == 0 ? 1 : sample_count;

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
    desc.DepthOrArraySize   = (UINT16)resolved_layers;
    desc.MipLevels          = (UINT16)(mip_levels == 0 ? 1 : mip_levels);
    desc.Format             = map_wgpu_format_to_dxgi(format);
    desc.SampleDesc.Count   = resolved_samples;
    desc.SampleDesc.Quality = 0;
    desc.Layout             = D3D12_TEXTURE_LAYOUT_UNKNOWN;
    desc.Flags              = map_wgpu_usage_to_d3d12_flags(format, usage_flags);

    D3D12_RESOURCE_STATES initial = D3D12_RESOURCE_STATE_COPY_DEST;
    if (usage_flags & 0x0000000000000010) {
        if (desc.Flags & D3D12_RESOURCE_FLAG_ALLOW_DEPTH_STENCIL) {
            initial = D3D12_RESOURCE_STATE_DEPTH_WRITE;
        } else {
            initial = D3D12_RESOURCE_STATE_RENDER_TARGET;
        }
    } else if (usage_flags & 0x0000000000000008) {
        initial = D3D12_RESOURCE_STATE_UNORDERED_ACCESS;
    }

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
    d3d12_bridge_command_list_copy_texture_region_subresource(
        cmd_list_h,
        dst_texture_h,
        0,
        src_buffer_h,
        src_offset,
        width,
        height,
        1,
        bytes_per_row,
        format);
}

void d3d12_bridge_command_list_copy_texture_region_subresource(
    D3D12Handle cmd_list_h,
    D3D12Handle dst_texture_h,
    uint32_t subresource_index,
    D3D12Handle src_buffer_h,
    uint64_t src_offset,
    uint32_t width,
    uint32_t height,
    uint32_t depth,
    uint32_t bytes_per_row,
    uint32_t format) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12Resource* dst = (ID3D12Resource*)dst_texture_h;
    ID3D12Resource* src = (ID3D12Resource*)src_buffer_h;

    D3D12_TEXTURE_COPY_LOCATION dst_loc;
    dst_loc.pResource        = dst;
    dst_loc.Type             = D3D12_TEXTURE_COPY_TYPE_SUBRESOURCE_INDEX;
    dst_loc.SubresourceIndex = subresource_index;

    D3D12_TEXTURE_COPY_LOCATION src_loc;
    src_loc.pResource                            = src;
    src_loc.Type                                 = D3D12_TEXTURE_COPY_TYPE_PLACED_FOOTPRINT;
    src_loc.PlacedFootprint.Offset               = src_offset;
    src_loc.PlacedFootprint.Footprint.Format     = map_wgpu_format_to_dxgi(format);
    src_loc.PlacedFootprint.Footprint.Width      = width;
    src_loc.PlacedFootprint.Footprint.Height     = height;
    src_loc.PlacedFootprint.Footprint.Depth      = depth == 0 ? 1 : depth;
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

static D3D12_TEXTURE_ADDRESS_MODE map_wgpu_address_mode(uint32_t mode) {
    switch (mode) {
        case 0x00000001: return D3D12_TEXTURE_ADDRESS_MODE_CLAMP;
        case 0x00000003: return D3D12_TEXTURE_ADDRESS_MODE_MIRROR;
        case 0x00000002:
        default:         return D3D12_TEXTURE_ADDRESS_MODE_WRAP;
    }
}

static D3D12_FILTER map_wgpu_sampler_filter(uint32_t min_filter,
                                            uint32_t mag_filter,
                                            uint32_t mipmap_filter,
                                            uint32_t compare,
                                            uint16_t max_anisotropy) {
    const int comparison = compare != 0;
    const int anisotropic = max_anisotropy > 1;
    if (anisotropic) {
        return comparison ? D3D12_FILTER_COMPARISON_ANISOTROPIC : D3D12_FILTER_ANISOTROPIC;
    }

    const int min_linear = min_filter == 0x00000002;
    const int mag_linear = mag_filter == 0x00000002;
    const int mip_linear = mipmap_filter == 0x00000002;

    if (comparison) {
        if (!min_linear && !mag_linear && !mip_linear) return D3D12_FILTER_COMPARISON_MIN_MAG_MIP_POINT;
        if (!min_linear && !mag_linear && mip_linear)  return D3D12_FILTER_COMPARISON_MIN_MAG_POINT_MIP_LINEAR;
        if (!min_linear && mag_linear && !mip_linear)  return D3D12_FILTER_COMPARISON_MIN_POINT_MAG_LINEAR_MIP_POINT;
        if (!min_linear && mag_linear && mip_linear)   return D3D12_FILTER_COMPARISON_MIN_POINT_MAG_MIP_LINEAR;
        if (min_linear && !mag_linear && !mip_linear)  return D3D12_FILTER_COMPARISON_MIN_LINEAR_MAG_MIP_POINT;
        if (min_linear && !mag_linear && mip_linear)   return D3D12_FILTER_COMPARISON_MIN_LINEAR_MAG_POINT_MIP_LINEAR;
        if (min_linear && mag_linear && !mip_linear)   return D3D12_FILTER_COMPARISON_MIN_MAG_LINEAR_MIP_POINT;
        return D3D12_FILTER_COMPARISON_MIN_MAG_MIP_LINEAR;
    }

    if (!min_linear && !mag_linear && !mip_linear) return D3D12_FILTER_MIN_MAG_MIP_POINT;
    if (!min_linear && !mag_linear && mip_linear)  return D3D12_FILTER_MIN_MAG_POINT_MIP_LINEAR;
    if (!min_linear && mag_linear && !mip_linear)  return D3D12_FILTER_MIN_POINT_MAG_LINEAR_MIP_POINT;
    if (!min_linear && mag_linear && mip_linear)   return D3D12_FILTER_MIN_POINT_MAG_MIP_LINEAR;
    if (min_linear && !mag_linear && !mip_linear)  return D3D12_FILTER_MIN_LINEAR_MAG_MIP_POINT;
    if (min_linear && !mag_linear && mip_linear)   return D3D12_FILTER_MIN_LINEAR_MAG_POINT_MIP_LINEAR;
    if (min_linear && mag_linear && !mip_linear)   return D3D12_FILTER_MIN_MAG_LINEAR_MIP_POINT;
    return D3D12_FILTER_MIN_MAG_MIP_LINEAR;
}

static D3D12_COMPARISON_FUNC map_wgpu_compare(uint32_t compare);

D3D12Handle d3d12_bridge_device_create_sampler(D3D12Handle device_h,
                                                 uint32_t min_filter,
                                                 uint32_t mag_filter,
                                                 uint32_t mipmap_filter,
                                                 uint32_t address_mode_u,
                                                 uint32_t address_mode_v,
                                                 uint32_t address_mode_w,
                                                 float lod_min_clamp,
                                                 float lod_max_clamp,
                                                 uint32_t compare,
                                                 uint16_t max_anisotropy) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    if (device == NULL) return NULL;

    ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)d3d12_bridge_device_create_sampler_heap(device_h, 1);
    if (heap == NULL) return NULL;

    D3D12_CPU_DESCRIPTOR_HANDLE handle;
    heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap, &handle);

    D3D12_SAMPLER_DESC desc;
    memset(&desc, 0, sizeof(desc));
    desc.Filter = map_wgpu_sampler_filter(min_filter, mag_filter, mipmap_filter, compare, max_anisotropy);
    desc.AddressU = map_wgpu_address_mode(address_mode_u);
    desc.AddressV = map_wgpu_address_mode(address_mode_v);
    desc.AddressW = map_wgpu_address_mode(address_mode_w);
    desc.MipLODBias = 0.0f;
    desc.MaxAnisotropy = max_anisotropy > 1 ? (UINT)(max_anisotropy > 16 ? 16 : max_anisotropy) : 1;
    desc.ComparisonFunc = compare != 0 ? map_wgpu_compare(compare) : D3D12_COMPARISON_FUNC_ALWAYS;
    desc.BorderColor[0] = 0.0f;
    desc.BorderColor[1] = 0.0f;
    desc.BorderColor[2] = 0.0f;
    desc.BorderColor[3] = 0.0f;
    desc.MinLOD = lod_min_clamp;
    desc.MaxLOD = lod_max_clamp;

    device->lpVtbl->CreateSampler(device, &desc, handle);
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

static DXGI_FORMAT map_depth_format(uint32_t format);

static D3D12_PRIMITIVE_TOPOLOGY_TYPE map_wgpu_topology_type(uint32_t topology_type, uint32_t topology) {
    if (topology_type != 0) return (D3D12_PRIMITIVE_TOPOLOGY_TYPE)topology_type;
    switch (topology) {
        case 0x00000001: return D3D12_PRIMITIVE_TOPOLOGY_TYPE_POINT;
        case 0x00000002:
        case 0x00000003: return D3D12_PRIMITIVE_TOPOLOGY_TYPE_LINE;
        case 0x00000004:
        case 0x00000005: return D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
        default:         return D3D12_PRIMITIVE_TOPOLOGY_TYPE_TRIANGLE;
    }
}

static D3D12_CULL_MODE map_wgpu_cull_mode(uint32_t cull_mode) {
    switch (cull_mode) {
        case 0x00000002: return D3D12_CULL_MODE_FRONT;
        case 0x00000003: return D3D12_CULL_MODE_BACK;
        case 0x00000001:
        default:         return D3D12_CULL_MODE_NONE;
    }
}

static D3D12_BLEND_OP map_wgpu_blend_op(uint32_t op) {
    switch (op) {
        case 0x00000002: return D3D12_BLEND_OP_SUBTRACT;
        case 0x00000003: return D3D12_BLEND_OP_REV_SUBTRACT;
        case 0x00000004: return D3D12_BLEND_OP_MIN;
        case 0x00000005: return D3D12_BLEND_OP_MAX;
        case 0x00000001:
        default:         return D3D12_BLEND_OP_ADD;
    }
}

static D3D12_BLEND map_wgpu_blend_factor(uint32_t factor) {
    switch (factor) {
        case 0x00000001: return D3D12_BLEND_ZERO;
        case 0x00000002: return D3D12_BLEND_ONE;
        case 0x00000003: return D3D12_BLEND_SRC_COLOR;
        case 0x00000004: return D3D12_BLEND_INV_SRC_COLOR;
        case 0x00000005: return D3D12_BLEND_SRC_ALPHA;
        case 0x00000006: return D3D12_BLEND_INV_SRC_ALPHA;
        case 0x00000007: return D3D12_BLEND_DEST_COLOR;
        case 0x00000008: return D3D12_BLEND_INV_DEST_COLOR;
        case 0x00000009: return D3D12_BLEND_DEST_ALPHA;
        case 0x0000000A: return D3D12_BLEND_INV_DEST_ALPHA;
        case 0x0000000B: return D3D12_BLEND_SRC_ALPHA_SAT;
        case 0x0000000C: return D3D12_BLEND_BLEND_FACTOR;
        case 0x0000000D: return D3D12_BLEND_INV_BLEND_FACTOR;
        case 0x0000000E: return D3D12_BLEND_SRC1_COLOR;
        case 0x0000000F: return D3D12_BLEND_INV_SRC1_COLOR;
        case 0x00000010: return D3D12_BLEND_SRC1_ALPHA;
        case 0x00000011: return D3D12_BLEND_INV_SRC1_ALPHA;
        default:         return D3D12_BLEND_ONE;
    }
}

static D3D12_COMPARISON_FUNC map_wgpu_compare(uint32_t compare) {
    switch (compare) {
        case 0x00000001: return D3D12_COMPARISON_FUNC_NEVER;
        case 0x00000002: return D3D12_COMPARISON_FUNC_LESS;
        case 0x00000003: return D3D12_COMPARISON_FUNC_EQUAL;
        case 0x00000004: return D3D12_COMPARISON_FUNC_LESS_EQUAL;
        case 0x00000005: return D3D12_COMPARISON_FUNC_GREATER;
        case 0x00000006: return D3D12_COMPARISON_FUNC_NOT_EQUAL;
        case 0x00000007: return D3D12_COMPARISON_FUNC_GREATER_EQUAL;
        case 0x00000008:
        default:         return D3D12_COMPARISON_FUNC_ALWAYS;
    }
}

static D3D12_STENCIL_OP map_wgpu_stencil_op(uint32_t op) {
    switch (op) {
        case 0x00000001: return D3D12_STENCIL_OP_ZERO;
        case 0x00000002: return D3D12_STENCIL_OP_REPLACE;
        case 0x00000003: return D3D12_STENCIL_OP_INVERT;
        case 0x00000004: return D3D12_STENCIL_OP_INCR_SAT;
        case 0x00000005: return D3D12_STENCIL_OP_DECR_SAT;
        case 0x00000006: return D3D12_STENCIL_OP_INCR;
        case 0x00000007: return D3D12_STENCIL_OP_DECR;
        case 0x00000000:
        default:         return D3D12_STENCIL_OP_KEEP;
    }
}

static UINT mask_color_write(uint32_t mask) {
    UINT d3d_mask = 0;
    if (mask & 0x1u) d3d_mask |= D3D12_COLOR_WRITE_ENABLE_RED;
    if (mask & 0x2u) d3d_mask |= D3D12_COLOR_WRITE_ENABLE_GREEN;
    if (mask & 0x4u) d3d_mask |= D3D12_COLOR_WRITE_ENABLE_BLUE;
    if (mask & 0x8u) d3d_mask |= D3D12_COLOR_WRITE_ENABLE_ALPHA;
    return d3d_mask;
}

typedef HRESULT (WINAPI *PFN_D3DCOMPILE)(
    LPCVOID,
    SIZE_T,
    LPCSTR,
    const D3D_SHADER_MACRO*,
    ID3DInclude*,
    LPCSTR,
    LPCSTR,
    UINT,
    UINT,
    ID3DBlob**,
    ID3DBlob**);

static PFN_D3DCOMPILE load_d3d_compile(void) {
    static PFN_D3DCOMPILE fn = NULL;
    static int attempted = 0;
    if (attempted) return fn;
    attempted = 1;
    HMODULE compiler = LoadLibraryA("d3dcompiler_47.dll");
    if (compiler == NULL) compiler = LoadLibraryA("d3dcompiler_46.dll");
    if (compiler == NULL) compiler = LoadLibraryA("d3dcompiler_43.dll");
    if (compiler == NULL) return NULL;
    fn = (PFN_D3DCOMPILE)GetProcAddress(compiler, "D3DCompile");
    return fn;
}

static ID3DBlob* compile_hlsl_blob(const char* source, size_t source_len, const char* entry, const char* target) {
    PFN_D3DCOMPILE compile_fn = load_d3d_compile();
    if (compile_fn == NULL || source == NULL || entry == NULL || target == NULL) return NULL;

    ID3DBlob* code = NULL;
    ID3DBlob* errors = NULL;
    UINT flags = D3DCOMPILE_ENABLE_STRICTNESS | D3DCOMPILE_OPTIMIZATION_LEVEL3;
    HRESULT hr = compile_fn(source, source_len, "doe_d3d12", NULL, NULL, entry, target, flags, 0, &code, &errors);
    if (errors) errors->lpVtbl->Release(errors);
    if (FAILED(hr)) {
        if (code) code->lpVtbl->Release(code);
        return NULL;
    }
    return code;
}

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

D3D12Handle d3d12_bridge_device_create_graphics_pipeline_hlsl(
    D3D12Handle device_h,
    D3D12Handle root_sig_h,
    const char* vs_source,
    size_t vs_source_len,
    const char* vs_entry,
    const char* ps_source,
    size_t ps_source_len,
    const char* ps_entry,
    const D3D12GraphicsPipelineDesc* pipeline_desc,
    const D3D12InputElementDesc* input_elements,
    uint32_t input_element_count) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12RootSignature* root_sig = (ID3D12RootSignature*)root_sig_h;
    if (device == NULL || root_sig == NULL || pipeline_desc == NULL) return NULL;

    ID3DBlob* vs_blob = compile_hlsl_blob(vs_source, vs_source_len, vs_entry, "vs_5_0");
    if (vs_blob == NULL) return NULL;
    ID3DBlob* ps_blob = compile_hlsl_blob(ps_source, ps_source_len, ps_entry, "ps_5_0");
    if (ps_blob == NULL) {
        vs_blob->lpVtbl->Release(vs_blob);
        return NULL;
    }

    D3D12_INPUT_ELEMENT_DESC stack_elements[16];
    D3D12_INPUT_ELEMENT_DESC* native_elements = NULL;
    if (input_element_count > 0) {
        if (input_element_count <= 16) {
            native_elements = stack_elements;
        } else {
            native_elements = (D3D12_INPUT_ELEMENT_DESC*)calloc(input_element_count, sizeof(D3D12_INPUT_ELEMENT_DESC));
            if (native_elements == NULL) {
                vs_blob->lpVtbl->Release(vs_blob);
                ps_blob->lpVtbl->Release(ps_blob);
                return NULL;
            }
        }
        for (uint32_t i = 0; i < input_element_count; ++i) {
            native_elements[i].SemanticName = "ATTR";
            native_elements[i].SemanticIndex = input_elements[i].semantic_index;
            native_elements[i].Format = (DXGI_FORMAT)input_elements[i].format;
            native_elements[i].InputSlot = input_elements[i].input_slot;
            native_elements[i].AlignedByteOffset = input_elements[i].aligned_byte_offset;
            native_elements[i].InputSlotClass = (D3D12_INPUT_CLASSIFICATION)input_elements[i].input_slot_class;
            native_elements[i].InstanceDataStepRate = input_elements[i].instance_data_step_rate;
        }
    }

    D3D12_GRAPHICS_PIPELINE_STATE_DESC desc;
    memset(&desc, 0, sizeof(desc));
    desc.pRootSignature = root_sig;
    desc.VS.pShaderBytecode = vs_blob->lpVtbl->GetBufferPointer(vs_blob);
    desc.VS.BytecodeLength = vs_blob->lpVtbl->GetBufferSize(vs_blob);
    desc.PS.pShaderBytecode = ps_blob->lpVtbl->GetBufferPointer(ps_blob);
    desc.PS.BytecodeLength = ps_blob->lpVtbl->GetBufferSize(ps_blob);
    desc.InputLayout.pInputElementDescs = native_elements;
    desc.InputLayout.NumElements = input_element_count;
    desc.SampleMask = UINT_MAX;
    desc.RasterizerState.FillMode = D3D12_FILL_MODE_SOLID;
    desc.RasterizerState.CullMode = map_wgpu_cull_mode(pipeline_desc->cull_mode);
    desc.RasterizerState.FrontCounterClockwise = pipeline_desc->front_face == 0x00000001 ? TRUE : FALSE;
    desc.RasterizerState.DepthBias = pipeline_desc->depth_bias;
    desc.RasterizerState.DepthBiasClamp = pipeline_desc->depth_bias_clamp;
    desc.RasterizerState.SlopeScaledDepthBias = pipeline_desc->depth_bias_slope_scale;
    desc.RasterizerState.DepthClipEnable = pipeline_desc->unclipped_depth ? FALSE : TRUE;
    desc.BlendState.AlphaToCoverageEnable = FALSE;
    desc.BlendState.IndependentBlendEnable = FALSE;
    desc.BlendState.RenderTarget[0].BlendEnable = pipeline_desc->blend_enabled ? TRUE : FALSE;
    desc.BlendState.RenderTarget[0].LogicOpEnable = FALSE;
    desc.BlendState.RenderTarget[0].SrcBlend = map_wgpu_blend_factor(pipeline_desc->color_src_factor);
    desc.BlendState.RenderTarget[0].DestBlend = map_wgpu_blend_factor(pipeline_desc->color_dst_factor);
    desc.BlendState.RenderTarget[0].BlendOp = map_wgpu_blend_op(pipeline_desc->color_operation);
    desc.BlendState.RenderTarget[0].SrcBlendAlpha = map_wgpu_blend_factor(pipeline_desc->alpha_src_factor);
    desc.BlendState.RenderTarget[0].DestBlendAlpha = map_wgpu_blend_factor(pipeline_desc->alpha_dst_factor);
    desc.BlendState.RenderTarget[0].BlendOpAlpha = map_wgpu_blend_op(pipeline_desc->alpha_operation);
    desc.BlendState.RenderTarget[0].RenderTargetWriteMask = mask_color_write(pipeline_desc->color_write_mask);
    desc.DepthStencilState.DepthEnable = pipeline_desc->depth_stencil_format != 0 ? TRUE : FALSE;
    desc.DepthStencilState.DepthWriteMask = pipeline_desc->depth_write_enabled ? D3D12_DEPTH_WRITE_MASK_ALL : D3D12_DEPTH_WRITE_MASK_ZERO;
    desc.DepthStencilState.DepthFunc = map_wgpu_compare(pipeline_desc->depth_compare);
    desc.DepthStencilState.StencilEnable =
        (pipeline_desc->stencil_front_compare != 0x00000008 || pipeline_desc->stencil_back_compare != 0x00000008 ||
         pipeline_desc->stencil_front_fail_op != 0 || pipeline_desc->stencil_front_depth_fail_op != 0 ||
         pipeline_desc->stencil_front_pass_op != 0 || pipeline_desc->stencil_back_fail_op != 0 ||
         pipeline_desc->stencil_back_depth_fail_op != 0 || pipeline_desc->stencil_back_pass_op != 0 ||
         pipeline_desc->stencil_read_mask != 0xFFFFFFFFu || pipeline_desc->stencil_write_mask != 0xFFFFFFFFu) ? TRUE : FALSE;
    desc.DepthStencilState.StencilReadMask = (UINT8)(pipeline_desc->stencil_read_mask & 0xFFu);
    desc.DepthStencilState.StencilWriteMask = (UINT8)(pipeline_desc->stencil_write_mask & 0xFFu);
    desc.DepthStencilState.FrontFace.StencilFunc = map_wgpu_compare(pipeline_desc->stencil_front_compare);
    desc.DepthStencilState.FrontFace.StencilFailOp = map_wgpu_stencil_op(pipeline_desc->stencil_front_fail_op);
    desc.DepthStencilState.FrontFace.StencilDepthFailOp = map_wgpu_stencil_op(pipeline_desc->stencil_front_depth_fail_op);
    desc.DepthStencilState.FrontFace.StencilPassOp = map_wgpu_stencil_op(pipeline_desc->stencil_front_pass_op);
    desc.DepthStencilState.BackFace.StencilFunc = map_wgpu_compare(pipeline_desc->stencil_back_compare);
    desc.DepthStencilState.BackFace.StencilFailOp = map_wgpu_stencil_op(pipeline_desc->stencil_back_fail_op);
    desc.DepthStencilState.BackFace.StencilDepthFailOp = map_wgpu_stencil_op(pipeline_desc->stencil_back_depth_fail_op);
    desc.DepthStencilState.BackFace.StencilPassOp = map_wgpu_stencil_op(pipeline_desc->stencil_back_pass_op);
    desc.PrimitiveTopologyType = map_wgpu_topology_type(pipeline_desc->topology_type, pipeline_desc->topology);
    desc.NumRenderTargets = 1;
    desc.RTVFormats[0] = map_wgpu_format_to_dxgi(pipeline_desc->target_format);
    desc.DSVFormat = pipeline_desc->depth_stencil_format != 0
        ? map_depth_format(pipeline_desc->depth_stencil_format)
        : DXGI_FORMAT_UNKNOWN;
    desc.SampleDesc.Count = pipeline_desc->sample_count == 0 ? 1 : pipeline_desc->sample_count;
    desc.SampleDesc.Quality = 0;

    ID3D12PipelineState* pso = NULL;
    HRESULT hr = device->lpVtbl->CreateGraphicsPipelineState(device, &desc, &IID_ID3D12PipelineState, (void**)&pso);

    if (native_elements != NULL && native_elements != stack_elements) free(native_elements);
    vs_blob->lpVtbl->Release(vs_blob);
    ps_blob->lpVtbl->Release(ps_blob);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)pso;
}

/* --- Render commands --- */

void d3d12_bridge_command_list_set_graphics_root_signature(D3D12Handle cmd_list_h, D3D12Handle root_sig_h) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12RootSignature* root_sig  = (ID3D12RootSignature*)root_sig_h;
    cmd->lpVtbl->SetGraphicsRootSignature(cmd, root_sig);
}

void d3d12_bridge_command_list_set_render_targets(
    D3D12Handle cmd_list_h,
    D3D12Handle rtv_heap_h,
    uint32_t rtv_index,
    D3D12Handle dsv_heap_h,
    uint32_t dsv_index) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12DescriptorHeap* rtv_heap = (ID3D12DescriptorHeap*)rtv_heap_h;
    ID3D12DescriptorHeap* dsv_heap = (ID3D12DescriptorHeap*)dsv_heap_h;
    D3D12_CPU_DESCRIPTOR_HANDLE rtv_handle;
    rtv_heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(rtv_heap, &rtv_handle);
    (void)rtv_index;
    if (dsv_heap != NULL) {
        D3D12_CPU_DESCRIPTOR_HANDLE dsv_handle;
        dsv_heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(dsv_heap, &dsv_handle);
        (void)dsv_index;
        cmd->lpVtbl->OMSetRenderTargets(cmd, 1, &rtv_handle, FALSE, &dsv_handle);
    } else {
        cmd->lpVtbl->OMSetRenderTargets(cmd, 1, &rtv_handle, FALSE, NULL);
    }
}

void d3d12_bridge_command_list_set_render_target(D3D12Handle cmd_list_h, D3D12Handle rtv_heap_h, uint32_t index) {
    d3d12_bridge_command_list_set_render_targets(cmd_list_h, rtv_heap_h, index, NULL, 0);
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

void d3d12_bridge_command_list_set_blend_factor(D3D12Handle cmd_list_h, const float rgba[4]) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    cmd->lpVtbl->OMSetBlendFactor(cmd, rgba);
}

void d3d12_bridge_command_list_set_stencil_ref(D3D12Handle cmd_list_h, uint32_t reference) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    cmd->lpVtbl->OMSetStencilRef(cmd, reference);
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

void d3d12_bridge_command_list_ia_set_vertex_buffers(D3D12Handle cmd_list_h, uint32_t start_slot,
                                                      uint32_t num_views, D3D12Handle buffer_h,
                                                      uint32_t size_in_bytes, uint32_t stride_in_bytes,
                                                      uint64_t offset) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12Resource* buffer = (ID3D12Resource*)buffer_h;
    if (cmd == NULL || buffer == NULL || num_views == 0) return;

    D3D12_RESOURCE_DESC desc = buffer->lpVtbl->GetDesc(buffer);
    UINT64 total_size = desc.Width;
    if (offset >= total_size) return;

    D3D12_VERTEX_BUFFER_VIEW view;
    view.BufferLocation = buffer->lpVtbl->GetGPUVirtualAddress(buffer) + offset;
    view.SizeInBytes = size_in_bytes != 0 && (UINT64)size_in_bytes <= total_size - offset
        ? size_in_bytes
        : (UINT)(total_size - offset);
    view.StrideInBytes = stride_in_bytes;
    cmd->lpVtbl->IASetVertexBuffers(cmd, start_slot, 1, &view);
}

void d3d12_bridge_command_list_ia_set_index_buffer(D3D12Handle cmd_list_h, D3D12Handle buffer_h,
                                                    uint32_t format, uint32_t size_in_bytes,
                                                    uint64_t offset) {
    ID3D12GraphicsCommandList* cmd = (ID3D12GraphicsCommandList*)cmd_list_h;
    ID3D12Resource* buffer = (ID3D12Resource*)buffer_h;
    if (cmd == NULL || buffer == NULL) return;

    D3D12_RESOURCE_DESC desc = buffer->lpVtbl->GetDesc(buffer);
    UINT64 total_size = desc.Width;
    if (offset >= total_size) return;

    DXGI_FORMAT dxgi_format;
    switch (format) {
        case 0x00000001:
        case DXGI_FORMAT_R16_UINT:
            dxgi_format = DXGI_FORMAT_R16_UINT;
            break;
        case 0x00000002:
        case DXGI_FORMAT_R32_UINT:
            dxgi_format = DXGI_FORMAT_R32_UINT;
            break;
        default:
            return;
    }

    D3D12_INDEX_BUFFER_VIEW view;
    view.BufferLocation = buffer->lpVtbl->GetGPUVirtualAddress(buffer) + offset;
    view.SizeInBytes = size_in_bytes != 0 && (UINT64)size_in_bytes <= total_size - offset
        ? size_in_bytes
        : (UINT)(total_size - offset);
    view.Format = dxgi_format;
    cmd->lpVtbl->IASetIndexBuffer(cmd, &view);
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
        case 0x0000002C: return DXGI_FORMAT_D24_UNORM_S8_UINT;    /* Stencil8 */
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
                                                uint32_t aspect, uint32_t base_mip, uint32_t mip_count,
                                                uint32_t base_array_layer, uint32_t array_layer_count) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12Resource* resource = (ID3D12Resource*)resource_h;
    ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)heap_h;
    const uint32_t resolved_layers = array_layer_count == 0 ? 1 : array_layer_count;

    UINT incr = device->lpVtbl->GetDescriptorHandleIncrementSize(device, D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
    D3D12_CPU_DESCRIPTOR_HANDLE handle;
    heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap, &handle);
    handle.ptr += (SIZE_T)(incr * index);

    D3D12_SHADER_RESOURCE_VIEW_DESC srv_desc;
    memset(&srv_desc, 0, sizeof(srv_desc));
    srv_desc.Format                        = map_wgpu_format_to_dxgi_view(format, aspect);
    srv_desc.Shader4ComponentMapping       = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
    if (base_array_layer > 0 || resolved_layers > 1) {
        srv_desc.ViewDimension                     = D3D12_SRV_DIMENSION_TEXTURE2DARRAY;
        srv_desc.Texture2DArray.MostDetailedMip   = base_mip;
        srv_desc.Texture2DArray.MipLevels         = mip_count == 0 ? (UINT)-1 : mip_count;
        srv_desc.Texture2DArray.FirstArraySlice   = base_array_layer;
        srv_desc.Texture2DArray.ArraySize         = resolved_layers;
        srv_desc.Texture2DArray.PlaneSlice        = 0;
        srv_desc.Texture2DArray.ResourceMinLODClamp = 0.0f;
    } else {
        srv_desc.ViewDimension                 = D3D12_SRV_DIMENSION_TEXTURE2D;
        srv_desc.Texture2D.MostDetailedMip     = base_mip;
        srv_desc.Texture2D.MipLevels           = mip_count == 0 ? (UINT)-1 : mip_count;
        srv_desc.Texture2D.PlaneSlice          = 0;
        srv_desc.Texture2D.ResourceMinLODClamp = 0.0f;
    }

    device->lpVtbl->CreateShaderResourceView(device, resource, &srv_desc, handle);
}

void d3d12_bridge_device_create_srv_texture_cube(D3D12Handle device_h, D3D12Handle resource_h,
                                                  D3D12Handle heap_h, uint32_t index, uint32_t format,
                                                  uint32_t aspect, uint32_t base_mip, uint32_t mip_count,
                                                  uint32_t base_array_layer, uint32_t array_layer_count) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12Resource* resource = (ID3D12Resource*)resource_h;
    ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)heap_h;
    const uint32_t resolved_layers = array_layer_count == 0 ? 6 : array_layer_count;
    const uint32_t resolved_cube_count = resolved_layers / 6;

    UINT incr = device->lpVtbl->GetDescriptorHandleIncrementSize(device, D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
    D3D12_CPU_DESCRIPTOR_HANDLE handle;
    heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap, &handle);
    handle.ptr += (SIZE_T)(incr * index);

    D3D12_SHADER_RESOURCE_VIEW_DESC srv_desc;
    memset(&srv_desc, 0, sizeof(srv_desc));
    srv_desc.Format                           = map_wgpu_format_to_dxgi_view(format, aspect);
    srv_desc.Shader4ComponentMapping          = D3D12_DEFAULT_SHADER_4_COMPONENT_MAPPING;
    if (base_array_layer > 0 || resolved_layers > 6) {
        srv_desc.ViewDimension                            = D3D12_SRV_DIMENSION_TEXTURECUBEARRAY;
        srv_desc.TextureCubeArray.MostDetailedMip         = base_mip;
        srv_desc.TextureCubeArray.MipLevels               = mip_count == 0 ? (UINT)-1 : mip_count;
        srv_desc.TextureCubeArray.First2DArrayFace        = base_array_layer;
        srv_desc.TextureCubeArray.NumCubes                = resolved_cube_count == 0 ? 1 : resolved_cube_count;
        srv_desc.TextureCubeArray.ResourceMinLODClamp     = 0.0f;
    } else {
        srv_desc.ViewDimension                    = D3D12_SRV_DIMENSION_TEXTURECUBE;
        srv_desc.TextureCube.MostDetailedMip      = base_mip;
        srv_desc.TextureCube.MipLevels            = mip_count == 0 ? (UINT)-1 : mip_count;
        srv_desc.TextureCube.ResourceMinLODClamp  = 0.0f;
    }

    device->lpVtbl->CreateShaderResourceView(device, resource, &srv_desc, handle);
}

void d3d12_bridge_device_create_srv_texture_3d(D3D12Handle device_h, D3D12Handle resource_h,
                                                D3D12Handle heap_h, uint32_t index, uint32_t format,
                                                uint32_t aspect, uint32_t base_mip, uint32_t mip_count) {
    ID3D12Device* device = (ID3D12Device*)device_h;
    ID3D12Resource* resource = (ID3D12Resource*)resource_h;
    ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)heap_h;

    UINT incr = device->lpVtbl->GetDescriptorHandleIncrementSize(device, D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
    D3D12_CPU_DESCRIPTOR_HANDLE handle;
    heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap, &handle);
    handle.ptr += (SIZE_T)(incr * index);

    D3D12_SHADER_RESOURCE_VIEW_DESC srv_desc;
    memset(&srv_desc, 0, sizeof(srv_desc));
    srv_desc.Format                          = map_wgpu_format_to_dxgi_view(format, aspect);
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

D3D12Handle d3d12_bridge_texture_create_view(D3D12Handle texture_h, uint32_t format, uint32_t dimension,
                                               uint32_t aspect, uint32_t base_mip, uint32_t mip_count,
                                               uint32_t base_array_layer, uint32_t array_layer_count,
                                               uint64_t usage_flags) {
    ID3D12Resource* resource = (ID3D12Resource*)texture_h;
    if (resource == NULL) return NULL;

    ID3D12Device* device = NULL;
    HRESULT hr = resource->lpVtbl->GetDevice(resource, &IID_ID3D12Device, (void**)&device);
    if (FAILED(hr) || device == NULL) return NULL;

    D3D12Handle heap_h = d3d12_bridge_device_create_cbv_srv_uav_heap((D3D12Handle)device, 1);
    if (heap_h == NULL) {
        device->lpVtbl->Release(device);
        return NULL;
    }

    const int storage_only =
        (usage_flags & 0x0000000000000008ull) != 0 &&
        (usage_flags & 0x0000000000000004ull) == 0;

    if (storage_only) {
        ID3D12DescriptorHeap* heap = (ID3D12DescriptorHeap*)heap_h;
        D3D12_RESOURCE_DESC desc;
        resource->lpVtbl->GetDesc(resource, &desc);

        UINT incr = device->lpVtbl->GetDescriptorHandleIncrementSize(device, D3D12_DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV);
        D3D12_CPU_DESCRIPTOR_HANDLE handle;
        heap->lpVtbl->GetCPUDescriptorHandleForHeapStart(heap, &handle);

        D3D12_UNORDERED_ACCESS_VIEW_DESC uav_desc;
        memset(&uav_desc, 0, sizeof(uav_desc));
        uav_desc.Format = map_wgpu_format_to_dxgi(format);

        switch (dimension) {
            case 0x00000002: /* 2D */
            case 0x00000007: /* 2DDepth */
                uav_desc.ViewDimension = D3D12_UAV_DIMENSION_TEXTURE2D;
                uav_desc.Texture2D.MipSlice = base_mip;
                break;
            case 0x00000003: /* 2DArray */
            case 0x00000008: { /* 2DArrayDepth */
                const UINT resolved_layers = array_layer_count == 0
                    ? (UINT)((desc.DepthOrArraySize > base_array_layer) ? (desc.DepthOrArraySize - base_array_layer) : 1)
                    : (UINT)array_layer_count;
                uav_desc.ViewDimension = D3D12_UAV_DIMENSION_TEXTURE2DARRAY;
                uav_desc.Texture2DArray.MipSlice = base_mip;
                uav_desc.Texture2DArray.FirstArraySlice = base_array_layer;
                uav_desc.Texture2DArray.ArraySize = resolved_layers;
                uav_desc.Texture2DArray.PlaneSlice = 0;
                break;
            }
            case 0x00000006: { /* 3D */
                const UINT resolved_depth = array_layer_count == 0
                    ? (UINT)((desc.DepthOrArraySize > base_array_layer) ? (desc.DepthOrArraySize - base_array_layer) : 1)
                    : (UINT)array_layer_count;
                uav_desc.ViewDimension = D3D12_UAV_DIMENSION_TEXTURE3D;
                uav_desc.Texture3D.MipSlice = base_mip;
                uav_desc.Texture3D.FirstWSlice = base_array_layer;
                uav_desc.Texture3D.WSize = resolved_depth;
                break;
            }
            default:
                d3d12_bridge_release(heap_h);
                device->lpVtbl->Release(device);
                return NULL;
        }

        device->lpVtbl->CreateUnorderedAccessView(device, resource, NULL, &uav_desc, handle);
        device->lpVtbl->Release(device);
        return heap_h;
    }

    switch (dimension) {
        case 0x00000002: /* 2D */
        case 0x00000003: /* 2DArray */
        case 0x00000007: /* 2DDepth */
        case 0x00000008: /* 2DArrayDepth */
            d3d12_bridge_device_create_srv_texture_2d((D3D12Handle)device, texture_h, heap_h, 0, format, aspect, base_mip, mip_count, base_array_layer, array_layer_count);
            break;
        case 0x00000004: /* Cube */
        case 0x00000005: /* CubeArray */
            d3d12_bridge_device_create_srv_texture_cube((D3D12Handle)device, texture_h, heap_h, 0, format, aspect, base_mip, mip_count, base_array_layer, array_layer_count);
            break;
        case 0x00000006: /* 3D */
            d3d12_bridge_device_create_srv_texture_3d((D3D12Handle)device, texture_h, heap_h, 0, format, aspect, base_mip, mip_count);
            break;
        default:
            d3d12_bridge_release(heap_h);
            device->lpVtbl->Release(device);
            return NULL;
    }

    device->lpVtbl->Release(device);
    return heap_h;
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
    desc.Flags              = map_wgpu_usage_to_d3d12_flags(format, usage_flags);

    D3D12_RESOURCE_STATES initial = D3D12_RESOURCE_STATE_COPY_DEST;
    if (usage_flags & 0x0000000000000008) {
        initial = D3D12_RESOURCE_STATE_UNORDERED_ACCESS;
    }

    ID3D12Resource* tex = NULL;
    HRESULT hr = device->lpVtbl->CreateCommittedResource(
        device, &heap_props, D3D12_HEAP_FLAG_NONE,
        &desc, initial, NULL,
        &IID_ID3D12Resource, (void**)&tex);
    if (FAILED(hr)) return NULL;
    return (D3D12Handle)tex;
}

/* --- Hardware capability queries ---
 * TODO: On actual Windows hardware, query the device for real values:
 *   - CheckFeatureSupport(D3D12_FEATURE_SHADER_MODEL, ...) for HighestShaderModel
 *   - CheckFeatureSupport(D3D12_FEATURE_D3D12_OPTIONS1, ...) for WaveLaneCountMin/Max
 *   - CheckFeatureSupport(D3D12_FEATURE_D3D12_OPTIONS4, ...) for Native16BitShaderOpsSupported
 * These stubs return conservative defaults for cross-compilation environments. */

int d3d12_bridge_device_get_shader_model(D3D12Handle device) {
    (void)device;
    /* SM6.0 — minimum for D3D12 wave intrinsics */
    return 0x60;
}

int d3d12_bridge_device_get_wave_lane_count_min(D3D12Handle device) {
    (void)device;
    /* Conservative minimum; real hardware is typically 32 (NVIDIA/Intel) or 64 (AMD) */
    return 4;
}

int d3d12_bridge_device_get_wave_lane_count_max(D3D12Handle device) {
    (void)device;
    /* Conservative maximum covering NVIDIA (32), Intel (8-32), AMD (64) */
    return 64;
}

int d3d12_bridge_device_supports_native_16bit(D3D12Handle device) {
    (void)device;
    /* Conservative: 0 (false). Native 16-bit ops require SM6.2+ and hardware support. */
    return 0;
}

/* --- DXGI swap chain (surface) --- */

static DXGI_ALPHA_MODE map_canvas_alpha_mode(uint32_t alpha_mode) {
    switch (alpha_mode) {
        case 0x00000002: return DXGI_ALPHA_MODE_PREMULTIPLIED;
        case 0x00000001:
        default:         return DXGI_ALPHA_MODE_IGNORE;
    }
}

static DXGI_COLOR_SPACE_TYPE map_canvas_color_space(uint32_t tone_mapping_mode) {
    switch (tone_mapping_mode) {
        case 0x00000002: return DXGI_COLOR_SPACE_RGB_FULL_G2084_NONE_P2020;
        case 0x00000001:
        default:         return DXGI_COLOR_SPACE_RGB_FULL_G22_NONE_P709;
    }
}

D3D12Handle d3d12_bridge_create_swap_chain(D3D12Handle queue_h, uint32_t width, uint32_t height, uint32_t format,
                                           uint32_t alpha_mode, uint32_t tone_mapping_mode) {
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
    desc.AlphaMode   = map_canvas_alpha_mode(alpha_mode);

    /* Headless swap chain for benchmarking; no HWND target */
    IDXGISwapChain1* chain = NULL;
    hr = factory->lpVtbl->CreateSwapChainForComposition(factory, (IUnknown*)queue_h, &desc, NULL, &chain);
    factory->lpVtbl->Release(factory);
    if (FAILED(hr)) return NULL;
    if (tone_mapping_mode == 0x00000002) {
        IDXGISwapChain3* chain3 = NULL;
        hr = chain->lpVtbl->QueryInterface(chain, &IID_IDXGISwapChain3, (void**)&chain3);
        if (FAILED(hr) || chain3 == NULL) {
            chain->lpVtbl->Release(chain);
            return NULL;
        }
        hr = chain3->lpVtbl->SetColorSpace1(chain3, map_canvas_color_space(tone_mapping_mode));
        chain3->lpVtbl->Release(chain3);
        if (FAILED(hr)) {
            chain->lpVtbl->Release(chain);
            return NULL;
        }
    }
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
    srv_desc.Format                        = map_wgpu_format_to_dxgi_view(format, 0);
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
