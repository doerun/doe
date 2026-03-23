const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");
const p1cap = @import("wgpu_p1_capability_procs.zig");
const p0 = @import("wgpu_p0_procs.zig");
const p1res = @import("wgpu_p1_resource_table_procs.zig");
const p2life = @import("wgpu_p2_lifecycle_procs.zig");
const surface = @import("full/surface/wgpu_surface_procs.zig");
const texture = @import("wgpu_texture_procs.zig");
const render = @import("full/render/wgpu_render_api.zig");
const async_procs = @import("wgpu_async_procs.zig");
const native = @import("doe_wgpu_native.zig");
const query_native = @import("doe_query_native.zig");
const error_scope = @import("error_scope.zig");
const task_pool = @import("runtime/task_pool.zig");
const singleflight = @import("runtime/pipeline_singleflight.zig");
const pipeline_cache_integration = @import("runtime/pipeline_cache_integration.zig");

extern fn wgpuGetProcAddress(name: types.WGPUStringView) callconv(.c) p1cap.WGPUProc;
extern fn doeWgpuDropinAbortMissingRequiredSymbol(name: types.WGPUStringView) callconv(.c) noreturn;
extern fn doeNativeComputePassSetImmediates(
    encoder_raw: ?*anyopaque,
    index: u32,
    data_ptr: ?[*]const u8,
    data_len: usize,
) callconv(.c) void;
extern fn doeNativeQuerySetDestroy(qs_raw: ?*anyopaque) callconv(.c) void;
extern fn doeNativeQuerySetGetCount(qs_raw: ?*anyopaque) callconv(.c) u32;
extern fn doeNativeQuerySetGetType(qs_raw: ?*anyopaque) callconv(.c) types.WGPUQueryType;

const FEATURE_CANDIDATES = [_]types.WGPUFeatureName{
    types.WGPUFeatureName_CoreFeaturesAndLimits,
    types.WGPUFeatureName_DepthClipControl,
    types.WGPUFeatureName_Depth32FloatStencil8,
    types.WGPUFeatureName_TextureCompressionBC,
    types.WGPUFeatureName_TextureCompressionBCSliced3D,
    types.WGPUFeatureName_TextureCompressionETC2,
    types.WGPUFeatureName_TextureCompressionASTC,
    types.WGPUFeatureName_TextureCompressionASTCSliced3D,
    types.WGPUFeatureName_RG11B10UfloatRenderable,
    types.WGPUFeatureName_TimestampQuery,
    types.WGPUFeatureName_BGRA8UnormStorage,
    types.WGPUFeatureName_ShaderF16,
    types.WGPUFeatureName_IndirectFirstInstance,
    types.WGPUFeatureName_Float32Filterable,
    types.WGPUFeatureName_Subgroups,
    types.WGPUFeatureName_SubgroupsF16,
    types.WGPUFeatureName_Float32Blendable,
    types.WGPUFeatureName_ClipDistances,
    types.WGPUFeatureName_DualSourceBlending,
    types.WGPUFeatureName_TextureFormatsTier1,
    types.WGPUFeatureName_TextureFormatsTier2,
    types.WGPUFeatureName_PrimitiveIndex,
    types.WGPUFeatureName_TextureComponentSwizzle,
};

