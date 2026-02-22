const std = @import("std");
const model = @import("model.zig");
const types = @import("wgpu_types.zig");
const loader = @import("wgpu_loader.zig");
const resources = @import("wgpu_resources.zig");
const async_procs_mod = @import("wgpu_async_procs.zig");
const render_api_mod = @import("wgpu_render_api.zig");
const render_types_mod = @import("wgpu_render_types.zig");
const ffi = @import("webgpu_ffi.zig");
const Backend = ffi.WebGPUBackend;

const RENDER_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST: u32 = 0x00000004;
const RENDER_FRONT_FACE_CCW: u32 = 0x00000001;
const RENDER_CULL_MODE_NONE: u32 = 0x00000001;
const RENDER_COLOR_WRITE_MASK_ALL: u64 = 0x000000000000000F;
const RENDER_MULTISAMPLE_MASK_ALL: u32 = 0xFFFF_FFFF;
const RENDER_LOAD_OP_CLEAR: u32 = 0x00000002;
const RENDER_STORE_OP_STORE: u32 = 0x00000001;
const DIAG_RENDER_TARGET_WIDTH: u32 = 4;
const DIAG_RENDER_TARGET_HEIGHT: u32 = 4;
const DIAG_PLS_ATTACHMENT_HANDLE: u64 = 0x8C9F_2D00_0000_0000;
const DIAG_PLS_TOTAL_SIZE_BYTES: u64 = 4;
const DIAG_PLS_SLOT_OFFSET_BYTES: u64 = 0;
const DIAG_PLS_ATTACHMENT_FORMAT: types.WGPUTextureFormat = model.WGPUTextureFormat_R32Uint;

const DIAGNOSTIC_PIXEL_LOCAL_SHADER_SOURCE =
    \\enable chromium_experimental_pixel_local;
    \\struct PLS {
    \\  slot0: u32,
    \\};
    \\var<pixel_local> pls: PLS;
    \\@vertex
    \\fn vs_main(@builtin(vertex_index) idx: u32) -> @builtin(position) vec4f {
    \\  var p = array<vec2f, 3>(
    \\    vec2f(0.0, 0.5),
    \\    vec2f(-0.5, -0.5),
    \\    vec2f(0.5, -0.5),
    \\  );
    \\  let pos = p[idx];
    \\  return vec4f(pos, 0.0, 1.0);
    \\}
    \\@fragment
    \\fn fs_main() -> @location(0) vec4f {
    \\  pls.slot0 = pls.slot0 + 1u;
    \\  return vec4f(f32(pls.slot0 & 255u) / 255.0, 0.0, 0.0, 1.0);
    \\}
;

