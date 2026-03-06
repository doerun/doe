// doe_wgsl/lexer.zig — WGSL tokenizer.

const std = @import("std");
const token = @import("token.zig");
const Token = token.Token;
const Tag = token.Tag;

pub const Lexer = struct {
    source: []const u8,
    pos: u32,

    pub fn init(source: []const u8) Lexer {
        return .{ .source = source, .pos = 0 };
    }

    pub fn next(self: *Lexer) Token {
        self.skipWhitespaceAndComments();
        const start = self.pos;
        if (start >= self.source.len) {
            return .{ .tag = .eof, .loc = .{ .start = start, .end = start } };
        }
        const c = self.source[start];

        // Single-char tokens that can't start a compound.
        switch (c) {
            '(' => return self.single(.@"("),
            ')' => return self.single(.@")"),
            '{' => return self.single(.@"{"),
            '}' => return self.single(.@"}"),
            '[' => return self.single(.@"["),
            ']' => return self.single(.@"]"),
            ';' => return self.single(.@";"),
            ':' => return self.single(.@":"),
            ',' => return self.single(.@","),
            '.' => return self.single(.@"."),
            '@' => return self.single(.@"@"),
            '~' => return self.single(.@"~"),
            else => {},
        }

        // Compound or single-char operators.
        switch (c) {
            '+' => return self.compoundOrSingle('=', .plus_eq, .@"+"),
            '*' => return self.compoundOrSingle('=', .star_eq, .@"*"),
            '%' => return self.compoundOrSingle('=', .percent_eq, .@"%"),
            '^' => return self.compoundOrSingle('=', .caret_eq, .@"^"),
            '-' => {
                if (self.peek(1) == '>') return self.double(.arrow);
                if (self.peek(1) == '=') return self.double(.minus_eq);
                return self.single(.@"-");
            },
            '/' => {
                if (self.peek(1) == '=') return self.double(.slash_eq);
                return self.single(.@"/");
            },
            '&' => {
                if (self.peek(1) == '&') return self.double(.and_and);
                if (self.peek(1) == '=') return self.double(.amp_eq);
                return self.single(.@"&");
            },
            '|' => {
                if (self.peek(1) == '|') return self.double(.or_or);
                if (self.peek(1) == '=') return self.double(.pipe_eq);
                return self.single(.@"|");
            },
            '<' => {
                if (self.peek(1) == '<') return self.double(.shift_left);
                if (self.peek(1) == '=') return self.double(.lte);
                return self.single(.@"<");
            },
            '>' => {
                if (self.peek(1) == '>') return self.double(.shift_right);
                if (self.peek(1) == '=') return self.double(.gte);
                return self.single(.@">");
            },
            '=' => {
                if (self.peek(1) == '=') return self.double(.eq_eq);
                return self.single(.@"=");
            },
            '!' => {
                if (self.peek(1) == '=') return self.double(.not_eq);
                return self.single(.@"!");
            },
            else => {},
        }

        // Number literals.
        if (isDigit(c) or (c == '.' and self.pos + 1 < self.source.len and isDigit(self.source[self.pos + 1]))) {
            return self.lexNumber();
        }

        // Identifiers and keywords.
        if (isIdentStart(c)) {
            return self.lexIdent();
        }

        // Unknown character.
        self.pos += 1;
        return .{ .tag = .invalid, .loc = .{ .start = start, .end = self.pos } };
    }

    fn single(self: *Lexer, tag: Tag) Token {
        const start = self.pos;
        self.pos += 1;
        return .{ .tag = tag, .loc = .{ .start = start, .end = self.pos } };
    }

    fn double(self: *Lexer, tag: Tag) Token {
        const start = self.pos;
        self.pos += 2;
        return .{ .tag = tag, .loc = .{ .start = start, .end = self.pos } };
    }

    fn compoundOrSingle(self: *Lexer, next_char: u8, compound: Tag, simple: Tag) Token {
        if (self.peek(1) == next_char) return self.double(compound);
        return self.single(simple);
    }

    fn peek(self: *const Lexer, offset: u32) u8 {
        const idx = self.pos + offset;
        if (idx >= self.source.len) return 0;
        return self.source[idx];
    }

    fn skipWhitespaceAndComments(self: *Lexer) void {
        while (self.pos < self.source.len) {
            const c = self.source[self.pos];
            if (c == ' ' or c == '\t' or c == '\n' or c == '\r') {
                self.pos += 1;
                continue;
            }
            // Line comment.
            if (c == '/' and self.pos + 1 < self.source.len and self.source[self.pos + 1] == '/') {
                while (self.pos < self.source.len and self.source[self.pos] != '\n') {
                    self.pos += 1;
                }
                continue;
            }
            // Block comment (nestable per WGSL spec).
            if (c == '/' and self.pos + 1 < self.source.len and self.source[self.pos + 1] == '*') {
                self.pos += 2;
                var depth: u32 = 1;
                while (depth > 0 and self.pos + 1 < self.source.len) {
                    if (self.source[self.pos] == '/' and self.source[self.pos + 1] == '*') {
                        depth += 1;
                        self.pos += 2;
                    } else if (self.source[self.pos] == '*' and self.source[self.pos + 1] == '/') {
                        depth -= 1;
                        self.pos += 2;
                    } else {
                        self.pos += 1;
                    }
                }
                continue;
            }
            break;
        }
    }

    fn lexNumber(self: *Lexer) Token {
        const start = self.pos;
        var is_float = false;

        // Hex prefix.
        if (self.source[self.pos] == '0' and self.pos + 1 < self.source.len and
            (self.source[self.pos + 1] == 'x' or self.source[self.pos + 1] == 'X'))
        {
            self.pos += 2;
            while (self.pos < self.source.len and isHexDigit(self.source[self.pos])) {
                self.pos += 1;
            }
            // Hex float (0x...p...).
            if (self.pos < self.source.len and (self.source[self.pos] == 'p' or self.source[self.pos] == 'P')) {
                is_float = true;
                self.pos += 1;
                if (self.pos < self.source.len and (self.source[self.pos] == '+' or self.source[self.pos] == '-')) {
                    self.pos += 1;
                }
                while (self.pos < self.source.len and isDigit(self.source[self.pos])) {
                    self.pos += 1;
                }
            }
            // Suffix.
            self.skipNumericSuffix();
            return .{ .tag = if (is_float) .float_literal else .int_literal, .loc = .{ .start = start, .end = self.pos } };
        }

        // Decimal.
        while (self.pos < self.source.len and isDigit(self.source[self.pos])) {
            self.pos += 1;
        }
        if (self.pos < self.source.len and self.source[self.pos] == '.') {
            // Check it's not a member access like array.len — only treat as float if followed by digit or end-of-number context.
            if (self.pos + 1 < self.source.len and isDigit(self.source[self.pos + 1])) {
                is_float = true;
                self.pos += 1;
                while (self.pos < self.source.len and isDigit(self.source[self.pos])) {
                    self.pos += 1;
                }
            } else if (self.pos + 1 >= self.source.len or !isIdentStart(self.source[self.pos + 1])) {
                is_float = true;
                self.pos += 1;
            }
        }
        // Exponent.
        if (self.pos < self.source.len and (self.source[self.pos] == 'e' or self.source[self.pos] == 'E')) {
            is_float = true;
            self.pos += 1;
            if (self.pos < self.source.len and (self.source[self.pos] == '+' or self.source[self.pos] == '-')) {
                self.pos += 1;
            }
            while (self.pos < self.source.len and isDigit(self.source[self.pos])) {
                self.pos += 1;
            }
        }
        self.skipNumericSuffix();
        return .{ .tag = if (is_float) .float_literal else .int_literal, .loc = .{ .start = start, .end = self.pos } };
    }

    fn skipNumericSuffix(self: *Lexer) void {
        // WGSL allows i, u, f, h suffixes on numeric literals.
        if (self.pos < self.source.len) {
            const c = self.source[self.pos];
            if (c == 'i' or c == 'u' or c == 'f' or c == 'h') {
                self.pos += 1;
            }
        }
    }

    fn lexIdent(self: *Lexer) Token {
        const start = self.pos;
        while (self.pos < self.source.len and isIdentContinue(self.source[self.pos])) {
            self.pos += 1;
        }
        const ident = self.source[start..self.pos];
        const tag = token.lookupIdent(ident);
        return .{ .tag = tag, .loc = .{ .start = start, .end = self.pos } };
    }
};