const LoggingCallback = *const fn (u32, types.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void;
const PopErrorScopeCallback = *const fn (u32, u32, types.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void;

const LoggingCallbackInfo = extern struct {
    nextInChain: ?*anyopaque,
    callback: ?LoggingCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

const PopErrorScopeBridgeState = struct {
    callback: ?PopErrorScopeCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
};

const RenderStringView = extern struct {
    data: ?[*]const u8,
    length: usize,
};

const RenderBlendComponent = extern struct {
    operation: u32,
    srcFactor: u32,
    dstFactor: u32,
};

const RenderBlendState = extern struct {
    color: RenderBlendComponent,
    alpha: RenderBlendComponent,
};

const RenderColorTargetState = extern struct {
    nextInChain: ?*anyopaque,
    format: u32,
    blend: ?*const RenderBlendState,
    writeMask: u64,
};

const RenderVertexState = extern struct {
    nextInChain: ?*anyopaque,
    module: ?*anyopaque,
    entryPoint: RenderStringView,
    constantCount: usize,
    constants: ?*anyopaque,
    bufferCount: usize,
    buffers: ?*anyopaque,
};

const RenderFragmentState = extern struct {
    nextInChain: ?*anyopaque,
    module: ?*anyopaque,
    entryPoint: RenderStringView,
    constantCount: usize,
    constants: ?*anyopaque,
    targetCount: usize,
    targets: ?[*]const RenderColorTargetState,
};

const RenderPrimitiveState = extern struct {
    nextInChain: ?*anyopaque,
    topology: u32,
    stripIndexFormat: u32,
    frontFace: u32,
    cullMode: u32,
    unclippedDepth: u32,
};

const RenderMultisampleState = extern struct {
    nextInChain: ?*anyopaque,
    count: u32,
    mask: u32,
    alphaToCoverageEnabled: u32,
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

const RenderDepthStencilDesc = extern struct {
    nextInChain: ?*anyopaque,
    format: u32,
    depthWriteEnabled: u32,
    depthCompare: u32,
    stencilFront: extern struct {
        compare: u32,
        failOp: u32,
        depthFailOp: u32,
        passOp: u32,
    },
    stencilBack: extern struct {
        compare: u32,
        failOp: u32,
        depthFailOp: u32,
        passOp: u32,
    },
    stencilReadMask: u32,
    stencilWriteMask: u32,
    depthBias: i32,
    depthBiasSlopeScale: f32,
    depthBiasClamp: f32,
};

const RenderPipelineDesc = extern struct {
    nextInChain: ?*anyopaque,
    label: RenderStringView,
    layout: ?*anyopaque,
    vertex: RenderVertexState,
    primitive: RenderPrimitiveState,
    depthStencil: ?*anyopaque,
    multisample: RenderMultisampleState,
    fragment: ?*const RenderFragmentState,
};

var g_next_async_future_id = std.atomic.Value(u64).init(32);
var g_compute_inflight = singleflight.Registry(ComputePipelineAsyncRequest){};
var g_render_inflight = singleflight.Registry(RenderPipelineAsyncRequest){};

fn next_async_future_id() u64 {
    return g_next_async_future_id.fetchAdd(1, .monotonic);
}

fn string_view_slice(view: types.WGPUStringView) []const u8 {
    const data = view.data orelse return "";
    if (view.length == types.WGPU_STRLEN) {
        return std.mem.sliceTo(@as([*:0]const u8, @ptrCast(data)), 0);
    }
    return data[0..view.length];
}

fn dup_string_view(view: types.WGPUStringView) ?[]u8 {
    const src = string_view_slice(view);
    if (src.len == 0) return null;
    return std.heap.c_allocator.dupe(u8, src) catch null;
}

fn make_string_view(bytes: ?[]u8) types.WGPUStringView {
    if (bytes) |owned| {
        return .{ .data = owned.ptr, .length = owned.len };
    }
    return .{ .data = null, .length = 0 };
}

fn render_string_view_slice(view: RenderStringView) []const u8 {
    const data = view.data orelse return "";
    return data[0..view.length];
}

fn dup_render_string_view(view: RenderStringView) ?[]u8 {
    const src = render_string_view_slice(view);
    if (src.len == 0) return null;
    return std.heap.c_allocator.dupe(u8, src) catch null;
}

fn make_render_string_view(bytes: ?[]u8) RenderStringView {
    if (bytes) |owned| {
        return .{ .data = owned.ptr, .length = owned.len };
    }
    return .{ .data = null, .length = 0 };
}

fn optional_ptr_id(raw: ?*anyopaque) usize {
    if (raw) |ptr| return @intFromPtr(ptr);
    return 0;
}

fn compute_pipeline_request_key(req: *const ComputePipelineAsyncRequest) u64 {
    var hasher = std.hash.Wyhash.init(0);
    const device_ptr = optional_ptr_id(req.device);
    const module_ptr = optional_ptr_id(req.descriptor.compute.module);
    const layout_ptr = optional_ptr_id(req.descriptor.layout);
    hasher.update(std.mem.asBytes(&device_ptr));
    hasher.update(std.mem.asBytes(&module_ptr));
    hasher.update(std.mem.asBytes(&layout_ptr));
    hasher.update(string_view_slice(req.descriptor.compute.entryPoint));
    if (req.constants) |constants| {
        for (constants) |entry| {
            hasher.update(string_view_slice(entry.key));
            hasher.update(std.mem.asBytes(&entry.value));
        }
    }
    return hasher.final();
}

fn render_pipeline_request_key(req: *const RenderPipelineAsyncRequest) u64 {
    var hasher = std.hash.Wyhash.init(0);
    const device_ptr = optional_ptr_id(req.device);
    const layout_ptr = optional_ptr_id(req.descriptor.layout);
    const vertex_module_ptr = optional_ptr_id(req.descriptor.vertex.module);
    const fragment_module_ptr = if (req.descriptor.fragment) |frag| optional_ptr_id(frag.module) else 0;
    hasher.update(std.mem.asBytes(&device_ptr));
    hasher.update(std.mem.asBytes(&layout_ptr));
    hasher.update(std.mem.asBytes(&vertex_module_ptr));
    hasher.update(std.mem.asBytes(&fragment_module_ptr));
    hasher.update(render_string_view_slice(req.descriptor.vertex.entryPoint));
    if (req.descriptor.fragment) |frag| {
        hasher.update(render_string_view_slice(frag.entryPoint));
        hasher.update(std.mem.asBytes(&frag.targetCount));
        if (req.fragment_targets) |targets| {
            for (targets) |target| {
                hasher.update(std.mem.asBytes(&target.format));
                hasher.update(std.mem.asBytes(&target.writeMask));
            }
        }
    }
    hasher.update(std.mem.asBytes(&req.descriptor.multisample.count));
    return hasher.final();
}

const ComputePipelineAsyncRequest = struct {
    next: ?*ComputePipelineAsyncRequest = null,
    device: types.WGPUDevice,
    descriptor: types.WGPUComputePipelineDescriptor,
    callback_info: p0.CreateComputePipelineAsyncCallbackInfo,
    label_bytes: ?[]u8 = null,
    entry_point_bytes: ?[]u8 = null,
    constants: ?[]types.WGPUConstantEntry = null,
    constant_key_bytes: ?[]?[]u8 = null,
    pipeline: types.WGPUComputePipeline = null,
    status: u32 = p0.CREATE_COMPUTE_PIPELINE_ASYNC_STATUS_SUCCESS,
    message_bytes: ?[]u8 = null,
};

const ComputeInflightEntry = singleflight.Registry(ComputePipelineAsyncRequest).Entry;

const RenderPipelineAsyncRequest = struct {
    next: ?*RenderPipelineAsyncRequest = null,
    device: types.WGPUDevice,
    descriptor: RenderPipelineDesc,
    callback_info: async_procs.CreateRenderPipelineAsyncCallbackInfo,
    label_bytes: ?[]u8 = null,
    vertex_entry_bytes: ?[]u8 = null,
    fragment_entry_bytes: ?[]u8 = null,
    vertex_buffers: ?[]RenderVertexBufferLayout = null,
    vertex_attributes: ?[]RenderVertexAttribute = null,
    fragment_state: ?*RenderFragmentState = null,
    fragment_targets: ?[]RenderColorTargetState = null,
    depth_stencil: ?*RenderDepthStencilDesc = null,
    pipeline: types.WGPURenderPipeline = null,
    status: u32 = async_procs.CREATE_PIPELINE_ASYNC_STATUS_SUCCESS,
    message_bytes: ?[]u8 = null,
};

const RenderInflightEntry = singleflight.Registry(RenderPipelineAsyncRequest).Entry;

fn free_compute_pipeline_request(req: *ComputePipelineAsyncRequest) void {
    if (req.label_bytes) |bytes| std.heap.c_allocator.free(bytes);
    if (req.entry_point_bytes) |bytes| std.heap.c_allocator.free(bytes);
    if (req.constant_key_bytes) |all_keys| {
        for (all_keys) |maybe_key| {
            if (maybe_key) |key| std.heap.c_allocator.free(key);
        }
        std.heap.c_allocator.free(all_keys);
    }
    if (req.constants) |constants| std.heap.c_allocator.free(constants);
    if (req.message_bytes) |bytes| std.heap.c_allocator.free(bytes);
    if (req.descriptor.layout != null) native.doeNativePipelineLayoutRelease(req.descriptor.layout);
    if (req.descriptor.compute.module != null) native.doeNativeShaderModuleRelease(req.descriptor.compute.module);
    native.doeNativeDeviceRelease(req.device);
    std.heap.c_allocator.destroy(req);
}

fn copy_compute_pipeline_request(
    device: types.WGPUDevice,
    desc: *const types.WGPUComputePipelineDescriptor,
    callback_info: p0.CreateComputePipelineAsyncCallbackInfo,
) ?*ComputePipelineAsyncRequest {
    const req = std.heap.c_allocator.create(ComputePipelineAsyncRequest) catch return null;
    errdefer std.heap.c_allocator.destroy(req);

    req.* = .{
        .device = device,
        .descriptor = desc.*,
        .callback_info = callback_info,
    };

    native.doeNativeDeviceAddRef(device);
    if (desc.compute.module != null) native.object_add_ref(native.DoeShaderModule, desc.compute.module);
    if (desc.layout != null) native.object_add_ref(native.DoePipelineLayout, desc.layout);

    req.label_bytes = dup_string_view(desc.label);
    req.descriptor.label = make_string_view(req.label_bytes);

    req.entry_point_bytes = dup_string_view(desc.compute.entryPoint);
    req.descriptor.compute.entryPoint = make_string_view(req.entry_point_bytes);

    if (desc.compute.constantCount > 0 and desc.compute.constants != null) {
        const count = desc.compute.constantCount;
        const constants = std.heap.c_allocator.alloc(types.WGPUConstantEntry, count) catch {
            free_compute_pipeline_request(req);
            return null;
        };
        const key_bytes = std.heap.c_allocator.alloc(?[]u8, count) catch {
            std.heap.c_allocator.free(constants);
            free_compute_pipeline_request(req);
            return null;
        };
        @memset(key_bytes, null);
        for (constants, 0..) |*entry, index| {
            entry.* = desc.compute.constants.?[index];
            key_bytes[index] = dup_string_view(entry.key);
            entry.key = make_string_view(key_bytes[index]);
        }
        req.constants = constants;
        req.constant_key_bytes = key_bytes;
        req.descriptor.compute.constants = constants.ptr;
        req.descriptor.compute.constantCount = count;
    } else {
        req.descriptor.compute.constants = null;
        req.descriptor.compute.constantCount = 0;
    }

    return req;
}

fn set_compute_pipeline_request_error(req: *ComputePipelineAsyncRequest, message: []const u8) void {
    req.status = 2;
    req.message_bytes = std.heap.c_allocator.dupe(u8, message) catch null;
}

fn copy_render_pipeline_request(
    device: types.WGPUDevice,
    desc_raw: *const anyopaque,
    callback_info: async_procs.CreateRenderPipelineAsyncCallbackInfo,
) ?*RenderPipelineAsyncRequest {
    const src: *const RenderPipelineDesc = @ptrCast(@alignCast(desc_raw));
    const req = std.heap.c_allocator.create(RenderPipelineAsyncRequest) catch return null;
    errdefer std.heap.c_allocator.destroy(req);

    req.* = .{
        .device = device,
        .descriptor = src.*,
        .callback_info = callback_info,
    };

    native.doeNativeDeviceAddRef(device);
    if (src.layout != null) native.object_add_ref(native.DoePipelineLayout, src.layout);
    if (src.vertex.module != null) native.object_add_ref(native.DoeShaderModule, src.vertex.module);
    if (src.fragment) |frag| {
        if (frag.module != null) native.object_add_ref(native.DoeShaderModule, frag.module);
    }

    req.label_bytes = dup_render_string_view(src.label);
    req.descriptor.label = make_render_string_view(req.label_bytes);
    req.vertex_entry_bytes = dup_render_string_view(src.vertex.entryPoint);
    req.descriptor.vertex.entryPoint = make_render_string_view(req.vertex_entry_bytes);

    if (src.vertex.bufferCount > 0 and src.vertex.buffers != null) {
        const src_bufs = @as([*]const RenderVertexBufferLayout, @ptrCast(@alignCast(src.vertex.buffers)))[0..src.vertex.bufferCount];
        const dst_bufs = std.heap.c_allocator.alloc(RenderVertexBufferLayout, src_bufs.len) catch {
            free_render_pipeline_request(req);
            return null;
        };
        var attr_total: usize = 0;
        for (src_bufs) |buf| attr_total += buf.attributeCount;
        const dst_attrs = if (attr_total > 0)
            std.heap.c_allocator.alloc(RenderVertexAttribute, attr_total) catch {
                std.heap.c_allocator.free(dst_bufs);
                free_render_pipeline_request(req);
                return null;
            }
        else
            null;
        req.vertex_buffers = dst_bufs;
        req.vertex_attributes = dst_attrs;
        req.descriptor.vertex.buffers = @ptrCast(dst_bufs.ptr);
        req.descriptor.vertex.bufferCount = dst_bufs.len;

        var attr_index: usize = 0;
        for (src_bufs, 0..) |src_buf, index| {
            dst_bufs[index] = src_buf;
            dst_bufs[index].nextInChain = null;
            if (src_buf.attributeCount > 0 and src_buf.attributes != null and dst_attrs != null) {
                const src_attrs = src_buf.attributes.?[0..src_buf.attributeCount];
                const dst_slice = dst_attrs.?[attr_index .. attr_index + src_buf.attributeCount];
                for (src_attrs, 0..) |src_attr, attr_offset| {
                    dst_slice[attr_offset] = src_attr;
                    dst_slice[attr_offset].nextInChain = null;
                }
                dst_bufs[index].attributes = dst_slice.ptr;
                attr_index += src_buf.attributeCount;
            } else {
                dst_bufs[index].attributes = null;
                dst_bufs[index].attributeCount = 0;
            }
        }
    } else {
        req.descriptor.vertex.buffers = null;
        req.descriptor.vertex.bufferCount = 0;
    }

    if (src.fragment) |frag| {
        const frag_copy = std.heap.c_allocator.create(RenderFragmentState) catch {
            free_render_pipeline_request(req);
            return null;
        };
        frag_copy.* = frag.*;
        req.fragment_state = frag_copy;
        req.fragment_entry_bytes = dup_render_string_view(frag.entryPoint);
        frag_copy.entryPoint = make_render_string_view(req.fragment_entry_bytes);
        if (frag.targetCount > 0 and frag.targets != null) {
            const targets = std.heap.c_allocator.alloc(RenderColorTargetState, frag.targetCount) catch {
                free_render_pipeline_request(req);
                return null;
            };
            @memcpy(targets, frag.targets.?[0..frag.targetCount]);
            for (targets) |*target| target.nextInChain = null;
            req.fragment_targets = targets;
            frag_copy.targets = targets.ptr;
            frag_copy.targetCount = targets.len;
        } else {
            frag_copy.targets = null;
            frag_copy.targetCount = 0;
        }
        req.descriptor.fragment = frag_copy;
    } else {
        req.descriptor.fragment = null;
    }

    if (src.depthStencil) |depth_raw| {
        const src_depth: *const RenderDepthStencilDesc = @ptrCast(@alignCast(depth_raw));
        const depth_copy = std.heap.c_allocator.create(RenderDepthStencilDesc) catch {
            free_render_pipeline_request(req);
            return null;
        };
        depth_copy.* = src_depth.*;
        depth_copy.nextInChain = null;
        req.depth_stencil = depth_copy;
        req.descriptor.depthStencil = @ptrCast(depth_copy);
    } else {
        req.descriptor.depthStencil = null;
    }

    return req;
}

fn free_render_pipeline_request(req: *RenderPipelineAsyncRequest) void {
    if (req.label_bytes) |bytes| std.heap.c_allocator.free(bytes);
    if (req.vertex_entry_bytes) |bytes| std.heap.c_allocator.free(bytes);
    if (req.fragment_entry_bytes) |bytes| std.heap.c_allocator.free(bytes);
    if (req.vertex_buffers) |bufs| std.heap.c_allocator.free(bufs);
    if (req.vertex_attributes) |attrs| std.heap.c_allocator.free(attrs);
    if (req.fragment_targets) |targets| std.heap.c_allocator.free(targets);
    if (req.fragment_state) |frag| std.heap.c_allocator.destroy(frag);
    if (req.depth_stencil) |depth| std.heap.c_allocator.destroy(depth);
    if (req.message_bytes) |bytes| std.heap.c_allocator.free(bytes);
    if (req.descriptor.layout != null) native.doeNativePipelineLayoutRelease(req.descriptor.layout);
    if (req.descriptor.vertex.module != null) native.doeNativeShaderModuleRelease(req.descriptor.vertex.module);
    if (req.descriptor.fragment) |frag| {
        if (frag.module != null) native.doeNativeShaderModuleRelease(frag.module);
    }
    native.doeNativeDeviceRelease(req.device);
    std.heap.c_allocator.destroy(req);
}

fn set_render_pipeline_request_error(req: *RenderPipelineAsyncRequest, message: []const u8) void {
    req.status = 2;
    req.message_bytes = std.heap.c_allocator.dupe(u8, message) catch null;
}

fn run_compute_pipeline_async(ctx_raw: ?*anyopaque) void {
    const entry: *ComputeInflightEntry = @ptrCast(@alignCast(ctx_raw orelse return));
    const head = g_compute_inflight.take(std.heap.c_allocator, entry) orelse return;
    const lead = head;
    lead.pipeline = native.doeNativeDeviceCreateComputePipeline(lead.device, &lead.descriptor);
    pipeline_cache_integration.recordComputePipelineCreation(if (lead.entry_point_bytes) |ep| ep else null);
    if (lead.pipeline == null) {
        set_compute_pipeline_request_error(lead, "pipeline creation failed");
    }
    var req: ?*ComputePipelineAsyncRequest = head;
    var first = true;
    while (req) |current| {
        const next = current.next;
        current.status = lead.status;
        if (lead.pipeline != null) {
            current.pipeline = lead.pipeline;
            if (!first) native.object_add_ref(native.DoeComputePipeline, current.pipeline);
        } else if (current != lead) {
            set_compute_pipeline_request_error(current, "pipeline creation failed");
        }
        if (current.callback_info.callback) |cb| {
            cb(current.status, current.pipeline, make_string_view(current.message_bytes), current.callback_info.userdata1, current.callback_info.userdata2);
        }
        free_compute_pipeline_request(current);
        first = false;
        req = next;
    }
}

fn run_render_pipeline_async(ctx_raw: ?*anyopaque) void {
    const entry: *RenderInflightEntry = @ptrCast(@alignCast(ctx_raw orelse return));
    const head = g_render_inflight.take(std.heap.c_allocator, entry) orelse return;
    const lead = head;
    lead.pipeline = native.doeNativeDeviceCreateRenderPipeline(lead.device, @ptrCast(&lead.descriptor));
    pipeline_cache_integration.recordRenderPipelineCreation();
    if (lead.pipeline == null) {
        set_render_pipeline_request_error(lead, "render pipeline creation failed");
    }
    var req: ?*RenderPipelineAsyncRequest = head;
    var first = true;
    while (req) |current| {
        const next = current.next;
        current.status = lead.status;
        if (lead.pipeline != null) {
            current.pipeline = lead.pipeline;
            if (!first) native.object_add_ref(native.DoeRenderPipeline, current.pipeline);
        } else if (current != lead) {
            set_render_pipeline_request_error(current, "render pipeline creation failed");
        }
        if (current.callback_info.callback) |cb| {
            cb(current.status, current.pipeline, make_string_view(current.message_bytes), current.callback_info.userdata1, current.callback_info.userdata2);
        }
        free_render_pipeline_request(current);
        first = false;
        req = next;
    }
}

fn bridge_pop_error_scope_callback(
    error_type: u32,
    msg: types.WGPUStringView,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void {
    _ = userdata2;
    const state = userdata1 orelse return;
    const bridge_state: *PopErrorScopeBridgeState = @ptrCast(@alignCast(state));
    const callback = bridge_state.callback orelse return;
    callback(async_procs.POP_ERROR_SCOPE_STATUS_SUCCESS, error_type, msg, bridge_state.userdata1, bridge_state.userdata2);
}

fn static_string_view(comptime text: []const u8) types.WGPUStringView {
    return .{ .data = text.ptr, .length = text.len };
}

fn backend_type_for(adapter: *native.DoeAdapter) types.WGPUBackendType {
    return switch (adapter.backend) {
        .metal => .metal,
        .vulkan => .vulkan,
        .d3d12 => .d3d12,
    };
}

fn fill_adapter_info_struct(adapter_raw: types.WGPUAdapter, out: *p1cap.AdapterInfo) types.WGPUStatus {
    const adapter = native.cast(native.DoeAdapter, adapter_raw) orelse return 0;
    out.* = p1cap.initAdapterInfo(out.nextInChain);
    out.vendor = static_string_view("Doe");
    out.architecture = switch (adapter.backend) {
        .metal => static_string_view("metal"),
        .vulkan => static_string_view("vulkan"),
        .d3d12 => static_string_view("d3d12"),
    };
    out.device = switch (adapter.backend) {
        .metal => static_string_view("Doe Metal Adapter"),
        .vulkan => static_string_view("Doe Vulkan Adapter"),
        .d3d12 => static_string_view("Doe D3D12 Adapter"),
    };
    out.description = out.device;
    out.backendType = backend_type_for(adapter);
    out.adapterType = 0x00000004; // Unknown
    out.vendorID = 0;
    out.deviceID = 0;
    out.subgroupMinSize = 0;
    out.subgroupMaxSize = 0;
    return types.WGPUStatus_Success;
}

fn fill_supported_features_from_adapter(adapter_raw: types.WGPUAdapter, out: *p1cap.SupportedFeatures) void {
    out.* = p1cap.initSupportedFeatures();
    var count: usize = 0;
    for (FEATURE_CANDIDATES) |feature| {
        if (native.doeNativeAdapterHasFeature(adapter_raw, feature) != 0) count += 1;
    }
    if (count == 0) return;
    const owned = std.heap.c_allocator.alloc(types.WGPUFeatureName, count) catch return;
    var write_index: usize = 0;
    for (FEATURE_CANDIDATES) |feature| {
        if (native.doeNativeAdapterHasFeature(adapter_raw, feature) == 0) continue;
        owned[write_index] = feature;
        write_index += 1;
    }
    out.featureCount = write_index;
    out.features = owned.ptr;
}

fn fill_supported_features_from_device(device_raw: types.WGPUDevice, out: *p1cap.SupportedFeatures) void {
    out.* = p1cap.initSupportedFeatures();
    var count: usize = 0;
    for (FEATURE_CANDIDATES) |feature| {
        if (native.doeNativeDeviceHasFeature(device_raw, feature) != 0) count += 1;
    }
    if (count == 0) return;
    const owned = std.heap.c_allocator.alloc(types.WGPUFeatureName, count) catch return;
    var write_index: usize = 0;
    for (FEATURE_CANDIDATES) |feature| {
        if (native.doeNativeDeviceHasFeature(device_raw, feature) == 0) continue;
        owned[write_index] = feature;
        write_index += 1;
    }
    out.featureCount = write_index;
    out.features = owned.ptr;
}

fn symbolView(comptime name: []const u8) types.WGPUStringView {
    return .{ .data = name.ptr, .length = name.len };
}

fn resolveRequiredProc(comptime FnType: type, comptime symbol_name: []const u8) FnType {
    const proc = wgpuGetProcAddress(symbolView(symbol_name)) orelse
        doeWgpuDropinAbortMissingRequiredSymbol(symbolView(symbol_name));
    return @as(FnType, @ptrCast(proc));
}

pub export fn wgpuAdapterAddRef(a0: types.WGPUAdapter) callconv(.c) void {
    native.doeNativeAdapterAddRef(a0);
}

pub export fn wgpuAdapterGetFeatures(a0: types.WGPUAdapter, a1: *p1cap.SupportedFeatures) callconv(.c) void {
    fill_supported_features_from_adapter(a0, a1);
}

pub export fn wgpuAdapterGetFormatCapabilities(a0: types.WGPUAdapter, a1: types.WGPUTextureFormat, a2: *p1cap.DawnFormatCapabilities) callconv(.c) types.WGPUStatus {
    const proc = resolveRequiredProc(*const fn (types.WGPUAdapter, types.WGPUTextureFormat, *p1cap.DawnFormatCapabilities) callconv(.c) types.WGPUStatus, "wgpuAdapterGetFormatCapabilities");
    return proc(a0, a1, a2);
}

pub export fn wgpuAdapterGetInfo(a0: types.WGPUAdapter, a1: *p1cap.AdapterInfo) callconv(.c) types.WGPUStatus {
    return fill_adapter_info_struct(a0, a1);
}

pub export fn wgpuAdapterGetInstance(a0: types.WGPUAdapter) callconv(.c) types.WGPUInstance {
    return native.doeNativeAdapterGetInstance(a0);
}

pub export fn wgpuAdapterGetLimits(a0: types.WGPUAdapter, a1: *p1cap.Limits) callconv(.c) types.WGPUStatus {
    return native.doeNativeAdapterGetLimits(a0, a1);
}

pub export fn wgpuAdapterInfoFreeMembers(a0: p1cap.AdapterInfo) callconv(.c) void {
    _ = a0;
}

pub export fn wgpuAdapterPropertiesMemoryHeapsFreeMembers(a0: p1cap.AdapterPropertiesMemoryHeaps) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p1cap.AdapterPropertiesMemoryHeaps) callconv(.c) void, "wgpuAdapterPropertiesMemoryHeapsFreeMembers");
    proc(a0);
}

pub export fn wgpuAdapterPropertiesSubgroupMatrixConfigsFreeMembers(a0: p1cap.AdapterPropertiesSubgroupMatrixConfigs) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p1cap.AdapterPropertiesSubgroupMatrixConfigs) callconv(.c) void, "wgpuAdapterPropertiesSubgroupMatrixConfigsFreeMembers");
    proc(a0);
}

