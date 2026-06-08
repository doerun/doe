const std = @import("std");
const model_compute_types = @import("../../model_compute_types.zig");

pub const BindingHashes = struct {
    layout_hash: u64,
    descriptor_bindings_hash: u64,
};

pub const BindingHashBuilder = struct {
    layout_hasher: std.hash.Wyhash,
    descriptor_hasher: std.hash.Wyhash,

    pub fn init() BindingHashBuilder {
        return .{
            .layout_hasher = std.hash.Wyhash.init(0),
            .descriptor_hasher = std.hash.Wyhash.init(0),
        };
    }

    pub fn update(self: *BindingHashBuilder, binding: model_compute_types.KernelBinding) void {
        update_layout_hash(&self.layout_hasher, binding);
        update_descriptor_hash(&self.descriptor_hasher, binding);
    }

    pub fn finish(self: *BindingHashBuilder) BindingHashes {
        return .{
            .layout_hash = self.layout_hasher.final(),
            .descriptor_bindings_hash = self.descriptor_hasher.final(),
        };
    }
};

pub fn compute_layout_hash(bindings: ?[]const model_compute_types.KernelBinding) u64 {
    var hasher = std.hash.Wyhash.init(0);
    if (bindings) |bs| {
        for (bs) |binding| update_layout_hash(&hasher, binding);
    }
    return hasher.final();
}

pub fn compute_descriptor_bindings_hash(bindings: []const model_compute_types.KernelBinding) u64 {
    var hasher = std.hash.Wyhash.init(0);
    for (bindings) |binding| update_descriptor_hash(&hasher, binding);
    return hasher.final();
}

fn update_layout_hash(hasher: *std.hash.Wyhash, binding: model_compute_types.KernelBinding) void {
    hasher.update(std.mem.asBytes(&binding.group));
    hasher.update(std.mem.asBytes(&binding.binding));
    hasher.update(std.mem.asBytes(&binding.resource_kind));
    hasher.update(std.mem.asBytes(&binding.buffer_type));
    hasher.update(std.mem.asBytes(&binding.texture_sample_type));
    hasher.update(std.mem.asBytes(&binding.texture_view_dimension));
    hasher.update(std.mem.asBytes(&binding.storage_texture_access));
    hasher.update(std.mem.asBytes(&binding.texture_format));
    hasher.update(std.mem.asBytes(&binding.texture_multisampled));
}

fn update_descriptor_hash(hasher: *std.hash.Wyhash, binding: model_compute_types.KernelBinding) void {
    hasher.update(std.mem.asBytes(&binding.group));
    hasher.update(std.mem.asBytes(&binding.binding));
    hasher.update(std.mem.asBytes(&binding.resource_kind));
    hasher.update(std.mem.asBytes(&binding.resource_handle));
    hasher.update(std.mem.asBytes(&binding.visibility));
    hasher.update(std.mem.asBytes(&binding.buffer_offset));
    hasher.update(std.mem.asBytes(&binding.buffer_size));
    hasher.update(std.mem.asBytes(&binding.buffer_type));
    hasher.update(std.mem.asBytes(&binding.texture_sample_type));
    hasher.update(std.mem.asBytes(&binding.texture_view_dimension));
    hasher.update(std.mem.asBytes(&binding.storage_texture_access));
    hasher.update(std.mem.asBytes(&binding.texture_aspect));
    hasher.update(std.mem.asBytes(&binding.texture_format));
    hasher.update(std.mem.asBytes(&binding.texture_multisampled));
}

test "incremental binding hashes match slice helpers" {
    const bindings = [_]model_compute_types.KernelBinding{
        .{
            .group = 0,
            .binding = 1,
            .resource_kind = .buffer,
            .resource_handle = 11,
            .buffer_offset = 16,
            .buffer_size = 64,
        },
        .{
            .group = 1,
            .binding = 2,
            .resource_kind = .buffer,
            .resource_handle = 22,
            .buffer_offset = 32,
            .buffer_size = 128,
        },
    };
    var builder = BindingHashBuilder.init();
    for (bindings) |binding| builder.update(binding);
    const hashes = builder.finish();

    try std.testing.expectEqual(compute_layout_hash(&bindings), hashes.layout_hash);
    try std.testing.expectEqual(compute_descriptor_bindings_hash(&bindings), hashes.descriptor_bindings_hash);
}
