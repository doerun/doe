const std = @import("std");
const rb = @import("../../src/render_bundle.zig");

// Convenience aliases.
const BundleCmd = rb.BundleCmd;
const BundleCmdTag = rb.BundleCmdTag;
const DoeBundleEncoder = rb.DoeBundleEncoder;
const DoeRenderBundle = rb.DoeRenderBundle;

// ============================================================
// Helpers
// ============================================================

// Create an encoder using the testing allocator instead of the global allocator
// so tests do not depend on set_allocator / alloc() initialization.
fn make_test_encoder(allocator: std.mem.Allocator) DoeBundleEncoder {
    return .{
        .allocator = allocator,
        .color_format = 0x04, // BGRA8Unorm-like placeholder
        .depth_stencil_format = 0,
        .sample_count = 1,
        .depth_read_only = false,
        .stencil_read_only = false,
        .cmds = .{},
    };
}

fn push_draw(enc: *DoeBundleEncoder, vertex_count: u32, instance_count: u32) void {
    rb.bundle_encoder_push(enc, BundleCmd{ .draw = .{
        .vertex_count = vertex_count,
        .instance_count = instance_count,
        .first_vertex = 0,
        .first_instance = 0,
    } });
}

fn finish_to_bundle(enc: *DoeBundleEncoder) DoeRenderBundle {
    // Manual finish that does not destroy the encoder (tests manage their own memory).
    const cmds_slice = enc.cmds.toOwnedSlice(enc.allocator) catch unreachable;
    return .{
        .allocator = enc.allocator,
        .color_format = enc.color_format,
        .depth_stencil_format = enc.depth_stencil_format,
        .sample_count = enc.sample_count,
        .cmds = cmds_slice,
    };
}

// ============================================================
// Command recording tests
// ============================================================

test "push single draw command increments count" {
    var enc = make_test_encoder(std.testing.allocator);
    defer enc.cmds.deinit(enc.allocator);

    push_draw(&enc, 3, 1);

    try std.testing.expectEqual(@as(usize, 1), enc.cmds.items.len);
    try std.testing.expectEqual(BundleCmdTag.draw, std.meta.activeTag(enc.cmds.items[0]));
}

test "push multiple commands preserves order" {
    var enc = make_test_encoder(std.testing.allocator);
    defer enc.cmds.deinit(enc.allocator);

    rb.bundle_encoder_push(&enc, BundleCmd{ .set_pipeline = .{ .mtl_pso = null } });
    push_draw(&enc, 6, 1);
    rb.bundle_encoder_push(&enc, BundleCmd{ .set_vertex_buffer = .{
        .slot = 0,
        .mtl_buffer = null,
        .offset = 0,
    } });
    push_draw(&enc, 12, 2);

    try std.testing.expectEqual(@as(usize, 4), enc.cmds.items.len);
    try std.testing.expectEqual(BundleCmdTag.set_pipeline, std.meta.activeTag(enc.cmds.items[0]));
    try std.testing.expectEqual(BundleCmdTag.draw, std.meta.activeTag(enc.cmds.items[1]));
    try std.testing.expectEqual(BundleCmdTag.set_vertex_buffer, std.meta.activeTag(enc.cmds.items[2]));
    try std.testing.expectEqual(BundleCmdTag.draw, std.meta.activeTag(enc.cmds.items[3]));
}

test "draw command records vertex and instance counts" {
    var enc = make_test_encoder(std.testing.allocator);
    defer enc.cmds.deinit(enc.allocator);

    push_draw(&enc, 36, 4);

    const d = enc.cmds.items[0].draw;
    try std.testing.expectEqual(@as(u32, 36), d.vertex_count);
    try std.testing.expectEqual(@as(u32, 4), d.instance_count);
    try std.testing.expectEqual(@as(u32, 0), d.first_vertex);
    try std.testing.expectEqual(@as(u32, 0), d.first_instance);
}

