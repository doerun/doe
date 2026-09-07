const core = @import("wgpu_dropin_ext_a_core.zig");
const process_roots = @import("../runtime/process_roots.zig");
const std = core.std;
const types = core.types;
const p0 = core.p0;
const async_procs = core.async_procs;
const native = core.native;
const singleflight = core.singleflight;

pub const SnapshotError = error{ OutOfMemory, InvalidDescriptor, UnsupportedDescriptor };

pub const string_view_slice = core.string_view_slice;
pub const dup_string_view = core.dup_string_view;
pub const make_string_view = core.make_string_view;

pub const RenderStringView = extern struct {
    data: ?[*]const u8,
    length: usize,
};

pub const RenderBlendComponent = extern struct {
    operation: u32,
    srcFactor: u32,
    dstFactor: u32,
};

pub const RenderBlendState = extern struct {
    color: RenderBlendComponent,
    alpha: RenderBlendComponent,
};

pub const RenderColorTargetState = extern struct {
    nextInChain: ?*anyopaque,
    format: u32,
    blend: ?*const RenderBlendState,
    writeMask: u64,
};

pub const RenderVertexState = extern struct {
    nextInChain: ?*anyopaque,
    module: ?*anyopaque,
    entryPoint: RenderStringView,
    constantCount: usize,
    constants: ?*anyopaque,
    bufferCount: usize,
    buffers: ?*anyopaque,
};

pub const RenderFragmentState = extern struct {
    nextInChain: ?*anyopaque,
    module: ?*anyopaque,
    entryPoint: RenderStringView,
    constantCount: usize,
    constants: ?*anyopaque,
    targetCount: usize,
    targets: ?[*]const RenderColorTargetState,
};

pub const RenderPrimitiveState = extern struct {
    nextInChain: ?*anyopaque,
    topology: u32,
    stripIndexFormat: u32,
    frontFace: u32,
    cullMode: u32,
    unclippedDepth: u32,
};

pub const RenderMultisampleState = extern struct {
    nextInChain: ?*anyopaque,
    count: u32,
    mask: u32,
    alphaToCoverageEnabled: u32,
};

pub const RenderVertexAttribute = extern struct {
    nextInChain: ?*anyopaque,
    format: u32,
    offset: u64,
    shaderLocation: u32,
};

pub const RenderVertexBufferLayout = extern struct {
    nextInChain: ?*anyopaque,
    stepMode: u32,
    arrayStride: u64,
    attributeCount: usize,
    attributes: ?[*]const RenderVertexAttribute,
};

