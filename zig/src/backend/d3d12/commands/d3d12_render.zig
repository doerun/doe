const std = @import("std");
const model = @import("../../../model.zig");
const common_timing = @import("../../common/timing.zig");

extern fn d3d12_bridge_device_create_root_signature_empty(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_graphics_pipeline(device: ?*anyopaque, root_sig: ?*anyopaque, vs_bytecode: [*]const u8, vs_size: usize, ps_bytecode: [*]const u8, ps_size: usize, target_format: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_texture_2d(device: ?*anyopaque, width: u32, height: u32, mip_levels: u32, format: u32, usage_flags: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_rtv_heap(device: ?*anyopaque, num_descriptors: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_rtv(device: ?*anyopaque, resource: ?*anyopaque, rtv_heap: ?*anyopaque, index: u32, format: u32) callconv(.c) void;
extern fn d3d12_bridge_device_create_command_allocator(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_list(device: ?*anyopaque, allocator_h: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_buffer(device: ?*anyopaque, size: usize, heap_type: c_int) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_signature_draw(device: ?*anyopaque, root_sig: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_signature_draw_indexed(device: ?*anyopaque, root_sig: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_command_list_set_graphics_root_signature(cmd_list: ?*anyopaque, root_sig: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_pipeline_state(cmd_list: ?*anyopaque, pipeline: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_render_target(cmd_list: ?*anyopaque, rtv_heap: ?*anyopaque, index: u32) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_viewport(cmd_list: ?*anyopaque, x: f32, y: f32, w: f32, h: f32, min_depth: f32, max_depth: f32) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_scissor(cmd_list: ?*anyopaque, left: i32, top: i32, right: i32, bottom: i32) callconv(.c) void;
extern fn d3d12_bridge_command_list_ia_set_primitive_topology(cmd_list: ?*anyopaque, topology: c_int) callconv(.c) void;
extern fn d3d12_bridge_command_list_draw_instanced(cmd_list: ?*anyopaque, vertex_count: u32, instance_count: u32, start_vertex: u32, start_instance: u32) callconv(.c) void;
extern fn d3d12_bridge_command_list_draw_indexed_instanced(cmd_list: ?*anyopaque, index_count: u32, instance_count: u32, start_index: u32, base_vertex: i32, start_instance: u32) callconv(.c) void;
extern fn d3d12_bridge_command_list_execute_indirect(cmd_list: ?*anyopaque, command_sig: ?*anyopaque, max_count: u32, arg_buffer: ?*anyopaque, arg_offset: u64) callconv(.c) void;
extern fn d3d12_bridge_command_list_resource_barrier_transition(cmd_list: ?*anyopaque, resource: ?*anyopaque, state_before: c_int, state_after: c_int) callconv(.c) void;
extern fn d3d12_bridge_command_list_close(cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_command_allocator_reset(allocator_h: ?*anyopaque) callconv(.c) c_int;
extern fn d3d12_bridge_command_list_reset(cmd_list: ?*anyopaque, allocator_h: ?*anyopaque) callconv(.c) c_int;
extern fn d3d12_bridge_queue_execute_command_list(queue: ?*anyopaque, cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_queue_signal(queue: ?*anyopaque, fence: ?*anyopaque, value: u64) callconv(.c) void;
extern fn d3d12_bridge_fence_wait(fence: ?*anyopaque, value: u64) callconv(.c) void;
extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;

const HEAP_TYPE_UPLOAD: c_int = 2;
const RESOURCE_STATE_RENDER_TARGET: c_int = 0x00000004;
const RESOURCE_STATE_PRESENT: c_int = 0x00000000;
const D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST: c_int = 4;
const RENDER_ATTACHMENT_USAGE: u32 = 0x00000010;
const DRAW_INDIRECT_ARG_BYTES: usize = 16;
const DRAW_INDEXED_INDIRECT_ARG_BYTES: usize = 20;

pub const RenderMetrics = struct {
    setup_ns: u64 = 0,
    encode_ns: u64 = 0,
    submit_wait_ns: u64 = 0,
    draw_count: u32 = 0,
};

pub const RenderState = struct {
    root_signature: ?*anyopaque = null,
    graphics_pipeline: ?*anyopaque = null,
    render_target: ?*anyopaque = null,
    rtv_heap: ?*anyopaque = null,
    cmd_allocator: ?*anyopaque = null,
    cmd_list: ?*anyopaque = null,
    has_cmd: bool = false,
    cached_format: u32 = 0,
    cached_width: u32 = 0,
    cached_height: u32 = 0,
    draw_cmd_sig: ?*anyopaque = null,
    draw_indexed_cmd_sig: ?*anyopaque = null,
    indirect_arg_buffer: ?*anyopaque = null,

    pub fn execute_render_draw(
        self: *RenderState,
        device: ?*anyopaque,
        queue: ?*anyopaque,
        fence: ?*anyopaque,
        fence_value: *u64,
        cmd: model.RenderDrawCommand,
        is_indirect: bool,
        is_indexed_indirect: bool,
    ) !RenderMetrics {
        const setup_start = common_timing.now_ns();

        try self.ensure_pipeline(device, cmd.target_format, cmd.target_width, cmd.target_height);

        const setup_ns = common_timing.ns_delta(common_timing.now_ns(), setup_start);
        const encode_start = common_timing.now_ns();

        if (d3d12_bridge_command_allocator_reset(self.cmd_allocator) != 0) return error.InvalidState;
        if (d3d12_bridge_command_list_reset(self.cmd_list, self.cmd_allocator) != 0) return error.InvalidState;

        d3d12_bridge_command_list_resource_barrier_transition(self.cmd_list, self.render_target, RESOURCE_STATE_PRESENT, RESOURCE_STATE_RENDER_TARGET);
        d3d12_bridge_command_list_set_graphics_root_signature(self.cmd_list, self.root_signature);
        d3d12_bridge_command_list_set_pipeline_state(self.cmd_list, self.graphics_pipeline);
        d3d12_bridge_command_list_set_render_target(self.cmd_list, self.rtv_heap, 0);

        const vp_w: f32 = cmd.viewport_width orelse @floatFromInt(cmd.target_width);
        const vp_h: f32 = cmd.viewport_height orelse @floatFromInt(cmd.target_height);
        d3d12_bridge_command_list_set_viewport(self.cmd_list, cmd.viewport_x, cmd.viewport_y, vp_w, vp_h, cmd.viewport_min_depth, cmd.viewport_max_depth);

        const sc_w: i32 = @intCast(cmd.scissor_width orelse cmd.target_width);
        const sc_h: i32 = @intCast(cmd.scissor_height orelse cmd.target_height);
        const sc_x: i32 = @intCast(cmd.scissor_x);
        const sc_y: i32 = @intCast(cmd.scissor_y);
        d3d12_bridge_command_list_set_scissor(self.cmd_list, sc_x, sc_y, sc_x + sc_w, sc_y + sc_h);

        d3d12_bridge_command_list_ia_set_primitive_topology(self.cmd_list, D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST);

        var draw_count: u32 = 0;

        if (is_indexed_indirect) {
            try self.ensure_indexed_indirect(device);
            var i: u32 = 0;
            while (i < cmd.draw_count) : (i += 1) {
                d3d12_bridge_command_list_execute_indirect(self.cmd_list, self.draw_indexed_cmd_sig, 1, self.indirect_arg_buffer, 0);
                draw_count += 1;
            }
        } else if (is_indirect) {
            try self.ensure_draw_indirect(device);
            var i: u32 = 0;
            while (i < cmd.draw_count) : (i += 1) {
                d3d12_bridge_command_list_execute_indirect(self.cmd_list, self.draw_cmd_sig, 1, self.indirect_arg_buffer, 0);
                draw_count += 1;
            }
        } else {
            var i: u32 = 0;
            while (i < cmd.draw_count) : (i += 1) {
                if (cmd.index_count) |ic| {
                    d3d12_bridge_command_list_draw_indexed_instanced(self.cmd_list, ic, cmd.instance_count, cmd.first_index, cmd.base_vertex, cmd.first_instance);
                } else {
                    d3d12_bridge_command_list_draw_instanced(self.cmd_list, cmd.vertex_count, cmd.instance_count, cmd.first_vertex, cmd.first_instance);
                }
                draw_count += 1;
            }
        }

        d3d12_bridge_command_list_resource_barrier_transition(self.cmd_list, self.render_target, RESOURCE_STATE_RENDER_TARGET, RESOURCE_STATE_PRESENT);
        d3d12_bridge_command_list_close(self.cmd_list);

        const encode_ns = common_timing.ns_delta(common_timing.now_ns(), encode_start);

        d3d12_bridge_queue_execute_command_list(queue, self.cmd_list);
        fence_value.* +|= 1;
        d3d12_bridge_queue_signal(queue, fence, fence_value.*);
        const submit_start = common_timing.now_ns();
        d3d12_bridge_fence_wait(fence, fence_value.*);
        const submit_wait_ns = common_timing.ns_delta(common_timing.now_ns(), submit_start);

        return .{ .setup_ns = setup_ns, .encode_ns = encode_ns, .submit_wait_ns = submit_wait_ns, .draw_count = draw_count };
    }

    fn ensure_pipeline(self: *RenderState, device: ?*anyopaque, format: u32, width: u32, height: u32) !void {
        if (self.root_signature == null) {
            self.root_signature = d3d12_bridge_device_create_root_signature_empty(device) orelse return error.InvalidState;
        }

        const needs_rebuild = self.graphics_pipeline == null or self.cached_format != format or self.cached_width != width or self.cached_height != height;
        if (!needs_rebuild) return;

        if (self.graphics_pipeline) |old| d3d12_bridge_release(old);
        if (self.render_target) |old| d3d12_bridge_release(old);

        const vs = noop_vs_bytecode();
        const ps = noop_ps_bytecode();
        self.graphics_pipeline = d3d12_bridge_device_create_graphics_pipeline(device, self.root_signature, vs.ptr, vs.len, ps.ptr, ps.len, format) orelse return error.ShaderCompileFailed;

        self.render_target = d3d12_bridge_device_create_texture_2d(device, width, height, 1, format, RENDER_ATTACHMENT_USAGE) orelse return error.InvalidState;

        if (self.rtv_heap == null) {
            self.rtv_heap = d3d12_bridge_device_create_rtv_heap(device, 1) orelse return error.InvalidState;
        }
        d3d12_bridge_device_create_rtv(device, self.render_target, self.rtv_heap, 0, format);

        if (!self.has_cmd) {
            self.cmd_allocator = d3d12_bridge_device_create_command_allocator(device) orelse return error.InvalidState;
            self.cmd_list = d3d12_bridge_device_create_command_list(device, self.cmd_allocator) orelse return error.InvalidState;
            d3d12_bridge_command_list_close(self.cmd_list);
            self.has_cmd = true;
        }

        self.cached_format = format;
        self.cached_width = width;
        self.cached_height = height;
    }

    fn ensure_draw_indirect(self: *RenderState, device: ?*anyopaque) !void {
        if (self.draw_cmd_sig != null) return;
        self.draw_cmd_sig = d3d12_bridge_device_create_command_signature_draw(device, self.root_signature) orelse return error.InvalidState;
        if (self.indirect_arg_buffer == null) {
            self.indirect_arg_buffer = d3d12_bridge_device_create_buffer(device, DRAW_INDIRECT_ARG_BYTES, HEAP_TYPE_UPLOAD) orelse return error.InvalidState;
        }
    }

    fn ensure_indexed_indirect(self: *RenderState, device: ?*anyopaque) !void {
        if (self.draw_indexed_cmd_sig != null) return;
        self.draw_indexed_cmd_sig = d3d12_bridge_device_create_command_signature_draw_indexed(device, self.root_signature) orelse return error.InvalidState;
        if (self.indirect_arg_buffer == null) {
            self.indirect_arg_buffer = d3d12_bridge_device_create_buffer(device, DRAW_INDEXED_INDIRECT_ARG_BYTES, HEAP_TYPE_UPLOAD) orelse return error.InvalidState;
        }
    }

    pub fn deinit(self: *RenderState) void {
        if (self.has_cmd) {
            d3d12_bridge_release(self.cmd_list);
            d3d12_bridge_release(self.cmd_allocator);
        }
        if (self.graphics_pipeline) |p| d3d12_bridge_release(p);
        if (self.root_signature) |r| d3d12_bridge_release(r);
        if (self.render_target) |t| d3d12_bridge_release(t);
        if (self.rtv_heap) |h| d3d12_bridge_release(h);
        if (self.draw_cmd_sig) |s| d3d12_bridge_release(s);
        if (self.draw_indexed_cmd_sig) |s| d3d12_bridge_release(s);
        if (self.indirect_arg_buffer) |b| d3d12_bridge_release(b);
        self.* = .{};
    }
};

fn noop_vs_bytecode() []const u8 {
    // Minimal DXBC vertex shader: float4 main(uint id : SV_VertexID) : SV_Position { return float4(0,0,0,1); }
    const bytecode = [_]u8{
        0x44, 0x58, 0x42, 0x43, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,
        0x50, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x24, 0x00, 0x00, 0x00,
        0x53, 0x48, 0x45, 0x58, 0x24, 0x00, 0x00, 0x00, 0x50, 0x00, 0x01, 0x00,
        0x03, 0x00, 0x00, 0x00, 0x65, 0x00, 0x00, 0x03, 0xF2, 0x20, 0x10, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x36, 0x00, 0x00, 0x08, 0xF2, 0x20, 0x10, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x02, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80, 0x3F,
        0x3E, 0x00, 0x00, 0x01,
    };
    return &bytecode;
}

fn noop_ps_bytecode() []const u8 {
    // Minimal DXBC pixel shader: float4 main() : SV_Target { return float4(0,0,0,1); }
    const bytecode = [_]u8{
        0x44, 0x58, 0x42, 0x43, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00,
        0x50, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x24, 0x00, 0x00, 0x00,
        0x53, 0x48, 0x45, 0x58, 0x24, 0x00, 0x00, 0x00, 0x40, 0x00, 0x00, 0x00,
        0x03, 0x00, 0x00, 0x00, 0x65, 0x00, 0x00, 0x03, 0xF2, 0x20, 0x10, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x36, 0x00, 0x00, 0x08, 0xF2, 0x20, 0x10, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x02, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80, 0x3F,
        0x3E, 0x00, 0x00, 0x01,
    };
    return &bytecode;
}
