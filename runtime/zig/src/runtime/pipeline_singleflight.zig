const std = @import("std");

const DEFAULT_ENTRY_CAPACITY: usize = 64;

pub fn Registry(comptime Node: type) type {
    comptime {
        if (!@hasField(Node, "next")) {
            @compileError("pipeline_singleflight.Registry requires Node.next for wait-list reconstruction");
        }
    }

    return struct {
        const Self = @This();

        pub const Entry = struct {
            in_use: bool = false,
            key: u64 = 0,
            head: ?*Node = null,
            tail: ?*Node = null,
        };

        pub const JoinResult = struct {
            entry: *Entry,
            leader: bool,
        };

        allocator: std.mem.Allocator,
        mutex: std.Thread.Mutex = .{},
        entries: []Entry = &.{},

        pub fn init(allocator: std.mem.Allocator) Self {
            return .{ .allocator = allocator };
        }

        pub fn deinit(self: *Self) void {
            if (self.entries.len > 0) {
                self.allocator.free(self.entries);
            }
            self.entries = &.{};
        }

        fn appendWaiter(entry: *Entry, node: *Node) void {
            @field(node, "next") = null;
            if (entry.tail) |tail| {
                @field(tail, "next") = node;
            } else {
                entry.head = node;
            }
            entry.tail = node;
        }

        fn ensureEntryStorage(self: *Self) !void {
            if (self.entries.len > 0) return;
            self.entries = try self.allocator.alloc(Entry, DEFAULT_ENTRY_CAPACITY);
            for (self.entries) |*entry| {
                entry.* = .{};
            }
        }

        pub fn join_or_create(self: *Self, key: u64, node: *Node) !JoinResult {
            self.mutex.lock();
            defer self.mutex.unlock();

            try self.ensureEntryStorage();

            for (self.entries) |*entry| {
                if (!entry.in_use or entry.key != key) continue;
                appendWaiter(entry, node);
                return .{ .entry = entry, .leader = false };
            }

            for (self.entries) |*entry| {
                if (entry.in_use) continue;
                entry.* = .{
                    .in_use = true,
                    .key = key,
                };
                appendWaiter(entry, node);
                return .{ .entry = entry, .leader = true };
            }
            return error.RegistryFull;
        }

        pub fn take(self: *Self, entry: *Entry) ?*Node {
            self.mutex.lock();
            defer self.mutex.unlock();

            if (!entry.in_use or entry.head == null) return null;

            const head = entry.head;
            entry.head = null;
            entry.tail = null;
            entry.in_use = false;
            return head;
        }
    };
}

const TestNode = struct {
    next: ?*TestNode = null,
    id: u32,
};

test "singleflight registry can join take deinit and recreate" {
    const testing = std.testing;
    const TestRegistry = Registry(TestNode);

    var registry = TestRegistry.init(testing.allocator);
    defer registry.deinit();

    var first = TestNode{ .id = 1 };
    var second = TestNode{ .id = 2 };

    const leader = try registry.join_or_create(7, &first);
    try testing.expect(leader.leader);
    const follower = try registry.join_or_create(7, &second);
    try testing.expect(!follower.leader);

    const head = registry.take(leader.entry).?;
    try testing.expectEqual(@as(u32, 1), head.id);
    try testing.expectEqual(@as(u32, 2), head.next.?.id);

    registry.deinit();
    registry = TestRegistry.init(testing.allocator);

    var third = TestNode{ .id = 3 };
    const recreated = try registry.join_or_create(9, &third);
    try testing.expect(recreated.leader);
    try testing.expectEqual(@as(u32, 3), registry.take(recreated.entry).?.id);
}
