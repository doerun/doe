const std = @import("std");
const d3d12_descriptors = @import("../d3d12_descriptors.zig");
const d3d12_texture_view = @import("../resources/d3d12_texture_view.zig");
const d3d12_sampler = @import("../resources/d3d12_sampler.zig");

// --- WebGPU binding limits ---
const MAX_FLAT_BIND: usize = 64;

// --- Root parameter layout ---
// Root signature layout for render passes with texture/sampler bindings:
//   root param 0: CBV/SRV/UAV descriptor table (SRVs for textures)
//   root param 1: Sampler descriptor table
const ROOT_PARAM_SRV_TABLE: u32 = 0;
const ROOT_PARAM_SAMPLER_TABLE: u32 = 1;

/// Result of binding textures and samplers for a render pass. Tracks the
/// root signature and descriptor base indices needed to set descriptor tables.
pub const RenderBindResult = struct {
    root_signature: ?*anyopaque = null,
    srv_base_index: u32 = 0,
    sampler_base_index: u32 = 0,
    srv_count: u32 = 0,
    sampler_count: u32 = 0,
};

/// Bind texture SRV and sampler descriptors for a render pass.
///
/// Allocates SRV descriptors in the CBV/SRV/UAV heap for each bound texture,
/// and sampler descriptors in the sampler heap for each bound sampler. Creates
/// a root signature that matches the descriptor layout.
///
/// The caller is responsible for retaining the root signature handle.
pub fn bind_render_pass_textures_and_samplers(
    device: ?*anyopaque,
    descriptor_state: *d3d12_descriptors.DescriptorHeapState,
    texture_view_state: *const d3d12_texture_view.TextureViewState,
    sampler_state: *const d3d12_sampler.SamplerState,
    bind_textures: []const ?*anyopaque,
    bind_samplers: []const ?*anyopaque,
) !RenderBindResult {
    var result = RenderBindResult{};

    // Count active textures and samplers
    var texture_count: u32 = 0;
    for (bind_textures) |tex| {
        if (tex != null) texture_count += 1;
    }
    var sampler_count: u32 = 0;
    for (bind_samplers) |smp| {
        if (smp != null) sampler_count += 1;
    }

    if (texture_count == 0 and sampler_count == 0) return result;

    try descriptor_state.ensure_heaps(device);

    // Record start indices for contiguous descriptor table ranges
    const srv_base = descriptor_state.cbv_srv_uav_next;
    const sampler_base = descriptor_state.sampler_next;

    // Allocate SRV descriptors for each bound texture view
    for (bind_textures) |maybe_tex| {
        const tex_view_ptr = maybe_tex orelse continue;
        // The texture view's native resource handle is stored in the handle field.
        // Look up the texture view entry to get the format for the SRV descriptor.
        const handle_val = @intFromPtr(tex_view_ptr);
        const view_entry = texture_view_state.get_view(handle_val);
        if (view_entry) |entry| {
            // Allocate SRV using the view's format and the texture resource
            _ = try descriptor_state.allocate_srv_texture(
                device,
                tex_view_ptr,
                entry.format,
            );
        } else {
            // Fallback: allocate SRV with RGBA8Unorm format
            const RGBA8_UNORM_FORMAT: u32 = 0x00000012;
            _ = try descriptor_state.allocate_srv_texture(
                device,
                tex_view_ptr,
                RGBA8_UNORM_FORMAT,
            );
        }
    }

    // Allocate sampler descriptors for each bound sampler
    for (bind_samplers) |maybe_smp| {
        const smp_ptr = maybe_smp orelse continue;
        const handle_val = @intFromPtr(smp_ptr);
        const sampler_entry = sampler_state.map.get(handle_val);
        if (sampler_entry) |entry| {
            _ = try descriptor_state.allocate_sampler_descriptor(
                device,
                entry.min_filter,
                entry.mag_filter,
                entry.mipmap_filter,
                entry.address_mode_u,
                entry.address_mode_v,
                entry.address_mode_w,
                entry.lod_min_clamp,
                entry.lod_max_clamp,
                entry.compare,
                entry.max_anisotropy,
            );
        } else {
            // Fallback: linear wrap sampler with reasonable defaults
            _ = try descriptor_state.allocate_sampler_descriptor(
                device,
                0x00000002, // linear min
                0x00000002, // linear mag
                0x00000002, // linear mip
                0x00000002, // wrap U
                0x00000002, // wrap V
                0x00000002, // wrap W
                0.0, // lod min
                32.0, // lod max
                0, // no compare
                1, // no anisotropy
            );
        }
    }

    result.srv_base_index = srv_base;
    result.sampler_base_index = sampler_base;
    result.srv_count = texture_count;
    result.sampler_count = sampler_count;

    // Build root signature with SRV and sampler descriptor tables
    if (texture_count > 0 or sampler_count > 0) {
        var layout = d3d12_descriptors.RootSignatureLayout{
            .allow_input_assembler = true,
        };
        var entries_buf: [MAX_FLAT_BIND]d3d12_descriptors.BindingEntry = undefined;
        var entry_count: usize = 0;

        // SRV entries for textures
        var tex_i: u32 = 0;
        for (bind_textures) |tex| {
            if (tex != null) {
                entries_buf[entry_count] = .{
                    .binding = tex_i,
                    .binding_type = .sampled_texture,
                };
                entry_count += 1;
                tex_i += 1;
            }
        }

        // Sampler entries
        var smp_i: u32 = 0;
        for (bind_samplers) |smp| {
            if (smp != null) {
                entries_buf[entry_count] = .{
                    .binding = smp_i,
                    .binding_type = .sampler,
                };
                entry_count += 1;
                smp_i += 1;
            }
        }

        if (entry_count > 0) {
            layout.groups[0] = .{ .entries = entries_buf[0..entry_count] };
            result.root_signature = try d3d12_descriptors.create_root_signature_with_bindings(
                device,
                layout,
            );
        }
    }

    return result;
}

