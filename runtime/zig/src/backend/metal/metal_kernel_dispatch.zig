const std = @import("std");
const common_timing = @import("../common/timing.zig");
const resources = @import("metal_runtime_resources.zig");
const msl = @import("../../compiler/wgsl/emit/msl/emit_msl_ir.zig");
const binding_values = @import("../../contracts/model/model_binding_value_types.zig");
const execution_contract = @import("../../contracts/execution.zig");
const model_transfer_types = @import("../../contracts/model/model_compute_types.zig");
const webgpu = @import("../../contracts/runtime_types.zig");
const bridge = @import("metal_bridge_decls.zig");

const metal_bridge_cmd_buf_compute_encoder = bridge.metal_bridge_cmd_buf_compute_encoder;
const metal_bridge_command_buffer_commit = bridge.metal_bridge_command_buffer_commit;
const metal_bridge_create_command_buffer = bridge.metal_bridge_create_command_buffer;
const metal_bridge_end_blit_encoding = bridge.metal_bridge_end_blit_encoding;
const metal_bridge_release = bridge.metal_bridge_release;
const metal_bridge_render_encoder_end = bridge.metal_bridge_render_encoder_end;

const model = struct {
    pub const KernelBinding = model_transfer_types.KernelBinding;
};

pub const MAX_BINDING_SLOTS: usize = 32;
const METAL_BUFFER_SLOT_COUNT: usize = 31;
const BUFFER_BINDING_ALIGNMENT: u64 = 256;
const MAX_STREAMING_COMPUTE_DISPATCHES_BEFORE_COMMIT: u32 = 256;

pub const DispatchMetrics = execution_contract.DispatchMetrics;

pub const KernelDispatchResult = struct {
    metrics: DispatchMetrics,
    gpu_elapsed_ns: u64 = 0,
    gpu_timestamps_attempted: bool = false,
    gpu_timestamps_valid: bool = false,
};

const BindingPlan = struct {
    slots: [MAX_BINDING_SLOTS]u32 = undefined,
    offsets: [MAX_BINDING_SLOTS]u64 = [_]u64{0} ** MAX_BINDING_SLOTS,
    sizes: [MAX_BINDING_SLOTS]u32 = [_]u32{0} ** MAX_BINDING_SLOTS,
    allocations: [MAX_BINDING_SLOTS]u64 = undefined,
    slot_count: u32 = 0,
};

fn planBindings(interface: resources.KernelInterface, bindings: []const model.KernelBinding, whole_sizes: []const u64) !BindingPlan {
    if (bindings.len != interface.binding_count or bindings.len > MAX_BINDING_SLOTS or whole_sizes.len != bindings.len) return error.InvalidBindingLayout;
    var plan = BindingPlan{};
    for (bindings, 0..) |binding, i| {
        if (binding.resource_kind != .buffer) return error.UnsupportedBindingLayout;
        if (binding.visibility & binding_values.WGPUShaderStage_Compute == 0) return error.InvalidBindingLayout;
        const meta = for (interface.bindings[0..interface.binding_count]) |candidate| {
            if (candidate.group == binding.group and candidate.binding == binding.binding) break candidate;
        } else return error.InvalidBindingLayout;
        if (meta.kind != .buffer) return error.UnsupportedBindingLayout;
        const expected_type = if (meta.addr_space == .uniform) binding_values.WGPUBufferBindingType_Uniform else if (meta.access == .read) binding_values.WGPUBufferBindingType_ReadOnlyStorage else binding_values.WGPUBufferBindingType_Storage;
        if (binding.buffer_type != binding_values.WGPUBufferBindingType_Undefined and binding.buffer_type != expected_type) return error.InvalidBindingLayout;
        const slot = msl.bindingSlot(.{ .group = binding.group, .binding = binding.binding }) catch return error.UnsupportedBindingLayout;
        if (slot >= METAL_BUFFER_SLOT_COUNT or (interface.needs_sizes_buf and slot == msl.MSL_SIZES_SLOT)) return error.UnsupportedBindingLayout;
        for (plan.slots[0..i]) |previous| if (previous == slot) return error.InvalidBindingLayout;
        if (binding.buffer_offset % BUFFER_BINDING_ALIGNMENT != 0) return error.InvalidBindingRange;
        const size = if (binding.buffer_size == std.math.maxInt(u64)) whole_sizes[i] else binding.buffer_size;
        if (size == 0 or size > std.math.maxInt(u32) or size < meta.min_binding_size) return error.InvalidBindingRange;
        const end = std.math.add(u64, binding.buffer_offset, size) catch return error.InvalidBindingRange;
        plan.slots[i] = slot;
        plan.offsets[slot] = binding.buffer_offset;
        plan.sizes[slot] = @intCast(size);
        plan.allocations[i] = end;
        plan.slot_count = @max(plan.slot_count, slot + 1);
    }
    // Aliases allocate once at their largest required extent, independently of
    // binding order. No allocation is permitted until every range is checked.
    for (bindings, 0..) |binding, i| {
        for (bindings, 0..) |other, j| {
            if (binding.resource_handle == other.resource_handle) plan.allocations[i] = @max(plan.allocations[i], plan.allocations[j]);
        }
    }
    return plan;
}

