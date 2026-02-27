const std = @import("std");

pub const MAX_DIAGNOSTIC_RECORDS = 32;
pub const MAX_SYMBOL_BYTES = 128;
pub const MAX_OWNER_BYTES = 24;

pub const DropinDiagnostics = struct {
    symbol: []const u8,
    owner: []const u8,
    resolved: bool,
    fallback_used: bool,
};

const DiagnosticRecord = struct {
    symbol: [MAX_SYMBOL_BYTES]u8 = .{0} ** MAX_SYMBOL_BYTES,
    owner: [MAX_OWNER_BYTES]u8 = .{0} ** MAX_OWNER_BYTES,
    symbol_len: u8 = 0,
    owner_len: u8 = 0,
    resolved: bool = false,
    fallback_used: bool = false,
};

var g_lock: std.Thread.Mutex = .{};
var g_records: [MAX_DIAGNOSTIC_RECORDS]DiagnosticRecord = [_]DiagnosticRecord{.{}} ** MAX_DIAGNOSTIC_RECORDS;
var g_next_index: usize = 0;
var g_record_count: usize = 0;

fn write_text_into_slot(
    destination: []u8,
    text: []const u8,
) void {
    const copy_len = @min(text.len, destination.len);
    @memcpy(destination[0..copy_len], text[0..copy_len]);
    for (destination[copy_len..]) |*value| {
        value.* = 0;
    }
}

pub fn clear() void {
    g_lock.lock();
    defer g_lock.unlock();
    g_next_index = 0;
    g_record_count = 0;
}

pub fn record(
    symbol: []const u8,
    owner: []const u8,
    resolved: bool,
    fallback_used: bool,
) void {
    g_lock.lock();
    defer g_lock.unlock();

    const index = g_next_index % MAX_DIAGNOSTIC_RECORDS;
    g_next_index += 1;
    g_record_count = @min(g_record_count + 1, MAX_DIAGNOSTIC_RECORDS);

    write_text_into_slot(g_records[index].symbol[0..], symbol);
    write_text_into_slot(g_records[index].owner[0..], owner);
    g_records[index].symbol_len = @as(u8, @min(symbol.len, MAX_SYMBOL_BYTES));
    g_records[index].owner_len = @as(u8, @min(owner.len, MAX_OWNER_BYTES));
    g_records[index].resolved = resolved;
    g_records[index].fallback_used = fallback_used;
}

pub fn snapshot(out: []DropinDiagnostics) usize {
    g_lock.lock();
    defer g_lock.unlock();

    const record_count = @min(g_record_count, MAX_DIAGNOSTIC_RECORDS);
    const max_out = @min(out.len, record_count);
    const first = if (g_record_count < MAX_DIAGNOSTIC_RECORDS) 0 else (g_next_index % MAX_DIAGNOSTIC_RECORDS);
    var cursor = first;
    var written: usize = 0;

    while (written < max_out) : (written += 1) {
        const record = g_records[cursor];
        const symbol_len = @as(usize, record.symbol_len);
        const owner_len = @as(usize, record.owner_len);
        out[written] = .{
            .symbol = record.symbol[0..symbol_len],
            .owner = record.owner[0..owner_len],
            .resolved = record.resolved,
            .fallback_used = record.fallback_used,
        };
        cursor = (cursor + 1) % MAX_DIAGNOSTIC_RECORDS;
    }
    return written;
}