pub export fn wgpuBindGroupAddRef(a0: types.WGPUBindGroup) callconv(.c) void {
    native.object_add_ref(native.DoeBindGroup, a0);
}

pub export fn wgpuBindGroupLayoutAddRef(a0: types.WGPUBindGroupLayout) callconv(.c) void {
    native.object_add_ref(native.DoeBindGroupLayout, a0);
}

pub export fn wgpuBufferAddRef(a0: types.WGPUBuffer) callconv(.c) void {
    native.object_add_ref(native.DoeBuffer, a0);
}

pub export fn wgpuBufferDestroy(a0: types.WGPUBuffer) callconv(.c) void {
    // Doe buffers are cleaned up on release; destroy is a validated no-op.
    _ = native.cast(native.DoeBuffer, a0);
}

pub export fn wgpuCommandBufferAddRef(a0: types.WGPUCommandBuffer) callconv(.c) void {
    native.object_add_ref(native.DoeCommandBuffer, a0);
}

pub export fn wgpuCommandEncoderAddRef(a0: types.WGPUCommandEncoder) callconv(.c) void {
    native.object_add_ref(native.DoeCommandEncoder, a0);
}

pub export fn wgpuCommandEncoderClearBuffer(a0: types.WGPUCommandEncoder, a1: types.WGPUBuffer, a2: u64, a3: u64) callconv(.c) void {
    native.doeNativeCommandEncoderClearBuffer(a0, a1, a2, a3);
}