fn isDigit(c: u8) bool {
    return c >= '0' and c <= '9';
}

fn isHexDigit(c: u8) bool {
    return isDigit(c) or (c >= 'a' and c <= 'f') or (c >= 'A' and c <= 'F');
}

fn isIdentStart(c: u8) bool {
    return (c >= 'a' and c <= 'z') or (c >= 'A' and c <= 'Z') or c == '_';
}

fn isIdentContinue(c: u8) bool {
    return isIdentStart(c) or isDigit(c);
}

// ============================================================
// Tests
// ============================================================

test "lex simple compute shader" {
    const source = "@compute @workgroup_size(64) fn main(@builtin(global_invocation_id) id: vec3u) { }";
    var lex = Lexer.init(source);
    const expected = [_]Tag{
        .@"@", .ident, // @compute
        .@"@", .ident, // @workgroup_size
        .@"(", .int_literal, .@")", // (64)
        .kw_fn, .ident, // fn main
        .@"(", // (
        .@"@", .ident, // @builtin
        .@"(", .ident, .@")", // (global_invocation_id)
        .ident, .@":", .kw_vec3u, // id: vec3u
        .@")", // )
        .@"{", .@"}", // { }
        .eof,
    };
    for (expected) |exp| {
        const tok = lex.next();
        try std.testing.expectEqual(exp, tok.tag);
    }
}

