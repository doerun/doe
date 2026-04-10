const std = @import("std");
const byte_scan = @import("runtime/simd/byte_scan.zig");

pub fn writef(writer: anytype, comptime format: []const u8, args: anytype) !void {
    try writer.print(format, args);
}

pub fn writeJsonString(writer: anytype, value: []const u8) !void {
    try writer.writeByte('"');
    var start: usize = 0;
    while (start < value.len) {
        const next_escape = byte_scan.findFirstJsonEscapeOrControl(value[start..]) orelse {
            try writer.writeAll(value[start..]);
            break;
        };
        const escape_index = start + next_escape;
        if (escape_index > start) {
            try writer.writeAll(value[start..escape_index]);
        }
        const byte = value[escape_index];
        switch (byte) {
            '"' => try writer.writeAll("\\\""),
            '\\' => try writer.writeAll("\\\\"),
            '\n' => try writer.writeAll("\\n"),
            '\r' => try writer.writeAll("\\r"),
            '\t' => try writer.writeAll("\\t"),
            0...8, 11...12, 14...31 => try writef(writer, "\\u00{x:0>2}", .{byte}),
            else => try writer.writeByte(byte),
        }
        start = escape_index + 1;
    }
    try writer.writeByte('"');
}

pub fn normalizeExecutionStatusCode(
    message: []const u8,
    fallback: []const u8,
    buffer: *[160]u8,
) []const u8 {
    const source = if (message.len > 0) message else fallback;
    var out_len: usize = 0;
    var last_was_separator = true;

    var index: usize = 0;
    while (index < source.len) {
        const alnum_run = byte_scan.countLeadingAlnum(source[index..]);
        if (alnum_run > 0) {
            var run_index: usize = 0;
            while (run_index < alnum_run and out_len < buffer.len) : (run_index += 1) {
                buffer[out_len] = std.ascii.toLower(source[index + run_index]);
                out_len += 1;
            }
            last_was_separator = false;
            index += alnum_run;
            continue;
        }
        if (!last_was_separator and out_len < buffer.len) {
            buffer[out_len] = '_';
            out_len += 1;
            last_was_separator = true;
        }
        index += 1;
        while (index < source.len and byte_scan.countLeadingAlnum(source[index .. index + 1]) == 0) : (index += 1) {}
        if (out_len >= buffer.len) break;
    }

    while (out_len > 0 and buffer[out_len - 1] == '_') {
        out_len -= 1;
    }

    if (out_len == 0) {
        const fallback_len = @min(fallback.len, buffer.len);
        std.mem.copyForwards(u8, buffer[0..fallback_len], fallback[0..fallback_len]);
        return buffer[0..fallback_len];
    }
    return buffer[0..out_len];
}
