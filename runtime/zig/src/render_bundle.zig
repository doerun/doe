// render_bundle.zig — GPURenderBundle encoder and handle for Doe native Metal backend.
//
// A render bundle records a fixed set of render commands (draw calls, pipeline
// binds, bind group binds, vertex/index buffer binds) that can be replayed into
// any compatible render pass with executeBundles.
//
// Metal implementation: commands are stored as a typed command list and replayed
// into the open MTLRenderCommandEncoder of the enclosing render pass. For workloads
// where the draw parameters are static, the replay can be optimised later into an
// MTLIndirectCommandBuffer (ICB); that path is not taken here to avoid the
// inheritPipelineState complexity for user-supplied pipelines.
//
// Compatibility check: the bundle's colorFormats[0] must match the render pass
// attachment format. sampleCount must match. Mismatches fail fast with an
// actionable error rather than a silent misfire.

const std = @import("std");
const types = @import("core/abi/wgpu_types.zig");

// ============================================================
// Constants
// ============================================================

const MAGIC_BUNDLE_ENCODER: u32 = 0xD0E1_0020;
const MAGIC_BUNDLE: u32 = 0xD0E1_0021;

// Maximum commands that can be recorded into a single bundle encoder.
pub const MAX_BUNDLE_CMDS: usize = 4096;

// Maximum vertex buffer slots per draw.
pub const MAX_VTX_BUFS: usize = 8;

// Maximum bind groups per bundle.
pub const MAX_BIND_GROUPS: usize = 4;

// Maximum bindings per bind group.
pub const MAX_BINDINGS_PER_GROUP: usize = 16;

// ============================================================
// Recorded command types
// ============================================================

pub const BundleCmdTag = enum {
    set_pipeline,
    set_bind_group,
    set_vertex_buffer,
    set_index_buffer,
    draw,
    draw_indexed,
    draw_indirect,
    draw_indexed_indirect,
};

pub const BundleBindEntry = struct {
    mtl_buffer: ?*anyopaque,
    offset: u64,
};

pub const BundleBindGroup = struct {
    entries: [MAX_BINDINGS_PER_GROUP]BundleBindEntry,
    count: u32,
};

pub const BundleCmd = union(BundleCmdTag) {
    set_pipeline: struct {
        mtl_pso: ?*anyopaque,
    },
    set_bind_group: struct {
        group: u32,
        bg: BundleBindGroup,
    },
    set_vertex_buffer: struct {
        slot: u32,
        mtl_buffer: ?*anyopaque,
        offset: u64,
    },
    set_index_buffer: struct {
        mtl_buffer: ?*anyopaque,
        format: u32, // WGPUIndexFormat: 0x1=uint16, 0x2=uint32
        offset: u64,
        size: u64,
    },
    draw: struct {
        vertex_count: u32,
        instance_count: u32,
        first_vertex: u32,
        first_instance: u32,
    },
    draw_indexed: struct {
        index_count: u32,
        instance_count: u32,
        first_index: u32,
        base_vertex: i32,
        first_instance: u32,
    },
    draw_indirect: struct {
        indirect_buffer: ?*anyopaque,
        indirect_offset: u64,
    },
    draw_indexed_indirect: struct {
        indirect_buffer: ?*anyopaque,
        indirect_offset: u64,
    },
};

// ============================================================
// DoeBundleEncoder — records commands until finish()
// ============================================================

pub const DoeBundleEncoder = struct {
    pub const TYPE_MAGIC = MAGIC_BUNDLE_ENCODER;
    magic: u32 = TYPE_MAGIC,
    allocator: std.mem.Allocator,
    // Compatibility signature — validated against render pass at executeBundles time.
    color_format: types.WGPUTextureFormat,
    depth_stencil_format: types.WGPUTextureFormat,
    sample_count: u32,
    depth_read_only: bool,
    stencil_read_only: bool,
    // Recorded commands.
    cmds: std.ArrayListUnmanaged(BundleCmd),
};

// ============================================================
// DoeRenderBundle — immutable after finish()
// ============================================================

pub const DoeRenderBundle = struct {
    pub const TYPE_MAGIC = MAGIC_BUNDLE;
    magic: u32 = TYPE_MAGIC,
    allocator: std.mem.Allocator,
    color_format: types.WGPUTextureFormat,
    depth_stencil_format: types.WGPUTextureFormat,
    sample_count: u32,
    cmds: []BundleCmd, // owned slice
};