pub export fn wgpuCommandEncoderWriteBuffer(a0: types.WGPUCommandEncoder, a1: types.WGPUBuffer, a2: u64, a3: [*]const u8, a4: u64) callconv(.c) void {
    // Write data directly into the Doe buffer's backing memory at the given offset.
    _ = a0;
    const size: usize = @intCast(a4);
    const offset: usize = @intCast(a2);
    const dst_ptr = native.doeNativeBufferGetMappedRange(a1, offset, size) orelse return;
    const dst: [*]u8 = @ptrCast(dst_ptr);
    @memcpy(dst[0..size], a3[0..size]);
}

pub export fn wgpuComputePassEncoderAddRef(a0: types.WGPUComputePassEncoder) callconv(.c) void {
    native.object_add_ref(native.DoeComputePass, a0);
}

pub export fn wgpuComputePassEncoderDispatchWorkgroupsIndirect(a0: types.WGPUComputePassEncoder, a1: types.WGPUBuffer, a2: u64) callconv(.c) void {
    native.doeNativeComputePassDispatchIndirect(a0, a1, a2);
}

pub export fn wgpuComputePassEncoderSetImmediates(a0: types.WGPUComputePassEncoder, a1: u32, a2: ?*const anyopaque, a3: usize) callconv(.c) void {
    doeNativeComputePassSetImmediates(a0, a1, if (a2) |ptr| @as([*]const u8, @ptrCast(ptr)) else null, a3);
}

