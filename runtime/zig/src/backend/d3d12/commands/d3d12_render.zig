const std = @import("std");
const model = @import("../../../model.zig");
const common_timing = @import("../../common/timing.zig");
const dc = @import("../d3d12_constants.zig");
const d3d12_formats = @import("../d3d12_formats.zig");
const d3d12_depth_stencil = @import("../resources/d3d12_depth_stencil.zig");
const render_bundle = @import("../../../render_bundle.zig");

extern fn d3d12_bridge_device_create_root_signature_empty(device: ?*anyopaque) callconv(.c) ?*anyopaque;
const D3D12InputElementDesc = extern struct {
    format: u32,
    input_slot: u32,
    aligned_byte_offset: u32,
    semantic_index: u32,
    input_slot_class: u32,
    instance_data_step_rate: u32,
};

const D3D12GraphicsPipelineDesc = extern struct {
    target_format: u32,
    depth_stencil_format: u32,
    sample_count: u32,
    topology: u32,
    topology_type: u32,
    front_face: u32,
    cull_mode: u32,
    blend_enabled: u32,
    color_operation: u32,
    color_src_factor: u32,
    color_dst_factor: u32,
    alpha_operation: u32,
    alpha_src_factor: u32,
    alpha_dst_factor: u32,
    color_write_mask: u32,
    depth_compare: u32,
    depth_write_enabled: u32,
    stencil_front_compare: u32,
    stencil_front_fail_op: u32,
    stencil_front_depth_fail_op: u32,
    stencil_front_pass_op: u32,
    stencil_back_compare: u32,
    stencil_back_fail_op: u32,
    stencil_back_depth_fail_op: u32,
    stencil_back_pass_op: u32,
    stencil_read_mask: u32,
    stencil_write_mask: u32,
    depth_bias: i32,
    depth_bias_slope_scale: f32,
    depth_bias_clamp: f32,
    unclipped_depth: u32,
};

