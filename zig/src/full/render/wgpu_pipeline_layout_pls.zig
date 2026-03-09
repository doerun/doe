const types = @import("../../core/abi/wgpu_types.zig");
const loader = @import("../../core/abi/wgpu_loader.zig");
const render_types_mod = @import("wgpu_render_types.zig");
const ffi = @import("../../webgpu_ffi.zig");
const Backend = ffi.WebGPUBackend;

pub fn createPipelineLayoutWithPixelLocalStorage(
    self: *Backend,
    bind_group_layouts: []const types.WGPUBindGroupLayout,
    total_size_bytes: u64,
    storage_attachments: []const render_types_mod.PipelineLayoutStorageAttachment,
) !types.WGPUPipelineLayout {
    if (storage_attachments.len == 0 or total_size_bytes == 0) return error.PipelineLayoutCreationFailed;
    const procs = self.core.procs orelse return error.ProceduralNotReady;
    var pls_chain = render_types_mod.PipelineLayoutPixelLocalStorage{
        .chain = .{
            .next = null,
            .sType = render_types_mod.WGPUSType_PipelineLayoutPixelLocalStorage,
        },
        .totalPixelLocalStorageSize = total_size_bytes,
        .storageAttachmentCount = storage_attachments.len,
        .storageAttachments = storage_attachments.ptr,
    };
    const descriptor = types.WGPUPipelineLayoutDescriptor{
        .nextInChain = @ptrCast(&pls_chain.chain),
        .label = loader.emptyStringView(),
        .bindGroupLayoutCount = bind_group_layouts.len,
        .bindGroupLayouts = bind_group_layouts.ptr,
        .immediateSize = 0,
    };
    const layout = procs.wgpuDeviceCreatePipelineLayout(self.core.device.?, &descriptor);
    if (layout == null) return error.PipelineLayoutCreationFailed;
    return layout;
}