pub export fn wgpuComputePassEncoderSetResourceTable(a0: types.WGPUComputePassEncoder, a1: p1res.WGPUResourceTable) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (types.WGPUComputePassEncoder, p1res.WGPUResourceTable) callconv(.c) void, "wgpuComputePassEncoderSetResourceTable");
    proc(a0, a1);
}

pub export fn wgpuComputePassEncoderWriteTimestamp(a0: types.WGPUComputePassEncoder, a1: types.WGPUQuerySet, a2: u32) callconv(.c) void {
    // Route through the command encoder timestamp path, extracting the
    // parent encoder from the compute pass.
    const pass = native.cast(native.DoeComputePass, a0) orelse return;
    query_native.doeNativeCommandEncoderWriteTimestamp(native.toOpaque(pass.enc), a1, a2);
}

pub export fn wgpuComputePipelineAddRef(a0: types.WGPUComputePipeline) callconv(.c) void {
    native.object_add_ref(native.DoeComputePipeline, a0);
}

pub export fn wgpuDawnDrmFormatCapabilitiesFreeMembers(a0: p1cap.DawnDrmFormatCapabilities) callconv(.c) void {
    const proc = resolveRequiredProc(*const fn (p1cap.DawnDrmFormatCapabilities) callconv(.c) void, "wgpuDawnDrmFormatCapabilitiesFreeMembers");
    proc(a0);
}