extern fn d3d12_bridge_device_create_graphics_pipeline_hlsl(
    device: ?*anyopaque,
    root_sig: ?*anyopaque,
    vs_source: [*:0]const u8,
    vs_source_len: usize,
    vs_entry: [*:0]const u8,
    ps_source: [*:0]const u8,
    ps_source_len: usize,
    ps_entry: [*:0]const u8,
    desc: *const D3D12GraphicsPipelineDesc,
    input_elements: ?[*]const D3D12InputElementDesc,
    input_element_count: u32,
) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_texture_2d(device: ?*anyopaque, width: u32, height: u32, mip_levels: u32, format: u32, usage_flags: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_rtv_heap(device: ?*anyopaque, num_descriptors: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_rtv(device: ?*anyopaque, resource: ?*anyopaque, rtv_heap: ?*anyopaque, index: u32, format: u32) callconv(.c) void;
extern fn d3d12_bridge_device_create_command_allocator(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_list(device: ?*anyopaque, allocator_h: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_buffer(device: ?*anyopaque, size: usize, heap_type: c_int) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_buffer_get_size(buffer: ?*anyopaque) callconv(.c) u64;
extern fn d3d12_bridge_device_create_command_signature_draw(device: ?*anyopaque, root_sig: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_signature_draw_indexed(device: ?*anyopaque, root_sig: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_command_list_set_graphics_root_signature(cmd_list: ?*anyopaque, root_sig: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_pipeline_state(cmd_list: ?*anyopaque, pipeline: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_render_target(cmd_list: ?*anyopaque, rtv_heap: ?*anyopaque, index: u32) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_render_targets(cmd_list: ?*anyopaque, rtv_heap: ?*anyopaque, rtv_index: u32, dsv_heap: ?*anyopaque, dsv_index: u32) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_viewport(cmd_list: ?*anyopaque, x: f32, y: f32, w: f32, h: f32, min_depth: f32, max_depth: f32) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_scissor(cmd_list: ?*anyopaque, left: i32, top: i32, right: i32, bottom: i32) callconv(.c) void;
extern fn d3d12_bridge_command_list_ia_set_primitive_topology(cmd_list: ?*anyopaque, topology: c_int) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_blend_factor(cmd_list: ?*anyopaque, rgba: *const [4]f32) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_stencil_ref(cmd_list: ?*anyopaque, reference: u32) callconv(.c) void;
extern fn d3d12_bridge_command_list_ia_set_vertex_buffers(cmd_list: ?*anyopaque, start_slot: u32, num_views: u32, buffer: ?*anyopaque, size_in_bytes: u32, stride_in_bytes: u32, offset: u64) callconv(.c) void;
extern fn d3d12_bridge_command_list_ia_set_index_buffer(cmd_list: ?*anyopaque, buffer: ?*anyopaque, format: u32, size_in_bytes: u32, offset: u64) callconv(.c) void;
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
extern fn d3d12_bridge_resource_map(resource: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_resource_unmap(resource: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;

const RENDER_ATTACHMENT_USAGE: u32 = 0x00000010;
const DRAW_INDIRECT_ARG_BYTES: usize = 16;
const DRAW_INDEXED_INDIRECT_ARG_BYTES: usize = 20;
const D3D12_INPUT_CLASSIFICATION_PER_VERTEX_DATA: u32 = 0;
const D3D12_INPUT_CLASSIFICATION_PER_INSTANCE_DATA: u32 = 1;

const passthrough_vs_source =
    \\struct VSOutput {
    \\    float4 position : SV_Position;
    \\    float4 color : COLOR0;
    \\};
    \\VSOutput main_vertex(uint vertex_id : SV_VertexID, uint instance_id : SV_InstanceID) {
    \\    static const float2 positions[3] = {
    \\        float2(-0.5f, -0.5f),
    \\        float2( 0.5f, -0.5f),
    \\        float2( 0.0f,  0.5f)
    \\    };
    \\    VSOutput output;
    \\    float2 p = positions[vertex_id % 3];
    \\    output.position = float4(p, 0.0f, 1.0f);
    \\    output.color = float4((instance_id & 1u) ? 0.75f : 0.25f, 0.5f, 0.9f, 1.0f);
    \\    return output;
    \\}
;

const passthrough_ps_source =
    \\float4 main_fragment(float4 position : SV_Position, float4 color : COLOR0) : SV_Target0 {
    \\    return color;
    \\}
;

pub const RenderMetrics = struct {
    setup_ns: u64 = 0,
    encode_ns: u64 = 0,
    submit_wait_ns: u64 = 0,
    draw_count: u32 = 0,
};

const PipelineKey = struct {
    target_format: u32 = 0,
    depth_stencil_format: u32 = 0,
    sample_count: u32 = 1,
    topology: u32 = 0x00000004,
    front_face: u32 = 0x00000001,
    cull_mode: u32 = 0x00000001,
    blend_enabled: bool = false,
    color_operation: u32 = 1,
    color_src_factor: u32 = 2,
    color_dst_factor: u32 = 1,
    alpha_operation: u32 = 1,
    alpha_src_factor: u32 = 2,
    alpha_dst_factor: u32 = 1,
    color_write_mask: u32 = 0xF,
    depth_compare: u32 = 0x00000008,
    depth_write_enabled: bool = false,
    stencil_front_compare: u32 = 0x00000008,
    stencil_front_fail_op: u32 = 0,
    stencil_front_depth_fail_op: u32 = 0,
    stencil_front_pass_op: u32 = 0,
    stencil_back_compare: u32 = 0x00000008,
    stencil_back_fail_op: u32 = 0,
    stencil_back_depth_fail_op: u32 = 0,
    stencil_back_pass_op: u32 = 0,
    stencil_read_mask: u32 = 0xFFFF_FFFF,
    stencil_write_mask: u32 = 0xFFFF_FFFF,
    unclipped_depth: bool = false,
    vertex_buffer_count: u32 = 0,
    vertex_buffer_strides: [model.MAX_VERTEX_BUFFERS]u64 = [_]u64{0} ** model.MAX_VERTEX_BUFFERS,
    vertex_step_modes: [model.MAX_VERTEX_BUFFERS]u32 = [_]u32{0} ** model.MAX_VERTEX_BUFFERS,
    vertex_attribute_count: u32 = 0,
    vertex_attribute_formats: [model.MAX_VERTEX_ATTRIBUTES]u32 = [_]u32{0} ** model.MAX_VERTEX_ATTRIBUTES,
    vertex_attribute_offsets: [model.MAX_VERTEX_ATTRIBUTES]u64 = [_]u64{0} ** model.MAX_VERTEX_ATTRIBUTES,
    vertex_attribute_locations: [model.MAX_VERTEX_ATTRIBUTES]u32 = [_]u32{0} ** model.MAX_VERTEX_ATTRIBUTES,
    vertex_attribute_buffer_slots: [model.MAX_VERTEX_ATTRIBUTES]u32 = [_]u32{0} ** model.MAX_VERTEX_ATTRIBUTES,
};

pub const RenderState = struct {
    root_signature: ?*anyopaque = null,
    graphics_pipeline: ?*anyopaque = null,
    render_target: ?*anyopaque = null,
    rtv_heap: ?*anyopaque = null,
    depth_stencil: d3d12_depth_stencil.DepthStencilState = .{},
    cmd_allocator: ?*anyopaque = null,
    cmd_list: ?*anyopaque = null,
    has_cmd: bool = false,
    cached_format: u32 = 0,
    cached_width: u32 = 0,
    cached_height: u32 = 0,
    cached_pipeline_key: PipelineKey = .{},
    has_cached_pipeline_key: bool = false,
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

        try self.ensure_pipeline(device, cmd);

        const setup_ns = common_timing.ns_delta(common_timing.now_ns(), setup_start);
        const encode_start = common_timing.now_ns();

        if (d3d12_bridge_command_allocator_reset(self.cmd_allocator) != 0) return error.InvalidState;
        if (d3d12_bridge_command_list_reset(self.cmd_list, self.cmd_allocator) != 0) return error.InvalidState;

        d3d12_bridge_command_list_resource_barrier_transition(self.cmd_list, self.render_target, dc.RESOURCE_STATE_PRESENT, dc.RESOURCE_STATE_RENDER_TARGET);
        d3d12_bridge_command_list_set_graphics_root_signature(self.cmd_list, self.root_signature);
        d3d12_bridge_command_list_set_pipeline_state(self.cmd_list, self.graphics_pipeline);
        d3d12_bridge_command_list_set_render_targets(
            self.cmd_list,
            self.rtv_heap,
            0,
            if (has_depth_attachment(cmd)) self.depth_stencil.get_dsv_heap() else null,
            0,
        );

        const vp_w: f32 = cmd.viewport_width orelse @floatFromInt(cmd.target_width);
        const vp_h: f32 = cmd.viewport_height orelse @floatFromInt(cmd.target_height);
        d3d12_bridge_command_list_set_viewport(self.cmd_list, cmd.viewport_x, cmd.viewport_y, vp_w, vp_h, cmd.viewport_min_depth, cmd.viewport_max_depth);

        const sc_w: i32 = @intCast(cmd.scissor_width orelse cmd.target_width);
        const sc_h: i32 = @intCast(cmd.scissor_height orelse cmd.target_height);
        const sc_x: i32 = @intCast(cmd.scissor_x);
        const sc_y: i32 = @intCast(cmd.scissor_y);
        d3d12_bridge_command_list_set_scissor(self.cmd_list, sc_x, sc_y, sc_x + sc_w, sc_y + sc_h);

        d3d12_bridge_command_list_ia_set_primitive_topology(self.cmd_list, map_topology(cmd.topology));
        d3d12_bridge_command_list_set_blend_factor(self.cmd_list, &cmd.blend_constant);
        d3d12_bridge_command_list_set_stencil_ref(self.cmd_list, cmd.stencil_reference);
        try self.bind_vertex_and_index_buffers(cmd);

        var draw_count: u32 = 0;

        if (is_indexed_indirect) {
            try self.ensure_indexed_indirect(device);
            try self.write_indirect_args(cmd, true);
            var i: u32 = 0;
            while (i < cmd.draw_count) : (i += 1) {
                d3d12_bridge_command_list_execute_indirect(self.cmd_list, self.draw_indexed_cmd_sig, 1, self.indirect_arg_buffer, 0);
                draw_count += 1;
            }
        } else if (is_indirect) {
            try self.ensure_draw_indirect(device);
            try self.write_indirect_args(cmd, false);
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

        d3d12_bridge_command_list_resource_barrier_transition(self.cmd_list, self.render_target, dc.RESOURCE_STATE_RENDER_TARGET, dc.RESOURCE_STATE_PRESENT);
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

    fn ensure_pipeline(self: *RenderState, device: ?*anyopaque, cmd: model.RenderDrawCommand) !void {
        const width = cmd.target_width;
        const height = cmd.target_height;
        const format = cmd.target_format;
        if (self.root_signature == null) {
            self.root_signature = d3d12_bridge_device_create_root_signature_empty(device) orelse return error.InvalidState;
        }

        const key = build_pipeline_key(cmd);
        const needs_rebuild = self.graphics_pipeline == null or
            self.cached_format != format or
            self.cached_width != width or
            self.cached_height != height or
            !self.has_cached_pipeline_key or
            !std.meta.eql(self.cached_pipeline_key, key);
        if (!needs_rebuild) return;

        if (self.graphics_pipeline) |old| d3d12_bridge_release(old);
        if (self.render_target) |old| d3d12_bridge_release(old);

        var input_elements: [model.MAX_VERTEX_ATTRIBUTES]D3D12InputElementDesc = [_]D3D12InputElementDesc{std.mem.zeroes(D3D12InputElementDesc)} ** model.MAX_VERTEX_ATTRIBUTES;
        const input_count = try build_input_elements(cmd, &input_elements);
        const desc = D3D12GraphicsPipelineDesc{
            .target_format = key.target_format,
            .depth_stencil_format = key.depth_stencil_format,
            .sample_count = key.sample_count,
            .topology = key.topology,
            .topology_type = 0,
            .front_face = key.front_face,
            .cull_mode = key.cull_mode,
            .blend_enabled = if (key.blend_enabled) 1 else 0,
            .color_operation = key.color_operation,
            .color_src_factor = key.color_src_factor,
            .color_dst_factor = key.color_dst_factor,
            .alpha_operation = key.alpha_operation,
            .alpha_src_factor = key.alpha_src_factor,
            .alpha_dst_factor = key.alpha_dst_factor,
            .color_write_mask = key.color_write_mask,
            .depth_compare = key.depth_compare,
            .depth_write_enabled = if (key.depth_write_enabled) 1 else 0,
            .stencil_front_compare = key.stencil_front_compare,
            .stencil_front_fail_op = key.stencil_front_fail_op,
            .stencil_front_depth_fail_op = key.stencil_front_depth_fail_op,
            .stencil_front_pass_op = key.stencil_front_pass_op,
            .stencil_back_compare = key.stencil_back_compare,
            .stencil_back_fail_op = key.stencil_back_fail_op,
            .stencil_back_depth_fail_op = key.stencil_back_depth_fail_op,
            .stencil_back_pass_op = key.stencil_back_pass_op,
            .stencil_read_mask = key.stencil_read_mask,
            .stencil_write_mask = key.stencil_write_mask,
            .depth_bias = 0,
            .depth_bias_slope_scale = 0,
            .depth_bias_clamp = 0,
            .unclipped_depth = if (key.unclipped_depth) 1 else 0,
        };
        self.graphics_pipeline = d3d12_bridge_device_create_graphics_pipeline_hlsl(
            device,
            self.root_signature,
            passthrough_vs_source,
            passthrough_vs_source.len,
            "main_vertex",
            passthrough_ps_source,
            passthrough_ps_source.len,
            "main_fragment",
            &desc,
            if (input_count > 0) &input_elements else null,
            input_count,
        ) orelse return error.ShaderCompileFailed;

        self.render_target = d3d12_bridge_device_create_texture_2d(device, width, height, 1, format, RENDER_ATTACHMENT_USAGE) orelse return error.InvalidState;
        if (has_depth_attachment(cmd)) {
            try self.depth_stencil.ensure_depth_texture(device, width, height, cmd.depth_stencil_format);
        } else {
            self.depth_stencil.deinit();
        }

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
        self.cached_pipeline_key = key;
        self.has_cached_pipeline_key = true;
    }

    fn ensure_draw_indirect(self: *RenderState, device: ?*anyopaque) !void {
        if (self.draw_cmd_sig != null) return;
        self.draw_cmd_sig = d3d12_bridge_device_create_command_signature_draw(device, self.root_signature) orelse return error.InvalidState;
        if (self.indirect_arg_buffer == null) {
            self.indirect_arg_buffer = d3d12_bridge_device_create_buffer(device, DRAW_INDIRECT_ARG_BYTES, dc.HEAP_TYPE_UPLOAD) orelse return error.InvalidState;
        }
    }

    fn ensure_indexed_indirect(self: *RenderState, device: ?*anyopaque) !void {
        if (self.draw_indexed_cmd_sig != null) return;
        self.draw_indexed_cmd_sig = d3d12_bridge_device_create_command_signature_draw_indexed(device, self.root_signature) orelse return error.InvalidState;
        if (self.indirect_arg_buffer == null) {
            self.indirect_arg_buffer = d3d12_bridge_device_create_buffer(device, DRAW_INDEXED_INDIRECT_ARG_BYTES, dc.HEAP_TYPE_UPLOAD) orelse return error.InvalidState;
        }
    }

    fn write_indirect_args(self: *RenderState, cmd: model.RenderDrawCommand, indexed: bool) !void {
        const ptr = d3d12_bridge_resource_map(self.indirect_arg_buffer) orelse return error.InvalidState;
        defer d3d12_bridge_resource_unmap(self.indirect_arg_buffer);
        if (indexed) {
            const args = @as(*[5]u32, @ptrCast(@alignCast(ptr)));
            args[0] = cmd.index_count orelse 0;
            args[1] = cmd.instance_count;
            args[2] = cmd.first_index;
            args[3] = @bitCast(cmd.base_vertex);
            args[4] = cmd.first_instance;
        } else {
            const args = @as(*[4]u32, @ptrCast(@alignCast(ptr)));
            args[0] = cmd.vertex_count;
            args[1] = cmd.instance_count;
            args[2] = cmd.first_vertex;
            args[3] = cmd.first_instance;
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
        self.depth_stencil.deinit();
        self.* = .{};
    }
    
    fn bind_vertex_and_index_buffers(self: *RenderState, cmd: model.RenderDrawCommand) !void {
        const vb_count = resolve_vertex_buffer_count(cmd);
        var slot: u32 = 0;
        while (slot < vb_count and slot < @as(u32, model.MAX_VERTEX_BUFFERS)) : (slot += 1) {
            const buffer = resolve_vertex_buffer_handle(cmd, slot) orelse continue;
            const offset = resolve_vertex_buffer_offset(cmd, slot);
            const total_size = d3d12_bridge_buffer_get_size(buffer);
            if (total_size <= offset) continue;
            const stride = try resolve_vertex_buffer_stride(cmd, slot);
            d3d12_bridge_command_list_ia_set_vertex_buffers(
                self.cmd_list,
                slot,
                1,
                buffer,
                @intCast(@min(total_size - offset, std.math.maxInt(u32))),
                stride,
                offset,
            );
        }

        const index_buffer = resolve_index_buffer_handle(cmd) orelse return;
        const index_offset = resolve_index_buffer_offset(cmd);
        const total_size = d3d12_bridge_buffer_get_size(index_buffer);
        if (total_size <= index_offset) return;
        const index_format = resolve_index_format(cmd) orelse return;
        d3d12_bridge_command_list_ia_set_index_buffer(
            self.cmd_list,
            index_buffer,
            index_format,
            @intCast(@min(total_size - index_offset, std.math.maxInt(u32))),
            index_offset,
        );
    }
};

fn build_pipeline_key(cmd: model.RenderDrawCommand) PipelineKey {
    var key = PipelineKey{
        .target_format = cmd.target_format,
        .depth_stencil_format = cmd.depth_stencil_format,
        .sample_count = if (cmd.sample_count == 0) 1 else cmd.sample_count,
        .topology = cmd.topology,
        .front_face = cmd.front_face,
        .cull_mode = cmd.cull_mode,
        .blend_enabled = cmd.blend_enabled,
        .color_operation = cmd.color_operation,
        .color_src_factor = cmd.color_src_factor,
        .color_dst_factor = cmd.color_dst_factor,
        .alpha_operation = cmd.alpha_operation,
        .alpha_src_factor = cmd.alpha_src_factor,
        .alpha_dst_factor = cmd.alpha_dst_factor,
        .color_write_mask = cmd.color_write_mask,
        .depth_compare = cmd.depth_compare,
        .depth_write_enabled = cmd.depth_write_enabled,
        .stencil_front_compare = cmd.stencil_front_compare,
        .stencil_front_fail_op = cmd.stencil_front_fail_op,
        .stencil_front_depth_fail_op = cmd.stencil_front_depth_fail_op,
        .stencil_front_pass_op = cmd.stencil_front_pass_op,
        .stencil_back_compare = cmd.stencil_back_compare,
        .stencil_back_fail_op = cmd.stencil_back_fail_op,
        .stencil_back_depth_fail_op = cmd.stencil_back_depth_fail_op,
        .stencil_back_pass_op = cmd.stencil_back_pass_op,
        .stencil_read_mask = cmd.stencil_read_mask,
        .stencil_write_mask = cmd.stencil_write_mask,
        .unclipped_depth = cmd.unclipped_depth,
        .vertex_buffer_count = resolve_vertex_buffer_count(cmd),
        .vertex_attribute_count = resolve_vertex_attribute_count(cmd),
    };

    var slot: u32 = 0;
    while (slot < key.vertex_buffer_count and slot < @as(u32, model.MAX_VERTEX_BUFFERS)) : (slot += 1) {
        key.vertex_buffer_strides[slot] = resolve_vertex_buffer_stride_fallback(cmd, slot);
        key.vertex_step_modes[slot] = resolve_vertex_step_mode(cmd, slot);
    }
    fill_vertex_attributes_into_key(cmd, &key);
    return key;
}

fn build_input_elements(cmd: model.RenderDrawCommand, out: *[model.MAX_VERTEX_ATTRIBUTES]D3D12InputElementDesc) !u32 {
    const attribute_count = resolve_vertex_attribute_count(cmd);
    var i: u32 = 0;
    while (i < attribute_count and i < @as(u32, model.MAX_VERTEX_ATTRIBUTES)) : (i += 1) {
        const attr = resolve_vertex_attribute(cmd, i) orelse continue;
        const slot = attr.buffer_slot;
        out[i] = .{
            .format = try d3d12_formats.wgpu_vertex_format_to_dxgi(attr.format),
            .input_slot = slot,
            .aligned_byte_offset = @intCast(attr.offset),
            .semantic_index = attr.shader_location,
            .input_slot_class = if (resolve_vertex_step_mode(cmd, slot) == model.WGPUVertexStepMode_Instance)
                D3D12_INPUT_CLASSIFICATION_PER_INSTANCE_DATA
            else
                D3D12_INPUT_CLASSIFICATION_PER_VERTEX_DATA,
            .instance_data_step_rate = if (resolve_vertex_step_mode(cmd, slot) == model.WGPUVertexStepMode_Instance) 1 else 0,
        };
    }
    return @min(attribute_count, @as(u32, model.MAX_VERTEX_ATTRIBUTES));
}

const ResolvedVertexAttribute = struct {
    format: u32,
    offset: u64,
    shader_location: u32,
    buffer_slot: u32,
};

fn resolve_vertex_attribute(cmd: model.RenderDrawCommand, index: u32) ?ResolvedVertexAttribute {
    if (index < cmd.vertex_attribute_count) {
        return .{
            .format = cmd.vertex_attribute_formats[index],
            .offset = cmd.vertex_attribute_offsets[index],
            .shader_location = cmd.vertex_attribute_locations[index],
            .buffer_slot = cmd.vertex_attribute_buffer_slots[index],
        };
    }
    if (cmd.vertex_layouts) |layouts| {
        var base: u32 = 0;
        var slot: usize = 0;
        while (slot < @min(layouts.len, model.MAX_VERTEX_BUFFERS)) : (slot += 1) {
            const layout = layouts[slot];
            if (index < base + layout.attribute_count) {
                const attr = layout.attributes[index - base];
                return .{
                    .format = attr.format,
                    .offset = attr.offset,
                    .shader_location = attr.shader_location,
                    .buffer_slot = @intCast(slot),
                };
            }
            base += layout.attribute_count;
        }
    }
    return null;
}

fn fill_vertex_attributes_into_key(cmd: model.RenderDrawCommand, key: *PipelineKey) void {
    var i: u32 = 0;
    while (i < key.vertex_attribute_count and i < @as(u32, model.MAX_VERTEX_ATTRIBUTES)) : (i += 1) {
        const attr = resolve_vertex_attribute(cmd, i) orelse break;
        key.vertex_attribute_formats[i] = attr.format;
        key.vertex_attribute_offsets[i] = attr.offset;
        key.vertex_attribute_locations[i] = attr.shader_location;
        key.vertex_attribute_buffer_slots[i] = attr.buffer_slot;
    }
}

fn resolve_vertex_buffer_count(cmd: model.RenderDrawCommand) u32 {
    if (cmd.vertex_buffer_count != 0) return @min(cmd.vertex_buffer_count, @as(u32, model.MAX_VERTEX_BUFFERS));
    if (cmd.vertex_binding_count != 0) return @min(cmd.vertex_binding_count, @as(u32, model.MAX_VERTEX_BUFFERS));
    if (cmd.vertex_layout_count != 0) return @min(cmd.vertex_layout_count, @as(u32, model.MAX_VERTEX_BUFFERS));
    if (cmd.vertex_layouts) |layouts| return @min(@as(u32, @intCast(layouts.len)), @as(u32, model.MAX_VERTEX_BUFFERS));
    return 0;
}

fn resolve_vertex_attribute_count(cmd: model.RenderDrawCommand) u32 {
    if (cmd.vertex_attribute_count != 0) return @min(cmd.vertex_attribute_count, @as(u32, model.MAX_VERTEX_ATTRIBUTES));
    if (cmd.vertex_layouts) |layouts| {
        var total: u32 = 0;
        var i: usize = 0;
        while (i < @min(layouts.len, model.MAX_VERTEX_BUFFERS)) : (i += 1) total += layouts[i].attribute_count;
        return @min(total, @as(u32, model.MAX_VERTEX_ATTRIBUTES));
    }
    return 0;
}

fn resolve_vertex_buffer_handle(cmd: model.RenderDrawCommand, slot: u32) ?*anyopaque {
    if (slot < cmd.vertex_buffer_count and cmd.vertex_buffer_handles[slot] != 0) {
        return @ptrFromInt(cmd.vertex_buffer_handles[slot]);
    }
    if (cmd.vertex_bindings) |bindings| {
        for (bindings) |binding| {
            if (binding.slot == slot) return binding.handle;
        }
    }
    return null;
}

fn resolve_vertex_buffer_offset(cmd: model.RenderDrawCommand, slot: u32) u64 {
    if (slot < cmd.vertex_buffer_count and cmd.vertex_buffer_handles[slot] != 0) {
        return cmd.vertex_buffer_offsets[slot];
    }
    if (cmd.vertex_bindings) |bindings| {
        for (bindings) |binding| {
            if (binding.slot == slot) return binding.offset;
        }
    }
    return 0;
}

fn resolve_vertex_step_mode(cmd: model.RenderDrawCommand, slot: u32) u32 {
    const fallback = resolve_vertex_step_mode_fallback(cmd, slot);
    return if (fallback != 0) fallback else model.WGPUVertexStepMode_Vertex;
}

fn resolve_vertex_step_mode_fallback(cmd: model.RenderDrawCommand, slot: u32) u32 {
    if (slot < cmd.vertex_layout_count and cmd.vertex_step_modes[slot] != 0) {
        return cmd.vertex_step_modes[slot];
    }
    if (cmd.vertex_layouts) |layouts| {
        if (slot < layouts.len) return layouts[slot].step_mode;
    }
    return 0;
}

fn resolve_vertex_buffer_stride_fallback(cmd: model.RenderDrawCommand, slot: u32) u64 {
    if (slot < cmd.vertex_layout_count and cmd.vertex_buffer_strides[slot] != 0) {
        return cmd.vertex_buffer_strides[slot];
    }
    if (cmd.vertex_layouts) |layouts| {
        if (slot < layouts.len) return layouts[slot].array_stride;
    }
    return 0;
}

fn resolve_vertex_buffer_stride(cmd: model.RenderDrawCommand, slot: u32) !u32 {
    var stride = resolve_vertex_buffer_stride_fallback(cmd, slot);
    if (stride == 0) {
        const attribute_count = resolve_vertex_attribute_count(cmd);
        var i: u32 = 0;
        while (i < attribute_count) : (i += 1) {
            const attr = resolve_vertex_attribute(cmd, i) orelse continue;
            if (attr.buffer_slot != slot) continue;
            stride = @max(stride, attr.offset + try vertex_format_size(attr.format));
        }
    }
    if (stride == 0 or stride > std.math.maxInt(u32)) return error.UnsupportedFeature;
    return @intCast(stride);
}

fn resolve_index_buffer_handle(cmd: model.RenderDrawCommand) ?*anyopaque {
    if (cmd.index_buffer_handle != 0) return @ptrFromInt(cmd.index_buffer_handle);
    if (cmd.index_binding) |binding| return binding.handle;
    return null;
}

fn resolve_index_buffer_offset(cmd: model.RenderDrawCommand) u64 {
    if (cmd.index_buffer_handle != 0) return cmd.index_buffer_offset;
    if (cmd.index_binding) |binding| return binding.offset;
    return 0;
}

fn resolve_index_format(cmd: model.RenderDrawCommand) ?u32 {
    if (cmd.index_format != 0) return cmd.index_format;
    if (cmd.index_binding) |binding| return binding.format;
    return null;
}

fn vertex_format_size(format: u32) !u64 {
    return switch (format) {
        0x00000001, 0x00000004, 0x00000007, 0x0000000A => 1,
        0x00000002, 0x00000005, 0x00000008, 0x0000000B, 0x0000000D, 0x00000010, 0x00000013, 0x00000016, 0x0000001D, 0x00000021, 0x00000025 => 2,
        0x00000003, 0x00000006, 0x00000009, 0x0000000C, 0x0000000E, 0x00000011, 0x00000014, 0x00000017, 0x00000019, 0x00000029, 0x0000002A => 4,
        0x0000000F, 0x00000012, 0x00000015, 0x00000018, 0x0000001A, 0x0000001E, 0x00000022, 0x00000026 => 8,
        0x0000001B, 0x00000023, 0x00000027 => 12,
        0x0000001C, 0x0000001F, 0x00000024, 0x00000028 => 16,
        else => error.UnsupportedFeature,
    };
}

fn has_depth_attachment(cmd: model.RenderDrawCommand) bool {
    return cmd.depth_stencil_format != 0;
}

fn map_topology(topology: u32) c_int {
    return switch (topology) {
        0x00000001 => dc.D3D_PRIMITIVE_TOPOLOGY_POINTLIST,
        0x00000002 => dc.D3D_PRIMITIVE_TOPOLOGY_LINELIST,
        0x00000003 => dc.D3D_PRIMITIVE_TOPOLOGY_LINESTRIP,
        0x00000005 => dc.D3D_PRIMITIVE_TOPOLOGY_TRIANGLESTRIP,
        else => dc.D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST,
    };
}

// Replay render bundles into a standalone render pass. Creates render target,
// sets up the command list, then replays each bundle's command list via
// replay_bundle_d3d12 from the shared render_bundle module.
pub fn execute_render_bundles(
    self: *RenderState,
    device: ?*anyopaque,
    queue: ?*anyopaque,
    fence: ?*anyopaque,
    fence_value: *u64,
    bundles: []const *const render_bundle.DoeRenderBundle,
    target_width: u32,
    target_height: u32,
    color_format: u32,
    sample_count: u32,
) !RenderMetrics {
    if (bundles.len == 0) return .{};

    const width = if (target_width > 0) target_width else 256;
    const height = if (target_height > 0) target_height else 256;
    const pass_sample_count: u32 = if (sample_count == 0) 1 else sample_count;
    const pipeline_cmd = model.RenderDrawCommand{
        .draw_count = 1,
        .target_width = width,
        .target_height = height,
        .target_format = color_format,
        .sample_count = pass_sample_count,
    };

    const setup_start = common_timing.now_ns();
    try self.ensure_pipeline(device, pipeline_cmd);
    try self.ensure_draw_indirect(device);
    try self.ensure_indexed_indirect(device);
    const setup_ns = common_timing.ns_delta(common_timing.now_ns(), setup_start);

    const encode_start = common_timing.now_ns();
    if (d3d12_bridge_command_allocator_reset(self.cmd_allocator) != 0) return error.InvalidState;
    if (d3d12_bridge_command_list_reset(self.cmd_list, self.cmd_allocator) != 0) return error.InvalidState;

    d3d12_bridge_command_list_resource_barrier_transition(self.cmd_list, self.render_target, dc.RESOURCE_STATE_PRESENT, dc.RESOURCE_STATE_RENDER_TARGET);
    d3d12_bridge_command_list_set_graphics_root_signature(self.cmd_list, self.root_signature);
    d3d12_bridge_command_list_set_pipeline_state(self.cmd_list, self.graphics_pipeline);
    d3d12_bridge_command_list_set_render_targets(self.cmd_list, self.rtv_heap, 0, null, 0);

    const vp_w: f32 = @floatFromInt(width);
    const vp_h: f32 = @floatFromInt(height);
    d3d12_bridge_command_list_set_viewport(self.cmd_list, 0, 0, vp_w, vp_h, 0, 1);
    d3d12_bridge_command_list_set_scissor(self.cmd_list, 0, 0, @intCast(width), @intCast(height));
    d3d12_bridge_command_list_ia_set_primitive_topology(self.cmd_list, dc.D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST);

    var draw_count: u32 = 0;
    for (bundles) |b| {
        render_bundle.replay_bundle_d3d12(b, self.cmd_list, color_format, pass_sample_count, self.draw_cmd_sig, self.draw_indexed_cmd_sig) catch |err| {
            std.debug.print("d3d12_render: bundle replay failed: {}\n", .{err});
            continue;
        };
        draw_count += 1;
    }

    d3d12_bridge_command_list_resource_barrier_transition(self.cmd_list, self.render_target, dc.RESOURCE_STATE_RENDER_TARGET, dc.RESOURCE_STATE_PRESENT);
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
