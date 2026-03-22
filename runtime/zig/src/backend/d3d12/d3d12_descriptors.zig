const std = @import("std");

// --- D3D12 descriptor heap type constants ---
// D3D12_DESCRIPTOR_HEAP_TYPE values from d3d12.h
const DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV: c_int = 0;
const DESCRIPTOR_HEAP_TYPE_SAMPLER: c_int = 1;

// --- Capacity defaults ---
// 256 is the minimum guaranteed by D3D12 for shader-visible CBV/SRV/UAV heaps;
// keeps resident memory low while covering typical bind group layouts.
const DEFAULT_CBV_SRV_UAV_HEAP_SIZE: u32 = 256;
// 64 covers 4 bind groups x 16 samplers per group, the WebGPU maximum.
const DEFAULT_SAMPLER_HEAP_SIZE: u32 = 64;

// --- WebGPU binding limits ---
const MAX_BIND_GROUPS: u32 = 4;
const MAX_BINDINGS_PER_GROUP: u32 = 16;

// --- Root signature serialization flags ---
const ROOT_SIG_FLAG_NONE: u32 = 0;
const ROOT_SIG_FLAG_ALLOW_INPUT_ASSEMBLER: u32 = 0x1;

// --- Descriptor range types (D3D12_DESCRIPTOR_RANGE_TYPE) ---
const RANGE_TYPE_SRV: u32 = 0;
const RANGE_TYPE_UAV: u32 = 1;
const RANGE_TYPE_CBV: u32 = 2;
const RANGE_TYPE_SAMPLER: u32 = 3;