pub export fn wgpuDeviceAddRef(a0: types.WGPUDevice) callconv(.c) void {
    native.doeNativeDeviceAddRef(a0);
}

pub export fn wgpuDeviceCreateComputePipelineAsync(a0: types.WGPUDevice, a1: *const types.WGPUComputePipelineDescriptor, a2: p0.CreateComputePipelineAsyncCallbackInfo) callconv(.c) types.WGPUFuture {
    const future = types.WGPUFuture{ .id = next_async_future_id() };
    const req = copy_compute_pipeline_request(a0, a1, a2) orelse {
        if (a2.callback) |cb| {
            const msg = "async request allocation failed";
            cb(2, null, .{ .data = msg.ptr, .length = msg.len }, a2.userdata1, a2.userdata2);
        }
        return future;
    };
    const joined = g_compute_inflight.join_or_create(std.heap.c_allocator, compute_pipeline_request_key(req), req) catch {
        free_compute_pipeline_request(req);
        if (a2.callback) |cb| {
            const msg = "async pipeline single-flight allocation failed";
            cb(2, null, .{ .data = msg.ptr, .length = msg.len }, a2.userdata1, a2.userdata2);
        }
        return future;
    };
    if (joined.leader) {
        task_pool.submit(.{
            .run = run_compute_pipeline_async,
            .ctx = joined.entry,
        }) catch {
            _ = g_compute_inflight.take(std.heap.c_allocator, joined.entry);
            free_compute_pipeline_request(req);
            if (a2.callback) |cb| {
                const msg = "async pipeline worker submit failed";
                cb(2, null, .{ .data = msg.ptr, .length = msg.len }, a2.userdata1, a2.userdata2);
            }
        };
    }
    return future;
}

pub export fn wgpuDeviceCreateRenderBundleEncoder(a0: types.WGPUDevice, a1: *const anyopaque) callconv(.c) render.RenderBundleEncoder {
    return native.doeNativeDeviceCreateRenderBundleEncoder(a0, @ptrCast(@alignCast(a1)));
}