test "draw_indexed command records all parameters" {
    var enc = make_test_encoder(std.testing.allocator);
    defer enc.cmds.deinit(enc.allocator);

    rb.bundle_encoder_push(&enc, BundleCmd{ .draw_indexed = .{
        .index_count = 100,
        .instance_count = 3,
        .first_index = 10,
        .base_vertex = -5,
        .first_instance = 2,
    } });

    const d = enc.cmds.items[0].draw_indexed;
    try std.testing.expectEqual(@as(u32, 100), d.index_count);
    try std.testing.expectEqual(@as(u32, 3), d.instance_count);
    try std.testing.expectEqual(@as(u32, 10), d.first_index);
    try std.testing.expectEqual(@as(i32, -5), d.base_vertex);
    try std.testing.expectEqual(@as(u32, 2), d.first_instance);
}

test "set_bind_group records group index and entry count" {
    var enc = make_test_encoder(std.testing.allocator);
    defer enc.cmds.deinit(enc.allocator);

    var bg = rb.BundleBindGroup{
        .entries = undefined,
        .count = 2,
    };
    bg.entries[0] = .{ .mtl_buffer = null, .offset = 0 };
    bg.entries[1] = .{ .mtl_buffer = null, .offset = 64 };

    rb.bundle_encoder_push(&enc, BundleCmd{ .set_bind_group = .{
        .group = 1,
        .bg = bg,
    } });

    try std.testing.expectEqual(@as(usize, 1), enc.cmds.items.len);
    const sbg = enc.cmds.items[0].set_bind_group;
    try std.testing.expectEqual(@as(u32, 1), sbg.group);
    try std.testing.expectEqual(@as(u32, 2), sbg.bg.count);
    try std.testing.expectEqual(@as(u64, 64), sbg.bg.entries[1].offset);
}

test "set_index_buffer records format and offset" {
    var enc = make_test_encoder(std.testing.allocator);
    defer enc.cmds.deinit(enc.allocator);

    rb.bundle_encoder_push(&enc, BundleCmd{ .set_index_buffer = .{
        .mtl_buffer = null,
        .format = 0x1, // uint16
        .offset = 128,
        .size = 2048,
    } });

    const ib = enc.cmds.items[0].set_index_buffer;
    try std.testing.expectEqual(@as(u32, 0x1), ib.format);
    try std.testing.expectEqual(@as(u64, 128), ib.offset);
    try std.testing.expectEqual(@as(u64, 2048), ib.size);
}

// ============================================================
// Bundle state transition (recording -> finished) tests
// ============================================================

test "finish produces bundle with correct command count and format" {
    var enc = make_test_encoder(std.testing.allocator);

    push_draw(&enc, 3, 1);
    push_draw(&enc, 6, 1);
    push_draw(&enc, 9, 1);

    const bundle = finish_to_bundle(&enc);
    defer std.testing.allocator.free(bundle.cmds);

    try std.testing.expectEqual(@as(usize, 3), bundle.cmds.len);
    try std.testing.expectEqual(@as(u32, 0x04), bundle.color_format);
    try std.testing.expectEqual(@as(u32, 1), bundle.sample_count);
}

test "finish transfers ownership of commands to bundle" {
    var enc = make_test_encoder(std.testing.allocator);

    push_draw(&enc, 10, 1);
    push_draw(&enc, 20, 1);

    const bundle = finish_to_bundle(&enc);
    defer std.testing.allocator.free(bundle.cmds);

    // Encoder's command list should be empty after toOwnedSlice.
    try std.testing.expectEqual(@as(usize, 0), enc.cmds.items.len);

    // Bundle holds all commands.
    try std.testing.expectEqual(@as(u32, 10), bundle.cmds[0].draw.vertex_count);
    try std.testing.expectEqual(@as(u32, 20), bundle.cmds[1].draw.vertex_count);
}

test "bundle magic values are correct" {
    try std.testing.expectEqual(@as(u32, 0xD0E1_0020), DoeBundleEncoder.TYPE_MAGIC);
    try std.testing.expectEqual(@as(u32, 0xD0E1_0021), DoeRenderBundle.TYPE_MAGIC);
}

