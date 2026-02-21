const std = @import("std");
const model = @import("model.zig");
const types = @import("wgpu_types.zig");
const loader = @import("wgpu_loader.zig");
const resources = @import("wgpu_resources.zig");
const ffi = @import("webgpu_ffi.zig");
const Backend = ffi.WebGPUBackend;

const RenderPassEncoder = ?*anyopaque;
const RENDER_LOAD_OP_CLEAR: u32 = 0x00000002;
const RENDER_STORE_OP_STORE: u32 = 0x00000001;
const RENDER_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST: u32 = 0x00000004;
const RENDER_FRONT_FACE_CCW: u32 = 0x00000001;
const RENDER_CULL_MODE_NONE: u32 = 0x00000001;
const RENDER_COLOR_WRITE_MASK_ALL: u64 = 0x000000000000000F;
const RENDER_TARGET_DEPTH_SLICE_UNDEFINED: u32 = std.math.maxInt(u32);
const RENDER_MULTISAMPLE_MASK_ALL: u32 = 0xFFFF_FFFF;
const RENDER_DEPTH_STENCIL_FORMAT: types.WGPUTextureFormat = model.WGPUTextureFormat_Depth24PlusStencil8;
const RENDER_DEPTH_STENCIL_CLEAR_VALUE: f32 = 1.0;
const RENDER_STENCIL_CLEAR_VALUE: u32 = 0;
const RENDER_COMPARE_FUNCTION_ALWAYS: u32 = 0x00000008;
const RENDER_STENCIL_OPERATION_KEEP: u32 = 0x00000001;
const RENDER_OPTIONAL_BOOL_FALSE: u32 = 0x00000000;
const RENDER_STENCIL_MASK_DEFAULT: u32 = 0x000000FF;
const RENDER_DEPTH_ATTACHMENT_HANDLE_MASK: u64 = 0x8C9F_2400_0000_0000;
const RENDER_VERTEX_BUFFER_HANDLE: u64 = 0x8C9F_2500_0000_0000;
const RENDER_UNIFORM_BUFFER_HANDLE: u64 = 0x8C9F_2600_0000_0000;
const RENDER_VERTEX_FORMAT_FLOAT32X4: u32 = 0x0000001F;
const RENDER_VERTEX_STEP_MODE_VERTEX: u32 = 0x00000001;
const RENDER_VERTEX_STRIDE_BYTES: u64 = 4 * @sizeOf(f32);
const RENDER_UNIFORM_BINDING_INDEX: u32 = 0;
const RENDER_UNIFORM_MIN_BINDING_SIZE_BYTES: u64 = 3 * @sizeOf(f32);

const RENDER_DRAW_SHADER_SOURCE =
    \\@group(0) @binding(0) var<uniform> color: vec3f;
    \\@vertex
    \\fn vs_main(@location(0) pos: vec4f) -> @builtin(position) vec4f {
    \\  return pos;
    \\}
    \\@fragment
    \\fn fs_main() -> @location(0) vec4f {
    \\  return vec4f(color * (1.0 / 5000.0), 1.0);
    \\}
;
const RENDER_DRAW_VERTEX_DATA = [12]f32{
    0.0, 0.5, 0.0, 1.0,
    -0.5, -0.5, 0.0, 1.0,
    0.5, -0.5, 0.0, 1.0,
};
const RENDER_DRAW_UNIFORM_COLOR = [3]f32{ 0.0, 0.0, 0.0 };

const RenderColor = extern struct {
    r: f64,
    g: f64,
    b: f64,
    a: f64,
};

const RenderPassColorAttachment = extern struct {
    nextInChain: ?*anyopaque,
    view: types.WGPUTextureView,
    depthSlice: u32,
    resolveTarget: types.WGPUTextureView,
    loadOp: u32,
    storeOp: u32,
    clearValue: RenderColor,
};

const RenderPassDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: types.WGPUStringView,
    colorAttachmentCount: usize,
    colorAttachments: [*]const RenderPassColorAttachment,
    depthStencilAttachment: ?*const anyopaque,
    occlusionQuerySet: types.WGPUQuerySet,
    timestampWrites: ?*const types.WGPUPassTimestampWrites,
};

