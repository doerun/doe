const std = @import("std");

pub const SHA256_HEX_SIZE: usize = 64;

const HEX = "0123456789abcdef";

pub fn sha256_hex(input: []const u8) [SHA256_HEX_SIZE]u8 {
    var output: [SHA256_HEX_SIZE]u8 = undefined;
    var digest: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(input, &digest, .{});
    for (digest, 0..) |byte, index| {
        const output_index = index * 2;
        output[output_index] = HEX[(byte >> 4) & 0x0F];
        output[output_index + 1] = HEX[byte & 0x0F];
    }
    return output;
}

test "SHA256_HEX_SIZE equals 64" {
    try std.testing.expectEqual(@as(usize, 64), SHA256_HEX_SIZE);
}

test "sha256_hex produces 64 hex chars" {
    const result = sha256_hex("hello");
    try std.testing.expectEqual(@as(usize, 64), result.len);
    for (result) |c| {
        try std.testing.expect((c >= '0' and c <= '9') or (c >= 'a' and c <= 'f'));
    }
}

test "sha256_hex is deterministic" {
    const a = sha256_hex("deterministic input");
    const b = sha256_hex("deterministic input");
    try std.testing.expectEqual(a, b);
}

test "sha256_hex produces different output for different inputs" {
    const a = sha256_hex("input one");
    const b = sha256_hex("input two");
    try std.testing.expect(!std.mem.eql(u8, &a, &b));
}