test "Metal binding plan preserves groups offsets sizes and aliases" {
    var interface = resources.KernelInterface{ .binding_count = 2, .needs_sizes_buf = true };
    interface.bindings[0] = .{ .group = 1, .binding = 0, .kind = .buffer, .addr_space = .storage, .access = .read_write };
    interface.bindings[1] = .{ .group = 0, .binding = 2, .kind = .buffer, .addr_space = .storage, .access = .read_write };
    const bindings = [_]model.KernelBinding{
        .{ .group = 1, .binding = 0, .resource_kind = .buffer, .resource_handle = 7, .buffer_offset = 256, .buffer_size = 16 },
        .{ .group = 0, .binding = 2, .resource_kind = .buffer, .resource_handle = 7, .buffer_size = 512 },
    };
    const plan = try planBindings(interface, &bindings, &.{ 0, 0 });
    try std.testing.expectEqualSlices(u32, &.{ 16, 2 }, plan.slots[0..2]);
    try std.testing.expectEqual(@as(u64, 256), plan.offsets[16]);
    try std.testing.expectEqual(@as(u32, 16), plan.sizes[16]);
    try std.testing.expectEqualSlices(u64, &.{ 512, 512 }, plan.allocations[0..2]);
}

test "Metal binding plan rejects incomplete unsupported duplicate and overflowing layouts" {
    var interface = resources.KernelInterface{ .binding_count = 1, .needs_sizes_buf = true };
    interface.bindings[0] = .{ .group = 0, .binding = 0, .kind = .buffer, .addr_space = .storage, .access = .read_write };
    var bindings = [_]model.KernelBinding{.{ .binding = 0, .resource_kind = .buffer, .resource_handle = 1, .buffer_size = 16 }};
    try std.testing.expectError(error.InvalidBindingLayout, planBindings(interface, &.{}, &.{}));
    bindings[0].resource_kind = .texture;
    try std.testing.expectError(error.UnsupportedBindingLayout, planBindings(interface, &bindings, &.{0}));
    bindings[0].resource_kind = .buffer;
    bindings[0].buffer_offset = std.math.maxInt(u64) - 255;
    bindings[0].buffer_size = 512;
    try std.testing.expectError(error.InvalidBindingRange, planBindings(interface, &bindings, &.{0}));
    bindings[0].buffer_offset = 0;
    bindings[0].buffer_size = std.math.maxInt(u64);
    try std.testing.expectError(error.InvalidBindingRange, planBindings(interface, &bindings, &.{0}));
    const whole = try planBindings(interface, &bindings, &.{64});
    try std.testing.expectEqual(@as(u32, 64), whole.sizes[0]);
    interface.bindings[0].binding = msl.MSL_SIZES_SLOT;
    bindings[0].binding = msl.MSL_SIZES_SLOT;
    try std.testing.expectError(error.UnsupportedBindingLayout, planBindings(interface, &bindings, &.{64}));
    interface.binding_count = 2;
    interface.bindings[0].binding = 0;
    interface.bindings[1] = interface.bindings[0];
    bindings[0].binding = 0;
    try std.testing.expectError(error.InvalidBindingLayout, planBindings(interface, &.{ bindings[0], bindings[0] }, &.{ 64, 64 }));
}

