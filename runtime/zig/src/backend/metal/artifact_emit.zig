const artifact_state = @import("../common/artifact_state.zig");
const shared_manifest = @import("../common/shader_artifact_manifest.zig");

const SPEC = shared_manifest.ManifestSpec{
    .backend_id = "doe_metal",
    .file_prefix = "metal",
    .stages = &.{
        .{ .stage = "sema", .hash_label = "sema" },
        .{ .stage = "ir_build", .hash_label = "ir_build", .manifest_field = "irSha256" },
        .{ .stage = "ir_validate", .hash_label = "ir_validate" },
        .{ .stage = "ir_to_msl", .hash_label = "ir_to_msl", .manifest_field = "mslSha256" },
        .{
            .stage = "msl_compile",
            .hash_label = "msl_compile",
            .manifest_field = "metallibSha256",
        },
    },
};

pub fn flushPending(state: *artifact_state.State) !void {
    try shared_manifest.flushPending(state, SPEC);
}
