const std = @import("std");

pub const ToggleEffect = enum {
    behavioral,
    informational,
    unhandled,
};

pub const ToggleEntry = struct {
    toggle_name: []const u8,
    effect: ToggleEffect,
    description: []const u8,
};

const KNOWN_TOGGLES = [_]ToggleEntry{
    // Behavioral: these toggles produce real command transforms in active mode
    .{
        .toggle_name = "use_temporary_buffer_in_texture_to_texture_copy",
        .effect = .behavioral,
        .description = "Vulkan spec gap: staging buffer for compressed tex-to-tex with non-block-aligned extents (crbug.com/dawn/42)",
    },
    .{
        .toggle_name = "use_temp_buffer_in_small_format_texture_to_texture_copy_from_greater_to_less_mip_level",
        .effect = .behavioral,
        .description = "Intel Gen9/Gen11 D3D12 CopyTextureRegion bug for small-format mip copies (crbug.com/1161355)",
    },
    .{
        .toggle_name = "d3d12_use_temp_buffer_in_depth_stencil_texture_and_buffer_copy_with_non_zero_buffer_offset",
        .effect = .behavioral,
        .description = "D3D12 depth-stencil copy restriction without programmable MSAA (crbug.com/dawn/727)",
    },
    .{
        .toggle_name = "d3d12_use_temp_buffer_in_texture_to_texture_copy_between_different_dimensions",
        .effect = .behavioral,
        .description = "D3D12 cross-dimension texture copy not natively supported (crbug.com/dawn/1216)",
    },
    .{
        .toggle_name = "MetalRenderR8RG8UnormSmallMipToTempTexture",
        .effect = .behavioral,
        .description = "Intel Metal: render to temp texture for R8/RG8 unorm small mips (level >= 2) (crbug.com/dawn/1071)",
    },
    // Informational: these toggles are trace-only (identity transform)
    .{
        .toggle_name = "VulkanCooperativeMatrixStrideIsMatrixElements",
        .effect = .informational,
        .description = "treat cooperative matrix stride as matrix elements instead of pointee elements (Mali workaround)",
    },
    .{
        .toggle_name = "disable_resource_suballocation",
        .effect = .informational,
        .description = "disable sub-allocation for buffers and textures",
    },
    .{
        .toggle_name = "use_d3d12_render_pass",
        .effect = .informational,
        .description = "use D3D12 render pass API when available",
    },
    .{
        .toggle_name = "use_dxc",
        .effect = .informational,
        .description = "use DXC compiler instead of FXC for HLSL",
    },
    .{
        .toggle_name = "disable_robustness",
        .effect = .informational,
        .description = "disable robustness transforms in shaders",
    },
    .{
        .toggle_name = "use_vulkan_zero_initialize_workgroup_memory_extension",
        .effect = .informational,
        .description = "use VK_KHR_zero_initialize_workgroup_memory when available",
    },
    .{
        .toggle_name = "MetalReplaceWorkgroupBoolWithU32",
        .effect = .informational,
        .description = "replace workgroup bool with u32 in MSL for Mac AMD/Intel",
    },
};

pub fn lookup(toggle_name: []const u8) ?ToggleEntry {
    for (&KNOWN_TOGGLES) |*entry| {
        if (std.ascii.eqlIgnoreCase(toggle_name, entry.toggle_name)) {
            return entry.*;
        }
    }
    return null;
}

pub fn effect(toggle_name: []const u8) ToggleEffect {
    if (lookup(toggle_name)) |entry| {
        return entry.effect;
    }
    return .unhandled;
}

pub fn knownCount() usize {
    return KNOWN_TOGGLES.len;
}

test "lookup finds known toggles case-insensitively" {
    const entry = lookup("vulkancooperativematrixstrideismatrixelements");
    try std.testing.expect(entry != null);
    try std.testing.expectEqual(ToggleEffect.informational, entry.?.effect);
}

test "lookup returns null for unknown toggles" {
    try std.testing.expect(lookup("nonexistent_toggle_xyz") == null);
}

test "effect returns unhandled for unknown toggles" {
    try std.testing.expectEqual(ToggleEffect.unhandled, effect("unknown_toggle"));
}

test "known toggle count" {
    try std.testing.expect(knownCount() > 0);
}
