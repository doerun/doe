const std = @import("std");
pub const c = @cImport({
    @cInclude("dawn/dawn_proc_table.h");
});
const wrappers = @import("proc_wrappers.zig");

// ONNX's dawnProcSetProcs binds once per process. This module has the same owner.
var library: ?std.DynLib = null;
var initialization_mutex: std.Thread.Mutex = .{};
pub var native_table: c.DawnProcTable = std.mem.zeroes(c.DawnProcTable);
var bridge_table: c.DawnProcTable = std.mem.zeroes(c.DawnProcTable);
var calls: [@typeInfo(c.DawnProcTable).@"struct".fields.len]std.atomic.Value(u64) =
    @splat(std.atomic.Value(u64).init(0));

/// Publish only after loading the caller-selected library. Never replace a live table.
pub export fn doeDawnBridgeInitialize(path: [*:0]const u8) callconv(.c) ?*const c.DawnProcTable {
    initialization_mutex.lock();
    defer initialization_mutex.unlock();
    if (library != null) return null;
    var selected = std.DynLib.open(std.mem.span(path)) catch return null;
    inline for (@typeInfo(c.DawnProcTable).@"struct".fields) |field| {
        const symbol = "wgpu" ++ .{std.ascii.toUpper(field.name[0])} ++ field.name[1..];
        @field(native_table, field.name) = selected.lookup(@typeInfo(field.type).optional.child, symbol);
        @field(bridge_table, field.name) = @field(wrappers, field.name);
    }
    if (native_table.createInstance == null or native_table.queueSubmit == null or
        native_table.deviceCreateShaderModule == null)
    {
        selected.close();
        native_table = std.mem.zeroes(c.DawnProcTable);
        return null;
    }
    library = selected;
    return &bridge_table;
}

pub export fn doeDawnBridgeCallCount(index: usize) callconv(.c) u64 {
    if (index >= calls.len) return 0;
    return calls[index].load(.monotonic);
}

pub export fn doeDawnBridgeProcCount() callconv(.c) usize {
    return calls.len;
}

pub fn invoke(comptime field: []const u8, args: anytype) Return(field) {
    const fields = @typeInfo(c.DawnProcTable).@"struct".fields;
    const index = comptime blk: {
        for (fields, 0..) |entry, i| {
            if (std.mem.eql(u8, entry.name, field)) break :blk i;
        }
        @compileError("Unknown Dawn proc");
    };
    _ = calls[index].fetchAdd(1, .monotonic);
    if (!wrappers.isStandard(field)) @panic("UnsupportedDawnProc: " ++ field);
    inline for (args) |arg| checkDescriptor(field, arg);
    const proc = @field(native_table, field) orelse
        @panic("MissingDoeNativeProc: " ++ field);
    return @call(.auto, proc, args);
}

pub fn Return(comptime field: []const u8) type {
    const pointer = @typeInfo(@FieldType(c.DawnProcTable, field)).optional.child;
    return @typeInfo(@typeInfo(pointer).pointer.child).@"fn".return_type.?;
}

fn checkDescriptor(comptime field: []const u8, arg: anytype) void {
    const arg_info = @typeInfo(@TypeOf(arg));
    if (arg_info == .@"struct") {
        if (@hasField(@TypeOf(arg), "nextInChain") and arg.nextInChain != null)
            @panic("UnsupportedDawnCallbackChain: " ++ field);
        return;
    }
    if (arg_info != .pointer) return;
    const child = arg_info.pointer.child;
    if (@typeInfo(child) != .@"struct" or !@hasField(child, "nextInChain")) return;
    if (comptime arg_info.pointer.size == .c) {
        if (arg == null) return;
    }
    if (comptime @hasField(child, "entries") and @hasField(child, "entryCount")) {
        for (arg.*.entries[0..arg.*.entryCount]) |entry| checkDescriptor(field, &entry);
    }
    const chain = arg.*.nextInChain;
    if (chain == null) return;
    if (comptime std.mem.eql(u8, field, "deviceCreateShaderModule")) {
        if (chain.*.sType == c.WGPUSType_ShaderSourceWGSL and chain.*.next == null) return;
    }
    @panic("UnsupportedDawnDescriptorChain: " ++ field);
}
