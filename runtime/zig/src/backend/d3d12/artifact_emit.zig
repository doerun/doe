const artifact_state = @import("../common/artifact_state.zig");
const shared_manifest = @import("../common/shader_artifact_manifest.zig");

const SPEC = shared_manifest.ManifestSpec{
    .backend_id = "doe_d3d12",
    .file_prefix = "d3d12",
    .stages = &.{
        .{ .stage = "sema", .hash_label = "sema" },
        .{ .stage = "ir_build", .hash_label = "ir_build", .manifest_field = "irSha256" },
        .{ .stage = "ir_validate", .hash_label = "ir_validate" },
        .{ .stage = "ir_to_dxil", .hash_label = "ir_to_dxil", .manifest_field = "dxilSha256" },
    },
};

pub fn flushPending(state: *artifact_state.State) !void {
    try shared_manifest.flushPending(state, SPEC);
}