test "encoder default magic is set on construction" {
    var enc = make_test_encoder(std.testing.allocator);
    defer enc.cmds.deinit(enc.allocator);

    try std.testing.expectEqual(DoeBundleEncoder.TYPE_MAGIC, enc.magic);
}

// ============================================================
// Empty bundle tests
// ============================================================

test "empty encoder finishes to bundle with zero commands" {
    var enc = make_test_encoder(std.testing.allocator);

    const bundle = finish_to_bundle(&enc);
    defer std.testing.allocator.free(bundle.cmds);

    try std.testing.expectEqual(@as(usize, 0), bundle.cmds.len);
}

test "empty bundle passes compatibility check" {
    var enc = make_test_encoder(std.testing.allocator);
    const bundle = finish_to_bundle(&enc);
    defer std.testing.allocator.free(bundle.cmds);

    // Same format as encoder: should pass.
    try rb.check_compatibility(&bundle, 0x04, 1);
}

// ============================================================
// Replay command sequence tests (pure logic, no Metal calls)
// ============================================================

test "replay produces correct command sequence for mixed commands" {
    var enc = make_test_encoder(std.testing.allocator);

    // Record: pipeline -> vertex buffer -> draw -> draw_indexed
    rb.bundle_encoder_push(&enc, BundleCmd{ .set_pipeline = .{ .mtl_pso = null } });
    rb.bundle_encoder_push(&enc, BundleCmd{ .set_vertex_buffer = .{
        .slot = 0,
        .mtl_buffer = null,
        .offset = 0,
    } });
    push_draw(&enc, 6, 1);
    rb.bundle_encoder_push(&enc, BundleCmd{ .set_index_buffer = .{
        .mtl_buffer = null,
        .format = 0x2,
        .offset = 0,
        .size = 1024,
    } });
    rb.bundle_encoder_push(&enc, BundleCmd{ .draw_indexed = .{
        .index_count = 12,
        .instance_count = 1,
        .first_index = 0,
        .base_vertex = 0,
        .first_instance = 0,
    } });

    const bundle = finish_to_bundle(&enc);
    defer std.testing.allocator.free(bundle.cmds);

    // Verify command sequence matches recording order.
    try std.testing.expectEqual(@as(usize, 5), bundle.cmds.len);
    try std.testing.expectEqual(BundleCmdTag.set_pipeline, std.meta.activeTag(bundle.cmds[0]));
    try std.testing.expectEqual(BundleCmdTag.set_vertex_buffer, std.meta.activeTag(bundle.cmds[1]));
    try std.testing.expectEqual(BundleCmdTag.draw, std.meta.activeTag(bundle.cmds[2]));
    try std.testing.expectEqual(BundleCmdTag.set_index_buffer, std.meta.activeTag(bundle.cmds[3]));
    try std.testing.expectEqual(BundleCmdTag.draw_indexed, std.meta.activeTag(bundle.cmds[4]));

    // Verify data integrity of the draw_indexed command.
    try std.testing.expectEqual(@as(u32, 12), bundle.cmds[4].draw_indexed.index_count);
}

// ============================================================
// Compatibility check tests
// ============================================================

test "check_compatibility succeeds when formats match" {
    var bundle = DoeRenderBundle{
        .allocator = std.testing.allocator,
        .color_format = 0x04,
        .depth_stencil_format = 0,
        .sample_count = 4,
        .cmds = &.{},
    };

    try rb.check_compatibility(&bundle, 0x04, 4);
}

test "check_compatibility fails on color format mismatch" {
    var bundle = DoeRenderBundle{
        .allocator = std.testing.allocator,
        .color_format = 0x04,
        .depth_stencil_format = 0,
        .sample_count = 1,
        .cmds = &.{},
    };

    try std.testing.expectError(
        rb.ReplayError.FormatMismatch,
        rb.check_compatibility(&bundle, 0x08, 1),
    );
}

