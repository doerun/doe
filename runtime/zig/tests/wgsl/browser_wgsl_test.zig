const std = @import("std");
const compiler = @import("../../src/compiler/wgsl/emit/wgsl_rewrite.zig");
const rewrite = compiler.rewrite;
const Diagnostic = compiler.Diagnostic;

test "WGSL rewrite preserves precedence, signed operands, overrides and disabled bytes" {
    const source = "override d: u32 = 8u; fn f(x: u32, y: i32) -> u32 { let a = x / 8u * 2u; let b = x % 4u; let c = y / 8i; let e = x / d; return a + b + u32(c) + e; }";
    var diagnostic = Diagnostic{};
    const result = try rewrite(std.testing.allocator, source, true, &diagnostic);
    defer result.deinit(std.testing.allocator);
    try std.testing.expectEqual(2, result.rewrites);
    try std.testing.expect(std.mem.indexOf(u8, result.wgsl, "(x >> 3u) * 2u") != null);
    try std.testing.expect(std.mem.indexOf(u8, result.wgsl, "(x & 3u)") != null);
    try std.testing.expect(std.mem.indexOf(u8, result.wgsl, "y / 8i") != null);
    const disabled = try rewrite(std.testing.allocator, source, false, &diagnostic);
    defer disabled.deinit(std.testing.allocator);
    try std.testing.expectEqualStrings(source, disabled.wgsl);
    const reparsed = try rewrite(std.testing.allocator, result.wgsl, false, &diagnostic);
    reparsed.deinit(std.testing.allocator);
}

test "WGSL rewrite declines ambiguous spans and nonliteral divisors" {
    const source = "fn f(x: u32) -> u32 { return (x) / 8u + x / (8u) + x / 3u + x / 0u + x / 0x80000000u; }";
    var diagnostic = Diagnostic{};
    const result = try rewrite(std.testing.allocator, source, true, &diagnostic);
    defer result.deinit(std.testing.allocator);
    try std.testing.expectEqual(1, result.rewrites);
    try std.testing.expect(std.mem.indexOf(u8, result.wgsl, "(x >> 31u)") != null);
}

test "WGSL rewrite keeps original diagnostic offset" {
    var diagnostic = Diagnostic{};
    try std.testing.expectError(error.UnexpectedToken, rewrite(std.testing.allocator, "fn alias() {}", true, &diagnostic));
    try std.testing.expectEqual(3, diagnostic.byte_offset);
}

test "WGSL rewrite handles member chains without duplicating evaluation" {
    const source = "struct S { value: u32 } fn f(s: S, x: u32) -> u32 { return s.value / 8u + x / 8u / 2u; }";
    var diagnostic = Diagnostic{};
    const result = try rewrite(std.testing.allocator, source, true, &diagnostic);
    defer result.deinit(std.testing.allocator);
    try std.testing.expectEqual(2, result.rewrites);
    try std.testing.expect(std.mem.indexOf(u8, result.wgsl, "(s.value >> 3u)") != null);
    const checked = try rewrite(std.testing.allocator, result.wgsl, false, &diagnostic);
    checked.deinit(std.testing.allocator);
}

test "WGSL rewrite does not depend on whitespace" {
    var diagnostic = Diagnostic{};
    const result = try rewrite(std.testing.allocator, "fn f(x:u32)->u32{return x/8u+x%4u;}", true, &diagnostic);
    defer result.deinit(std.testing.allocator);
    try std.testing.expectEqual(2, result.rewrites);
    const checked = try rewrite(std.testing.allocator, result.wgsl, false, &diagnostic);
    checked.deinit(std.testing.allocator);
}

test "WGSL rewrite cleans up allocation failures" {
    try std.testing.checkAllAllocationFailures(std.testing.allocator, struct {
        fn run(allocator: std.mem.Allocator) !void {
            var diagnostic = Diagnostic{};
            const result = try rewrite(allocator, "fn f(x: u32) -> u32 { return x / 8u; }", true, &diagnostic);
            result.deinit(allocator);
        }
    }.run, .{});
}
