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
threadlocal var last_error: ?[*:0]const u8 = null;
var calls: [@typeInfo(c.DawnProcTable).@"struct".fields.len]std.atomic.Value(u64) =
    @splat(std.atomic.Value(u64).init(0));

/// Publish only after loading the caller-selected library. Never replace a live table.
pub export fn doeDawnBridgeInitialize(path: [*:0]const u8) callconv(.c) ?*const c.DawnProcTable {
    return initialize(path, false);
}

/// Explicit pinned source-built incumbent arm, with identical bridge observations.
pub export fn doeDawnBridgeInitializeControl(path: [*:0]const u8) callconv(.c) ?*const c.DawnProcTable {
    return initialize(path, true);
}

fn initialize(path: [*:0]const u8, source_control: bool) ?*const c.DawnProcTable {
    initialization_mutex.lock();
    defer initialization_mutex.unlock();
    last_error = null;
    if (library != null) {
        last_error = "DoeBridgeAlreadyInitialized";
        return null;
    }
    var selected = std.DynLib.open(std.mem.span(path)) catch {
        last_error = "DoeBridgeLibraryOpenFailed";
        return null;
    };
    if (source_control) {
        const get_table = selected.lookup(*const fn () callconv(.c) *const c.DawnProcTable, "doeDawnControlGetProcs") orelse {
            selected.close();
            last_error = "DoeBridgeControlTableMissing";
            return null;
        };
        native_table = get_table().*;
    } else {
        inline for (@typeInfo(c.DawnProcTable).@"struct".fields) |field| {
            const symbol = "wgpu" ++ .{std.ascii.toUpper(field.name[0])} ++ field.name[1..];
            @field(native_table, field.name) = selected.lookup(@typeInfo(field.type).optional.child, symbol);
        }
    }
    inline for (@typeInfo(c.DawnProcTable).@"struct".fields) |field| {
        @field(bridge_table, field.name) = @field(wrappers, field.name);
    }
    if (native_table.createInstance == null or native_table.queueSubmit == null or
        native_table.deviceCreateShaderModule == null)
    {
        selected.close();
        native_table = std.mem.zeroes(c.DawnProcTable);
        bridge_table = std.mem.zeroes(c.DawnProcTable);
        last_error = "DoeBridgeRequiredProcMissing";
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

/// Static storage; calling thread consumes the preceding rejection diagnostic.
pub export fn doeDawnBridgeTakeError() callconv(.c) ?[*:0]const u8 {
    const message = last_error;
    last_error = null;
    return message;
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
    last_error = null;
    if (!wrappers.isStandard(field)) return reject(field, "UnsupportedDawnProc: " ++ field);
    inline for (args) |arg| {
        if (!descriptorSupported(field, arg))
            return reject(field, "UnsupportedDawnDescriptorChain: " ++ field);
    }
    const proc = @field(native_table, field) orelse
        return reject(field, "MissingDoeNativeProc: " ++ field);
    return @call(.auto, proc, args);
}

fn reject(comptime field: []const u8, comptime message: [:0]const u8) Return(field) {
    last_error = message.ptr;
    const info = @typeInfo(Return(field));
    if (comptime info == .optional) {
        if (comptime @typeInfo(info.optional.child) == .pointer) return null;
    }
    if (comptime info == .pointer and info.pointer.size == .c) return null;
    if (comptime wrappers.isStatus(field)) return c.WGPUStatus_Error;
    if (comptime std.mem.eql(u8, field, "instanceWaitAny")) return c.WGPUWaitStatus_Error;
    // Void, boolean and future APIs have no interchangeable error sentinel.
    // Do not fabricate a completed callback or silently drop submitted work.
    @panic(message);
}

pub fn Return(comptime field: []const u8) type {
    const pointer = @typeInfo(@FieldType(c.DawnProcTable, field)).optional.child;
    return @typeInfo(@typeInfo(pointer).pointer.child).@"fn".return_type.?;
}

fn descriptorSupported(comptime field: []const u8, arg: anytype) bool {
    const arg_info = @typeInfo(@TypeOf(arg));
    if (arg_info == .@"struct") {
        if (@hasField(@TypeOf(arg), "nextInChain") and arg.nextInChain != null) return false;
        return true;
    }
    if (arg_info != .pointer) return true;
    const child = arg_info.pointer.child;
    if (@typeInfo(child) != .@"struct" or !@hasField(child, "nextInChain")) return true;
    if (comptime arg_info.pointer.size == .c) {
        if (arg == null) return true;
    }
    if (comptime @hasField(child, "entries") and @hasField(child, "entryCount")) {
        for (arg.*.entries[0..arg.*.entryCount]) |entry| {
            if (!descriptorSupported(field, &entry)) return false;
        }
    }
    const chain = arg.*.nextInChain;
    if (chain == null) return true;
    if (comptime std.mem.eql(u8, field, "deviceCreateShaderModule")) {
        if (chain.*.sType == c.WGPUSType_ShaderSourceWGSL and chain.*.next == null) return true;
    }
    return false;
}
