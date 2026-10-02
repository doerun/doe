const std = @import("std");
const ir = @import("../ir/ir.zig");

pub const ApplyError = error{ UnknownIdentifier, InvalidType };

pub fn diagnosticDetail(err: ApplyError) []const u8 {
    return switch (err) {
        error.UnknownIdentifier => "unknown pipeline override constant",
        error.InvalidType => "pipeline override value cannot be converted to its declared type",
    };
}

pub fn applyOverrides(module: *ir.Module, overrides: []const ir.OverrideEntry) ApplyError!void {
    for (overrides) |entry| {
        // A declaration with @id is addressed only by its canonical decimal ID.
        const numeric_id = std.fmt.parseInt(u32, entry.key, 10) catch null;
        var numeric_buffer: [10]u8 = undefined;
        if (numeric_id) |id| {
            const canonical = std.fmt.bufPrint(&numeric_buffer, "{d}", .{id}) catch unreachable;
            if (!std.mem.eql(u8, canonical, entry.key)) return error.UnknownIdentifier;
        }
        var applied = false;
        for (module.globals.items) |*global| {
            if (global.class != .override_) continue;
            const matched = if (numeric_id) |id|
                (global.override_id != null and global.override_id.? == id)
            else
                (global.override_id == null and std.mem.eql(u8, global.name, entry.key));
            if (!matched) continue;
            // Replace the initializer with the override value.
            const scalar_type = switch (module.types.get(global.ty)) {
                .scalar => |s| s,
                else => continue,
            };
            if (!std.math.isFinite(entry.value)) return error.InvalidType;
            global.initializer = switch (scalar_type) {
                .bool => .{ .bool = entry.value != 0.0 },
                .i32 => .{ .int = @bitCast(@as(i64, @intFromFloat(try integerValue(entry.value, std.math.minInt(i32), std.math.maxInt(i32))))) },
                .abstract_int => .{ .int = @bitCast(@as(i64, @intFromFloat(try integerValue(entry.value, std.math.minInt(i64), std.math.maxInt(i64))))) },
                .u32 => .{ .int = @intFromFloat(try integerValue(entry.value, 0, std.math.maxInt(u32))) },
                .f32, .f16, .abstract_float => .{ .float = entry.value },
                else => continue,
            };
            // Demote to const so emitter outputs a fixed constant.
            global.class = .const_;
            applied = true;
            break;
        }
        if (!applied) return error.UnknownIdentifier;
    }
}

fn integerValue(value: f64, min: anytype, max: anytype) ApplyError!f64 {
    if (@floor(value) != value or value < @as(f64, @floatFromInt(min)) or value >= @as(f64, @floatFromInt(max)) + 1.0) return error.InvalidType;
    return value;
}
