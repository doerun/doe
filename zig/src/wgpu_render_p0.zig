const loader = @import("wgpu_loader.zig");
const p0_procs_mod = @import("wgpu_p0_procs.zig");
const render_api_mod = @import("wgpu_render_api.zig");
const render_types_mod = @import("wgpu_render_types.zig");
const resources = @import("wgpu_resources.zig");
const types = @import("wgpu_types.zig");
const ffi = @import("webgpu_ffi.zig");

const Backend = ffi.WebGPUBackend;
const BUFFER_USAGE_INDIRECT: types.WGPUBufferUsage = 0x0000000000000100;

pub const RenderP0State = struct {
    p0_procs: ?p0_procs_mod.P0Procs = null,
    command_encoder_write_buffer: ?p0_procs_mod.FnCommandEncoderWriteBuffer = null,
    occlusion_query_set: types.WGPUQuerySet = null,
    timestamp_query_set: types.WGPUQuerySet = null,
    indirect_buffer: types.WGPUBuffer = null,
};

pub fn prepare(
    self: *Backend,
    procs: types.Procs,
    render_api: render_api_mod.RenderApi,
    indexed_draw: bool,
    indirect_buffer_handle: u64,
) RenderP0State {
    _ = procs;
    var state = RenderP0State{ .p0_procs = p0_procs_mod.loadP0Procs(self.dyn_lib) };
    state.command_encoder_write_buffer = if (state.p0_procs) |loaded| loaded.command_encoder_write_buffer else null;

    if (self.has_multi_draw_indirect and
        state.command_encoder_write_buffer != null and
        ((indexed_draw and render_api.render_pass_encoder_multi_draw_indexed_indirect != null) or
            (!indexed_draw and render_api.render_pass_encoder_multi_draw_indirect != null)))
    {
        const indirect_size: u64 = if (indexed_draw)
            @as(u64, @sizeOf(render_types_mod.RenderDrawIndexedIndirectArgs))
        else
            @as(u64, @sizeOf(render_types_mod.RenderDrawIndirectArgs));
        state.indirect_buffer = resources.getOrCreateBuffer(
            self,
            indirect_buffer_handle,
            indirect_size,
            BUFFER_USAGE_INDIRECT | types.WGPUBufferUsage_CopyDst,
        ) catch null;
    }

    return state;
}

pub fn deinit(state: RenderP0State, procs: types.Procs) void {
    _ = state;
    _ = procs;
}

pub fn beginPass(
    state: RenderP0State,
    render_api: render_api_mod.RenderApi,
    render_pass: types.WGPURenderPassEncoder,
) void {
    if (render_api.render_pass_encoder_begin_occlusion_query) |begin_occlusion_query| {
        if (state.occlusion_query_set != null) begin_occlusion_query(render_pass, 0);
    }
    if (render_api.render_pass_encoder_write_timestamp) |write_timestamp| {
        if (state.timestamp_query_set != null) write_timestamp(render_pass, state.timestamp_query_set, 0);
    }
}

pub fn endPass(
    state: RenderP0State,
    render_api: render_api_mod.RenderApi,
    render_pass: types.WGPURenderPassEncoder,
) void {
    if (render_api.render_pass_encoder_write_timestamp) |write_timestamp| {
        if (state.timestamp_query_set != null) write_timestamp(render_pass, state.timestamp_query_set, 1);
    }
    if (render_api.render_pass_encoder_end_occlusion_query) |end_occlusion_query| {
        if (state.occlusion_query_set != null) end_occlusion_query(render_pass);
    }
}