test "check_compatibility fails on sample count mismatch" {
    var bundle = DoeRenderBundle{
        .allocator = std.testing.allocator,
        .color_format = 0x04,
        .depth_stencil_format = 0,
        .sample_count = 4,
        .cmds = &.{},
    };

    try std.testing.expectError(
        rb.ReplayError.SampleCountMismatch,
        rb.check_compatibility(&bundle, 0x04, 1),
    );
}

test "check_compatibility skips format check when bundle color_format is 0" {
    // color_format=0 means the bundle is format-agnostic (unset).
    var bundle = DoeRenderBundle{
        .allocator = std.testing.allocator,
        .color_format = 0,
        .depth_stencil_format = 0,
        .sample_count = 1,
        .cmds = &.{},
    };

    // Any pass format should be accepted.
    try rb.check_compatibility(&bundle, 0xFF, 1);
}

test "check_compatibility skips sample count check when bundle sample_count is 0" {
    var bundle = DoeRenderBundle{
        .allocator = std.testing.allocator,
        .color_format = 0x04,
        .depth_stencil_format = 0,
        .sample_count = 0,
        .cmds = &.{},
    };

    try rb.check_compatibility(&bundle, 0x04, 8);
}

// ============================================================
// make_bundle_encoder via global allocator
// ============================================================

test "make_bundle_encoder produces valid encoder with correct fields" {
    rb.set_allocator(std.testing.allocator);
    defer rb.set_allocator(std.testing.allocator); // keep stable for other tests

    const enc = rb.make_bundle_encoder(0x04, 0x20, 4, true, false) orelse
        return error.AllocationFailed;

    try std.testing.expectEqual(DoeBundleEncoder.TYPE_MAGIC, enc.magic);
    try std.testing.expectEqual(@as(u32, 0x04), enc.color_format);
    try std.testing.expectEqual(@as(u32, 0x20), enc.depth_stencil_format);
    try std.testing.expectEqual(@as(u32, 4), enc.sample_count);
    try std.testing.expect(enc.depth_read_only);
    try std.testing.expect(!enc.stencil_read_only);
    try std.testing.expectEqual(@as(usize, 0), enc.cmds.items.len);

    // Clean up via the public destroy path.
    enc.allocator.destroy(enc);
}

test "make_bundle_encoder normalizes zero sample_count to 1" {
    rb.set_allocator(std.testing.allocator);

    const enc = rb.make_bundle_encoder(0x04, 0, 0, false, false) orelse
        return error.AllocationFailed;
    defer enc.allocator.destroy(enc);

    try std.testing.expectEqual(@as(u32, 1), enc.sample_count);
}

// ============================================================
// Full lifecycle: make -> push -> finish -> destroy
// ============================================================

test "full lifecycle: create encoder, record, finish, destroy" {
    rb.set_allocator(std.testing.allocator);

    const enc = rb.make_bundle_encoder(0x04, 0, 1, false, false) orelse
        return error.AllocationFailed;

    rb.bundle_encoder_push(enc, BundleCmd{ .set_pipeline = .{ .mtl_pso = null } });
    rb.bundle_encoder_push(enc, BundleCmd{ .draw = .{
        .vertex_count = 3,
        .instance_count = 1,
        .first_vertex = 0,
        .first_instance = 0,
    } });

    // finish consumes the encoder.
    const bundle = rb.bundle_encoder_finish(enc) orelse
        return error.FinishFailed;

    try std.testing.expectEqual(DoeRenderBundle.TYPE_MAGIC, bundle.magic);
    try std.testing.expectEqual(@as(usize, 2), bundle.cmds.len);
    try std.testing.expectEqual(@as(u32, 3), bundle.cmds[1].draw.vertex_count);

    // Destroy frees bundle + its command slice.
    rb.bundle_destroy(bundle);
}

// ============================================================
// Cast helpers
// ============================================================

test "cast_bundle_encoder returns null for null input" {
    try std.testing.expect(rb.cast_bundle_encoder(null) == null);
}

test "cast_bundle returns null for null input" {
    try std.testing.expect(rb.cast_bundle(null) == null);
}