pub export fn wgpuDeviceCreateRenderPipelineAsync(a0: types.WGPUDevice, a1: *const anyopaque, a2: async_procs.CreateRenderPipelineAsyncCallbackInfo) callconv(.c) types.WGPUFuture {
    const future = types.WGPUFuture{ .id = next_async_future_id() };
    const req = copy_render_pipeline_request(a0, a1, a2) orelse {
        if (a2.callback) |cb| {
            const msg = "async render request allocation failed";
            cb(2, null, .{ .data = msg.ptr, .length = msg.len }, a2.userdata1, a2.userdata2);
        }
        return future;
    };
    const joined = g_render_inflight.join_or_create(std.heap.c_allocator, render_pipeline_request_key(req), req) catch {
        free_render_pipeline_request(req);
        if (a2.callback) |cb| {
            const msg = "async render single-flight allocation failed";
            cb(2, null, .{ .data = msg.ptr, .length = msg.len }, a2.userdata1, a2.userdata2);
        }
        return future;
    };
    if (joined.leader) {
        task_pool.submit(.{
            .run = run_render_pipeline_async,
            .ctx = joined.entry,
        }) catch {
            _ = g_render_inflight.take(std.heap.c_allocator, joined.entry);
            free_render_pipeline_request(req);
            if (a2.callback) |cb| {
                const msg = "async render worker submit failed";
                cb(2, null, .{ .data = msg.ptr, .length = msg.len }, a2.userdata1, a2.userdata2);
            }
        };
    }
    return future;
}

pub export fn wgpuDeviceCreateExternalTexture(a0: types.WGPUDevice, a1: ?*const anyopaque) callconv(.c) p2life.WGPUExternalTexture {
    return native.doeNativeDeviceCreateExternalTexture(a0, a1);
}

pub export fn wgpuDeviceCreateResourceTable(a0: types.WGPUDevice, a1: *const p1res.ResourceTableDescriptor) callconv(.c) p1res.WGPUResourceTable {
    const proc = resolveRequiredProc(*const fn (types.WGPUDevice, *const p1res.ResourceTableDescriptor) callconv(.c) p1res.WGPUResourceTable, "wgpuDeviceCreateResourceTable");
    return proc(a0, a1);
}

pub export fn wgpuDeviceDestroy(a0: types.WGPUDevice) callconv(.c) void {
    _ = a0;
}

pub export fn wgpuDeviceGetAdapter(a0: types.WGPUDevice) callconv(.c) types.WGPUAdapter {
    return native.doeNativeDeviceGetAdapter(a0);
}

pub export fn wgpuDeviceGetAdapterInfo(a0: types.WGPUDevice, a1: *p1cap.AdapterInfo) callconv(.c) types.WGPUStatus {
    const adapter = native.doeNativeDeviceGetAdapter(a0) orelse return 0;
    defer native.doeNativeAdapterRelease(adapter);
    return fill_adapter_info_struct(adapter, a1);
}

pub export fn wgpuDeviceGetFeatures(a0: types.WGPUDevice, a1: *p1cap.SupportedFeatures) callconv(.c) void {
    fill_supported_features_from_device(a0, a1);
}

pub export fn wgpuDeviceGetLimits(a0: types.WGPUDevice, a1: *p1cap.Limits) callconv(.c) types.WGPUStatus {
    return native.doeNativeDeviceGetLimits(a0, a1);
}

pub export fn wgpuDevicePopErrorScope(a0: types.WGPUDevice, a1: async_procs.PopErrorScopeCallbackInfo) callconv(.c) types.WGPUFuture {
    const dev = native.cast(native.DoeDevice, a0) orelse {
        if (a1.callback) |callback| {
            callback(
                async_procs.POP_ERROR_SCOPE_STATUS_SUCCESS,
                error_scope.ERROR_TYPE_INTERNAL,
                .{ .data = null, .length = 0 },
                a1.userdata1,
                a1.userdata2,
            );
        }
        return .{ .id = 5 };
    };
    var state = PopErrorScopeBridgeState{
        .callback = a1.callback,
        .userdata1 = a1.userdata1,
        .userdata2 = a1.userdata2,
    };
    if (!dev.error_scopes.pop(.{
        .next_in_chain = null,
        .mode = 0,
        .callback = bridge_pop_error_scope_callback,
        .userdata1 = &state,
        .userdata2 = null,
    })) {
        if (a1.callback) |callback| {
            callback(
                async_procs.POP_ERROR_SCOPE_STATUS_SUCCESS,
                error_scope.ERROR_TYPE_INTERNAL,
                .{ .data = null, .length = 0 },
                a1.userdata1,
                a1.userdata2,
            );
        }
    }
    return .{ .id = 5 };
}

pub export fn wgpuDevicePushErrorScope(a0: types.WGPUDevice, a1: u32) callconv(.c) void {
    native.doeNativeDevicePushErrorScope(a0, a1);
}

pub export fn wgpuDeviceSetUncapturedErrorCallback(
    a0: types.WGPUDevice,
    callback: ?error_scope.UncapturedErrorCallback,
    userdata1: ?*anyopaque,
    userdata2: ?*anyopaque,
) callconv(.c) void {
    native.doeNativeDeviceSetUncapturedErrorCallback(a0, callback, userdata1, userdata2);
}

pub export fn wgpuDeviceSetLoggingCallback(a0: types.WGPUDevice, a1: LoggingCallbackInfo) callconv(.c) void {
    _ = a0;
    _ = a1;
}

pub export fn wgpuDeviceTick(a0: types.WGPUDevice) callconv(.c) types.WGPUBool {
    const dev = native.cast(native.DoeDevice, a0) orelse return types.WGPU_FALSE;
    if (dev.queue) |queue| {
        queue.gpu_timeline.drain_ready();
    }
    return types.WGPU_FALSE;
}

pub export fn wgpuExternalTextureAddRef(a0: p2life.WGPUExternalTexture) callconv(.c) void {
    native.doeNativeExternalTextureAddRef(a0);
}

