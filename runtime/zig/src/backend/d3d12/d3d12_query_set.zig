const std = @import("std");

const d3d12_constants = @import("d3d12_constants.zig");

// --- Named constants ---

const HEAP_TYPE_READBACK: c_int = 3;
const NS_PER_SECOND: u64 = 1_000_000_000;

/// D3D12 pipeline statistics produce 11 u64 fields per query slot
/// (IAVertices, IAPrimitives, VSInvocations, GSInvocations, GSPrimitives,
///  CInvocations, CPrimitives, PSInvocations, HSInvocations, DSInvocations,
///  CSInvocations).
const PIPELINE_STATS_FIELDS_PER_QUERY: u32 = 11;

/// Maximum number of query sets a single state tracker will manage.
/// Prevents unbounded growth from leaked handles.
const MAX_QUERY_SETS: u32 = 256;

// --- Bridge externs (timestamp / shared) ---

extern fn d3d12_bridge_device_create_timestamp_query_heap(device: ?*anyopaque, count: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_buffer(device: ?*anyopaque, size: usize, heap_type: c_int) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_allocator(device: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_command_list(device: ?*anyopaque, allocator_h: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_command_list_end_query(cmd_list: ?*anyopaque, query_heap: ?*anyopaque, index: u32) callconv(.c) void;
extern fn d3d12_bridge_command_list_resolve_query_data(cmd_list: ?*anyopaque, query_heap: ?*anyopaque, start_index: u32, count: u32, dst_buffer: ?*anyopaque, dst_offset: u64) callconv(.c) void;
extern fn d3d12_bridge_command_list_close(cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_queue_execute_command_list(queue: ?*anyopaque, cmd_list: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_queue_signal(queue: ?*anyopaque, fence: ?*anyopaque, value: u64) callconv(.c) void;
extern fn d3d12_bridge_fence_wait(fence: ?*anyopaque, value: u64) callconv(.c) void;
extern fn d3d12_bridge_queue_get_timestamp_frequency(queue: ?*anyopaque) callconv(.c) u64;
extern fn d3d12_bridge_resource_map(resource: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_resource_unmap(resource: ?*anyopaque) callconv(.c) void;
extern fn d3d12_bridge_release(obj: ?*anyopaque) callconv(.c) void;

// --- Bridge externs (occlusion + pipeline statistics) ---

extern fn d3d12_bridge_device_create_occlusion_query_heap(device: ?*anyopaque, count: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_device_create_pipeline_statistics_query_heap(device: ?*anyopaque, count: u32) callconv(.c) ?*anyopaque;
extern fn d3d12_bridge_command_list_begin_query(cmd_list: ?*anyopaque, query_heap: ?*anyopaque, index: u32) callconv(.c) void;

// --- Public types ---

pub const QueryType = enum {
    timestamp,
    occlusion,
    pipeline_statistics,
};

pub const QuerySetEntry = struct {
    handle: u64,
    query_type: QueryType,
    count: u32,
    query_heap: ?*anyopaque,
    readback_buffer: ?*anyopaque,
    cmd_allocator: ?*anyopaque,
    cmd_list: ?*anyopaque,
    has_cmd: bool,
    /// GPU timestamp frequency; only meaningful for timestamp query sets
    frequency: u64,
};

/// Manages multiple named query sets, each backed by a D3D12 query heap
/// and a readback buffer for CPU-visible results.
pub const QuerySetState = struct {
    map: std.AutoHashMapUnmanaged(u64, QuerySetEntry) = .{},

    /// Create a new query set of the given type with `count` slots.
    /// Returns the handle on success.
    pub fn create(
        self: *QuerySetState,
        allocator: std.mem.Allocator,
        device: ?*anyopaque,
        queue: ?*anyopaque,
        handle: u64,
        query_type: QueryType,
        count: u32,
    ) !u64 {
        if (count == 0) return error.InvalidArgument;
        if (self.map.count() >= MAX_QUERY_SETS) return error.InvalidState;

        const query_heap = create_query_heap(device, query_type, count) orelse
            return error.UnsupportedFeature;

        const readback_size = readback_byte_count(query_type, count);
        const readback_buffer = d3d12_bridge_device_create_buffer(
            device,
            readback_size,
            HEAP_TYPE_READBACK,
        ) orelse {
            d3d12_bridge_release(query_heap);
            return error.InvalidState;
        };

        const cmd_allocator = d3d12_bridge_device_create_command_allocator(device) orelse {
            d3d12_bridge_release(readback_buffer);
            d3d12_bridge_release(query_heap);
            return error.InvalidState;
        };

        const cmd_list = d3d12_bridge_device_create_command_list(device, cmd_allocator) orelse {
            d3d12_bridge_release(cmd_allocator);
            d3d12_bridge_release(readback_buffer);
            d3d12_bridge_release(query_heap);
            return error.InvalidState;
        };
        d3d12_bridge_command_list_close(cmd_list);

        var frequency: u64 = 0;
        if (query_type == .timestamp) {
            frequency = d3d12_bridge_queue_get_timestamp_frequency(queue);
            if (frequency == 0) frequency = 1;
        }

        try self.map.put(allocator, handle, .{
            .handle = handle,
            .query_type = query_type,
            .count = count,
            .query_heap = query_heap,
            .readback_buffer = readback_buffer,
            .cmd_allocator = cmd_allocator,
            .cmd_list = cmd_list,
            .has_cmd = true,
            .frequency = frequency,
        });

        return handle;
    }

    /// Mark the start of a query at `index` within the query set.
    /// Only valid for occlusion and pipeline_statistics query types.
    /// Timestamp queries use end_query only (D3D12 timestamp queries
    /// record a single point-in-time value, not a begin/end pair).
    pub fn begin_query(
        self: *QuerySetState,
        handle: u64,
        cmd_list: ?*anyopaque,
        index: u32,
    ) !void {
        const entry = self.map.getPtr(handle) orelse return error.InvalidArgument;

        if (index >= entry.count) return error.InvalidArgument;

        switch (entry.query_type) {
            .timestamp => return error.InvalidState,
            .occlusion, .pipeline_statistics => {
                d3d12_bridge_command_list_begin_query(
                    cmd_list,
                    entry.query_heap,
                    index,
                );
            },
        }
    }

    /// End a query at `index`. For timestamp queries this records a single
    /// timestamp tick. For occlusion / pipeline_statistics it closes the
    /// region opened by begin_query.
    pub fn end_query(
        self: *QuerySetState,
        handle: u64,
        cmd_list: ?*anyopaque,
        index: u32,
    ) !void {
        const entry = self.map.getPtr(handle) orelse return error.InvalidArgument;

        if (index >= entry.count) return error.InvalidArgument;

        d3d12_bridge_command_list_end_query(cmd_list, entry.query_heap, index);
    }

    /// Resolve all query results into the readback buffer, execute on the
    /// queue, wait via fence, and return a slice of u64 values.
    ///
    /// For timestamp queries the returned values are raw GPU ticks.
    /// Callers can convert to nanoseconds with `ticks_to_ns`.
    ///
    /// For occlusion queries each slot holds the number of samples that
    /// passed the depth/stencil test (u64).
    ///
    /// For pipeline_statistics queries each slot holds
    /// `PIPELINE_STATS_FIELDS_PER_QUERY` consecutive u64 values.
    pub fn resolve(
        self: *QuerySetState,
        handle: u64,
        device: ?*anyopaque,
        queue: ?*anyopaque,
        fence: ?*anyopaque,
        fence_value: *u64,
    ) ![]const u64 {
        _ = device;
        const entry = self.map.getPtr(handle) orelse return error.InvalidArgument;
        if (entry.query_heap == null or entry.readback_buffer == null) return error.InvalidState;

        // Resolve query data into the readback buffer
        d3d12_bridge_command_list_resolve_query_data(
            entry.cmd_list,
            entry.query_heap,
            0,
            entry.count,
            entry.readback_buffer,
            0,
        );
        d3d12_bridge_command_list_close(entry.cmd_list);

        // Execute and wait
        d3d12_bridge_queue_execute_command_list(queue, entry.cmd_list);
        fence_value.* += 1;
        d3d12_bridge_queue_signal(queue, fence, fence_value.*);
        d3d12_bridge_fence_wait(fence, fence_value.*);

        // Map and return results
        const mapped = d3d12_bridge_resource_map(entry.readback_buffer) orelse
            return error.InvalidState;

        const element_count = readback_u64_count(entry.query_type, entry.count);
        const results: [*]const u64 = @ptrCast(@alignCast(mapped));
        return results[0..element_count];
    }

    /// Unmap the readback buffer after the caller has consumed the resolve
    /// results. Must be called after each successful resolve before the
    /// next resolve or destroy.
    pub fn unmap_readback(self: *QuerySetState, handle: u64) void {
        const entry = self.map.getPtr(handle) orelse return;
        if (entry.readback_buffer) |buf| {
            d3d12_bridge_resource_unmap(buf);
        }
    }

    /// Convert raw GPU ticks to nanoseconds using the frequency stored
    /// in the query set entry. Returns 0 when frequency is unavailable.
    pub fn ticks_to_ns(self: *QuerySetState, handle: u64, ticks: u64) u64 {
        const entry = self.map.getPtr(handle) orelse return 0;
        if (entry.frequency == 0) return 0;
        return ticks * NS_PER_SECOND / entry.frequency;
    }

    /// Release all D3D12 resources for a single query set and remove it
    /// from the map.
    pub fn destroy(self: *QuerySetState, handle: u64) void {
        const entry = self.map.get(handle) orelse return;
        release_entry_resources(entry);
        _ = self.map.remove(handle);
    }

    /// Release all tracked query sets and free the backing hash map.
    pub fn deinit(self: *QuerySetState, allocator: std.mem.Allocator) void {
        var it = self.map.iterator();
        while (it.next()) |kv| {
            release_entry_resources(kv.value_ptr.*);
        }
        self.map.deinit(allocator);
        self.* = .{};
    }
};

// --- Private helpers ---

fn create_query_heap(device: ?*anyopaque, query_type: QueryType, count: u32) ?*anyopaque {
    return switch (query_type) {
        .timestamp => d3d12_bridge_device_create_timestamp_query_heap(device, count),
        .occlusion => d3d12_bridge_device_create_occlusion_query_heap(device, count),
        .pipeline_statistics => d3d12_bridge_device_create_pipeline_statistics_query_heap(device, count),
    };
}

/// Compute the readback buffer size in bytes for a given query type and count.
fn readback_byte_count(query_type: QueryType, count: u32) usize {
    return readback_u64_count(query_type, count) * @sizeOf(u64);
}

/// Number of u64 elements in the readback buffer.
fn readback_u64_count(query_type: QueryType, count: u32) usize {
    return switch (query_type) {
        .timestamp, .occlusion => @as(usize, count),
        .pipeline_statistics => @as(usize, count) * PIPELINE_STATS_FIELDS_PER_QUERY,
    };
}

fn release_entry_resources(entry: QuerySetEntry) void {
    if (entry.has_cmd) {
        if (entry.cmd_list) |cl| d3d12_bridge_release(cl);
        if (entry.cmd_allocator) |ca| d3d12_bridge_release(ca);
    }
    if (entry.readback_buffer) |buf| d3d12_bridge_release(buf);
    if (entry.query_heap) |heap| d3d12_bridge_release(heap);
}