/// Set descriptor heaps and bind descriptor tables on a graphics command list.
/// Must be called after setting the root signature and before draw calls.
pub fn set_render_pass_descriptor_tables(
    cmd_list: ?*anyopaque,
    descriptor_state: *d3d12_descriptors.DescriptorHeapState,
    bind_result: RenderBindResult,
) void {
    if (bind_result.srv_count == 0 and bind_result.sampler_count == 0) return;

    // Bind both descriptor heaps to the command list
    descriptor_state.bind_heaps(cmd_list);

    // Set the SRV descriptor table (root param 0)
    if (bind_result.srv_count > 0) {
        d3d12_descriptors.set_graphics_descriptor_table(
            cmd_list,
            ROOT_PARAM_SRV_TABLE,
            descriptor_state.cbv_srv_uav_heap,
            bind_result.srv_base_index,
        );
    }

    // Set the sampler descriptor table (root param 1)
    if (bind_result.sampler_count > 0) {
        const sampler_root_param = if (bind_result.srv_count > 0)
            ROOT_PARAM_SAMPLER_TABLE
        else
            ROOT_PARAM_SRV_TABLE;
        d3d12_descriptors.set_graphics_sampler_table(
            cmd_list,
            sampler_root_param,
            descriptor_state.sampler_heap,
            bind_result.sampler_base_index,
        );
    }
}

// --- Tests ---

test "RenderBindResult defaults" {
    const result = RenderBindResult{};
    try std.testing.expect(result.root_signature == null);
    try std.testing.expectEqual(@as(u32, 0), result.srv_count);
    try std.testing.expectEqual(@as(u32, 0), result.sampler_count);
}

test "set_render_pass_descriptor_tables with no bindings is safe" {
    var state = d3d12_descriptors.DescriptorHeapState{};
    const result = RenderBindResult{};
    // Should be a no-op with no bindings
    set_render_pass_descriptor_tables(null, &state, result);
}