const RenderPassDepthStencilAttachment = extern struct {
    nextInChain: ?*anyopaque,
    view: types.WGPUTextureView,
    depthLoadOp: u32,
    depthStoreOp: u32,
    depthClearValue: f32,
    depthReadOnly: types.WGPUBool,
    stencilLoadOp: u32,
    stencilStoreOp: u32,
    stencilClearValue: u32,
    stencilReadOnly: types.WGPUBool,
};

const RenderConstantEntry = extern struct {
    nextInChain: ?*anyopaque,
    key: types.WGPUStringView,
    value: f64,
};

const RenderVertexState = extern struct {
    nextInChain: ?*anyopaque,
    module: types.WGPUShaderModule,
    entryPoint: types.WGPUStringView,
    constantCount: usize,
    constants: ?[*]const RenderConstantEntry,
    bufferCount: usize,
    buffers: ?*const anyopaque,
};

const RenderVertexAttribute = extern struct {
    nextInChain: ?*anyopaque,
    format: u32,
    offset: u64,
    shaderLocation: u32,
};

const RenderVertexBufferLayout = extern struct {
    nextInChain: ?*anyopaque,
    stepMode: u32,
    arrayStride: u64,
    attributeCount: usize,
    attributes: ?[*]const RenderVertexAttribute,
};

const RenderColorTargetState = extern struct {
    nextInChain: ?*anyopaque,
    format: types.WGPUTextureFormat,
    blend: ?*const anyopaque,
    writeMask: u64,
};

const RenderFragmentState = extern struct {
    nextInChain: ?*anyopaque,
    module: types.WGPUShaderModule,
    entryPoint: types.WGPUStringView,
    constantCount: usize,
    constants: ?[*]const RenderConstantEntry,
    targetCount: usize,
    targets: [*]const RenderColorTargetState,
};

const RenderPrimitiveState = extern struct {
    nextInChain: ?*anyopaque,
    topology: u32,
    stripIndexFormat: u32,
    frontFace: u32,
    cullMode: u32,
    unclippedDepth: types.WGPUBool,
};

const RenderMultisampleState = extern struct {
    nextInChain: ?*anyopaque,
    count: u32,
    mask: u32,
    alphaToCoverageEnabled: types.WGPUBool,
};

const RenderStencilFaceState = extern struct {
    compare: u32,
    failOp: u32,
    depthFailOp: u32,
    passOp: u32,
};

const RenderDepthStencilState = extern struct {
    nextInChain: ?*anyopaque,
    format: types.WGPUTextureFormat,
    depthWriteEnabled: u32,
    depthCompare: u32,
    stencilFront: RenderStencilFaceState,
    stencilBack: RenderStencilFaceState,
    stencilReadMask: u32,
    stencilWriteMask: u32,
    depthBias: i32,
    depthBiasSlopeScale: f32,
    depthBiasClamp: f32,
};

const RenderPipelineDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: types.WGPUStringView,
    layout: types.WGPUPipelineLayout,
    vertex: RenderVertexState,
    primitive: RenderPrimitiveState,
    depthStencil: ?*const RenderDepthStencilState,
    multisample: RenderMultisampleState,
    fragment: ?*const RenderFragmentState,
};

const FnCommandEncoderBeginRenderPass = *const fn (types.WGPUCommandEncoder, *const RenderPassDescriptor) callconv(.c) RenderPassEncoder;
const FnDeviceCreateRenderPipeline = *const fn (types.WGPUDevice, *const RenderPipelineDescriptor) callconv(.c) types.WGPURenderPipeline;
const FnRenderPassEncoderSetPipeline = *const fn (RenderPassEncoder, types.WGPURenderPipeline) callconv(.c) void;
const FnRenderPassEncoderSetVertexBuffer = *const fn (RenderPassEncoder, u32, types.WGPUBuffer, u64, u64) callconv(.c) void;
const FnRenderPassEncoderSetBindGroup = *const fn (RenderPassEncoder, u32, types.WGPUBindGroup, usize, ?[*]const u32) callconv(.c) void;
const FnRenderPassEncoderDraw = *const fn (RenderPassEncoder, u32, u32, u32, u32) callconv(.c) void;
const FnRenderPassEncoderEnd = *const fn (RenderPassEncoder) callconv(.c) void;
const FnRenderPassEncoderRelease = *const fn (RenderPassEncoder) callconv(.c) void;