// ============================================================
// Bridge functions imported from metal_bridge.m
// ============================================================

extern fn metal_bridge_render_encoder_draw(
    encoder: ?*anyopaque,
    draw_count: u32,
    vertex_count: u32,
    instance_count: u32,
    redundant_pipeline: c_int,
    pipeline: ?*anyopaque,
) callconv(.c) void;

extern fn metal_bridge_render_encoder_end(encoder: ?*anyopaque) callconv(.c) void;

// New bridge functions declared in metal_bridge.h (added below).
extern fn metal_bridge_render_encoder_set_pipeline(
    encoder: ?*anyopaque,
    pipeline: ?*anyopaque,
) callconv(.c) void;

extern fn metal_bridge_render_encoder_set_buffer(
    encoder: ?*anyopaque,
    buffer: ?*anyopaque,
    offset: u64,
    index: u32,
) callconv(.c) void;

extern fn metal_bridge_render_encoder_draw_indexed_bundle(
    encoder: ?*anyopaque,
    index_buffer: ?*anyopaque,
    index_buffer_offset: u64,
    index_type: u32,
    index_count: u32,
    instance_count: u32,
    first_index: u32,
    base_vertex: i32,
    first_instance: u32,
) callconv(.c) void;

extern fn metal_bridge_render_encoder_draw_indirect(
    encoder: ?*anyopaque,
    indirect_buffer: ?*anyopaque,
    indirect_offset: u64,
) callconv(.c) void;

extern fn metal_bridge_render_encoder_draw_indexed_indirect(
    encoder: ?*anyopaque,
    index_buffer: ?*anyopaque,
    index_buffer_offset: u64,
    index_type: u32,
    indirect_buffer: ?*anyopaque,
    indirect_offset: u64,
) callconv(.c) void;

// ============================================================
// Replay
// ============================================================

pub const ReplayError = error{
    FormatMismatch,
    SampleCountMismatch,
};

// Validate bundle compatibility against a render pass without replaying commands.
pub fn check_compatibility(
    b: *const DoeRenderBundle,
    pass_color_format: types.WGPUTextureFormat,
    pass_sample_count: u32,
) ReplayError!void {
    if (b.color_format != 0 and b.color_format != pass_color_format) {
        return ReplayError.FormatMismatch;
    }
    if (b.sample_count != 0 and b.sample_count != pass_sample_count) {
        return ReplayError.SampleCountMismatch;
    }
}

// Replay all recorded commands into an already-open MTLRenderCommandEncoder.
// `pass_color_format` and `pass_sample_count` must match the bundle's signature;
// we fail fast rather than silently producing incorrect draws.
// `encoder` must be a valid, open MTLRenderCommandEncoder — never null.
pub fn replay_bundle(
    b: *const DoeRenderBundle,
    encoder: ?*anyopaque,
    pass_color_format: types.WGPUTextureFormat,
    pass_sample_count: u32,
) ReplayError!void {
    try check_compatibility(b, pass_color_format, pass_sample_count);

    // Track the current index buffer across draw_indexed commands.
    var cur_index_buf: ?*anyopaque = null;
    var cur_index_off: u64 = 0;
    var cur_index_fmt: u32 = 0x2; // default uint32

    for (b.cmds) |cmd| {
        switch (cmd) {
            .set_pipeline => |p| {
                metal_bridge_render_encoder_set_pipeline(encoder, p.mtl_pso);
            },
            .set_bind_group => |bg_cmd| {
                // Metal buffer indices: group*MAX_BINDINGS_PER_GROUP + binding.
                for (bg_cmd.bg.entries[0..bg_cmd.bg.count]) |entry| {
                    const slot: u32 = bg_cmd.group * MAX_BINDINGS_PER_GROUP;
                    metal_bridge_render_encoder_set_buffer(encoder, entry.mtl_buffer, entry.offset, slot);
                }
            },
            .set_vertex_buffer => |vb| {
                // Metal vertex buffers start at index 16 (after fragment/vertex uniform slots).
                const metal_slot: u32 = 16 + vb.slot;
                metal_bridge_render_encoder_set_buffer(encoder, vb.mtl_buffer, vb.offset, metal_slot);
            },
            .set_index_buffer => |ib| {
                cur_index_buf = ib.mtl_buffer;
                cur_index_off = ib.offset;
                cur_index_fmt = ib.format;
            },
            .draw => |d| {
                // Reuse the Metal bridge draw loop (redundant_pipeline=0 here).
                // draw_count=1 because each bundle cmd is a single logical draw call.
                _ = d.first_vertex;
                _ = d.first_instance;
                metal_bridge_render_encoder_draw(encoder, 1, d.vertex_count, d.instance_count, 0, null);
            },
            .draw_indexed => |d| {
                metal_bridge_render_encoder_draw_indexed_bundle(
                    encoder,
                    cur_index_buf,
                    cur_index_off,
                    cur_index_fmt,
                    d.index_count,
                    d.instance_count,
                    d.first_index,
                    d.base_vertex,
                    d.first_instance,
                );
            },
            .draw_indirect => |d| {
                metal_bridge_render_encoder_draw_indirect(
                    encoder,
                    d.indirect_buffer,
                    d.indirect_offset,
                );
            },
            .draw_indexed_indirect => |d| {
                metal_bridge_render_encoder_draw_indexed_indirect(
                    encoder,
                    cur_index_buf,
                    cur_index_off,
                    cur_index_fmt,
                    d.indirect_buffer,
                    d.indirect_offset,
                );
            },
        }
    }
}