fn encodeDispatch(encoder: ?*anyopaque, pipeline: ?*anyopaque, buffers: *const [MAX_BINDING_SLOTS]?*anyopaque, plan: *const BindingPlan, dimensions: [3]u32, workgroup: [3]u32, repeat: u32, needs_sizes: bool) !void {
    if (bridge.metal_bridge_compute_encoder_dispatch_checked(encoder, pipeline, buffers, &plan.offsets, &plan.sizes, plan.slot_count, if (needs_sizes) msl.MSL_SIZES_SLOT else std.math.maxInt(u32), &dimensions, &workgroup, repeat) == 0) return error.MetalEncodingFailed;
}

test "Metal kernel encoding reports native rejection" {
    const buffers = [_]?*anyopaque{null} ** MAX_BINDING_SLOTS;
    const plan = BindingPlan{};
    try std.testing.expectError(error.MetalEncodingFailed, encodeDispatch(null, null, &buffers, &plan, .{ 1, 1, 1 }, .{ 1, 1, 1 }, 1, false));
}

fn encodeBatch(runtime: anytype, pipeline: ?*anyopaque, buffers: *const [MAX_BINDING_SLOTS]?*anyopaque, plan: *const BindingPlan, dimensions: [3]u32, workgroup: [3]u32, repeat: u32, needs_sizes: bool, timestamps: bool) !*anyopaque {
    const command = metal_bridge_create_command_buffer(runtime.queue) orelse return error.MetalEncodingFailed;
    errdefer metal_bridge_release(command);
    if (timestamps) runtime.timestamp_state.record_begin(command);
    const encoder = metal_bridge_cmd_buf_compute_encoder(command) orelse return error.MetalEncodingFailed;
    defer bridge.metal_bridge_end_compute_encoding(encoder);
    try encodeDispatch(encoder, pipeline, buffers, plan, dimensions, workgroup, repeat, needs_sizes);
    // End the compute encoder before encoding the end timestamp sample.
    return command;
}

pub fn run_kernel_dispatch(
    runtime: anytype,
    kernel: []const u8,
    entry_point: ?[]const u8,
    x: u32,
    y: u32,
    z: u32,
    repeat: u32,
    warmup: u32,
    initialize_buffers_on_create: bool,
    bindings: ?[]const model.KernelBinding,
) !DispatchMetrics {
    const result = try run_kernel_dispatch_timed(runtime, kernel, entry_point, x, y, z, repeat, warmup, initialize_buffers_on_create, bindings, .per_command, false);
    return result.metrics;
}