pub const RenderDepthStencilDesc = extern struct {
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

pub const RenderPipelineDesc = extern struct {
    nextInChain: ?*anyopaque,
    label: RenderStringView,
    layout: ?*anyopaque,
    vertex: RenderVertexState,
    primitive: RenderPrimitiveState,
    depthStencil: ?*anyopaque,
    multisample: RenderMultisampleState,
    fragment: ?*const RenderFragmentState,
};

pub var g_next_async_future_id = std.atomic.Value(u64).init(32);
pub var g_compute_inflight = singleflight.Registry(ComputePipelineAsyncRequest).init(process_roots.dropinAsyncPipelineAllocator());
pub var g_render_inflight = singleflight.Registry(RenderPipelineAsyncRequest).init(process_roots.dropinAsyncPipelineAllocator());

pub fn next_async_future_id() u64 {
    return g_next_async_future_id.fetchAdd(1, .monotonic);
}

pub fn render_string_view_slice(view: RenderStringView) []const u8 {
    return string_view_slice(.{ .data = view.data, .length = view.length });
}

pub fn dup_render_string_view(view: RenderStringView) ?[]u8 {
    const src = render_string_view_slice(view);
    if (src.len == 0) return null;
    return std.heap.c_allocator.dupe(u8, src) catch null;
}

pub fn make_render_string_view(bytes: ?[]u8) RenderStringView {
    if (bytes) |owned| {
        return .{ .data = owned.ptr, .length = owned.len };
    }
    return .{ .data = null, .length = 0 };
}

pub fn optional_ptr_id(raw: ?*anyopaque) usize {
    if (raw) |ptr| return @intFromPtr(ptr);
    return 0;
}

pub fn compute_pipeline_request_key(req: *const ComputePipelineAsyncRequest) u64 {
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

pub fn render_pipeline_request_key(req: *const RenderPipelineAsyncRequest) u64 {
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

pub const ComputePipelineAsyncRequest = struct {
    pub const matches = same_compute_request;
    allocator: std.mem.Allocator = std.heap.c_allocator,
    next: ?*ComputePipelineAsyncRequest = null,
    device: types.WGPUDevice,
    descriptor: types.WGPUComputePipelineDescriptor,
    callback_info: p0.CreateComputePipelineAsyncCallbackInfo,
    label_bytes: ?[]u8 = null,
    entry_point_bytes: ?[]u8 = null,
    constants: ?[]types.WGPUConstantEntry = null,
    pipeline: types.WGPUComputePipeline = null,
    status: u32 = p0.CREATE_COMPUTE_PIPELINE_ASYNC_STATUS_SUCCESS,
    message: []const u8 = "",
};

pub const ComputeInflightEntry = singleflight.Registry(ComputePipelineAsyncRequest).Entry;

pub const RenderPipelineAsyncRequest = struct {
    pub const matches = same_render_request;
    allocator: std.mem.Allocator = std.heap.c_allocator,
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
    fragment_blends: ?[]RenderBlendState = null,
    vertex_constants: ?[]types.WGPUConstantEntry = null,
    fragment_constants: ?[]types.WGPUConstantEntry = null,
    depth_stencil: ?*RenderDepthStencilDesc = null,
    pipeline: types.WGPURenderPipeline = null,
    status: u32 = async_procs.CREATE_PIPELINE_ASYNC_STATUS_SUCCESS,
    message: []const u8 = "",
};

pub const RenderInflightEntry = singleflight.Registry(RenderPipelineAsyncRequest).Entry;

fn same_constants(left: ?[]types.WGPUConstantEntry, right: ?[]types.WGPUConstantEntry) bool {
    const a = left orelse &.{};
    const b = right orelse &.{};
    if (a.len != b.len) return false;
    for (a, b) |x, y| {
        if (@as(u64, @bitCast(x.value)) != @as(u64, @bitCast(y.value)) or
            !std.mem.eql(u8, string_view_slice(x.key), string_view_slice(y.key))) return false;
    }
    return true;
}

fn same_compute_request(left: *const ComputePipelineAsyncRequest, right: *const ComputePipelineAsyncRequest) bool {
    return left.device == right.device and left.descriptor.layout == right.descriptor.layout and
        left.descriptor.compute.module == right.descriptor.compute.module and
        std.mem.eql(u8, string_view_slice(left.descriptor.label), string_view_slice(right.descriptor.label)) and
        std.mem.eql(u8, string_view_slice(left.descriptor.compute.entryPoint), string_view_slice(right.descriptor.compute.entryPoint)) and
        same_constants(left.constants, right.constants);
}

fn same_render_request(left: *const RenderPipelineAsyncRequest, right: *const RenderPipelineAsyncRequest) bool {
    const a = &left.descriptor;
    const b = &right.descriptor;
    if (left.device != right.device or a.layout != b.layout or a.vertex.module != b.vertex.module or
        !std.mem.eql(u8, render_string_view_slice(a.label), render_string_view_slice(b.label)) or
        !std.mem.eql(u8, render_string_view_slice(a.vertex.entryPoint), render_string_view_slice(b.vertex.entryPoint)) or
        !std.meta.eql(a.primitive, b.primitive) or !std.meta.eql(a.multisample, b.multisample) or
        !same_constants(left.vertex_constants, right.vertex_constants) or
        !same_constants(left.fragment_constants, right.fragment_constants)) return false;
    const ab = left.vertex_buffers orelse &.{};
    const bb = right.vertex_buffers orelse &.{};
    if (ab.len != bb.len) return false;
    for (ab, bb) |x, y| {
        if (x.arrayStride != y.arrayStride or x.stepMode != y.stepMode or x.attributeCount != y.attributeCount) return false;
        if (x.attributeCount != 0) {
            for (x.attributes.?[0..x.attributeCount], y.attributes.?[0..y.attributeCount]) |xa, ya| {
                if (!std.meta.eql(xa, ya)) return false;
            }
        }
    }
    if ((a.fragment == null) != (b.fragment == null)) return false;
    if (a.fragment) |af| {
        const bf = b.fragment.?;
        if (af.module != bf.module or
            !std.mem.eql(u8, render_string_view_slice(af.entryPoint), render_string_view_slice(bf.entryPoint))) return false;
        const at = left.fragment_targets orelse &.{};
        const bt = right.fragment_targets orelse &.{};
        if (at.len != bt.len) return false;
        for (at, bt) |x, y| {
            if (x.format != y.format or x.writeMask != y.writeMask or (x.blend == null) != (y.blend == null)) return false;
            if (x.blend) |blend| {
                if (!std.meta.eql(blend.*, y.blend.?.*)) return false;
            }
        }
    }
    if ((left.depth_stencil == null) != (right.depth_stencil == null)) return false;
    if (left.depth_stencil) |ad| {
        const bd = right.depth_stencil.?;
        if (!std.meta.eql(ad.*, bd.*) or
            @as(u32, @bitCast(ad.depthBiasSlopeScale)) != @as(u32, @bitCast(bd.depthBiasSlopeScale)) or
            @as(u32, @bitCast(ad.depthBiasClamp)) != @as(u32, @bitCast(bd.depthBiasClamp))) return false;
    }
    return true;
}

fn copy_string(allocator: std.mem.Allocator, bytes: []const u8) std.mem.Allocator.Error!?[]u8 {
    return if (bytes.len == 0) null else try allocator.dupe(u8, bytes);
}

fn free_constants(allocator: std.mem.Allocator, constants: ?[]types.WGPUConstantEntry) void {
    if (constants) |entries| {
        for (entries) |entry| {
            const key = string_view_slice(entry.key);
            if (key.len != 0) allocator.free(key);
        }
        allocator.free(entries);
    }
}

fn copy_constants(allocator: std.mem.Allocator, source: []const types.WGPUConstantEntry) SnapshotError!?[]types.WGPUConstantEntry {
    if (source.len == 0) return null;
    const entries = try allocator.alloc(types.WGPUConstantEntry, source.len);
    @memset(entries, std.mem.zeroes(types.WGPUConstantEntry));
    errdefer free_constants(allocator, entries);
    for (entries, source) |*entry, original| {
        if (original.nextInChain != null) return error.UnsupportedDescriptor;
        entry.value = original.value;
        entry.key = make_string_view(try copy_string(allocator, string_view_slice(original.key)));
    }
    return entries;
}

pub fn free_compute_pipeline_request(req: *ComputePipelineAsyncRequest) void {
    const allocator = req.allocator;
    if (req.label_bytes) |bytes| allocator.free(bytes);
    if (req.entry_point_bytes) |bytes| allocator.free(bytes);
    free_constants(allocator, req.constants);
    if (req.descriptor.layout != null) native.doeNativePipelineLayoutRelease(req.descriptor.layout);
    if (req.descriptor.compute.module != null) native.doeNativeShaderModuleRelease(req.descriptor.compute.module);
    native.doeNativeDeviceRelease(req.device);
    allocator.destroy(req);
}

pub fn copy_compute_pipeline_request(
    device: types.WGPUDevice,
    desc: *const types.WGPUComputePipelineDescriptor,
    callback_info: p0.CreateComputePipelineAsyncCallbackInfo,
) SnapshotError!*ComputePipelineAsyncRequest {
    return copy_compute_request(std.heap.c_allocator, device, desc, callback_info);
}

fn copy_compute_request(
    allocator: std.mem.Allocator,
    device: types.WGPUDevice,
    desc: *const types.WGPUComputePipelineDescriptor,
    callback_info: p0.CreateComputePipelineAsyncCallbackInfo,
) SnapshotError!*ComputePipelineAsyncRequest {
    if (desc.nextInChain != null or desc.compute.nextInChain != null) return error.UnsupportedDescriptor;
    if (desc.compute.constantCount > 0 and desc.compute.constants == null) return error.InvalidDescriptor;
    const req = try allocator.create(ComputePipelineAsyncRequest);
    req.* = .{ .allocator = allocator, .device = device, .descriptor = desc.*, .callback_info = callback_info };
    native.doeNativeDeviceAddRef(device);
    if (desc.compute.module != null) native.object_add_ref(native.DoeShaderModule, desc.compute.module);
    if (desc.layout != null) native.object_add_ref(native.DoePipelineLayout, desc.layout);
    errdefer free_compute_pipeline_request(req);
    req.label_bytes = try copy_string(allocator, string_view_slice(desc.label));
    req.descriptor.label = make_string_view(req.label_bytes);
    req.entry_point_bytes = try copy_string(allocator, string_view_slice(desc.compute.entryPoint));
    req.descriptor.compute.entryPoint = make_string_view(req.entry_point_bytes);
    if (desc.compute.constantCount > 0 and desc.compute.constants != null) {
        req.constants = try copy_constants(allocator, desc.compute.constants[0..desc.compute.constantCount]);
    }
    req.descriptor.compute.constants = if (req.constants) |entries| entries.ptr else null;
    req.descriptor.compute.constantCount = if (req.constants) |entries| entries.len else 0;
    return req;
}

pub fn set_compute_pipeline_request_error(req: *ComputePipelineAsyncRequest, comptime message: []const u8) void {
    req.status = async_procs.CREATE_PIPELINE_ASYNC_STATUS_INTERNAL_ERROR;
    req.message = message;
}

pub fn copy_render_pipeline_request(
    device: types.WGPUDevice,
    desc_raw: *const anyopaque,
    callback_info: async_procs.CreateRenderPipelineAsyncCallbackInfo,
) SnapshotError!*RenderPipelineAsyncRequest {
    return copy_render_request(std.heap.c_allocator, device, @ptrCast(@alignCast(desc_raw)), callback_info);
}

fn copy_render_request(
    allocator: std.mem.Allocator,
    device: types.WGPUDevice,
    src: *const RenderPipelineDesc,
    callback_info: async_procs.CreateRenderPipelineAsyncCallbackInfo,
) SnapshotError!*RenderPipelineAsyncRequest {
    if (src.nextInChain != null or src.vertex.nextInChain != null or src.primitive.nextInChain != null or src.multisample.nextInChain != null) return error.UnsupportedDescriptor;
    if ((src.vertex.constantCount > 0 and src.vertex.constants == null) or
        (src.vertex.bufferCount > 0 and src.vertex.buffers == null)) return error.InvalidDescriptor;
    if (src.fragment) |fragment| {
        if (fragment.nextInChain != null) return error.UnsupportedDescriptor;
        if ((fragment.constantCount > 0 and fragment.constants == null) or
            (fragment.targetCount > 0 and fragment.targets == null)) return error.InvalidDescriptor;
    }
    const req = try allocator.create(RenderPipelineAsyncRequest);
    req.* = .{ .allocator = allocator, .device = device, .descriptor = src.*, .callback_info = callback_info };
    native.doeNativeDeviceAddRef(device);
    if (src.layout != null) native.object_add_ref(native.DoePipelineLayout, src.layout);
    if (src.vertex.module != null) native.object_add_ref(native.DoeShaderModule, src.vertex.module);
    if (src.fragment) |frag| {
        if (frag.module != null) native.object_add_ref(native.DoeShaderModule, frag.module);
    }
    errdefer free_render_pipeline_request(req);
    req.label_bytes = try copy_string(allocator, render_string_view_slice(src.label));
    req.descriptor.label = make_render_string_view(req.label_bytes);
    req.vertex_entry_bytes = try copy_string(allocator, render_string_view_slice(src.vertex.entryPoint));
    req.descriptor.vertex.entryPoint = make_render_string_view(req.vertex_entry_bytes);
    if (src.vertex.constantCount > 0 and src.vertex.constants != null) {
        const entries: [*]const types.WGPUConstantEntry = @ptrCast(@alignCast(src.vertex.constants.?));
        req.vertex_constants = try copy_constants(allocator, entries[0..src.vertex.constantCount]);
    }
    req.descriptor.vertex.constants = if (req.vertex_constants) |entries| @ptrCast(entries.ptr) else null;
    req.descriptor.vertex.constantCount = if (req.vertex_constants) |entries| entries.len else 0;
    if (src.vertex.bufferCount > 0 and src.vertex.buffers != null) {
        const src_bufs = @as([*]const RenderVertexBufferLayout, @ptrCast(@alignCast(src.vertex.buffers)))[0..src.vertex.bufferCount];
        const dst_bufs = try allocator.dupe(RenderVertexBufferLayout, src_bufs);
        req.vertex_buffers = dst_bufs;
        var attr_total: usize = 0;
        for (src_bufs) |buf| {
            if (buf.nextInChain != null) return error.UnsupportedDescriptor;
            if (buf.attributeCount > 0 and buf.attributes == null) return error.InvalidDescriptor;
            attr_total = std.math.add(usize, attr_total, buf.attributeCount) catch return error.InvalidDescriptor;
        }
        const dst_attrs = if (attr_total > 0) try allocator.alloc(RenderVertexAttribute, attr_total) else null;
        req.vertex_attributes = dst_attrs;
        req.descriptor.vertex.buffers = @ptrCast(dst_bufs.ptr);
        req.descriptor.vertex.bufferCount = dst_bufs.len;
        var attr_index: usize = 0;
        for (dst_bufs, src_bufs) |*dst, original| {
            dst.nextInChain = null;
            if (original.attributeCount > 0 and original.attributes != null and dst_attrs != null) {
                const copied = dst_attrs.?[attr_index .. attr_index + original.attributeCount];
                @memcpy(copied, original.attributes.?[0..original.attributeCount]);
                for (copied) |attribute| {
                    if (attribute.nextInChain != null) return error.UnsupportedDescriptor;
                }
                dst.attributes = copied.ptr;
                attr_index += original.attributeCount;
            } else {
                dst.attributes = null;
                dst.attributeCount = 0;
            }
        }
    } else {
        req.descriptor.vertex.buffers = null;
        req.descriptor.vertex.bufferCount = 0;
    }
    if (src.fragment) |frag| {
        const copied = try allocator.create(RenderFragmentState);
        copied.* = frag.*;
        req.fragment_state = copied;
        req.descriptor.fragment = copied;
        req.fragment_entry_bytes = try copy_string(allocator, render_string_view_slice(frag.entryPoint));
        copied.entryPoint = make_render_string_view(req.fragment_entry_bytes);
        if (frag.constantCount > 0 and frag.constants != null) {
            const entries: [*]const types.WGPUConstantEntry = @ptrCast(@alignCast(frag.constants.?));
            req.fragment_constants = try copy_constants(allocator, entries[0..frag.constantCount]);
        }
        copied.constants = if (req.fragment_constants) |entries| @ptrCast(entries.ptr) else null;
        copied.constantCount = if (req.fragment_constants) |entries| entries.len else 0;
        if (frag.targetCount > 0 and frag.targets != null) {
            const targets = try allocator.dupe(RenderColorTargetState, frag.targets.?[0..frag.targetCount]);
            req.fragment_targets = targets;
            const blends = try allocator.alloc(RenderBlendState, targets.len);
            req.fragment_blends = blends;
            for (targets, blends) |*target, *blend| {
                if (target.nextInChain != null) return error.UnsupportedDescriptor;
                if (target.blend) |original| {
                    blend.* = original.*;
                    target.blend = blend;
                }
            }
            copied.targets = targets.ptr;
            copied.targetCount = targets.len;
        } else {
            copied.targets = null;
            copied.targetCount = 0;
        }
    }
    if (src.depthStencil) |depth_raw| {
        const original: *const RenderDepthStencilDesc = @ptrCast(@alignCast(depth_raw));
        if (original.nextInChain != null) return error.UnsupportedDescriptor;
        const copied = try allocator.create(RenderDepthStencilDesc);
        copied.* = original.*;
        copied.nextInChain = null;
        req.depth_stencil = copied;
        req.descriptor.depthStencil = @ptrCast(copied);
    }
    return req;
}

pub fn free_render_pipeline_request(req: *RenderPipelineAsyncRequest) void {
    if (req.descriptor.layout != null) native.doeNativePipelineLayoutRelease(req.descriptor.layout);
    if (req.descriptor.vertex.module != null) native.doeNativeShaderModuleRelease(req.descriptor.vertex.module);
    if (req.descriptor.fragment) |frag| {
        if (frag.module != null) native.doeNativeShaderModuleRelease(frag.module);
    }
    if (req.label_bytes) |bytes| req.allocator.free(bytes);
    if (req.vertex_entry_bytes) |bytes| req.allocator.free(bytes);
    if (req.fragment_entry_bytes) |bytes| req.allocator.free(bytes);
    if (req.vertex_buffers) |bufs| req.allocator.free(bufs);
    if (req.vertex_attributes) |attrs| req.allocator.free(attrs);
    free_constants(req.allocator, req.vertex_constants);
    free_constants(req.allocator, req.fragment_constants);
    if (req.fragment_blends) |blends| req.allocator.free(blends);
    if (req.fragment_targets) |targets| req.allocator.free(targets);
    if (req.fragment_state) |frag| req.allocator.destroy(frag);
    if (req.depth_stencil) |depth| req.allocator.destroy(depth);
    native.doeNativeDeviceRelease(req.device);
    req.allocator.destroy(req);
}

pub fn set_render_pipeline_request_error(req: *RenderPipelineAsyncRequest, comptime message: []const u8) void {
    req.status = async_procs.CREATE_PIPELINE_ASYNC_STATUS_INTERNAL_ERROR;
    req.message = message;
}

pub fn fail_compute_pipeline_async(entry: *ComputeInflightEntry, comptime message: []const u8) void {
    const head = g_compute_inflight.take(entry) orelse return;
    set_compute_pipeline_request_error(head, message);
    deliver_pipeline_requests(ComputePipelineAsyncRequest, native.DoeComputePipeline, native.doeNativeComputePipelineRelease, free_compute_pipeline_request, head);
}

pub fn fail_render_pipeline_async(entry: *RenderInflightEntry, comptime message: []const u8) void {
    const head = g_render_inflight.take(entry) orelse return;
    set_render_pipeline_request_error(head, message);
    deliver_pipeline_requests(RenderPipelineAsyncRequest, native.DoeRenderPipeline, native.doeNativeRenderPipelineRelease, free_render_pipeline_request, head);
}

pub fn run_compute_pipeline_async(ctx_raw: ?*anyopaque) void {
    const entry: *ComputeInflightEntry = @ptrCast(@alignCast(ctx_raw orelse return));
    const head = g_compute_inflight.take(entry) orelse return;
    const lead = head;
    lead.pipeline = @ptrCast(native.doeNativeDeviceCreateComputePipeline(lead.device, &lead.descriptor));
    if (lead.pipeline == null) {
        set_compute_pipeline_request_error(lead, "pipeline creation failed");
    }
    deliver_pipeline_requests(ComputePipelineAsyncRequest, native.DoeComputePipeline, native.doeNativeComputePipelineRelease, free_compute_pipeline_request, head);
}

pub fn run_render_pipeline_async(ctx_raw: ?*anyopaque) void {
    const entry: *RenderInflightEntry = @ptrCast(@alignCast(ctx_raw orelse return));
    const head = g_render_inflight.take(entry) orelse return;
    const lead = head;
    lead.pipeline = @ptrCast(native.doeNativeDeviceCreateRenderPipeline(lead.device, @ptrCast(&lead.descriptor)));
    if (lead.pipeline == null) {
        set_render_pipeline_request_error(lead, "render pipeline creation failed");
    }
    deliver_pipeline_requests(RenderPipelineAsyncRequest, native.DoeRenderPipeline, native.doeNativeRenderPipelineRelease, free_render_pipeline_request, head);
}

fn deliver_pipeline_requests(
    comptime Request: type,
    comptime Pipeline: type,
    comptime release_pipeline: fn (?*anyopaque) callconv(.c) void,
    comptime free_request: fn (*Request) void,
    head: *Request,
) void {
    defer free_request(head);
    defer if (head.pipeline != null) release_pipeline(head.pipeline);
    var req: ?*Request = head;
    while (req) |current| {
        const next = current.next;
        if (current.callback_info.callback) |cb| {
            // Each callback receives its own lease; earlier callbacks may release or reenter.
            if (head.pipeline != null) native.object_add_ref(Pipeline, head.pipeline);
            cb(head.status, head.pipeline, .{ .data = head.message.ptr, .length = head.message.len }, current.callback_info.userdata1, current.callback_info.userdata2);
        }
        if (current != head) free_request(current);
        req = next;
    }
}

test "async render cleanup releases shader leases before owned fragment storage" {
    var device = native.DoeDevice{};
    var shader = native.DoeShaderModule{};
    var descriptor = std.mem.zeroes(RenderPipelineDesc);
    var fragment = std.mem.zeroes(RenderFragmentState);
    fragment.module = native.toOpaque(&shader);
    descriptor.vertex.module = native.toOpaque(&shader);
    descriptor.fragment = &fragment;
    const request = try copy_render_pipeline_request(@ptrCast(&device), &descriptor, std.mem.zeroes(async_procs.CreateRenderPipelineAsyncCallbackInfo));
    try std.testing.expectEqual(@as(u32, 3), shader.ref_count);
    try std.testing.expectEqual(@as(u32, 2), device.ref_count);
    free_render_pipeline_request(request);
    try std.testing.expectEqual(@as(u32, 1), shader.ref_count);
    try std.testing.expectEqual(@as(u32, 1), device.ref_count);
}

fn test_callback_leases(comptime Pipeline: type, comptime release: fn (?*anyopaque) callconv(.c) void) !void {
    const Node = struct {
        const Self = @This();
        next: ?*@This() = null,
        pipeline: ?*anyopaque,
        status: u32,
        message_bytes: ?[]u8 = null,
        message: []const u8 = "",
        callback_info: struct {
            callback: ?*const fn (u32, ?*anyopaque, types.WGPUStringView, ?*anyopaque, ?*anyopaque) callconv(.c) void = null,
            userdata1: ?*anyopaque = null,
            userdata2: ?*anyopaque = null,
        },

        const State = struct { count: usize = 0, failed: bool = false, expected_status: u32 };
        fn callback(status: u32, pipeline: ?*anyopaque, message: types.WGPUStringView, data: ?*anyopaque, _: ?*anyopaque) callconv(.c) void {
            const state: *State = @ptrCast(@alignCast(data.?));
            state.failed = state.failed or status != state.expected_status or
                !std.mem.eql(u8, string_view_slice(message), "original cause");
            if (pipeline != null) release(pipeline);
            state.count += 1;
        }
        fn free(self: *Self) void {
            if (self.message_bytes) |bytes| std.testing.allocator.free(bytes);
            std.testing.allocator.destroy(self);
        }
    };
    for ([_]bool{ false, true }) |failed| {
        var pipeline = Pipeline{ .ref_count = 2 };
        var state = Node.State{ .expected_status = if (failed) 2 else 1 };
        var callback: @FieldType(Node, "callback_info") = .{};
        callback.callback = Node.callback;
        callback.userdata1 = &state;
        const head = try std.testing.allocator.create(Node);
        head.* = .{ .pipeline = if (failed) null else &pipeline, .status = state.expected_status, .callback_info = callback };
        head.message_bytes = try std.testing.allocator.dupe(u8, "original cause");
        head.message = head.message_bytes.?;
        const follower = try std.testing.allocator.create(Node);
        follower.* = .{ .pipeline = null, .status = 0, .callback_info = callback };
        head.next = follower;
        const unobserved = try std.testing.allocator.create(Node);
        unobserved.* = .{ .pipeline = null, .status = 0, .callback_info = .{} };
        follower.next = unobserved;
        deliver_pipeline_requests(Node, Pipeline, release, Node.free, head);
        try std.testing.expectEqual(@as(usize, 2), state.count);
        try std.testing.expect(!state.failed);
        try std.testing.expectEqual(@as(u32, if (failed) 2 else 1), pipeline.ref_count);
    }
}

test "async pipeline callbacks may release results before later waiters receive them" {
    try test_callback_leases(native.DoeComputePipeline, native.doeNativeComputePipelineRelease);
    try test_callback_leases(native.DoeRenderPipeline, native.doeNativeRenderPipelineRelease);
}

fn test_owned_snapshots(allocator: std.mem.Allocator) !void {
    var device = native.DoeDevice{};
    var shader = native.DoeShaderModule{};
    defer std.debug.assert(device.ref_count == 1 and shader.ref_count == 1);
    var key = [_]u8{'x'};
    var constants = [_]types.WGPUConstantEntry{std.mem.zeroes(types.WGPUConstantEntry)};
    constants[0].key = .{ .data = &key, .length = key.len };
    constants[0].value = 2;
    var compute = std.mem.zeroes(types.WGPUComputePipelineDescriptor);
    compute.label = .{ .data = "compute", .length = core.abi_core.WGPU_STRLEN };
    compute.compute.entryPoint = .{ .data = "main", .length = core.abi_core.WGPU_STRLEN };
    compute.compute.module = @ptrCast(&shader);
    compute.compute.constants = &constants;
    compute.compute.constantCount = constants.len;
    const first = try copy_compute_request(allocator, @ptrCast(&device), &compute, std.mem.zeroes(p0.CreateComputePipelineAsyncCallbackInfo));
    defer free_compute_pipeline_request(first);
    key[0] = 'y';
    try std.testing.expectEqualStrings("x", string_view_slice(first.constants.?[0].key));
    try std.testing.expectEqualStrings("main", string_view_slice(first.descriptor.compute.entryPoint));
    const second = try copy_compute_request(allocator, @ptrCast(&device), &compute, std.mem.zeroes(p0.CreateComputePipelineAsyncCallbackInfo));
    defer free_compute_pipeline_request(second);
    try std.testing.expect(!same_compute_request(first, second));

    var render = std.mem.zeroes(RenderPipelineDesc);
    render.vertex.module = @ptrCast(&shader);
    render.vertex.entryPoint = .{ .data = "vs", .length = core.abi_core.WGPU_STRLEN };
    render.vertex.constants = &constants;
    render.vertex.constantCount = constants.len;
    var attributes = [_]RenderVertexAttribute{std.mem.zeroes(RenderVertexAttribute)};
    var buffers = [_]RenderVertexBufferLayout{std.mem.zeroes(RenderVertexBufferLayout)};
    buffers[0].attributes = &attributes;
    buffers[0].attributeCount = attributes.len;
    render.vertex.buffers = &buffers;
    render.vertex.bufferCount = buffers.len;
    var blend = std.mem.zeroes(RenderBlendState);
    var target = [_]RenderColorTargetState{std.mem.zeroes(RenderColorTargetState)};
    target[0].blend = &blend;
    var fragment = std.mem.zeroes(RenderFragmentState);
    fragment.module = @ptrCast(&shader);
    fragment.entryPoint = .{ .data = "fs", .length = core.abi_core.WGPU_STRLEN };
    fragment.targets = &target;
    fragment.targetCount = target.len;
    fragment.constants = &constants;
    fragment.constantCount = constants.len;
    render.fragment = &fragment;
    var depth = std.mem.zeroes(RenderDepthStencilDesc);
    render.depthStencil = &depth;
    const a = try copy_render_request(allocator, @ptrCast(&device), &render, std.mem.zeroes(async_procs.CreateRenderPipelineAsyncCallbackInfo));
    defer free_render_pipeline_request(a);
    const b = try copy_render_request(allocator, @ptrCast(&device), &render, std.mem.zeroes(async_procs.CreateRenderPipelineAsyncCallbackInfo));
    defer free_render_pipeline_request(b);
    try std.testing.expect(same_render_request(a, b));
    blend.color.srcFactor = 2;
    attributes[0].offset = 16;
    constants[0].value = 3;
    key[0] = 'z';
    try std.testing.expectEqual(@as(u32, 0), a.fragment_targets.?[0].blend.?.color.srcFactor);
    try std.testing.expectEqual(@as(u64, 0), a.vertex_attributes.?[0].offset);
    try std.testing.expectEqual(@as(f64, 2), a.fragment_constants.?[0].value);
    try std.testing.expectEqualStrings("y", string_view_slice(a.vertex_constants.?[0].key));
    var changed = b.*;
    changed.descriptor.primitive.cullMode = 1;
    try std.testing.expect(!same_render_request(a, &changed));
    changed = b.*;
    changed.vertex_buffers = &buffers;
    try std.testing.expect(!same_render_request(a, &changed));
    changed = b.*;
    changed.fragment_targets = &target;
    try std.testing.expect(!same_render_request(a, &changed));
    changed = b.*;
    changed.fragment_constants = &constants;
    try std.testing.expect(!same_render_request(a, &changed));
    changed = b.*;
    changed.depth_stencil = &depth;
    depth.depthBias = 1;
    try std.testing.expect(!same_render_request(a, &changed));
}

test "async snapshots preserve nested declarations and roll back every allocation failure" {
    try std.testing.checkAllAllocationFailures(std.testing.allocator, test_owned_snapshots, .{});
}
