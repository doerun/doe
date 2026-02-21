const std = @import("std");
const types = @import("wgpu_types.zig");

pub const RenderPassEncoder = ?*anyopaque;

const FnCommandEncoderBeginRenderPass = *const fn (types.WGPUCommandEncoder, *const anyopaque) callconv(.c) RenderPassEncoder;
const FnDeviceCreateRenderPipeline = *const fn (types.WGPUDevice, *const anyopaque) callconv(.c) types.WGPURenderPipeline;
const FnRenderPassEncoderSetPipeline = *const fn (RenderPassEncoder, types.WGPURenderPipeline) callconv(.c) void;
const FnRenderPassEncoderSetVertexBuffer = *const fn (RenderPassEncoder, u32, types.WGPUBuffer, u64, u64) callconv(.c) void;
const FnRenderPassEncoderSetIndexBuffer = *const fn (RenderPassEncoder, types.WGPUBuffer, u32, u64, u64) callconv(.c) void;
const FnRenderPassEncoderSetBindGroup = *const fn (RenderPassEncoder, u32, types.WGPUBindGroup, usize, ?[*]const u32) callconv(.c) void;
const FnRenderPassEncoderDraw = *const fn (RenderPassEncoder, u32, u32, u32, u32) callconv(.c) void;
const FnRenderPassEncoderDrawIndexed = *const fn (RenderPassEncoder, u32, u32, u32, i32, u32) callconv(.c) void;
const FnRenderPassEncoderEnd = *const fn (RenderPassEncoder) callconv(.c) void;
const FnRenderPassEncoderRelease = *const fn (RenderPassEncoder) callconv(.c) void;

pub const RenderProcTable = struct {
    command_encoder_begin_render_pass: FnCommandEncoderBeginRenderPass,
    device_create_render_pipeline: FnDeviceCreateRenderPipeline,
    render_pass_encoder_set_pipeline: FnRenderPassEncoderSetPipeline,
    render_pass_encoder_set_vertex_buffer: FnRenderPassEncoderSetVertexBuffer,
    render_pass_encoder_set_index_buffer: FnRenderPassEncoderSetIndexBuffer,
    render_pass_encoder_set_bind_group: FnRenderPassEncoderSetBindGroup,
    render_pass_encoder_draw: FnRenderPassEncoderDraw,
    render_pass_encoder_draw_indexed: FnRenderPassEncoderDrawIndexed,
    render_pass_encoder_end: FnRenderPassEncoderEnd,
    render_pass_encoder_release: FnRenderPassEncoderRelease,
    render_pipeline_release: types.FnWgpuRenderPipelineRelease,
};

fn loadRenderProc(comptime T: type, lib: std.DynLib, comptime name: [:0]const u8) ?T {
    var mutable = lib;
    return mutable.lookup(T, name);
}

pub fn loadRenderProcs(dyn_lib: ?std.DynLib) ?RenderProcTable {
    const lib = dyn_lib orelse return null;
    return .{
        .command_encoder_begin_render_pass = loadRenderProc(FnCommandEncoderBeginRenderPass, lib, "wgpuCommandEncoderBeginRenderPass") orelse return null,
        .device_create_render_pipeline = loadRenderProc(FnDeviceCreateRenderPipeline, lib, "wgpuDeviceCreateRenderPipeline") orelse return null,
        .render_pass_encoder_set_pipeline = loadRenderProc(FnRenderPassEncoderSetPipeline, lib, "wgpuRenderPassEncoderSetPipeline") orelse return null,
        .render_pass_encoder_set_vertex_buffer = loadRenderProc(FnRenderPassEncoderSetVertexBuffer, lib, "wgpuRenderPassEncoderSetVertexBuffer") orelse return null,
        .render_pass_encoder_set_index_buffer = loadRenderProc(FnRenderPassEncoderSetIndexBuffer, lib, "wgpuRenderPassEncoderSetIndexBuffer") orelse return null,
        .render_pass_encoder_set_bind_group = loadRenderProc(FnRenderPassEncoderSetBindGroup, lib, "wgpuRenderPassEncoderSetBindGroup") orelse return null,
        .render_pass_encoder_draw = loadRenderProc(FnRenderPassEncoderDraw, lib, "wgpuRenderPassEncoderDraw") orelse return null,
        .render_pass_encoder_draw_indexed = loadRenderProc(FnRenderPassEncoderDrawIndexed, lib, "wgpuRenderPassEncoderDrawIndexed") orelse return null,
        .render_pass_encoder_end = loadRenderProc(FnRenderPassEncoderEnd, lib, "wgpuRenderPassEncoderEnd") orelse return null,
        .render_pass_encoder_release = loadRenderProc(FnRenderPassEncoderRelease, lib, "wgpuRenderPassEncoderRelease") orelse return null,
        .render_pipeline_release = loadRenderProc(types.FnWgpuRenderPipelineRelease, lib, "wgpuRenderPipelineRelease") orelse return null,
    };
}