pub fn run_kernel_dispatch_timed(
    runtime: anytype,
    kernel: []const u8,
    entry_point: ?[]const u8,
    x: u32,
    y: u32,
    z: u32,
    repeat: u32,
    warmup: u32,
    initialize_buffers_on_create: bool,
    bindings: ?[]const model.KernelBinding,
    queue_sync_mode: webgpu.QueueSyncMode,
    record_timestamps: bool,
) !KernelDispatchResult {
    try runtime.completion.check();
    const setup_start = common_timing.now_ns();
    if (warmup > 0 or record_timestamps or queue_sync_mode != .deferred) {
        _ = try runtime.flush_queue();
    }
    // Setup includes retiring prior work before standalone or warmup dispatches.
    const pipeline_info = try runtime.ensure_kernel_pipeline_info(kernel, entry_point);
    const pipeline = pipeline_info.pipeline;
    const workgroup_size = pipeline_info.workgroup_size;

    var buf_slots: [MAX_BINDING_SLOTS]?*anyopaque = [_]?*anyopaque{null} ** MAX_BINDING_SLOTS;
    const bs = bindings orelse &.{};
    if (bs.len > MAX_BINDING_SLOTS) return error.InvalidBindingLayout;
    var whole_sizes = [_]u64{0} ** MAX_BINDING_SLOTS;
    for (bs, 0..) |binding, i| {
        if (runtime.compute_buffers.get(binding.resource_handle)) |buffer| {
            const length = bridge.metal_bridge_buffer_length(buffer);
            if (binding.buffer_offset > length) return error.InvalidBindingRange;
            whole_sizes[i] = length - binding.buffer_offset;
            if (binding.buffer_size != std.math.maxInt(u64) and binding.buffer_size > whole_sizes[i]) return error.InvalidBindingRange;
        }
    }
    const plan = try planBindings(pipeline_info.interface, bs, whole_sizes[0..bs.len]);
    for (bs, 0..) |binding, i| {
        buf_slots[plan.slots[i]] = try runtime.ensure_compute_buffer(binding.resource_handle, plan.allocations[i], initialize_buffers_on_create);
    }

    const run_count: u32 = if (repeat == 0) 1 else repeat;
    const dimensions = [3]u32{ x, y, z };

    if (warmup > 0) {
        const wcb = try encodeBatch(runtime, pipeline, &buf_slots, &plan, dimensions, workgroup_size, warmup, pipeline_info.interface.needs_sizes_buf, false);
        try commitAndWait(runtime, wcb);
    }
    const setup_ns = common_timing.ns_delta(common_timing.now_ns(), setup_start);

    const want_ts = record_timestamps and runtime.timestamp_state.supported;

    if (!want_ts and queue_sync_mode == .deferred) {
        const encode_start = common_timing.now_ns();
        try ensure_streaming_compute_encoder(runtime);
        try encodeDispatch(runtime.streaming_compute_encoder, pipeline, &buf_slots, &plan, dimensions, workgroup_size, run_count, pipeline_info.interface.needs_sizes_buf);
        var encode_ns = common_timing.ns_delta(common_timing.now_ns(), encode_start);
        runtime.streaming_compute_dispatch_count +|= run_count;
        runtime.has_deferred_submissions = true;
        if (runtime.streaming_compute_dispatch_count >= MAX_STREAMING_COMPUTE_DISPATCHES_BEFORE_COMMIT) {
            const rollover_start = common_timing.now_ns();
            try runtime.transition_streaming_submission_deferred();
            encode_ns +|= common_timing.ns_delta(common_timing.now_ns(), rollover_start);
        }
        return .{
            .metrics = .{
                .setup_ns = setup_ns,
                .encode_ns = encode_ns,
                .submit_wait_ns = 0,
                .dispatch_count = run_count,
            },
            .gpu_elapsed_ns = 0,
            .gpu_timestamps_attempted = false,
            .gpu_timestamps_valid = false,
        };
    }

    // Timed run: batch all repeat dispatches into one command buffer.
    const t_enc_start = common_timing.now_ns();

    const cmd_buf = try encodeBatch(runtime, pipeline, &buf_slots, &plan, dimensions, workgroup_size, run_count, pipeline_info.interface.needs_sizes_buf, want_ts);
    if (want_ts) runtime.timestamp_state.record_end(cmd_buf);

    const encode_ns = common_timing.ns_delta(common_timing.now_ns(), t_enc_start);

    const t_sub_start = common_timing.now_ns();
    try commitAndWait(runtime, cmd_buf);
    const submit_wait_ns = common_timing.ns_delta(common_timing.now_ns(), t_sub_start);

    var gpu_elapsed_ns: u64 = 0;
    if (want_ts) {
        gpu_elapsed_ns = runtime.timestamp_state.resolve_elapsed_ns();
    }

    return .{
        .metrics = .{
            .setup_ns = setup_ns,
            .encode_ns = encode_ns,
            .submit_wait_ns = submit_wait_ns,
            .dispatch_count = run_count,
        },
        .gpu_elapsed_ns = gpu_elapsed_ns,
        .gpu_timestamps_attempted = want_ts,
        .gpu_timestamps_valid = want_ts and gpu_elapsed_ns > 0,
    };
}

fn commitAndWait(runtime: anytype, cmd_buf: *anyopaque) !void {
    runtime.completion.reserve(runtime.allocator) catch |err| {
        metal_bridge_release(cmd_buf);
        return err;
    };
    metal_bridge_command_buffer_commit(cmd_buf);
    runtime.completion.retainSubmitted(cmd_buf);
    try runtime.completion.retire();
    try runtime.completion.check();
}

fn ensure_streaming_compute_encoder(runtime: anytype) !void {
    if (runtime.streaming_compute_encoder != null) return;

    if (runtime.streaming_render_encoder) |enc| {
        metal_bridge_render_encoder_end(enc);
        metal_bridge_release(enc);
        runtime.streaming_render_encoder = null;
    }
    if (runtime.streaming_blit_encoder) |enc| {
        metal_bridge_end_blit_encoding(enc);
        runtime.streaming_blit_encoder = null;
    }
    if (runtime.streaming_cmd_buf == null) {
        runtime.streaming_cmd_buf = metal_bridge_create_command_buffer(runtime.queue) orelse return error.InvalidState;
    }
    runtime.streaming_compute_encoder = metal_bridge_cmd_buf_compute_encoder(runtime.streaming_cmd_buf) orelse return error.InvalidState;
}