pub fn runPixelLocalStorageDiagnostics(self: *Backend, target_format: types.WGPUTextureFormat) !void {
    const procs = self.procs orelse return error.ProceduralNotReady;
    const render_api = render_api_mod.loadRenderApi(procs, self.dyn_lib) orelse return error.RenderApiUnavailable;
    const pixel_local_storage_barrier = render_api.render_pass_encoder_pixel_local_storage_barrier orelse {
        return error.PixelLocalStorageBarrierUnavailable;
    };
    try requirePixelLocalStorageFeature(procs, self.device.?);

    const normalized_target_format = normalizeDiagnosticFormat(target_format);
    const target_texture = try getOrCreateDiagnosticRenderTexture(self, normalized_target_format);
    const target_view = try createRenderAttachmentTextureView(procs, target_texture, normalized_target_format);
    defer procs.wgpuTextureViewRelease(target_view);

    const storage_texture = try resources.getOrCreateTexture(
        self,
        .{
            .handle = DIAG_PLS_ATTACHMENT_HANDLE,
            .kind = .texture,
            .width = DIAG_RENDER_TARGET_WIDTH,
            .height = DIAG_RENDER_TARGET_HEIGHT,
            .depth_or_array_layers = 1,
            .format = DIAG_PLS_ATTACHMENT_FORMAT,
            .usage = types.WGPUTextureUsage_RenderAttachment | types.WGPUTextureUsage_StorageAttachment,
            .dimension = model.WGPUTextureDimension_2D,
            .view_dimension = model.WGPUTextureViewDimension_2D,
            .mip_level = 0,
            .sample_count = 1,
            .aspect = model.WGPUTextureAspect_All,
            .bytes_per_row = 0,
            .rows_per_image = 0,
            .offset = 0,
        },
        types.WGPUTextureUsage_RenderAttachment | types.WGPUTextureUsage_StorageAttachment,
    );
    const storage_view = try createStorageAttachmentTextureView(procs, storage_texture, DIAG_PLS_ATTACHMENT_FORMAT);
    defer procs.wgpuTextureViewRelease(storage_view);

    const pipeline_storage_attachments = [_]render_types_mod.PipelineLayoutStorageAttachment{
        .{
            .nextInChain = null,
            .offset = DIAG_PLS_SLOT_OFFSET_BYTES,
            .format = DIAG_PLS_ATTACHMENT_FORMAT,
        },
    };
    const render_pipeline = try createPixelLocalStorageRenderPipelineForDiagnostics(
        self,
        normalized_target_format,
        pipeline_storage_attachments[0..],
    );
    defer render_api.render_pipeline_release(render_pipeline);

    const encoder = procs.wgpuDeviceCreateCommandEncoder(self.device.?, &types.WGPUCommandEncoderDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    });
    if (encoder == null) return error.CommandEncoderCreationFailed;
    defer procs.wgpuCommandEncoderRelease(encoder);

    var color_attachment = render_types_mod.RenderPassColorAttachment{
        .nextInChain = null,
        .view = target_view,
        .depthSlice = std.math.maxInt(u32),
        .resolveTarget = null,
        .loadOp = RENDER_LOAD_OP_CLEAR,
        .storeOp = RENDER_STORE_OP_STORE,
        .clearValue = .{ .r = 0, .g = 0, .b = 0, .a = 1 },
    };
    const storage_attachments = [_]render_types_mod.RenderPassStorageAttachment{
        .{
            .nextInChain = null,
            .offset = DIAG_PLS_SLOT_OFFSET_BYTES,
            .storage = storage_view,
            .loadOp = RENDER_LOAD_OP_CLEAR,
            .storeOp = RENDER_STORE_OP_STORE,
            .clearValue = .{ .r = 0, .g = 0, .b = 0, .a = 0 },
        },
    };
    var pls_chain = render_types_mod.RenderPassPixelLocalStorage{
        .chain = .{
            .next = null,
            .sType = render_types_mod.WGPUSType_RenderPassPixelLocalStorage,
        },
        .totalPixelLocalStorageSize = DIAG_PLS_TOTAL_SIZE_BYTES,
        .storageAttachmentCount = storage_attachments.len,
        .storageAttachments = storage_attachments[0..].ptr,
    };
    const render_pass = render_api.command_encoder_begin_render_pass(
        encoder,
        &render_types_mod.RenderPassDescriptor{
            .nextInChain = @ptrCast(&pls_chain.chain),
            .label = loader.emptyStringView(),
            .colorAttachmentCount = 1,
            .colorAttachments = @ptrCast(&color_attachment),
            .depthStencilAttachment = null,
            .occlusionQuerySet = null,
            .timestampWrites = null,
        },
    );
    if (render_pass == null) return error.RenderPassCreationFailed;
    defer render_api.render_pass_encoder_release(render_pass);

    render_api.render_pass_encoder_set_pipeline(render_pass, render_pipeline);
    render_api.render_pass_encoder_draw(render_pass, 3, 1, 0, 0);
    pixel_local_storage_barrier(render_pass);
    render_api.render_pass_encoder_draw(render_pass, 3, 1, 0, 0);
    render_api.render_pass_encoder_end(render_pass);

    const command_buffer = procs.wgpuCommandEncoderFinish(
        encoder,
        &types.WGPUCommandBufferDescriptor{
            .nextInChain = null,
            .label = loader.emptyStringView(),
        },
    );
    if (command_buffer == null) return error.CommandBufferFinishFailed;
    procs.wgpuCommandBufferRelease(command_buffer);
}

fn createPixelLocalStorageRenderPipelineForDiagnostics(
    self: *Backend,
    target_format: types.WGPUTextureFormat,
    storage_attachments: []const render_types_mod.PipelineLayoutStorageAttachment,
) !types.WGPURenderPipeline {
    const procs = self.procs orelse return error.ProceduralNotReady;
    const async_procs = async_procs_mod.loadAsyncProcs(self.dyn_lib) orelse return error.AsyncProcUnavailable;

    const shader_module = resources.createShaderModule(self, DIAGNOSTIC_PIXEL_LOCAL_SHADER_SOURCE) catch |err| {
        return switch (err) {
            error.KernelModuleCreationFailed => error.DiagnosticShaderModuleCreationFailed,
            else => error.DiagnosticShaderModuleCreationFailed,
        };
    };
    defer procs.wgpuShaderModuleRelease(shader_module);

    const compilation_state = async_procs_mod.requestShaderCompilationInfoAndWait(
        async_procs,
        self.instance.?,
        procs,
        shader_module,
    ) catch return error.DiagnosticCompilationInfoFailed;
    if (compilation_state.status != async_procs_mod.COMPILATION_INFO_STATUS_SUCCESS) {
        return error.DiagnosticCompilationInfoFailed;
    }

    const pipeline_layout = resources.createPipelineLayoutWithPixelLocalStorage(
        self,
        &[_]types.WGPUBindGroupLayout{},
        DIAG_PLS_TOTAL_SIZE_BYTES,
        storage_attachments,
    ) catch return error.DiagnosticPipelineCreationFailed;
    defer procs.wgpuPipelineLayoutRelease(pipeline_layout);

    var color_target = render_types_mod.RenderColorTargetState{
        .nextInChain = null,
        .format = target_format,
        .blend = null,
        .writeMask = RENDER_COLOR_WRITE_MASK_ALL,
    };
    var fragment_state = render_types_mod.RenderFragmentState{
        .nextInChain = null,
        .module = shader_module,
        .entryPoint = loader.stringView("fs_main"),
        .constantCount = 0,
        .constants = null,
        .targetCount = 1,
        .targets = @ptrCast(&color_target),
    };
    const pipeline_desc = render_types_mod.RenderPipelineDescriptor{
        .nextInChain = null,
        .label = loader.stringView("fawn.diag.pixel_local_storage"),
        .layout = pipeline_layout,
        .vertex = .{
            .nextInChain = null,
            .module = shader_module,
            .entryPoint = loader.stringView("vs_main"),
            .constantCount = 0,
            .constants = null,
            .bufferCount = 0,
            .buffers = null,
        },
        .primitive = .{
            .nextInChain = null,
            .topology = RENDER_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,
            .stripIndexFormat = 0,
            .frontFace = RENDER_FRONT_FACE_CCW,
            .cullMode = RENDER_CULL_MODE_NONE,
            .unclippedDepth = types.WGPU_FALSE,
        },
        .depthStencil = null,
        .multisample = .{
            .nextInChain = null,
            .count = 1,
            .mask = RENDER_MULTISAMPLE_MASK_ALL,
            .alphaToCoverageEnabled = types.WGPU_FALSE,
        },
        .fragment = &fragment_state,
    };
    return async_procs_mod.createRenderPipelineAsyncAndWait(
        async_procs,
        self.instance.?,
        procs,
        self.device.?,
        @ptrCast(&pipeline_desc),
    ) catch error.DiagnosticPipelineCreationFailed;
}

