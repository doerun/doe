const std = @import("std");
const common_errors = @import("../../src/backend/common/errors.zig");
const wgpu_types = @import("../../src/wgpu_types.zig");

test "map_error_status returns unsupported for taxonomy errors" {
    try std.testing.expectEqual(
        wgpu_types.NativeExecutionStatus.unsupported,
        common_errors.map_error_status(error.Unsupported),
    );
    try std.testing.expectEqual(
        wgpu_types.NativeExecutionStatus.unsupported,
        common_errors.map_error_status(error.UnsupportedFeature),
    );
    try std.testing.expectEqual(
        wgpu_types.NativeExecutionStatus.unsupported,
        common_errors.map_error_status(error.SyncUnavailable),
    );
    try std.testing.expectEqual(
        wgpu_types.NativeExecutionStatus.unsupported,
        common_errors.map_error_status(error.TimingPolicyMismatch),
    );
    try std.testing.expectEqual(
        wgpu_types.NativeExecutionStatus.unsupported,
        common_errors.map_error_status(error.SurfaceUnavailable),
    );
}

test "map_error_status returns error for non-taxonomy errors" {
    try std.testing.expectEqual(
        wgpu_types.NativeExecutionStatus.@"error",
        common_errors.map_error_status(error.OutOfMemory),
    );
}

test "error_code returns error name" {
    try std.testing.expectEqualStrings("Unsupported", common_errors.error_code(error.Unsupported));
    try std.testing.expectEqualStrings("InvalidArgument", common_errors.error_code(error.InvalidArgument));
    try std.testing.expectEqualStrings("InvalidState", common_errors.error_code(error.InvalidState));
}

test "per-backend error aliases resolve to common set" {
    const vulkan_errors = @import("../../src/backend/vulkan/vulkan_errors.zig");
    const metal_errors = @import("../../src/backend/metal/metal_errors.zig");
    const d3d12_errors = @import("../../src/backend/d3d12/d3d12_errors.zig");

    try std.testing.expectEqual(
        @as(vulkan_errors.VulkanError, error.Unsupported),
        @as(common_errors.BackendNativeError, error.Unsupported),
    );
    try std.testing.expectEqual(
        @as(metal_errors.MetalError, error.InvalidState),
        @as(common_errors.BackendNativeError, error.InvalidState),
    );
    try std.testing.expectEqual(
        @as(d3d12_errors.D3D12Error, error.ShaderCompileFailed),
        @as(common_errors.BackendNativeError, error.ShaderCompileFailed),
    );
}
