const std = @import("std");
const ast = @import("../frontend/ast.zig");
const parser = @import("../frontend/parser.zig");
const sema = @import("../frontend/sema.zig");
const ir = @import("../ir/ir.zig");

pub const Diagnostic = struct {
    stage: []const u8 = "parser",
    message: []const u8 = "",
    byte_offset: u32 = 0,
};

pub const Result = struct {
    wgsl: []const u8,
    rewrites: u32,

    pub fn deinit(self: Result, allocator: std.mem.Allocator) void {
        allocator.free(self.wgsl);
    }
};

const Edit = struct { start: u32, operator: u32, end: u32, replacement: u32, division: bool };

// Only identifiers and unparenthesized member chains have exact source spans
// here. Calls, indexing, vectors, signed values and abstract integers stay intact.
fn memberToken(tree: *const ast.Ast, node_index: u32) ?u32 {
    const node = tree.nodes.items[node_index];
    return switch (node.tag) {
        .ident_expr => node.main_token,
        .member_expr => memberToken(tree, node.data.lhs),
        else => null,
    };
}

fn isU32(semantic: *const sema.SemanticModule, node_index: u32) bool {
    const ty = semantic.node_info.items[node_index].ty;
    if (ty == ir.INVALID_TYPE) return false;
    return switch (semantic.types.get(ty)) {
        .scalar => |scalar| scalar == .u32,
        else => false,
    };
}

/// Borrows source for this call; result owns its emitted WGSL. Parsing and type
/// admission run in both modes. Browser validation remains the final authority.
pub fn rewrite(allocator: std.mem.Allocator, source: []const u8, enabled: bool, diagnostic: *Diagnostic) !Result {
    diagnostic.* = .{};
    var parse_failure = parser.FailureContext{};
    var tree = parser.parseSourceWithContext(allocator, source, &parse_failure) catch |err| {
        diagnostic.message = @errorName(err);
        diagnostic.byte_offset = if (parse_failure.loc) |loc| loc.start else 0;
        return err;
    };
    defer tree.deinit();
    var sema_failure = sema.FailureContext{};
    var semantic = sema.analyzeWithContext(allocator, &tree, &.{}, &sema_failure) catch |err| {
        diagnostic.stage = "sema";
        diagnostic.message = @errorName(err);
        if (sema_failure.token_idx) |index| diagnostic.byte_offset = tree.tokens.items[index].loc.start;
        return err;
    };
    defer semantic.deinit();
    var edits: std.ArrayList(Edit) = .empty;
    defer edits.deinit(allocator);
    if (enabled) for (tree.nodes.items, 0..) |node, index| {
        if (node.tag != .binary_expr or !isU32(&semantic, @intCast(index))) continue;
        const operator = tree.tokens.items[node.main_token];
        if (operator.tag != .@"/" and operator.tag != .@"%") continue;
        if (!isU32(&semantic, node.data.lhs)) continue;
        const first_token = memberToken(&tree, node.data.lhs) orelse continue;
        const start = tree.tokens.items[first_token].loc.start;
        const rhs = tree.nodes.items[node.data.rhs];
        if (rhs.tag != .int_literal) continue;
        const literal = tree.tokens.items[rhs.main_token];
        const text = literal.slice(source);
        if (text.len < 2 or text[text.len - 1] != 'u') continue;
        const value = std.fmt.parseInt(u32, text[0 .. text.len - 1], 0) catch continue;
        if (value == 0 or !std.math.isPowerOfTwo(value)) continue;
        // Parentheses around either operand are not represented as AST nodes.
        // Admit only the literal token and a contiguous identifier/member chain.
        var contiguous = true;
        for (tree.tokens.items[first_token..node.main_token]) |tok| {
            if (tok.tag != .ident and tok.tag != .@".") contiguous = false;
        }
        if (!contiguous) continue;
        const between = std.mem.trim(u8, source[operator.loc.end..literal.loc.start], " \t\r\n");
        if (between.len != 0) continue;
        try edits.append(allocator, .{
            .start = start,
            .operator = node.main_token,
            .end = literal.loc.end,
            .replacement = if (operator.tag == .@"/") @intCast(@ctz(value)) else value - 1,
            .division = operator.tag == .@"/",
        });
    };
    std.mem.sort(Edit, edits.items, {}, struct {
        fn less(_: void, a: Edit, b: Edit) bool {
            return a.start < b.start;
        }
    }.less);
    var output: std.ArrayList(u8) = .empty;
    errdefer output.deinit(allocator);
    var position: usize = 0;
    for (edits.items) |edit| {
        if (edit.start < position) return error.OverlappingSourceEdits;
        const operator = tree.tokens.items[edit.operator];
        try output.appendSlice(allocator, source[position..edit.start]);
        try output.append(allocator, '(');
        try output.appendSlice(allocator, source[edit.start..operator.loc.start]);
        try output.print(allocator, "{s} {d}u)", .{ if (edit.division) ">>" else "&", edit.replacement });
        position = edit.end;
    }
    try output.appendSlice(allocator, source[position..]);
    return .{ .wgsl = try output.toOwnedSlice(allocator), .rewrites = @intCast(edits.items.len) };
}