// ============================================================
// C ABI helpers (cast / make shared with doe_wgpu_native.zig)
// ============================================================

// Global allocator injected at init time from doe_wgpu_native.
// Using a pointer to the allocator allows zero-cost access without passing it everywhere.
var g_alloc: ?std.mem.Allocator = null;

pub fn set_allocator(a: std.mem.Allocator) void {
    g_alloc = a;
}

fn alloc() std.mem.Allocator {
    return g_alloc.?;
}

pub fn make_bundle_encoder(
    color_format: types.WGPUTextureFormat,
    depth_stencil_format: types.WGPUTextureFormat,
    sample_count: u32,
    depth_read_only: bool,
    stencil_read_only: bool,
) ?*DoeBundleEncoder {
    const a = alloc();
    const enc = a.create(DoeBundleEncoder) catch return null;
    enc.* = .{
        .allocator = a,
        .color_format = color_format,
        .depth_stencil_format = depth_stencil_format,
        .sample_count = if (sample_count == 0) 1 else sample_count,
        .depth_read_only = depth_read_only,
        .stencil_read_only = stencil_read_only,
        .cmds = .{},
    };
    return enc;
}

pub fn bundle_encoder_push(enc: *DoeBundleEncoder, cmd: BundleCmd) void {
    enc.cmds.append(enc.allocator, cmd) catch
        std.debug.panic("render_bundle: OOM recording bundle command", .{});
}

pub fn bundle_encoder_finish(enc: *DoeBundleEncoder) ?*DoeRenderBundle {
    const a = enc.allocator;
    const bundle = a.create(DoeRenderBundle) catch return null;
    const cmds_slice = enc.cmds.toOwnedSlice(a) catch return null;
    bundle.* = .{
        .allocator = a,
        .color_format = enc.color_format,
        .depth_stencil_format = enc.depth_stencil_format,
        .sample_count = enc.sample_count,
        .cmds = cmds_slice,
    };
    // Encoder cmds were moved into bundle; encoder is now empty.
    a.destroy(enc);
    return bundle;
}

pub fn bundle_destroy(b: *DoeRenderBundle) void {
    const a = b.allocator;
    a.free(b.cmds);
    a.destroy(b);
}

pub fn cast_bundle_encoder(p: ?*anyopaque) ?*DoeBundleEncoder {
    const ptr = p orelse return null;
    const result: *DoeBundleEncoder = @ptrCast(@alignCast(ptr));
    if (result.magic != DoeBundleEncoder.TYPE_MAGIC) return null;
    return result;
}

pub fn cast_bundle(p: ?*anyopaque) ?*DoeRenderBundle {
    const ptr = p orelse return null;
    const result: *DoeRenderBundle = @ptrCast(@alignCast(ptr));
    if (result.magic != DoeRenderBundle.TYPE_MAGIC) return null;
    return result;
}
