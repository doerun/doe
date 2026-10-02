// Vulkan adapter identity and capabilities captured from one physical-device
// selection. Keeping these values in one probe prevents capabilities from a
// different ICD/device being attached to the published adapter identity.

const std = @import("std");
const backend_contract = @import("../../contracts/backend.zig");
const c = @import("vk_constants.zig");
const native_runtime = @import("native_runtime.zig");
const webgpu = @import("../../contracts/runtime_types.zig");
const vk_device = @import("vk_device.zig");
const vk_device_caps = @import("vk_device_caps.zig");
const vk_feature_caps = @import("vk_feature_caps.zig");

pub const SelectedAdapter = struct {
    instance: c.VkInstance,
    physical_device: c.VkPhysicalDevice,
    queue_family_policy: webgpu.QueueFamilyPolicy,
    has_surface_maintenance_instance: bool,
    adapter_ordinal_value: ?u32,
    queue_family_index: u32,
    queue_family_index_value_cache: ?u32,
    queue_family_kind_value_cache: ?webgpu.QueueFamilyKind,
    queue_family_queue_count_value_cache: ?u32,
    queue_family_timestamp_valid_bits_value_cache: ?u32,
    queue_family_supports_graphics_value_cache: ?bool,
    present_capable_value: ?bool,
    timestamp_query_supported_value: bool,
    timestamp_period: f32,

    pub fn deinit(self: *SelectedAdapter, allocator: std.mem.Allocator) void {
        c.vkDestroyInstance(self.instance, null);
        allocator.destroy(self);
    }
};

pub const AdapterProbe = struct {
    identity: native_runtime.AdapterIdentity,
    feature_caps: vk_feature_caps.VulkanFeatureCaps,
    device_caps: vk_device_caps.VulkanDeviceCaps,
    selection: ?*SelectedAdapter,

    pub fn deinit(self: *AdapterProbe, allocator: std.mem.Allocator) void {
        if (self.selection) |selection| {
            selection.deinit(allocator);
            self.selection = null;
        }
    }
};

pub fn release_selection(allocator: std.mem.Allocator, raw: *anyopaque) void {
    const selection: *SelectedAdapter = @ptrCast(@alignCast(raw));
    selection.deinit(allocator);
}

pub fn probe_selected_adapter(
    allocator: std.mem.Allocator,
    queue_family_policy: backend_contract.QueueFamilyPolicy,
) !AdapterProbe {
    var probe = native_runtime.NativeVulkanRuntime{
        .allocator = allocator,
        .kernel_root = null,
        .queue_family_policy = queue_family_policy,
    };
    try vk_device.create_instance(&probe);
    errdefer vk_device.destroy_instance_only(&probe);
    try vk_device.select_physical_device(&probe);

    const identity = query_identity(probe.physical_device);
    const timestamp_valid_bits = probe.queue_family_timestamp_valid_bits_value_cache orelse 0;
    const feature_caps = vk_feature_caps.query(probe.physical_device).caps;
    const device_caps = vk_device_caps.query_device_caps(probe.physical_device, timestamp_valid_bits);
    const selection = try allocator.create(SelectedAdapter);
    selection.* = .{
        .instance = probe.instance,
        .physical_device = probe.physical_device,
        .queue_family_policy = queue_family_policy,
        .has_surface_maintenance_instance = probe.has_surface_maintenance_instance,
        .adapter_ordinal_value = probe.adapter_ordinal_value,
        .queue_family_index = probe.queue_family_index,
        .queue_family_index_value_cache = probe.queue_family_index_value_cache,
        .queue_family_kind_value_cache = probe.queue_family_kind_value_cache,
        .queue_family_queue_count_value_cache = probe.queue_family_queue_count_value_cache,
        .queue_family_timestamp_valid_bits_value_cache = probe.queue_family_timestamp_valid_bits_value_cache,
        .queue_family_supports_graphics_value_cache = probe.queue_family_supports_graphics_value_cache,
        .present_capable_value = probe.present_capable_value,
        .timestamp_query_supported_value = probe.timestamp_query_supported_value,
        .timestamp_period = probe.timestamp_period,
    };
    probe.has_instance = false;
    return .{
        .identity = identity,
        .feature_caps = feature_caps,
        .device_caps = device_caps,
        .selection = selection,
    };
}