// --- Bridge extern declarations ---
// Existing bridge functions
extern fn d3d12_bridge_device_create_sampler_heap(device: ?*anyopaque, num_descriptors: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;

// New bridge functions — implementations will be added to d3d12_bridge.c
extern fn d3d12_bridge_device_create_cbv_srv_uav_heap(device: ?*anyopaque, num_descriptors: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_root_signature_with_tables(
    device: ?*anyopaque,
    ranges: [*]const DescriptorRangeDesc,
    range_count: u32,
    flags: u32,
) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_command_list_set_descriptor_heaps(
    cmd_list: ?*anyopaque,
    cbv_srv_uav_heap: ?*anyopaque,
    sampler_heap: ?*anyopaque,
) callconv(.c) void;
extern fn d3d12_bridge_device_create_cbv(
    device: ?*anyopaque,
    heap: ?*anyopaque,
    heap_index: u32,
    buffer: ?*anyopaque,
    offset: u64,
    size: u32,
) callconv(.c) void;
extern fn d3d12_bridge_device_create_srv_buffer(
    device: ?*anyopaque,
    heap: ?*anyopaque,
    heap_index: u32,
    buffer: ?*anyopaque,
    num_elements: u32,
    stride: u32,
) callconv(.c) void;
extern fn d3d12_bridge_device_create_uav_buffer(
    device: ?*anyopaque,
    heap: ?*anyopaque,
    heap_index: u32,
    buffer: ?*anyopaque,
    num_elements: u32,
    stride: u32,
) callconv(.c) void;
extern fn d3d12_bridge_device_create_srv_texture(
    device: ?*anyopaque,
    heap: ?*anyopaque,
    heap_index: u32,
    texture: ?*anyopaque,
    format: u32,
) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_compute_root_descriptor_table(
    cmd_list: ?*anyopaque,
    root_parameter_index: u32,
    heap: ?*anyopaque,
    base_descriptor_index: u32,
) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_graphics_root_descriptor_table(
    cmd_list: ?*anyopaque,
    root_parameter_index: u32,
    heap: ?*anyopaque,
    base_descriptor_index: u32,
) callconv(.c) void;
extern fn d3d12_bridge_device_create_sampler_in_heap(
    device: ?*anyopaque,
    sampler_heap: ?*anyopaque,
    heap_index: u32,
    min_filter: u32,
    mag_filter: u32,
    mipmap_filter: u32,
    address_mode_u: u32,
    address_mode_v: u32,
    address_mode_w: u32,
    lod_min_clamp: f32,
    lod_max_clamp: f32,
    compare: u32,
    max_anisotropy: u16,
) callconv(.c) void;
extern fn d3d12_bridge_command_list_set_graphics_root_sampler_table(
    cmd_list: ?*anyopaque,
    root_parameter_index: u32,
    sampler_heap: ?*anyopaque,
    base_descriptor_index: u32,
) callconv(.c) void;

/// Passed to the bridge to describe one descriptor range within a root parameter.
/// Layout must match the C struct consumed by `d3d12_bridge_device_create_root_signature_with_tables`.
pub const DescriptorRangeDesc = extern struct {
    range_type: u32,
    num_descriptors: u32,
    base_shader_register: u32,
    register_space: u32,
};

/// Binding type taxonomy — mirrors WebGPU GPUBufferBindingType / GPUBindGroupLayoutEntry.
pub const BindingType = enum(u8) {
    uniform_buffer,
    storage_buffer,
    read_only_storage_buffer,
    sampled_texture,
    storage_texture,
    sampler,
};

/// One binding slot within a bind group layout.
pub const BindingEntry = struct {
    binding: u32,
    binding_type: BindingType,
    /// Only relevant for buffer bindings; texture/sampler bindings ignore this.
    has_dynamic_offset: bool = false,
};

/// Layout of a single bind group, mapping to one or more D3D12 descriptor table ranges.
pub const BindGroupLayout = struct {
    entries: []const BindingEntry,
};

/// Describes the full root signature layout across all bind groups.
pub const RootSignatureLayout = struct {
    /// Up to MAX_BIND_GROUPS bind group layouts, indexed by group number.
    groups: [MAX_BIND_GROUPS]?BindGroupLayout = [_]?BindGroupLayout{null} ** MAX_BIND_GROUPS,
    /// Whether the root signature needs the input assembler (vertex input) flag.
    allow_input_assembler: bool = false,
};

/// Manages CBV/SRV/UAV and sampler descriptor heaps for a device lifetime.
/// Descriptors are allocated linearly; call `reset_allocations` between frames
/// or submissions to reclaim indices without releasing the underlying heap.
pub const DescriptorHeapState = struct {
    cbv_srv_uav_heap: ?*anyopaque = null,
    sampler_heap: ?*anyopaque = null,
    cbv_srv_uav_capacity: u32 = 0,
    sampler_capacity: u32 = 0,
    cbv_srv_uav_next: u32 = 0,
    sampler_next: u32 = 0,

    /// Lazily creates both descriptor heaps with default capacities.
    /// Safe to call multiple times — no-ops if heaps already exist.
    pub fn ensure_heaps(self: *DescriptorHeapState, device: ?*anyopaque) !void {
        if (self.cbv_srv_uav_heap == null) {
            self.cbv_srv_uav_heap = d3d12_bridge_device_create_cbv_srv_uav_heap(
                device,
                DEFAULT_CBV_SRV_UAV_HEAP_SIZE,
            ) orelse return error.InvalidState;
            self.cbv_srv_uav_capacity = DEFAULT_CBV_SRV_UAV_HEAP_SIZE;
        }
        if (self.sampler_heap == null) {
            self.sampler_heap = d3d12_bridge_device_create_sampler_heap(
                device,
                DEFAULT_SAMPLER_HEAP_SIZE,
            ) orelse return error.InvalidState;
            self.sampler_capacity = DEFAULT_SAMPLER_HEAP_SIZE;
        }
    }

    /// Allocate a constant buffer view in the CBV/SRV/UAV heap.
    /// Returns the descriptor index.
    pub fn allocate_cbv(
        self: *DescriptorHeapState,
        device: ?*anyopaque,
        buffer: ?*anyopaque,
        size: u64,
    ) !u32 {
        try self.ensure_heaps(device);
        const index = try self.next_cbv_srv_uav_index();
        // CBV size must be 256-byte aligned per D3D12 spec
        const aligned_size = align_cbv_size(size);
        d3d12_bridge_device_create_cbv(
            device,
            self.cbv_srv_uav_heap,
            index,
            buffer,
            0,
            @intCast(aligned_size),
        );
        return index;
    }

    /// Allocate a shader resource view for a structured buffer.
    /// Returns the descriptor index.
    pub fn allocate_srv_buffer(
        self: *DescriptorHeapState,
        device: ?*anyopaque,
        buffer: ?*anyopaque,
        num_elements: u32,
        stride: u32,
    ) !u32 {
        try self.ensure_heaps(device);
        const index = try self.next_cbv_srv_uav_index();
        d3d12_bridge_device_create_srv_buffer(
            device,
            self.cbv_srv_uav_heap,
            index,
            buffer,
            num_elements,
            stride,
        );
        return index;
    }

    /// Allocate an unordered access view for a storage buffer.
    /// Returns the descriptor index.
    pub fn allocate_uav_buffer(
        self: *DescriptorHeapState,
        device: ?*anyopaque,
        buffer: ?*anyopaque,
        num_elements: u32,
        stride: u32,
    ) !u32 {
        try self.ensure_heaps(device);
        const index = try self.next_cbv_srv_uav_index();
        d3d12_bridge_device_create_uav_buffer(
            device,
            self.cbv_srv_uav_heap,
            index,
            buffer,
            num_elements,
            stride,
        );
        return index;
    }

    /// Allocate a shader resource view for a 2D texture.
    /// Returns the descriptor index.
    pub fn allocate_srv_texture(
        self: *DescriptorHeapState,
        device: ?*anyopaque,
        texture: ?*anyopaque,
        format: u32,
    ) !u32 {
        try self.ensure_heaps(device);
        const index = try self.next_cbv_srv_uav_index();
        d3d12_bridge_device_create_srv_texture(
            device,
            self.cbv_srv_uav_heap,
            index,
            texture,
            format,
        );
        return index;
    }

    /// Allocate a sampler descriptor slot. The actual sampler parameters are
    /// handled by the bridge; this just reserves the index.
    pub fn allocate_sampler(self: *DescriptorHeapState, device: ?*anyopaque) !u32 {
        try self.ensure_heaps(device);
        if (self.sampler_next >= self.sampler_capacity) return error.UnsupportedFeature;
        const index = self.sampler_next;
        self.sampler_next += 1;
        return index;
    }

    /// Allocate a sampler descriptor slot and write the sampler parameters
    /// into the sampler heap at that index. Returns the descriptor index.
    pub fn allocate_sampler_descriptor(
        self: *DescriptorHeapState,
        device: ?*anyopaque,
        min_filter: u32,
        mag_filter: u32,
        mipmap_filter: u32,
        address_mode_u: u32,
        address_mode_v: u32,
        address_mode_w: u32,
        lod_min_clamp: f32,
        lod_max_clamp: f32,
        compare: u32,
        max_anisotropy: u16,
    ) !u32 {
        const index = try self.allocate_sampler(device);
        d3d12_bridge_device_create_sampler_in_heap(
            device,
            self.sampler_heap,
            index,
            min_filter,
            mag_filter,
            mipmap_filter,
            address_mode_u,
            address_mode_v,
            address_mode_w,
            lod_min_clamp,
            lod_max_clamp,
            compare,
            max_anisotropy,
        );
        return index;
    }

    /// Bind both descriptor heaps to a command list. Must be called before
    /// setting root descriptor tables.
    pub fn bind_heaps(self: *DescriptorHeapState, cmd_list: ?*anyopaque) void {
        d3d12_bridge_command_list_set_descriptor_heaps(
            cmd_list,
            self.cbv_srv_uav_heap,
            self.sampler_heap,
        );
    }

    /// Reset linear allocation indices without releasing the heaps.
    /// Call between submissions to reuse descriptor slots.
    pub fn reset_allocations(self: *DescriptorHeapState) void {
        self.cbv_srv_uav_next = 0;
        self.sampler_next = 0;
    }

    /// Release all heap resources. The state is left in the zero-initialized form
    /// and can be re-used by calling `ensure_heaps` again.
    pub fn deinit(self: *DescriptorHeapState) void {
        if (self.cbv_srv_uav_heap) |h| {
            d3d12_bridge_release(h);
        }
        if (self.sampler_heap) |h| {
            d3d12_bridge_release(h);
        }
        self.* = .{};
    }

    // --- Private helpers ---

    fn next_cbv_srv_uav_index(self: *DescriptorHeapState) !u32 {
        if (self.cbv_srv_uav_next >= self.cbv_srv_uav_capacity) return error.UnsupportedFeature;
        const index = self.cbv_srv_uav_next;
        self.cbv_srv_uav_next += 1;
        return index;
    }
};

/// Build a root signature from a `RootSignatureLayout` describing bind group bindings.
///
/// Each bind group with entries becomes a root parameter containing descriptor table
/// ranges. The ranges are ordered: CBVs first, then SRVs, then UAVs per group, with
/// samplers in a separate descriptor table (sampler heap cannot be mixed with CBV/SRV/UAV).
///
/// Returns an opaque root signature handle owned by the caller.
pub fn create_root_signature_with_bindings(
    device: ?*anyopaque,
    layout: RootSignatureLayout,
) !?*anyopaque {
    // Worst case: each binding produces one range, plus one sampler table per group
    const MAX_RANGES = MAX_BIND_GROUPS * MAX_BINDINGS_PER_GROUP;
    var ranges: [MAX_RANGES]DescriptorRangeDesc = undefined;
    var range_count: u32 = 0;

    for (layout.groups, 0..) |maybe_group, group_idx| {
        const group = maybe_group orelse continue;
        const register_space: u32 = @intCast(group_idx);

        // Collect CBV/SRV/UAV ranges for this group
        var cbv_count: u32 = 0;
        var srv_count: u32 = 0;
        var uav_count: u32 = 0;
        var sampler_count: u32 = 0;

        for (group.entries) |entry| {
            switch (entry.binding_type) {
                .uniform_buffer => cbv_count += 1,
                .sampled_texture => srv_count += 1,
                .read_only_storage_buffer => srv_count += 1,
                .storage_buffer => uav_count += 1,
                .storage_texture => uav_count += 1,
                .sampler => sampler_count += 1,
            }
        }

        // Emit CBV range
        if (cbv_count > 0) {
            if (range_count >= MAX_RANGES) return error.InvalidArgument;
            ranges[range_count] = .{
                .range_type = RANGE_TYPE_CBV,
                .num_descriptors = cbv_count,
                .base_shader_register = 0,
                .register_space = register_space,
            };
            range_count += 1;
        }

        // Emit SRV range
        if (srv_count > 0) {
            if (range_count >= MAX_RANGES) return error.InvalidArgument;
            ranges[range_count] = .{
                .range_type = RANGE_TYPE_SRV,
                .num_descriptors = srv_count,
                .base_shader_register = 0,
                .register_space = register_space,
            };
            range_count += 1;
        }

        // Emit UAV range
        if (uav_count > 0) {
            if (range_count >= MAX_RANGES) return error.InvalidArgument;
            ranges[range_count] = .{
                .range_type = RANGE_TYPE_UAV,
                .num_descriptors = uav_count,
                .base_shader_register = 0,
                .register_space = register_space,
            };
            range_count += 1;
        }

        // Sampler range — separate table because D3D12 requires sampler descriptors
        // in their own heap type.
        if (sampler_count > 0) {
            if (range_count >= MAX_RANGES) return error.InvalidArgument;
            ranges[range_count] = .{
                .range_type = RANGE_TYPE_SAMPLER,
                .num_descriptors = sampler_count,
                .base_shader_register = 0,
                .register_space = register_space,
            };
            range_count += 1;
        }
    }

    if (range_count == 0) return error.InvalidArgument;

    var flags: u32 = ROOT_SIG_FLAG_NONE;
    if (layout.allow_input_assembler) {
        flags |= ROOT_SIG_FLAG_ALLOW_INPUT_ASSEMBLER;
    }

    return d3d12_bridge_device_create_root_signature_with_tables(
        device,
        &ranges,
        range_count,
        flags,
    );
}

/// Set a compute root descriptor table on a command list, pointing into the
/// CBV/SRV/UAV heap at `base_descriptor_index`.
pub fn set_compute_descriptor_table(
    cmd_list: ?*anyopaque,
    root_parameter_index: u32,
    heap: ?*anyopaque,
    base_descriptor_index: u32,
) void {
    d3d12_bridge_command_list_set_compute_root_descriptor_table(
        cmd_list,
        root_parameter_index,
        heap,
        base_descriptor_index,
    );
}

/// Set a graphics root descriptor table on a command list, pointing into the
/// CBV/SRV/UAV heap at `base_descriptor_index`.
pub fn set_graphics_descriptor_table(
    cmd_list: ?*anyopaque,
    root_parameter_index: u32,
    heap: ?*anyopaque,
    base_descriptor_index: u32,
) void {
    d3d12_bridge_command_list_set_graphics_root_descriptor_table(
        cmd_list,
        root_parameter_index,
        heap,
        base_descriptor_index,
    );
}

/// Set a graphics root descriptor table on a command list, pointing into the
/// sampler heap at `base_descriptor_index`. Uses the sampler descriptor
/// increment size, which differs from CBV/SRV/UAV.
pub fn set_graphics_sampler_table(
    cmd_list: ?*anyopaque,
    root_parameter_index: u32,
    sampler_heap: ?*anyopaque,
    base_descriptor_index: u32,
) void {
    d3d12_bridge_command_list_set_graphics_root_sampler_table(
        cmd_list,
        root_parameter_index,
        sampler_heap,
        base_descriptor_index,
    );
}

// --- Alignment helper ---

const CBV_ALIGNMENT: u64 = 256;

/// D3D12 requires constant buffer views to have 256-byte aligned sizes.
fn align_cbv_size(size: u64) u64 {
    return (size + CBV_ALIGNMENT - 1) & ~(CBV_ALIGNMENT - 1);
}

// --- Tests ---

test "align_cbv_size rounds up to 256" {
    try std.testing.expectEqual(@as(u64, 256), align_cbv_size(1));
    try std.testing.expectEqual(@as(u64, 256), align_cbv_size(128));
    try std.testing.expectEqual(@as(u64, 256), align_cbv_size(256));
    try std.testing.expectEqual(@as(u64, 512), align_cbv_size(257));
    try std.testing.expectEqual(@as(u64, 512), align_cbv_size(512));
    try std.testing.expectEqual(@as(u64, 768), align_cbv_size(768));
}

test "DescriptorHeapState starts zeroed" {
    const state = DescriptorHeapState{};
    try std.testing.expect(state.cbv_srv_uav_heap == null);
    try std.testing.expect(state.sampler_heap == null);
    try std.testing.expectEqual(@as(u32, 0), state.cbv_srv_uav_next);
    try std.testing.expectEqual(@as(u32, 0), state.sampler_next);
}

test "reset_allocations zeroes indices but keeps capacity" {
    var state = DescriptorHeapState{
        .cbv_srv_uav_capacity = 256,
        .sampler_capacity = 64,
        .cbv_srv_uav_next = 42,
        .sampler_next = 7,
    };
    state.reset_allocations();
    try std.testing.expectEqual(@as(u32, 0), state.cbv_srv_uav_next);
    try std.testing.expectEqual(@as(u32, 0), state.sampler_next);
    try std.testing.expectEqual(@as(u32, 256), state.cbv_srv_uav_capacity);
    try std.testing.expectEqual(@as(u32, 64), state.sampler_capacity);
}

test "RootSignatureLayout defaults to no groups" {
    const layout = RootSignatureLayout{};
    for (layout.groups) |g| {
        try std.testing.expect(g == null);
    }
    try std.testing.expect(!layout.allow_input_assembler);
}

test "DescriptorRangeDesc extern struct size" {
    // 4 x u32 = 16 bytes, must match C layout
    try std.testing.expectEqual(@as(usize, 16), @sizeOf(DescriptorRangeDesc));
}