pub export fn wgpuGetInstanceFeatures(a0: *p1cap.SupportedInstanceFeatures) callconv(.c) void {
    a0.* = p1cap.initSupportedInstanceFeatures();
}

pub export fn wgpuGetInstanceLimits(a0: *p1cap.InstanceLimits) callconv(.c) types.WGPUStatus {
    a0.* = p1cap.initInstanceLimits();
    return types.WGPUStatus_Success;
}

pub export fn wgpuHasInstanceFeature(a0: p1cap.WGPUInstanceFeatureName) callconv(.c) types.WGPUBool {
    _ = a0;
    return types.WGPU_FALSE;
}

pub export fn wgpuInstanceAddRef(a0: types.WGPUInstance) callconv(.c) void {
    native.doeNativeInstanceAddRef(a0);
}

pub export fn wgpuInstanceCreateSurface(a0: types.WGPUInstance, a1: *const surface.SurfaceDescriptor) callconv(.c) surface.Surface {
    // Route through native Doe surface creation when the instance is a Doe handle.
    if (native.cast(native.DoeInstance, a0) != null) {
        return native.doeAbiBridgeInstanceCreateSurface(a0, a1);
    }
    const proc = resolveRequiredProc(*const fn (types.WGPUInstance, *const surface.SurfaceDescriptor) callconv(.c) surface.Surface, "wgpuInstanceCreateSurface");
    return proc(a0, a1);
}

pub export fn wgpuInstanceGetWGSLLanguageFeatures(a0: types.WGPUInstance, a1: *p1cap.SupportedWGSLLanguageFeatures) callconv(.c) void {
    _ = a0;
    a1.* = p1cap.initSupportedWGSLLanguageFeatures();
}

pub export fn wgpuInstanceHasWGSLLanguageFeature(a0: types.WGPUInstance, a1: p1cap.WGPUWGSLLanguageFeatureName) callconv(.c) types.WGPUBool {
    _ = a0;
    _ = a1;
    return types.WGPU_FALSE;
}

pub export fn wgpuPipelineLayoutAddRef(a0: types.WGPUPipelineLayout) callconv(.c) void {
    native.object_add_ref(native.DoePipelineLayout, a0);
}

pub export fn wgpuQuerySetAddRef(a0: types.WGPUQuerySet) callconv(.c) void {
    native.object_add_ref(query_native.DoeQuerySet, a0);
}

pub export fn wgpuQuerySetDestroy(a0: types.WGPUQuerySet) callconv(.c) void {
    doeNativeQuerySetDestroy(a0);
}

pub export fn wgpuQuerySetGetCount(a0: types.WGPUQuerySet) callconv(.c) u32 {
    return doeNativeQuerySetGetCount(a0);
}

pub export fn wgpuQuerySetGetType(a0: types.WGPUQuerySet) callconv(.c) types.WGPUQueryType {
    return doeNativeQuerySetGetType(a0);
}

pub export fn wgpuQueueAddRef(a0: types.WGPUQueue) callconv(.c) void {
    native.doeNativeQueueAddRef(a0);
}

pub export fn wgpuRenderBundleAddRef(_: render.RenderBundle) callconv(.c) void {
    // Render bundles are opaque Doe allocations; no ref counting yet.
}

pub export fn wgpuRenderBundleEncoderAddRef(_: render.RenderBundleEncoder) callconv(.c) void {
    // Render bundle encoders are opaque Doe allocations; no ref counting yet.
}

pub export fn wgpuRenderBundleEncoderDraw(a0: render.RenderBundleEncoder, a1: u32, a2: u32, a3: u32, a4: u32) callconv(.c) void {
    native.doeNativeRenderBundleEncoderDraw(a0, a1, a2, a3, a4);
}

pub export fn wgpuRenderBundleEncoderDrawIndexed(a0: render.RenderBundleEncoder, a1: u32, a2: u32, a3: u32, a4: i32, a5: u32) callconv(.c) void {
    native.doeNativeRenderBundleEncoderDrawIndexed(a0, a1, a2, a3, a4, a5);
}

pub export fn wgpuRenderBundleEncoderDrawIndexedIndirect(a0: render.RenderBundleEncoder, a1: types.WGPUBuffer, a2: u64) callconv(.c) void {
    native.doeNativeRenderBundleEncoderDrawIndexedIndirect(a0, a1, a2);
}

pub export fn wgpuRenderBundleEncoderDrawIndirect(a0: render.RenderBundleEncoder, a1: types.WGPUBuffer, a2: u64) callconv(.c) void {
    native.doeNativeRenderBundleEncoderDrawIndirect(a0, a1, a2);
}

pub export fn wgpuRenderBundleEncoderFinish(a0: render.RenderBundleEncoder, a1: ?*const anyopaque) callconv(.c) render.RenderBundle {
    return native.doeNativeRenderBundleEncoderFinish(a0, @ptrCast(@alignCast(a1)));
}

pub export fn wgpuRenderBundleEncoderInsertDebugMarker(a0: render.RenderBundleEncoder, a1: types.WGPUStringView) callconv(.c) void {
    native.doeNativeRenderBundleEncoderInsertDebugMarker(a0, if (a1.data) |d| d else null, a1.length);
}

pub export fn wgpuRenderBundleEncoderPopDebugGroup(a0: render.RenderBundleEncoder) callconv(.c) void {
    native.doeNativeRenderBundleEncoderPopDebugGroup(a0);
}

pub export fn wgpuRenderBundleEncoderPushDebugGroup(a0: render.RenderBundleEncoder, a1: types.WGPUStringView) callconv(.c) void {
    native.doeNativeRenderBundleEncoderPushDebugGroup(a0, if (a1.data) |d| d else null, a1.length);
}

pub export fn wgpuRenderBundleEncoderRelease(a0: render.RenderBundleEncoder) callconv(.c) void {
    native.doeNativeRenderBundleEncoderRelease(a0);
}

pub export fn wgpuRenderBundleEncoderSetBindGroup(a0: render.RenderBundleEncoder, a1: u32, a2: types.WGPUBindGroup, a3: usize, a4: ?[*]const u32) callconv(.c) void {
    native.doeNativeRenderBundleEncoderSetBindGroup(a0, a1, a2, a3, a4);
}