test "lex number literals" {
    var lex = Lexer.init("42 3.14 0xFF 1u 2.0f 0x1p10");
    try std.testing.expectEqual(Tag.int_literal, lex.next().tag);
    try std.testing.expectEqual(Tag.float_literal, lex.next().tag);
    try std.testing.expectEqual(Tag.int_literal, lex.next().tag);
    try std.testing.expectEqual(Tag.int_literal, lex.next().tag);
    try std.testing.expectEqual(Tag.float_literal, lex.next().tag);
    try std.testing.expectEqual(Tag.float_literal, lex.next().tag);
    try std.testing.expectEqual(Tag.eof, lex.next().tag);
}

test "lex compound operators" {
    var lex = Lexer.init("-> += -= *= /= %= &= |= ^= << >> <= >= == != && ||");
    const expected = [_]Tag{
        .arrow, .plus_eq, .minus_eq, .star_eq, .slash_eq,
        .percent_eq, .amp_eq, .pipe_eq, .caret_eq,
        .shift_left, .shift_right, .lte, .gte, .eq_eq, .not_eq,
        .and_and, .or_or, .eof,
    };
    for (expected) |exp| {
        try std.testing.expectEqual(exp, lex.next().tag);
    }
}

test "lex comments" {
    var lex = Lexer.init("a // line comment\nb /* block */ c /* nested /* inner */ outer */ d");
    try std.testing.expectEqual(Tag.ident, lex.next().tag);
    try std.testing.expectEqual(Tag.ident, lex.next().tag); // b
    try std.testing.expectEqual(Tag.ident, lex.next().tag); // c
    try std.testing.expectEqual(Tag.ident, lex.next().tag); // d
    try std.testing.expectEqual(Tag.eof, lex.next().tag);
}

test "lex keywords" {
    var lex = Lexer.init("fn var let const override struct return if else for while");
    const expected = [_]Tag{
        .kw_fn, .kw_var, .kw_let, .kw_const, .kw_override, .kw_struct,
        .kw_return, .kw_if, .kw_else, .kw_for, .kw_while, .eof,
    };
    for (expected) |exp| {
        try std.testing.expectEqual(exp, lex.next().tag);
    }
}