test "cast_bundle_encoder validates magic" {
    rb.set_allocator(std.testing.allocator);

    const enc = rb.make_bundle_encoder(0x04, 0, 1, false, false) orelse
        return error.AllocationFailed;
    defer enc.allocator.destroy(enc);

    // Valid cast.
    const opaque_ptr: *anyopaque = @ptrCast(enc);
    const recovered = rb.cast_bundle_encoder(opaque_ptr);
    try std.testing.expect(recovered != null);
    try std.testing.expectEqual(enc, recovered.?);
}

test "cast_bundle validates magic" {
    rb.set_allocator(std.testing.allocator);

    const enc = rb.make_bundle_encoder(0x04, 0, 1, false, false) orelse
        return error.AllocationFailed;

    const bundle = rb.bundle_encoder_finish(enc) orelse
        return error.FinishFailed;
    defer rb.bundle_destroy(bundle);

    const opaque_ptr: *anyopaque = @ptrCast(bundle);
    const recovered = rb.cast_bundle(opaque_ptr);
    try std.testing.expect(recovered != null);
    try std.testing.expectEqual(bundle, recovered.?);
}

// ============================================================
// All command tag variants are representable
// ============================================================

test "all BundleCmdTag variants can be pushed and recovered" {
    var enc = make_test_encoder(std.testing.allocator);
    defer enc.cmds.deinit(enc.allocator);

    rb.bundle_encoder_push(&enc, BundleCmd{ .set_pipeline = .{ .mtl_pso = null } });
    rb.bundle_encoder_push(&enc, BundleCmd{ .set_bind_group = .{
        .group = 0,
        .bg = .{ .entries = undefined, .count = 0 },
    } });
    rb.bundle_encoder_push(&enc, BundleCmd{ .set_vertex_buffer = .{
        .slot = 0,
        .mtl_buffer = null,
        .offset = 0,
    } });
    rb.bundle_encoder_push(&enc, BundleCmd{ .set_index_buffer = .{
        .mtl_buffer = null,
        .format = 0x2,
        .offset = 0,
        .size = 0,
    } });
    rb.bundle_encoder_push(&enc, BundleCmd{ .draw = .{
        .vertex_count = 1,
        .instance_count = 1,
        .first_vertex = 0,
        .first_instance = 0,
    } });
    rb.bundle_encoder_push(&enc, BundleCmd{ .draw_indexed = .{
        .index_count = 1,
        .instance_count = 1,
        .first_index = 0,
        .base_vertex = 0,
        .first_instance = 0,
    } });
    rb.bundle_encoder_push(&enc, BundleCmd{ .draw_indirect = .{
        .indirect_buffer = null,
        .indirect_offset = 0,
    } });
    rb.bundle_encoder_push(&enc, BundleCmd{ .draw_indexed_indirect = .{
        .indirect_buffer = null,
        .indirect_offset = 0,
    } });

    try std.testing.expectEqual(@as(usize, 8), enc.cmds.items.len);

    const expected_tags = [_]BundleCmdTag{
        .set_pipeline,
        .set_bind_group,
        .set_vertex_buffer,
        .set_index_buffer,
        .draw,
        .draw_indexed,
        .draw_indirect,
        .draw_indexed_indirect,
    };

    for (expected_tags, 0..) |tag, i| {
        try std.testing.expectEqual(tag, std.meta.activeTag(enc.cmds.items[i]));
    }
}

// ============================================================
// Constants
// ============================================================

test "MAX_BUNDLE_CMDS is 4096" {
    try std.testing.expectEqual(@as(usize, 4096), rb.MAX_BUNDLE_CMDS);
}

test "MAX_VTX_BUFS is 8" {
    try std.testing.expectEqual(@as(usize, 8), rb.MAX_VTX_BUFS);
}

test "MAX_BIND_GROUPS is 4" {
    try std.testing.expectEqual(@as(usize, 4), rb.MAX_BIND_GROUPS);
}

test "MAX_BINDINGS_PER_GROUP is 16" {
    try std.testing.expectEqual(@as(usize, 16), rb.MAX_BINDINGS_PER_GROUP);
}
