const std = @import("std");

/// Owns keys and storage for one function's straight-line instruction reuse.
/// Opcode eligibility and the points at which these methods run belong to emission.
pub const InstructionCache = struct {
    allocator: std.mem.Allocator,
    access_chains: std.ArrayListUnmanaged(AccessChain) = .{},
    local_loads: std.ArrayListUnmanaged(LocalLoad) = .{},
    results: std.ArrayListUnmanaged(Result) = .{},

    const AccessChain = struct { root: u32, pointer_type: u32, result: u32, indices: []u32 };
    const LocalLoad = struct { local: u32, value: u32 };
    const Result = struct { opcode: u16, result_type: u32, result: u32, operands: []u32 };

    pub fn deinit(self: *InstructionCache) void {
        self.beginBlock();
        self.access_chains.deinit(self.allocator);
        self.local_loads.deinit(self.allocator);
        self.results.deinit(self.allocator);
        self.* = .{ .allocator = self.allocator };
    }

    /// No cached definition is assumed to dominate the next block.
    pub fn beginBlock(self: *InstructionCache) void {
        for (self.access_chains.items) |entry| self.allocator.free(entry.indices);
        self.access_chains.clearRetainingCapacity();
        self.invalidateLoads();
        for (self.results.items) |entry| self.allocator.free(entry.operands);
        self.results.clearRetainingCapacity();
    }

    /// Calls can write through references, but do not change existing SSA IDs.
    pub fn invalidateLoads(self: *InstructionCache) void {
        self.local_loads.clearRetainingCapacity();
    }

    pub fn invalidateLocal(self: *InstructionCache, local: u32) void {
        var i: usize = 0;
        while (i < self.local_loads.items.len) {
            if (self.local_loads.items[i].local == local) {
                _ = self.local_loads.swapRemove(i);
            } else i += 1;
        }
    }

    pub fn findAccessChain(self: *const InstructionCache, root: u32, pointer_type: u32, indices: []const u32) ?u32 {
        for (self.access_chains.items) |entry| {
            if (entry.root == root and entry.pointer_type == pointer_type and std.mem.eql(u32, entry.indices, indices)) return entry.result;
        }
        return null;
    }

    pub fn putAccessChain(self: *InstructionCache, root: u32, pointer_type: u32, result: u32, indices: []const u32) std.mem.Allocator.Error!void {
        const owned = try self.allocator.dupe(u32, indices);
        errdefer self.allocator.free(owned);
        try self.access_chains.append(self.allocator, .{ .root = root, .pointer_type = pointer_type, .result = result, .indices = owned });
    }

    pub fn findLocalLoad(self: *const InstructionCache, local: u32) ?u32 {
        for (self.local_loads.items) |entry| if (entry.local == local) return entry.value;
        return null;
    }

    pub fn putLocalLoad(self: *InstructionCache, local: u32, value: u32) std.mem.Allocator.Error!void {
        try self.local_loads.append(self.allocator, .{ .local = local, .value = value });
    }

    pub fn findResult(self: *const InstructionCache, opcode: u16, result_type: u32, operands: []const u32) ?u32 {
        for (self.results.items) |entry| {
            if (entry.opcode == opcode and entry.result_type == result_type and std.mem.eql(u32, entry.operands, operands)) return entry.result;
        }
        return null;
    }

    pub fn putResult(self: *InstructionCache, opcode: u16, result_type: u32, result: u32, operands: []const u32) std.mem.Allocator.Error!void {
        const owned = try self.allocator.dupe(u32, operands);
        errdefer self.allocator.free(owned);
        try self.results.append(self.allocator, .{ .opcode = opcode, .result_type = result_type, .result = result, .operands = owned });
    }
};

test "instruction cache owns borrowed keys and separates mutation from block invalidation" {
    var cache = InstructionCache{ .allocator = std.testing.allocator };
    defer cache.deinit();
    var indices = [_]u32{ 3, 4 };
    var operands = [_]u32{ 5, 6 };
    try cache.putAccessChain(1, 2, 10, &indices);
    try cache.putResult(7, 8, 11, &operands);
    try cache.putLocalLoad(1, 12);
    try cache.putLocalLoad(2, 13);
    indices[0] = 99;
    operands[0] = 99;
    try std.testing.expectEqual(@as(?u32, 10), cache.findAccessChain(1, 2, &.{ 3, 4 }));
    try std.testing.expectEqual(@as(?u32, null), cache.findAccessChain(1, 3, &.{ 3, 4 }));
    try std.testing.expectEqual(@as(?u32, null), cache.findAccessChain(2, 2, &.{ 3, 4 }));
    try std.testing.expectEqual(@as(?u32, null), cache.findAccessChain(1, 2, &.{ 3, 5 }));
    try std.testing.expectEqual(@as(?u32, null), cache.findResult(8, 8, &.{ 5, 6 }));
    try std.testing.expectEqual(@as(?u32, null), cache.findResult(7, 9, &.{ 5, 6 }));
    cache.invalidateLocal(1);
    try std.testing.expectEqual(@as(?u32, null), cache.findLocalLoad(1));
    try std.testing.expectEqual(@as(?u32, 13), cache.findLocalLoad(2));
    cache.invalidateLoads();
    try std.testing.expectEqual(@as(?u32, null), cache.findLocalLoad(2));
    try std.testing.expectEqual(@as(?u32, 10), cache.findAccessChain(1, 2, &.{ 3, 4 }));
    try std.testing.expectEqual(@as(?u32, 11), cache.findResult(7, 8, &.{ 5, 6 }));
    cache.beginBlock();
    try std.testing.expectEqual(@as(?u32, null), cache.findAccessChain(1, 2, &.{ 3, 4 }));
    try std.testing.expectEqual(@as(?u32, null), cache.findResult(7, 8, &.{ 5, 6 }));
    try cache.putAccessChain(1, 2, 14, &.{ 3, 4 });
    try std.testing.expectEqual(@as(?u32, 14), cache.findAccessChain(1, 2, &.{ 3, 4 }));
}

fn exerciseAllocations(allocator: std.mem.Allocator) !void {
    var cache = InstructionCache{ .allocator = allocator };
    defer cache.deinit();
    for (0..2) |_| {
        for (0..24) |i| {
            const value: u32 = @intCast(i);
            try cache.putAccessChain(value, 2, value, &.{value});
            try cache.putLocalLoad(value, value);
            try cache.putResult(1, 2, value, &.{value});
        }
        cache.beginBlock();
    }
}

test "instruction cache unwinds every key and collection allocation failure" {
    try std.testing.checkAllAllocationFailures(std.testing.allocator, exerciseAllocations, .{});
}
