const std = @import("std");

pub fn Registry(comptime Node: type) type {
    return struct {
        const Self = @This();

        pub const Entry = struct {
            next: ?*Entry = null,
            key: u64,
            head: ?*Node = null,
        };

        pub const JoinResult = struct {
            entry: *Entry,
            leader: bool,
        };

        mutex: std.Thread.Mutex = .{},
        head: ?*Entry = null,

        pub fn join_or_create(self: *Self, allocator: std.mem.Allocator, key: u64, node: *Node) !JoinResult {
            self.mutex.lock();
            defer self.mutex.unlock();

            var cursor = self.head;
            while (cursor) |entry| : (cursor = entry.next) {
                if (entry.key != key) continue;
                node.next = entry.head;
                entry.head = node;
                return .{ .entry = entry, .leader = false };
            }

            const entry = try allocator.create(Entry);
            entry.* = .{
                .key = key,
                .head = node,
                .next = self.head,
            };
            self.head = entry;
            return .{ .entry = entry, .leader = true };
        }

        pub fn take(self: *Self, allocator: std.mem.Allocator, entry: *Entry) ?*Node {
            self.mutex.lock();
            defer self.mutex.unlock();

            var cursor = &self.head;
            while (cursor.*) |current| {
                if (current == entry) {
                    cursor.* = current.next;
                    const head = current.head;
                    allocator.destroy(current);
                    return head;
                }
                cursor = &current.next;
            }
            return null;
        }
    };
}