const RenderProcTable = struct {
    command_encoder_begin_render_pass: FnCommandEncoderBeginRenderPass,
    device_create_render_pipeline: FnDeviceCreateRenderPipeline,
    render_pass_encoder_set_pipeline: FnRenderPassEncoderSetPipeline,
    render_pass_encoder_set_vertex_buffer: FnRenderPassEncoderSetVertexBuffer,
    render_pass_encoder_set_bind_group: FnRenderPassEncoderSetBindGroup,
    render_pass_encoder_draw: FnRenderPassEncoderDraw,
    render_pass_encoder_end: FnRenderPassEncoderEnd,
    render_pass_encoder_release: FnRenderPassEncoderRelease,
    render_pipeline_release: types.FnWgpuRenderPipelineRelease,
};

fn loadRenderProc(comptime T: type, lib: std.DynLib, comptime name: [:0]const u8) ?T {
    var mutable = lib;
    return mutable.lookup(T, name);
}

fn loadRenderProcs(self: *Backend) ?RenderProcTable {
    const lib = self.dyn_lib orelse return null;
    return .{
        .command_encoder_begin_render_pass = loadRenderProc(FnCommandEncoderBeginRenderPass, lib, "wgpuCommandEncoderBeginRenderPass") orelse return null,
        .device_create_render_pipeline = loadRenderProc(FnDeviceCreateRenderPipeline, lib, "wgpuDeviceCreateRenderPipeline") orelse return null,
        .render_pass_encoder_set_pipeline = loadRenderProc(FnRenderPassEncoderSetPipeline, lib, "wgpuRenderPassEncoderSetPipeline") orelse return null,
        .render_pass_encoder_set_vertex_buffer = loadRenderProc(FnRenderPassEncoderSetVertexBuffer, lib, "wgpuRenderPassEncoderSetVertexBuffer") orelse return null,
        .render_pass_encoder_set_bind_group = loadRenderProc(FnRenderPassEncoderSetBindGroup, lib, "wgpuRenderPassEncoderSetBindGroup") orelse return null,
        .render_pass_encoder_draw = loadRenderProc(FnRenderPassEncoderDraw, lib, "wgpuRenderPassEncoderDraw") orelse return null,
        .render_pass_encoder_end = loadRenderProc(FnRenderPassEncoderEnd, lib, "wgpuRenderPassEncoderEnd") orelse return null,
        .render_pass_encoder_release = loadRenderProc(FnRenderPassEncoderRelease, lib, "wgpuRenderPassEncoderRelease") orelse return null,
        .render_pipeline_release = loadRenderProc(types.FnWgpuRenderPipelineRelease, lib, "wgpuRenderPipelineRelease") orelse return null,
    };
}

const RenderUniformBindingResources = struct {
    bind_group_layout: types.WGPUBindGroupLayout,
    bind_group: types.WGPUBindGroup,
};

