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