fn getOrCreateDiagnosticRenderTexture(self: *Backend, target_format: types.WGPUTextureFormat) !types.WGPUTexture {
    return resources.getOrCreateTexture(
        self,
        .{
            .handle = 0x8C9F_2C00_0000_0000,
            .kind = .texture,
            .width = DIAG_RENDER_TARGET_WIDTH,
            .height = DIAG_RENDER_TARGET_HEIGHT,
            .depth_or_array_layers = 1,
            .format = target_format,
            .usage = types.WGPUTextureUsage_RenderAttachment | types.WGPUTextureUsage_CopyDst | types.WGPUTextureUsage_CopySrc | types.WGPUTextureUsage_TextureBinding,
            .dimension = model.WGPUTextureDimension_2D,
            .view_dimension = model.WGPUTextureViewDimension_2D,
            .mip_level = 0,
            .sample_count = 1,
            .aspect = model.WGPUTextureAspect_All,
            .bytes_per_row = 0,
            .rows_per_image = 0,
            .offset = 0,
        },
        types.WGPUTextureUsage_RenderAttachment | types.WGPUTextureUsage_CopyDst | types.WGPUTextureUsage_CopySrc | types.WGPUTextureUsage_TextureBinding,
    );
}

fn createRenderAttachmentTextureView(
    procs: types.Procs,
    texture: types.WGPUTexture,
    target_format: types.WGPUTextureFormat,
) !types.WGPUTextureView {
    const view = procs.wgpuTextureCreateView(texture, &types.WGPUTextureViewDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
        .format = target_format,
        .dimension = types.WGPUTextureViewDimension_2D,
        .baseMipLevel = 0,
        .mipLevelCount = 1,
        .baseArrayLayer = 0,
        .arrayLayerCount = 1,
        .aspect = types.WGPUTextureAspect_All,
        .usage = types.WGPUTextureUsage_RenderAttachment,
    });
    if (view == null) return error.TextureViewCreationFailed;
    return view;
}

fn createStorageAttachmentTextureView(
    procs: types.Procs,
    texture: types.WGPUTexture,
    target_format: types.WGPUTextureFormat,
) !types.WGPUTextureView {
    const view = procs.wgpuTextureCreateView(texture, &types.WGPUTextureViewDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
        .format = target_format,
        .dimension = types.WGPUTextureViewDimension_2D,
        .baseMipLevel = 0,
        .mipLevelCount = 1,
        .baseArrayLayer = 0,
        .arrayLayerCount = 1,
        .aspect = types.WGPUTextureAspect_All,
        .usage = types.WGPUTextureUsage_RenderAttachment | types.WGPUTextureUsage_StorageAttachment,
    });
    if (view == null) return error.TextureViewCreationFailed;
    return view;
}

fn normalizeDiagnosticFormat(raw: types.WGPUTextureFormat) types.WGPUTextureFormat {
    const normalized = resources.normalizeTextureFormat(raw);
    return if (normalized == types.WGPUTextureFormat_Undefined) model.WGPUTextureFormat_RGBA8Unorm else normalized;
}

fn requirePixelLocalStorageFeature(procs: types.Procs, device: types.WGPUDevice) !void {
    const has_feature = procs.wgpuDeviceHasFeature orelse return error.PixelLocalStorageFeatureUnavailable;
    if (has_feature(device, types.WGPUFeatureName_PixelLocalStorageNonCoherent) == types.WGPU_FALSE) {
        return error.PixelLocalStorageFeatureUnavailable;
    }
}