fn getOrCreateRenderUniformBindingResources(self: *Backend) !RenderUniformBindingResources {
    const procs = self.procs orelse return error.ProceduralNotReady;
    if (self.render_uniform_bind_group_layout != null and self.render_uniform_bind_group != null) {
        return .{
            .bind_group_layout = self.render_uniform_bind_group_layout,
            .bind_group = self.render_uniform_bind_group,
        };
    }

    if (self.render_uniform_bind_group) |stale_group| {
        procs.wgpuBindGroupRelease(stale_group);
        self.render_uniform_bind_group = null;
    }
    if (self.render_uniform_bind_group_layout) |stale_layout| {
        procs.wgpuBindGroupLayoutRelease(stale_layout);
        self.render_uniform_bind_group_layout = null;
    }

    const uniform_bytes = std.mem.sliceAsBytes(RENDER_DRAW_UNIFORM_COLOR[0..]);
    const uniform_usage = types.WGPUBufferUsage_Uniform | types.WGPUBufferUsage_CopyDst;
    const uniform_bytes_u64 = @as(u64, @intCast(uniform_bytes.len));
    const should_upload_uniform_data = blk: {
        if (self.buffers.get(RENDER_UNIFORM_BUFFER_HANDLE)) |existing| {
            if (existing.size >= uniform_bytes_u64 and
                (existing.usage & uniform_usage) == uniform_usage)
            {
                break :blk false;
            }
        }
        break :blk true;
    };
    const uniform_buffer = try resources.getOrCreateBuffer(
        self,
        RENDER_UNIFORM_BUFFER_HANDLE,
        uniform_bytes_u64,
        uniform_usage,
    );
    if (should_upload_uniform_data) {
        procs.wgpuQueueWriteBuffer(
            self.queue.?,
            uniform_buffer,
            0,
            uniform_bytes.ptr,
            uniform_bytes.len,
        );
    }

    const layout_entries = [_]types.WGPUBindGroupLayoutEntry{.{
        .nextInChain = null,
        .binding = RENDER_UNIFORM_BINDING_INDEX,
        .visibility = types.WGPUShaderStage_Fragment,
        .bindingArraySize = 0,
        .buffer = .{
            .nextInChain = null,
            .type = types.WGPUBufferBindingType_Uniform,
            .hasDynamicOffset = types.WGPU_FALSE,
            .minBindingSize = RENDER_UNIFORM_MIN_BINDING_SIZE_BYTES,
        },
        .sampler = .{
            .nextInChain = null,
            .type = types.WGPUSamplerBindingType_BindingNotUsed,
        },
        .texture = .{
            .nextInChain = null,
            .sampleType = types.WGPUTextureSampleType_BindingNotUsed,
            .viewDimension = types.WGPUTextureViewDimension_Undefined,
            .multisampled = types.WGPU_FALSE,
        },
        .storageTexture = .{
            .nextInChain = null,
            .access = types.WGPUStorageTextureAccess_BindingNotUsed,
            .format = types.WGPUTextureFormat_Undefined,
            .viewDimension = types.WGPUTextureViewDimension_Undefined,
        },
    }};
    const bind_group_layout = try resources.createBindGroupLayout(self, layout_entries[0..]);
    errdefer procs.wgpuBindGroupLayoutRelease(bind_group_layout);

    const bind_entries = [_]types.WGPUBindGroupEntry{.{
        .nextInChain = null,
        .binding = RENDER_UNIFORM_BINDING_INDEX,
        .buffer = uniform_buffer,
        .offset = 0,
        .size = RENDER_UNIFORM_MIN_BINDING_SIZE_BYTES,
        .sampler = null,
        .textureView = null,
    }};
    const bind_group = try resources.createBindGroup(self, bind_group_layout, bind_entries[0..]);

    self.render_uniform_bind_group_layout = bind_group_layout;
    self.render_uniform_bind_group = bind_group;
    return .{
        .bind_group_layout = bind_group_layout,
        .bind_group = bind_group,
    };
}

fn getOrCreateCachedRenderTextureView(
    self: *Backend,
    cache: *std.AutoHashMap(u64, types.RenderTextureViewCacheEntry),
    key: u64,
    texture: types.WGPUTexture,
    width: u32,
    height: u32,
    format: types.WGPUTextureFormat,
    usage: types.WGPUTextureUsage,
) !types.WGPUTextureView {
    const procs = self.procs orelse return error.ProceduralNotReady;
    if (cache.get(key)) |existing| {
        if (existing.texture == texture and
            existing.width == width and
            existing.height == height and
            existing.format == format)
        {
            return existing.view;
        }
        procs.wgpuTextureViewRelease(existing.view);
        _ = cache.remove(key);
    }

    const view = procs.wgpuTextureCreateView(texture, &types.WGPUTextureViewDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
        .format = format,
        .dimension = types.WGPUTextureViewDimension_2D,
        .baseMipLevel = 0,
        .mipLevelCount = 1,
        .baseArrayLayer = 0,
        .arrayLayerCount = 1,
        .aspect = types.WGPUTextureAspect_All,
        .usage = usage,
    });
    if (view == null) return error.TextureViewCreationFailed;
    cache.put(key, .{
        .texture = texture,
        .view = view,
        .width = width,
        .height = height,
        .format = format,
    }) catch {
        procs.wgpuTextureViewRelease(view);
        return error.TextureViewCacheInsertFailed;
    };
    return view;
}