pub const SurfaceSource = union(enum) {
    xcb: struct { connection: *anyopaque, window: u32 },
    xlib: struct { display: *anyopaque, window: u64 },
    wayland: struct { display: *anyopaque, surface: *anyopaque },
};

/// Query before device creation without publishing a runtime or retaining window ownership.
/// Selection must still match the adapter whose public handle authorized the query.
pub fn probeSurfaceCapabilities(
    allocator: std.mem.Allocator,
    queue_family_policy: backend_contract.QueueFamilyPolicy,
    expected: native_runtime.AdapterIdentity,
    source: SurfaceSource,
) !@import("vulkan_surface.zig").CanvasCapabilities {
    const surfaces = @import("vulkan_surface.zig");
    var probe = native_runtime.NativeVulkanRuntime{ .allocator = allocator, .kernel_root = null, .queue_family_policy = queue_family_policy };
    try vk_device.create_instance(&probe);
    defer vk_device.destroy_instance_only(&probe);
    try vk_device.select_physical_device(&probe);
    if (!identity_matches(expected, query_identity(probe.physical_device))) return error.InvalidArgument;
    if (!vk_device.supportsSurfaceCompletion(probe.physical_device, probe.has_surface_maintenance_instance)) return error.UnsupportedFeature;
    const surface = try switch (source) {
        .xcb => |window| surfaces.create_xcb_surface(probe.instance, window.connection, window.window),
        .xlib => |window| surfaces.create_xlib_surface(probe.instance, window.display, window.window),
        .wayland => |window| surfaces.create_wayland_surface(probe.instance, window.display, window.surface),
    };
    defer surfaces.destroy_surface(probe.instance, surface);
    return surfaces.canvasCapabilities(try surfaces.query_surface_capabilities(probe.physical_device, probe.queue_family_index, surface));
}

pub fn query_identity(physical_device: c.VkPhysicalDevice) native_runtime.AdapterIdentity {
    var properties2 = std.mem.zeroes(c.VkPhysicalDeviceProperties2);
    properties2.sType = c.VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2;
    c.vkGetPhysicalDeviceProperties2(physical_device, &properties2);
    const properties = properties2.properties;
    return .{
        .vendor_id = properties.vendorID,
        .device_id = properties.deviceID,
        .driver_version = properties.driverVersion,
        .device_name = properties.deviceName,
        .device_name_len = std.mem.indexOfScalar(
            u8,
            properties.deviceName[0..],
            0,
        ) orelse properties.deviceName.len,
    };
}

pub fn identity_matches(
    expected: native_runtime.AdapterIdentity,
    actual: native_runtime.AdapterIdentity,
) bool {
    return expected.vendor_id == actual.vendor_id and
        expected.device_id == actual.device_id and
        expected.driver_version == actual.driver_version and
        std.mem.eql(
            u8,
            expected.device_name[0..expected.device_name_len],
            actual.device_name[0..actual.device_name_len],
        );
}

pub fn identity_matches_fields(
    vendor_id: u32,
    device_id: u32,
    driver_version: u32,
    device_name: []const u8,
    actual: native_runtime.AdapterIdentity,
) bool {
    return vendor_id == actual.vendor_id and
        device_id == actual.device_id and
        driver_version == actual.driver_version and
        std.mem.eql(
            u8,
            device_name,
            actual.device_name[0..actual.device_name_len],
        );
}

test "adapter capability binding requires the selected physical-device identity" {
    var name = [_]u8{0} ** backend_contract.ADAPTER_DEVICE_NAME_BYTES;
    @memcpy(name[0..6], "Radeon");
    const actual = native_runtime.AdapterIdentity{
        .vendor_id = 0x1002,
        .device_id = 0x744c,
        .driver_version = 7,
        .device_name = name,
        .device_name_len = 6,
    };
    try std.testing.expect(identity_matches_fields(
        0x1002,
        0x744c,
        7,
        "Radeon",
        actual,
    ));
    try std.testing.expect(!identity_matches_fields(
        0x10005,
        0x0000,
        1,
        "llvmpipe",
        actual,
    ));
}