pub fn executeRenderDraw(self: *Backend, render: model.RenderDrawCommand) !types.NativeExecutionResult {
    if (render.draw_count == 0) {
        return .{ .status = .unsupported, .status_message = "render_draw draw_count must be > 0" };
    }
    if (render.vertex_count == 0) {
        return .{ .status = .unsupported, .status_message = "render_draw vertex_count must be > 0" };
    }
    if (render.instance_count == 0) {
        return .{ .status = .unsupported, .status_message = "render_draw instance_count must be > 0" };
    }
    if (render.target_width == 0 or render.target_height == 0) {
        return .{ .status = .unsupported, .status_message = "render_draw target dimensions must be > 0" };
    }

    const procs = self.procs orelse return error.ProceduralNotReady;
    const render_procs = loadRenderProcs(self) orelse {
        return .{ .status = .unsupported, .status_message = "render_draw requires render proc symbols" };
    };

    const setup_start_ns = std.time.nanoTimestamp();
    const target_resource = model.CopyTextureResource{
        .handle = render.target_handle,
        .kind = .texture,
        .width = render.target_width,
        .height = render.target_height,
        .depth_or_array_layers = 1,
        .format = render.target_format,
        .usage = types.WGPUTextureUsage_RenderAttachment | types.WGPUTextureUsage_CopySrc | types.WGPUTextureUsage_CopyDst,
        .dimension = model.WGPUTextureDimension_2D,
        .view_dimension = model.WGPUTextureViewDimension_2D,
        .mip_level = 0,
        .sample_count = 1,
        .aspect = model.WGPUTextureAspect_All,
        .bytes_per_row = 0,
        .rows_per_image = 0,
        .offset = 0,
    };
    const target_texture = try resources.getOrCreateTexture(
        self,
        target_resource,
        types.WGPUTextureUsage_RenderAttachment | types.WGPUTextureUsage_CopySrc | types.WGPUTextureUsage_CopyDst,
    );
    const render_vertex_bytes = std.mem.sliceAsBytes(RENDER_DRAW_VERTEX_DATA[0..]);
    const render_vertex_usage = types.WGPUBufferUsage_Vertex | types.WGPUBufferUsage_CopyDst;
    const render_vertex_bytes_u64 = @as(u64, @intCast(render_vertex_bytes.len));
    const should_upload_vertex_data = blk: {
        if (self.buffers.get(RENDER_VERTEX_BUFFER_HANDLE)) |existing| {
            if (existing.size >= render_vertex_bytes_u64 and
                (existing.usage & render_vertex_usage) == render_vertex_usage)
            {
                break :blk false;
            }
        }
        break :blk true;
    };
    const render_vertex_buffer = try resources.getOrCreateBuffer(
        self,
        RENDER_VERTEX_BUFFER_HANDLE,
        render_vertex_bytes_u64,
        render_vertex_usage,
    );
    if (should_upload_vertex_data) {
        procs.wgpuQueueWriteBuffer(
            self.queue.?,
            render_vertex_buffer,
            0,
            render_vertex_bytes.ptr,
            render_vertex_bytes.len,
        );
    }

    const normalized_target_format = resources.normalizeTextureFormat(render.target_format);
    const target_format = if (normalized_target_format == types.WGPUTextureFormat_Undefined)
        model.WGPUTextureFormat_RGBA8Unorm
    else
        normalized_target_format;
    const depth_handle = render.target_handle ^ RENDER_DEPTH_ATTACHMENT_HANDLE_MASK;
    const depth_resource = model.CopyTextureResource{
        .handle = depth_handle,
        .kind = .texture,
        .width = render.target_width,
        .height = render.target_height,
        .depth_or_array_layers = 1,
        .format = RENDER_DEPTH_STENCIL_FORMAT,
        .usage = types.WGPUTextureUsage_RenderAttachment,
        .dimension = model.WGPUTextureDimension_2D,
        .view_dimension = model.WGPUTextureViewDimension_2D,
        .mip_level = 0,
        .sample_count = 1,
        .aspect = model.WGPUTextureAspect_All,
        .bytes_per_row = 0,
        .rows_per_image = 0,
        .offset = 0,
    };
    const depth_texture = try resources.getOrCreateTexture(
        self,
        depth_resource,
        types.WGPUTextureUsage_RenderAttachment,
    );
    const target_view = getOrCreateCachedRenderTextureView(
        self,
        &self.render_target_view_cache,
        render.target_handle,
        target_texture,
        render.target_width,
        render.target_height,
        target_format,
        types.WGPUTextureUsage_RenderAttachment,
    ) catch |err| {
        return .{
            .status = .@"error",
            .status_message = switch (err) {
                error.ProceduralNotReady => "backend not ready",
                error.TextureViewCreationFailed => "render_draw texture view creation failed",
                error.TextureViewCacheInsertFailed => "render_draw texture view cache insert failed",
            },
        };
    };
    const depth_view = getOrCreateCachedRenderTextureView(
        self,
        &self.render_depth_view_cache,
        depth_handle,
        depth_texture,
        render.target_width,
        render.target_height,
        RENDER_DEPTH_STENCIL_FORMAT,
        types.WGPUTextureUsage_RenderAttachment,
    ) catch |err| {
        return .{
            .status = .@"error",
            .status_message = switch (err) {
                error.ProceduralNotReady => "backend not ready",
                error.TextureViewCreationFailed => "render_draw depth view creation failed",
                error.TextureViewCacheInsertFailed => "render_draw depth view cache insert failed",
            },
        };
    };
    const render_uniform_resources = getOrCreateRenderUniformBindingResources(self) catch |err| {
        return .{
            .status = .@"error",
            .status_message = switch (err) {
                error.ProceduralNotReady => "backend not ready",
                error.BufferAllocationFailed => "render_draw uniform buffer allocation failed",
                error.BindGroupLayoutCreationFailed => "render_draw uniform bind group layout creation failed",
                error.BindGroupCreationFailed => "render_draw uniform bind group creation failed",
                else => "render_draw uniform setup failed",
            },
        };
    };

    const render_pipeline = if (self.render_pipeline_cache.get(target_format)) |cached|
        cached.pipeline
    else blk: {
        const shader_module = resources.createShaderModule(self, RENDER_DRAW_SHADER_SOURCE) catch |err| {
            return .{
                .status = .@"error",
                .status_message = switch (err) {
                    error.KernelModuleCreationFailed => "render_draw shader module creation failed",
                    error.ProceduralNotReady => "backend not ready",
                },
            };
        };

        var color_target = RenderColorTargetState{
            .nextInChain = null,
            .format = target_format,
            .blend = null,
            .writeMask = RENDER_COLOR_WRITE_MASK_ALL,
        };
        const vertex_attribute = RenderVertexAttribute{
            .nextInChain = null,
            .format = RENDER_VERTEX_FORMAT_FLOAT32X4,
            .offset = 0,
            .shaderLocation = 0,
        };
        const vertex_buffer_layout = RenderVertexBufferLayout{
            .nextInChain = null,
            .stepMode = RENDER_VERTEX_STEP_MODE_VERTEX,
            .arrayStride = RENDER_VERTEX_STRIDE_BYTES,
            .attributeCount = 1,
            .attributes = @ptrCast(&vertex_attribute),
        };
        var fragment_state = RenderFragmentState{
            .nextInChain = null,
            .module = shader_module,
            .entryPoint = loader.stringView("fs_main"),
            .constantCount = 0,
            .constants = null,
            .targetCount = 1,
            .targets = @ptrCast(&color_target),
        };
        const stencil_face_state = RenderStencilFaceState{
            .compare = RENDER_COMPARE_FUNCTION_ALWAYS,
            .failOp = RENDER_STENCIL_OPERATION_KEEP,
            .depthFailOp = RENDER_STENCIL_OPERATION_KEEP,
            .passOp = RENDER_STENCIL_OPERATION_KEEP,
        };
        const depth_stencil_state = RenderDepthStencilState{
            .nextInChain = null,
            .format = RENDER_DEPTH_STENCIL_FORMAT,
            .depthWriteEnabled = RENDER_OPTIONAL_BOOL_FALSE,
            .depthCompare = RENDER_COMPARE_FUNCTION_ALWAYS,
            .stencilFront = stencil_face_state,
            .stencilBack = stencil_face_state,
            .stencilReadMask = RENDER_STENCIL_MASK_DEFAULT,
            .stencilWriteMask = RENDER_STENCIL_MASK_DEFAULT,
            .depthBias = 0,
            .depthBiasSlopeScale = 0,
            .depthBiasClamp = 0,
        };
        const render_pipeline_layout = resources.createPipelineLayout(
            self,
            &[_]types.WGPUBindGroupLayout{render_uniform_resources.bind_group_layout},
        ) catch {
            procs.wgpuShaderModuleRelease(shader_module);
            return .{ .status = .@"error", .status_message = "render_draw pipeline layout creation failed" };
        };
        defer procs.wgpuPipelineLayoutRelease(render_pipeline_layout);

        const pipeline = render_procs.device_create_render_pipeline(self.device.?, &RenderPipelineDescriptor{
            .nextInChain = null,
            .label = loader.stringView("fawn.render_draw"),
            .layout = render_pipeline_layout,
            .vertex = .{
                .nextInChain = null,
                .module = shader_module,
                .entryPoint = loader.stringView("vs_main"),
                .constantCount = 0,
                .constants = null,
                .bufferCount = 1,
                .buffers = @ptrCast(&vertex_buffer_layout),
            },
            .primitive = .{
                .nextInChain = null,
                .topology = RENDER_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,
                .stripIndexFormat = 0,
                .frontFace = RENDER_FRONT_FACE_CCW,
                .cullMode = RENDER_CULL_MODE_NONE,
                .unclippedDepth = types.WGPU_FALSE,
            },
            .depthStencil = &depth_stencil_state,
            .multisample = .{
                .nextInChain = null,
                .count = 1,
                .mask = RENDER_MULTISAMPLE_MASK_ALL,
                .alphaToCoverageEnabled = types.WGPU_FALSE,
            },
            .fragment = &fragment_state,
        });
        if (pipeline == null) {
            procs.wgpuShaderModuleRelease(shader_module);
            return .{ .status = .@"error", .status_message = "render_draw pipeline creation failed" };
        }

        self.render_pipeline_cache.put(target_format, .{
            .shader_module = shader_module,
            .pipeline = pipeline,
        }) catch {
            render_procs.render_pipeline_release(pipeline);
            procs.wgpuShaderModuleRelease(shader_module);
            return .{ .status = .@"error", .status_message = "render_draw pipeline cache insert failed" };
        };
        break :blk pipeline;
    };
    const setup_end_ns = std.time.nanoTimestamp();

    const encode_start_ns = std.time.nanoTimestamp();
    const encoder = procs.wgpuDeviceCreateCommandEncoder(self.device.?, &types.WGPUCommandEncoderDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    });
    if (encoder == null) {
        return .{ .status = .@"error", .status_message = "deviceCreateCommandEncoder returned null" };
    }
    defer procs.wgpuCommandEncoderRelease(encoder);

    var color_attachment = RenderPassColorAttachment{
        .nextInChain = null,
        .view = target_view,
        .depthSlice = RENDER_TARGET_DEPTH_SLICE_UNDEFINED,
        .resolveTarget = null,
        .loadOp = RENDER_LOAD_OP_CLEAR,
        .storeOp = RENDER_STORE_OP_STORE,
        .clearValue = .{ .r = 0, .g = 0, .b = 0, .a = 1 },
    };
    const depth_stencil_attachment = RenderPassDepthStencilAttachment{
        .nextInChain = null,
        .view = depth_view,
        .depthLoadOp = RENDER_LOAD_OP_CLEAR,
        .depthStoreOp = RENDER_STORE_OP_STORE,
        .depthClearValue = RENDER_DEPTH_STENCIL_CLEAR_VALUE,
        .depthReadOnly = types.WGPU_FALSE,
        .stencilLoadOp = RENDER_LOAD_OP_CLEAR,
        .stencilStoreOp = RENDER_STORE_OP_STORE,
        .stencilClearValue = RENDER_STENCIL_CLEAR_VALUE,
        .stencilReadOnly = types.WGPU_FALSE,
    };
    const render_pass = render_procs.command_encoder_begin_render_pass(encoder, &RenderPassDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
        .colorAttachmentCount = 1,
        .colorAttachments = @ptrCast(&color_attachment),
        .depthStencilAttachment = &depth_stencil_attachment,
        .occlusionQuerySet = null,
        .timestampWrites = null,
    });
    if (render_pass == null) {
        return .{ .status = .@"error", .status_message = "render_draw begin render pass failed" };
    }
    defer render_procs.render_pass_encoder_release(render_pass);

    render_procs.render_pass_encoder_set_vertex_buffer(
        render_pass,
        0,
        render_vertex_buffer,
        0,
        types.WGPU_WHOLE_SIZE,
    );
    if (render.pipeline_mode == .static) {
        render_procs.render_pass_encoder_set_pipeline(render_pass, render_pipeline);
    }
    if (render.bind_group_mode == .no_change) {
        render_procs.render_pass_encoder_set_bind_group(
            render_pass,
            RENDER_UNIFORM_BINDING_INDEX,
            render_uniform_resources.bind_group,
            0,
            null,
        );
    }
    var draw_index: u32 = 0;
    while (draw_index < render.draw_count) : (draw_index += 1) {
        if (render.pipeline_mode == .redundant) {
            render_procs.render_pass_encoder_set_pipeline(render_pass, render_pipeline);
        }
        if (render.bind_group_mode == .redundant) {
            render_procs.render_pass_encoder_set_bind_group(
                render_pass,
                RENDER_UNIFORM_BINDING_INDEX,
                render_uniform_resources.bind_group,
                0,
                null,
            );
        }
        render_procs.render_pass_encoder_draw(render_pass, render.vertex_count, render.instance_count, 0, 0);
    }
    render_procs.render_pass_encoder_end(render_pass);

    const command_buffer = procs.wgpuCommandEncoderFinish(encoder, &types.WGPUCommandBufferDescriptor{
        .nextInChain = null,
        .label = loader.emptyStringView(),
    });
    if (command_buffer == null) {
        return .{ .status = .@"error", .status_message = "commandEncoderFinish returned null" };
    }
    defer procs.wgpuCommandBufferRelease(command_buffer);
    const encode_end_ns = std.time.nanoTimestamp();

    var commands = [_]types.WGPUCommandBuffer{command_buffer};
    const submit_wait_start_ns = std.time.nanoTimestamp();
    procs.wgpuQueueSubmit(self.queue.?, commands.len, commands[0..].ptr);
    try self.waitForQueue();
    const submit_wait_end_ns = std.time.nanoTimestamp();

    const setup_ns = if (setup_end_ns > setup_start_ns)
        @as(u64, @intCast(setup_end_ns - setup_start_ns))
    else
        0;
    const encode_ns = if (encode_end_ns > encode_start_ns)
        @as(u64, @intCast(encode_end_ns - encode_start_ns))
    else
        0;
    const submit_wait_ns = if (submit_wait_end_ns > submit_wait_start_ns)
        @as(u64, @intCast(submit_wait_end_ns - submit_wait_start_ns))
    else
        0;

    return .{
        .status = .ok,
        .status_message = "render_draw command submitted",
        .setup_ns = setup_ns,
        .encode_ns = encode_ns,
        .submit_wait_ns = submit_wait_ns,
        .dispatch_count = render.draw_count,
        .gpu_timestamp_ns = 0,
    };
}
