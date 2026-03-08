// doe_wgsl/parser.zig — WGSL parser producing an AST.
//
// Parses the subset of WGSL used by Doppler compute shaders:
// - enable directives
// - struct declarations (with nested array fields)
// - global var/let/const/override declarations with attributes
// - fn declarations with attributes, multiple entry points, helper functions
// - block statements with if/else, for, while, loop, switch, break, continue, return
// - expressions: binary, unary, call, member access, index, literals
// - type expressions: scalar, vec, mat, array, atomic, user-defined

const std = @import("std");
const ast_mod = @import("ast.zig");
const token_mod = @import("token.zig");
const lexer_mod = @import("lexer.zig");
const Ast = ast_mod.Ast;
const Node = ast_mod.Node;
const NodeTag = ast_mod.NodeTag;
const NULL_NODE = ast_mod.NULL_NODE;
const Token = token_mod.Token;
const Tag = token_mod.Tag;
const Lexer = lexer_mod.Lexer;

pub const ParseError = error{
    UnexpectedToken,
    OutOfMemory,
};

pub const Parser = struct {
    tree: *Ast,
    token_idx: u32,
    /// Scratch buffer for collecting child indices before committing to extra_data.
    scratch: std.ArrayListUnmanaged(u32),
    allocator: std.mem.Allocator,

    pub fn init(tree: *Ast, allocator: std.mem.Allocator) Parser {
        return .{
            .tree = tree,
            .token_idx = 0,
            .scratch = .{},
            .allocator = allocator,
        };
    }

    pub fn deinit(self: *Parser) void {
        self.scratch.deinit(self.allocator);
    }

    // ============================================================
    // Tokenization phase
    // ============================================================

    pub fn tokenize(tree: *Ast, source: []const u8) !void {
        tree.source = source;
        var lex = Lexer.init(source);
        while (true) {
            const tok = lex.next();
            try tree.tokens.append(tree.allocator, tok);
            if (tok.tag == .eof) break;
        }
    }

    // ============================================================
    // Top-level entry
    // ============================================================

    pub fn parse(self: *Parser) ParseError!u32 {
        const scratch_top = self.scratch.items.len;
        defer self.scratch.shrinkRetainingCapacity(scratch_top);

        while (self.peekTag() != .eof) {
            const decl = try self.parseTopLevelDecl();
            if (decl != NULL_NODE) {
                try self.scratch.append(self.allocator,decl);
            }
        }

        const decls = self.scratch.items[scratch_top..];
        const extra_start = try self.tree.addExtraSlice(decls);
        const count: u32 = @intCast(decls.len);

        // Overwrite node 0 (root).
        self.tree.nodes.items[0] = .{
            .tag = .root,
            .main_token = 0,
            .data = .{ .lhs = extra_start, .rhs = count },
        };
        return 0;
    }

    fn parseTopLevelDecl(self: *Parser) ParseError!u32 {
        // Collect leading attributes.
        const attrs = try self.parseAttributes();

        return switch (self.peekTag()) {
            .kw_enable => self.parseEnableDirective(),
            .kw_diagnostic => self.parseDiagnosticDirective(),
            .kw_struct => self.parseStructDecl(attrs),
            .kw_fn => self.parseFnDecl(attrs),
            .kw_var => self.parseGlobalVar(attrs),
            .kw_override => self.parseOverrideDecl(attrs),
            .kw_const => self.parseConstDecl(attrs),
            .kw_let => self.parseConstDecl(attrs),
            .kw_alias => self.parseAliasDecl(),
            else => {
                // Skip unknown token to avoid infinite loop.
                self.advance();
                return NULL_NODE;
            },
        };
    }

    // ============================================================
    // Directives
    // ============================================================

    fn parseEnableDirective(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume `enable`
        const name_token = self.token_idx;
        self.advance(); // consume extension name
        self.skipSemicolon();
        return self.tree.addNode(.{
            .tag = .enable_directive,
            .main_token = main_token,
            .data = .{ .lhs = name_token },
        });
    }

    fn parseDiagnosticDirective(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume `diagnostic`
        // Skip to semicolon.
        while (self.peekTag() != .@";" and self.peekTag() != .eof) {
            self.advance();
        }
        self.skipSemicolon();
        return self.tree.addNode(.{
            .tag = .diagnostic_directive,
            .main_token = main_token,
            .data = .{},
        });
    }

    // ============================================================
    // Struct
    // ============================================================

    fn parseStructDecl(self: *Parser, attrs: AttrSpan) ParseError!u32 {
        _ = attrs;
        const main_token = self.token_idx;
        self.advance(); // consume `struct`
        const name_token = self.token_idx;
        self.advance(); // consume name
        _ = try self.expect(.@"{");

        const scratch_top = self.scratch.items.len;
        defer self.scratch.shrinkRetainingCapacity(scratch_top);

        while (self.peekTag() != .@"}" and self.peekTag() != .eof) {
            const member = try self.parseStructMember();
            try self.scratch.append(self.allocator,member);
        }
        _ = try self.expect(.@"}");

        const members = self.scratch.items[scratch_top..];
        const extra_start = try self.tree.addExtraSlice(members);
        const count: u32 = @intCast(members.len);

        return self.tree.addNode(.{
            .tag = .struct_decl,
            .main_token = main_token,
            .data = .{ .lhs = name_token, .rhs = extra_start | (count << 16) },
        });
    }

    fn parseStructMember(self: *Parser) ParseError!u32 {
        const member_attrs = try self.parseAttributes();
        const name_token = self.token_idx;
        self.advance(); // consume member name
        _ = try self.expect(.@":");
        const type_node = try self.parseTypeExpr();
        // Optional trailing comma.
        if (self.peekTag() == .@",") self.advance();

        return self.tree.addNode(.{
            .tag = .struct_member,
            .main_token = name_token,
            .data = .{ .lhs = type_node, .rhs = member_attrs.start | (member_attrs.len << 16) },
        });
    }

    // ============================================================
    // Functions
    // ============================================================

    fn parseFnDecl(self: *Parser, attrs: AttrSpan) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume `fn`
        const name_token = self.token_idx;
        self.advance(); // consume function name
        _ = try self.expect(.@"(");

        // Parse parameters.
        const scratch_top = self.scratch.items.len;

        while (self.peekTag() != .@")" and self.peekTag() != .eof) {
            const param = try self.parseFnParam();
            try self.scratch.append(self.allocator,param);
            if (self.peekTag() == .@",") self.advance();
        }
        _ = try self.expect(.@")");

        // Return type.
        var return_type: u32 = NULL_NODE;
        if (self.peekTag() == .arrow) {
            self.advance(); // consume `->`
            // Collect return attributes.
            const ret_attrs = try self.parseAttributes();
            _ = ret_attrs;
            return_type = try self.parseTypeExpr();
        }

        const params = self.scratch.items[scratch_top..];
        const params_start = try self.tree.addExtraSlice(params);
        const params_len: u32 = @intCast(params.len);
        self.scratch.shrinkRetainingCapacity(scratch_top);

        // Store fn extra data.
        const extra_start = try self.tree.addExtraSlice(&.{
            name_token,
            params_start,
            params_len,
            return_type,
            attrs.start,
            attrs.len,
        });

        // Parse body.
        const body = try self.parseBlock();

        return self.tree.addNode(.{
            .tag = .fn_decl,
            .main_token = main_token,
            .data = .{ .lhs = extra_start, .rhs = body },
        });
    }

    fn parseFnParam(self: *Parser) ParseError!u32 {
        const param_attrs = try self.parseAttributes();
        const name_token = self.token_idx;
        self.advance(); // consume param name
        _ = try self.expect(.@":");
        const type_node = try self.parseTypeExpr();

        const extra_start = try self.tree.addExtraSlice(&.{
            name_token,
            type_node,
            param_attrs.start,
            param_attrs.len,
        });
        return extra_start;
    }

    // ============================================================
    // Global declarations
    // ============================================================

    fn parseGlobalVar(self: *Parser, attrs: AttrSpan) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume `var`

        var addr_space: u32 = 0;
        var access_mode: u32 = 0;
        if (self.peekTag() == .@"<") {
            self.advance(); // consume `<`
            addr_space = self.token_idx;
            self.advance(); // consume address space
            if (self.peekTag() == .@",") {
                self.advance(); // consume `,`
                access_mode = self.token_idx;
                self.advance(); // consume access mode
            }
            _ = try self.expect(.@">");
        }

        const name_token = self.token_idx;
        self.advance(); // consume name

        var type_node: u32 = NULL_NODE;
        if (self.peekTag() == .@":") {
            self.advance(); // consume `:`
            type_node = try self.parseTypeExpr();
        }

        var init_node: u32 = NULL_NODE;
        if (self.peekTag() == .@"=") {
            self.advance(); // consume `=`
            init_node = try self.parseExpr();
        }

        self.skipSemicolon();

        const extra_start = try self.tree.addExtraSlice(&.{
            name_token,
            addr_space,
            access_mode,
            init_node,
            attrs.start,
            attrs.len,
        });

        return self.tree.addNode(.{
            .tag = .global_var,
            .main_token = main_token,
            .data = .{ .lhs = type_node, .rhs = extra_start },
        });
    }

    fn parseOverrideDecl(self: *Parser, attrs: AttrSpan) ParseError!u32 {
        _ = attrs;
        const main_token = self.token_idx;
        self.advance(); // consume `override`

        // skip name
        self.advance();

        var type_node: u32 = NULL_NODE;
        if (self.peekTag() == .@":") {
            self.advance();
            type_node = try self.parseTypeExpr();
        }

        var init_node: u32 = NULL_NODE;
        if (self.peekTag() == .@"=") {
            self.advance();
            init_node = try self.parseExpr();
        }

        self.skipSemicolon();

        return self.tree.addNode(.{
            .tag = .override_decl,
            .main_token = main_token,
            .data = .{ .lhs = type_node, .rhs = init_node },
        });
    }

    fn parseConstDecl(self: *Parser, attrs: AttrSpan) ParseError!u32 {
        _ = attrs;
        const main_token = self.token_idx;
        self.advance(); // consume `const` or `let`

        // skip name
        self.advance();

        var type_node: u32 = NULL_NODE;
        if (self.peekTag() == .@":") {
            self.advance();
            type_node = try self.parseTypeExpr();
        }

        var init_node: u32 = NULL_NODE;
        if (self.peekTag() == .@"=") {
            self.advance();
            init_node = try self.parseExpr();
        }

        self.skipSemicolon();

        return self.tree.addNode(.{
            .tag = .const_decl,
            .main_token = main_token,
            .data = .{ .lhs = type_node, .rhs = init_node },
        });
    }

    fn parseAliasDecl(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume `alias`
        self.advance(); // consume name
        _ = try self.expect(.@"=");
        const type_node = try self.parseTypeExpr();
        self.skipSemicolon();
        return self.tree.addNode(.{
            .tag = .alias_decl,
            .main_token = main_token,
            .data = .{ .lhs = type_node },
        });
    }

    // ============================================================
    // Statements
    // ============================================================

    fn parseBlock(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        _ = try self.expect(.@"{");

        const scratch_top = self.scratch.items.len;
        defer self.scratch.shrinkRetainingCapacity(scratch_top);

        while (self.peekTag() != .@"}" and self.peekTag() != .eof) {
            const stmt = try self.parseStatement();
            if (stmt != NULL_NODE) {
                try self.scratch.append(self.allocator,stmt);
            }
        }
        _ = try self.expect(.@"}");

        const stmts = self.scratch.items[scratch_top..];
        const extra_start = try self.tree.addExtraSlice(stmts);
        const count: u32 = @intCast(stmts.len);

        return self.tree.addNode(.{
            .tag = .block,
            .main_token = main_token,
            .data = .{ .lhs = extra_start, .rhs = count },
        });
    }

    fn parseStatement(self: *Parser) ParseError!u32 {
        return switch (self.peekTag()) {
            .@"{" => self.parseBlock(),
            .kw_var => self.parseLocalVarStmt(),
            .kw_let => self.parseLocalLetStmt(),
            .kw_const => self.parseLocalConstStmt(),
            .kw_return => self.parseReturnStmt(),
            .kw_if => self.parseIfStmt(),
            .kw_for => self.parseForStmt(),
            .kw_while => self.parseWhileStmt(),
            .kw_loop => self.parseLoopStmt(),
            .kw_break => self.parseBreakStmt(),
            .kw_continue => self.parseContinueStmt(),
            .kw_continuing => self.parseContinuingStmt(),
            .kw_switch => self.parseSwitchStmt(),
            .kw_discard => self.parseDiscardStmt(),
            .@";" => blk: {
                self.advance();
                break :blk NULL_NODE;
            },
            else => self.parseExprOrAssignStmt(),
        };
    }

    fn parseLocalVarStmt(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume `var`

        // Optional address space.
        if (self.peekTag() == .@"<") {
            self.advance();
            self.advance(); // address space
            if (self.peekTag() == .@",") {
                self.advance();
                self.advance(); // access mode
            }
            _ = try self.expect(.@">");
        }

        self.advance(); // consume name

        var type_node: u32 = NULL_NODE;
        if (self.peekTag() == .@":") {
            self.advance();
            type_node = try self.parseTypeExpr();
        }

        var init_node: u32 = NULL_NODE;
        if (self.peekTag() == .@"=") {
            self.advance();
            init_node = try self.parseExpr();
        }

        self.skipSemicolon();
        return self.tree.addNode(.{
            .tag = .var_stmt,
            .main_token = main_token,
            .data = .{ .lhs = type_node, .rhs = init_node },
        });
    }

    fn parseLocalLetStmt(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume `let`
        self.advance(); // consume name

        var type_node: u32 = NULL_NODE;
        if (self.peekTag() == .@":") {
            self.advance();
            type_node = try self.parseTypeExpr();
        }

        _ = try self.expect(.@"=");
        const init_node = try self.parseExpr();
        self.skipSemicolon();

        return self.tree.addNode(.{
            .tag = .let_stmt,
            .main_token = main_token,
            .data = .{ .lhs = type_node, .rhs = init_node },
        });
    }

    fn parseLocalConstStmt(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume `const`
        self.advance(); // consume name

        var type_node: u32 = NULL_NODE;
        if (self.peekTag() == .@":") {
            self.advance();
            type_node = try self.parseTypeExpr();
        }

        _ = try self.expect(.@"=");
        const init_node = try self.parseExpr();
        self.skipSemicolon();

        return self.tree.addNode(.{
            .tag = .const_stmt,
            .main_token = main_token,
            .data = .{ .lhs = type_node, .rhs = init_node },
        });
    }

    fn parseReturnStmt(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume `return`

        var expr: u32 = NULL_NODE;
        if (self.peekTag() != .@";" and self.peekTag() != .eof) {
            expr = try self.parseExpr();
        }
        self.skipSemicolon();

        return self.tree.addNode(.{
            .tag = .return_stmt,
            .main_token = main_token,
            .data = .{ .lhs = expr },
        });
    }

    fn parseIfStmt(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume `if`

        // Condition — may or may not have parens.
        var skip_close = false;
        if (self.peekTag() == .@"(") {
            self.advance();
            skip_close = true;
        }
        const cond = try self.parseExpr();
        if (skip_close and self.peekTag() == .@")") {
            self.advance();
        }

        const then_block = try self.parseBlock();

        var else_node: u32 = NULL_NODE;
        if (self.peekTag() == .kw_else) {
            self.advance(); // consume `else`
            if (self.peekTag() == .kw_if) {
                else_node = try self.parseIfStmt();
            } else {
                else_node = try self.parseBlock();
            }
        }

        const extra_start = try self.tree.addExtraSlice(&.{ then_block, else_node });

        return self.tree.addNode(.{
            .tag = .if_stmt,
            .main_token = main_token,
            .data = .{ .lhs = cond, .rhs = extra_start },
        });
    }

    fn parseForStmt(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume `for`
        _ = try self.expect(.@"(");

        // Init.
        var init_stmt: u32 = NULL_NODE;
        if (self.peekTag() != .@";") {
            init_stmt = try self.parseStatement();
        } else {
            self.advance(); // consume `;`
        }

        // Condition.
        var cond: u32 = NULL_NODE;
        if (self.peekTag() != .@";") {
            cond = try self.parseExpr();
        }
        self.skipSemicolon();

        // Update.
        var update: u32 = NULL_NODE;
        if (self.peekTag() != .@")") {
            update = try self.parseExprOrAssignStmt();
        }
        _ = try self.expect(.@")");

        const body = try self.parseBlock();

        const extra_start = try self.tree.addExtraSlice(&.{ init_stmt, cond, update });

        return self.tree.addNode(.{
            .tag = .for_stmt,
            .main_token = main_token,
            .data = .{ .lhs = extra_start, .rhs = body },
        });
    }

    fn parseWhileStmt(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume `while`

        var skip_close = false;
        if (self.peekTag() == .@"(") {
            self.advance();
            skip_close = true;
        }
        const cond = try self.parseExpr();
        if (skip_close and self.peekTag() == .@")") {
            self.advance();
        }

        const body = try self.parseBlock();

        return self.tree.addNode(.{
            .tag = .while_stmt,
            .main_token = main_token,
            .data = .{ .lhs = cond, .rhs = body },
        });
    }

    fn parseLoopStmt(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume `loop`
        const body = try self.parseBlock();
        return self.tree.addNode(.{
            .tag = .loop_stmt,
            .main_token = main_token,
            .data = .{ .lhs = body },
        });
    }

    fn parseBreakStmt(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume `break`
        // `break if expr;` (WGSL loop break-if).
        var cond: u32 = NULL_NODE;
        if (self.peekTag() == .kw_if) {
            self.advance();
            cond = try self.parseExpr();
        }
        self.skipSemicolon();
        return self.tree.addNode(.{
            .tag = .break_stmt,
            .main_token = main_token,
            .data = .{ .lhs = cond },
        });
    }

    fn parseContinueStmt(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance();
        self.skipSemicolon();
        return self.tree.addNode(.{
            .tag = .continue_stmt,
            .main_token = main_token,
            .data = .{},
        });
    }

    fn parseContinuingStmt(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume `continuing`
        const body = try self.parseBlock();
        return self.tree.addNode(.{
            .tag = .continuing_stmt,
            .main_token = main_token,
            .data = .{ .lhs = body },
        });
    }

    fn parseSwitchStmt(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume `switch`

        var skip_close = false;
        if (self.peekTag() == .@"(") {
            self.advance();
            skip_close = true;
        }
        const expr = try self.parseExpr();
        if (skip_close and self.peekTag() == .@")") {
            self.advance();
        }

        _ = try self.expect(.@"{");

        const scratch_top = self.scratch.items.len;
        defer self.scratch.shrinkRetainingCapacity(scratch_top);

        while (self.peekTag() != .@"}" and self.peekTag() != .eof) {
            const case_node = try self.parseSwitchCase();
            try self.scratch.append(self.allocator,case_node);
        }
        _ = try self.expect(.@"}");

        const cases = self.scratch.items[scratch_top..];
        const extra_start = try self.tree.addExtraSlice(cases);
        const count: u32 = @intCast(cases.len);

        return self.tree.addNode(.{
            .tag = .switch_stmt,
            .main_token = main_token,
            .data = .{ .lhs = expr, .rhs = extra_start | (count << 16) },
        });
    }

    fn parseSwitchCase(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        var selectors = std.ArrayListUnmanaged(u32){};
        defer selectors.deinit(self.allocator);
        if (self.peekTag() == .kw_case) {
            self.advance(); // consume `case`
            while (true) {
                try selectors.append(self.allocator, try self.parseExpr());
                if (self.peekTag() != .@",") break;
                self.advance();
            }
        } else if (self.peekTag() == .kw_default) {
            self.advance(); // consume `default`
        }
        if (self.peekTag() == .@":") self.advance();
        const body = try self.parseBlock();
        const selectors_start = try self.tree.addExtraSlice(selectors.items);
        const selectors_len: u32 = @intCast(selectors.items.len);
        return self.tree.addNode(.{
            .tag = .switch_case,
            .main_token = main_token,
            .data = .{ .lhs = body, .rhs = selectors_start | (selectors_len << 16) },
        });
    }

    fn parseDiscardStmt(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance();
        self.skipSemicolon();
        return self.tree.addNode(.{
            .tag = .discard_stmt,
            .main_token = main_token,
            .data = .{},
        });
    }

    fn parseExprOrAssignStmt(self: *Parser) ParseError!u32 {
        const lhs = try self.parseExpr();

        // Check for assignment operators.
        const tag = self.peekTag();
        if (isAssignOp(tag)) {
            const op_token = self.token_idx;
            self.advance();
            const rhs = try self.parseExpr();
            self.skipSemicolon();
            return self.tree.addNode(.{
                .tag = .assign_stmt,
                .main_token = op_token,
                .data = .{ .lhs = lhs, .rhs = rhs },
            });
        }

        // Bare expression statement (e.g., function call).
        self.skipSemicolon();
        return self.tree.addNode(.{
            .tag = .expr_stmt,
            .main_token = self.tree.nodes.items[lhs].main_token,
            .data = .{ .lhs = lhs },
        });
    }

    // ============================================================
    // Expressions (precedence climbing)
    // ============================================================

    fn parseExpr(self: *Parser) ParseError!u32 {
        return self.parseOr();
    }

    fn parseOr(self: *Parser) ParseError!u32 {
        var lhs = try self.parseAnd();
        while (self.peekTag() == .or_or) {
            const op = self.token_idx;
            self.advance();
            const rhs = try self.parseAnd();
            lhs = try self.tree.addNode(.{
                .tag = .binary_expr,
                .main_token = op,
                .data = .{ .lhs = lhs, .rhs = rhs },
            });
        }
        return lhs;
    }

    fn parseAnd(self: *Parser) ParseError!u32 {
        var lhs = try self.parseBitwiseOr();
        while (self.peekTag() == .and_and) {
            const op = self.token_idx;
            self.advance();
            const rhs = try self.parseBitwiseOr();
            lhs = try self.tree.addNode(.{
                .tag = .binary_expr,
                .main_token = op,
                .data = .{ .lhs = lhs, .rhs = rhs },
            });
        }
        return lhs;
    }

    fn parseBitwiseOr(self: *Parser) ParseError!u32 {
        var lhs = try self.parseBitwiseXor();
        while (self.peekTag() == .@"|") {
            const op = self.token_idx;
            self.advance();
            const rhs = try self.parseBitwiseXor();
            lhs = try self.tree.addNode(.{
                .tag = .binary_expr,
                .main_token = op,
                .data = .{ .lhs = lhs, .rhs = rhs },
            });
        }
        return lhs;
    }

    fn parseBitwiseXor(self: *Parser) ParseError!u32 {
        var lhs = try self.parseBitwiseAnd();
        while (self.peekTag() == .@"^") {
            const op = self.token_idx;
            self.advance();
            const rhs = try self.parseBitwiseAnd();
            lhs = try self.tree.addNode(.{
                .tag = .binary_expr,
                .main_token = op,
                .data = .{ .lhs = lhs, .rhs = rhs },
            });
        }
        return lhs;
    }

    fn parseBitwiseAnd(self: *Parser) ParseError!u32 {
        var lhs = try self.parseEquality();
        while (self.peekTag() == .@"&") {
            const op = self.token_idx;
            self.advance();
            const rhs = try self.parseEquality();
            lhs = try self.tree.addNode(.{
                .tag = .binary_expr,
                .main_token = op,
                .data = .{ .lhs = lhs, .rhs = rhs },
            });
        }
        return lhs;
    }

    fn parseEquality(self: *Parser) ParseError!u32 {
        var lhs = try self.parseRelational();
        while (self.peekTag() == .eq_eq or self.peekTag() == .not_eq) {
            const op = self.token_idx;
            self.advance();
            const rhs = try self.parseRelational();
            lhs = try self.tree.addNode(.{
                .tag = .binary_expr,
                .main_token = op,
                .data = .{ .lhs = lhs, .rhs = rhs },
            });
        }
        return lhs;
    }

    fn parseRelational(self: *Parser) ParseError!u32 {
        var lhs = try self.parseShift();
        while (self.peekTag() == .@"<" or self.peekTag() == .@">" or
            self.peekTag() == .lte or self.peekTag() == .gte)
        {
            const op = self.token_idx;
            self.advance();
            const rhs = try self.parseShift();
            lhs = try self.tree.addNode(.{
                .tag = .binary_expr,
                .main_token = op,
                .data = .{ .lhs = lhs, .rhs = rhs },
            });
        }
        return lhs;
    }

    fn parseShift(self: *Parser) ParseError!u32 {
        var lhs = try self.parseAddSub();
        while (self.peekTag() == .shift_left or self.peekTag() == .shift_right) {
            const op = self.token_idx;
            self.advance();
            const rhs = try self.parseAddSub();
            lhs = try self.tree.addNode(.{
                .tag = .binary_expr,
                .main_token = op,
                .data = .{ .lhs = lhs, .rhs = rhs },
            });
        }
        return lhs;
    }

    fn parseAddSub(self: *Parser) ParseError!u32 {
        var lhs = try self.parseMulDiv();
        while (self.peekTag() == .@"+" or self.peekTag() == .@"-") {
            const op = self.token_idx;
            self.advance();
            const rhs = try self.parseMulDiv();
            lhs = try self.tree.addNode(.{
                .tag = .binary_expr,
                .main_token = op,
                .data = .{ .lhs = lhs, .rhs = rhs },
            });
        }
        return lhs;
    }

    fn parseMulDiv(self: *Parser) ParseError!u32 {
        var lhs = try self.parseUnary();
        while (self.peekTag() == .@"*" or self.peekTag() == .@"/" or self.peekTag() == .@"%") {
            const op = self.token_idx;
            self.advance();
            const rhs = try self.parseUnary();
            lhs = try self.tree.addNode(.{
                .tag = .binary_expr,
                .main_token = op,
                .data = .{ .lhs = lhs, .rhs = rhs },
            });
        }
        return lhs;
    }

    fn parseUnary(self: *Parser) ParseError!u32 {
        const tag = self.peekTag();
        if (tag == .@"-" or tag == .@"!" or tag == .@"~" or tag == .@"&" or tag == .@"*") {
            const op = self.token_idx;
            self.advance();
            const operand = try self.parseUnary();
            return self.tree.addNode(.{
                .tag = .unary_expr,
                .main_token = op,
                .data = .{ .lhs = operand },
            });
        }
        return self.parsePostfix();
    }

    fn parsePostfix(self: *Parser) ParseError!u32 {
        var lhs = try self.parsePrimary();
        while (true) {
            switch (self.peekTag()) {
                .@"." => {
                    const dot_token = self.token_idx;
                    self.advance(); // consume `.`
                    const field_token = self.token_idx;
                    self.advance(); // consume field name
                    lhs = try self.tree.addNode(.{
                        .tag = .member_expr,
                        .main_token = dot_token,
                        .data = .{ .lhs = lhs, .rhs = field_token },
                    });
                },
                .@"[" => {
                    const bracket_token = self.token_idx;
                    self.advance(); // consume `[`
                    const index = try self.parseExpr();
                    _ = try self.expect(.@"]");
                    lhs = try self.tree.addNode(.{
                        .tag = .index_expr,
                        .main_token = bracket_token,
                        .data = .{ .lhs = lhs, .rhs = index },
                    });
                },
                else => break,
            }
        }
        return lhs;
    }

    fn parsePrimary(self: *Parser) ParseError!u32 {
        const tag = self.peekTag();
        switch (tag) {
            .int_literal => {
                const tok = self.token_idx;
                self.advance();
                return self.tree.addNode(.{
                    .tag = .int_literal,
                    .main_token = tok,
                    .data = .{},
                });
            },
            .float_literal => {
                const tok = self.token_idx;
                self.advance();
                return self.tree.addNode(.{
                    .tag = .float_literal,
                    .main_token = tok,
                    .data = .{},
                });
            },
            .kw_true, .kw_false => {
                const tok = self.token_idx;
                self.advance();
                return self.tree.addNode(.{
                    .tag = .bool_literal,
                    .main_token = tok,
                    .data = .{},
                });
            },
            .@"(" => {
                self.advance(); // consume `(`
                const expr = try self.parseExpr();
                _ = try self.expect(.@")");
                return expr;
            },
            .ident => return self.parseIdentOrCall(),

            // Type constructors: vec4f(...), array(...), etc.
            .kw_vec2f, .kw_vec3f, .kw_vec4f,
            .kw_vec2h, .kw_vec3h, .kw_vec4h,
            .kw_vec2i, .kw_vec3i, .kw_vec4i,
            .kw_vec2u, .kw_vec3u, .kw_vec4u,
            .kw_mat2x2f, .kw_mat3x3f, .kw_mat4x4f,
            .kw_mat2x2h, .kw_mat3x3h, .kw_mat4x4h,
            => return self.parseTypeConstructor(),

            // Parameterized type constructors: vec4<f32>(...), array<T>(...).
            .kw_vec2, .kw_vec3, .kw_vec4,
            .kw_mat2x2, .kw_mat3x3, .kw_mat4x4,
            .kw_mat2x3, .kw_mat2x4, .kw_mat3x2,
            .kw_mat3x4, .kw_mat4x2, .kw_mat4x3,
            .kw_array, .kw_atomic,
            => return self.parseTypeConstructor(),

            // Scalar type constructors: f32(x), u32(x), i32(x), f16(x), bool(x).
            .kw_f32, .kw_f16, .kw_u32, .kw_i32, .kw_bool,
            => return self.parseTypeConstructor(),

            else => {
                // Fallback: produce an invalid ident node and advance.
                const tok = self.token_idx;
                self.advance();
                return self.tree.addNode(.{
                    .tag = .ident_expr,
                    .main_token = tok,
                    .data = .{},
                });
            },
        }
    }

    fn parseIdentOrCall(self: *Parser) ParseError!u32 {
        const name_token = self.token_idx;
        self.advance(); // consume identifier

        // Check for type-parameterized call: ident<T>(...).
        if (self.peekTag() == .@"<" and self.looksLikeTypeArgs()) {
            return self.parseGenericCall(name_token);
        }

        // Check for function call: ident(...).
        if (self.peekTag() == .@"(") {
            return self.parseCallArgs(name_token);
        }

        return self.tree.addNode(.{
            .tag = .ident_expr,
            .main_token = name_token,
            .data = .{},
        });
    }

    fn parseTypeConstructor(self: *Parser) ParseError!u32 {
        const name_token = self.token_idx;
        self.advance(); // consume type keyword

        // Skip type parameters if present: <T, N>.
        if (self.peekTag() == .@"<") {
            self.advance();
            var depth: u32 = 1;
            while (depth > 0 and self.peekTag() != .eof) {
                if (self.peekTag() == .@"<") depth += 1;
                if (self.peekTag() == .@">") depth -= 1;
                if (depth > 0) self.advance();
            }
            if (self.peekTag() == .@">") self.advance();
        }

        // Parse constructor args if present.
        if (self.peekTag() == .@"(") {
            return self.parseCallArgs(name_token);
        }

        // No parens — this is a type expression used as a value (shouldn't happen normally).
        return self.tree.addNode(.{
            .tag = .ident_expr,
            .main_token = name_token,
            .data = .{},
        });
    }

    fn parseGenericCall(self: *Parser, name_token: u32) ParseError!u32 {
        // Skip <...> type args.
        _ = try self.expect(.@"<");
        var depth: u32 = 1;
        while (depth > 0 and self.peekTag() != .eof) {
            if (self.peekTag() == .@"<") depth += 1;
            if (self.peekTag() == .@">") depth -= 1;
            if (depth > 0) self.advance();
        }
        if (self.peekTag() == .@">") self.advance();

        if (self.peekTag() == .@"(") {
            return self.parseCallArgs(name_token);
        }

        return self.tree.addNode(.{
            .tag = .ident_expr,
            .main_token = name_token,
            .data = .{},
        });
    }

    fn parseCallArgs(self: *Parser, name_token: u32) ParseError!u32 {
        _ = try self.expect(.@"(");

        const scratch_top = self.scratch.items.len;
        defer self.scratch.shrinkRetainingCapacity(scratch_top);

        while (self.peekTag() != .@")" and self.peekTag() != .eof) {
            const arg = try self.parseExpr();
            try self.scratch.append(self.allocator,arg);
            if (self.peekTag() == .@",") self.advance();
        }
        _ = try self.expect(.@")");

        const args = self.scratch.items[scratch_top..];
        const extra_start = try self.tree.addExtraSlice(args);
        const count: u32 = @intCast(args.len);

        return self.tree.addNode(.{
            .tag = .call_expr,
            .main_token = name_token,
            .data = .{ .lhs = extra_start, .rhs = count },
        });
    }

    /// Heuristic: does `<` start type arguments (vs a less-than comparison)?
    /// Check if we see a closing `>` before `;`, `{`, `}`, or binary operators.
    fn looksLikeTypeArgs(self: *const Parser) bool {
        var i = self.token_idx + 1;
        var depth: u32 = 1;
        while (i < self.tree.tokens.items.len and depth > 0) {
            const t = self.tree.tokens.items[i].tag;
            switch (t) {
                .@"<" => depth += 1,
                .@">" => {
                    depth -= 1;
                    if (depth == 0) return true;
                },
                .@";", .@"{", .@"}", .eof => return false,
                // If we see an operator that can't appear in type args, bail.
                .@"+", .@"-", .@"*", .@"/", .@"%",
                .eq_eq, .not_eq, .lte, .gte,
                .and_and, .or_or,
                => return false,
                else => {},
            }
            i += 1;
        }
        return false;
    }

    // ============================================================
    // Type expressions
    // ============================================================

    fn parseTypeExpr(self: *Parser) ParseError!u32 {
        const tag = self.peekTag();
        switch (tag) {
            // Shorthand types.
            .kw_vec2f, .kw_vec3f, .kw_vec4f,
            .kw_vec2h, .kw_vec3h, .kw_vec4h,
            .kw_vec2i, .kw_vec3i, .kw_vec4i,
            .kw_vec2u, .kw_vec3u, .kw_vec4u,
            => {
                const tok = self.token_idx;
                self.advance();
                return self.tree.addNode(.{
                    .tag = .type_vec_shorthand,
                    .main_token = tok,
                    .data = .{},
                });
            },
            .kw_mat2x2f, .kw_mat3x3f, .kw_mat4x4f,
            .kw_mat2x2h, .kw_mat3x3h, .kw_mat4x4h,
            => {
                const tok = self.token_idx;
                self.advance();
                return self.tree.addNode(.{
                    .tag = .type_mat_shorthand,
                    .main_token = tok,
                    .data = .{},
                });
            },

            // Parameterized built-in types.
            .kw_vec2, .kw_vec3, .kw_vec4,
            .kw_mat2x2, .kw_mat3x3, .kw_mat4x4,
            .kw_mat2x3, .kw_mat2x4, .kw_mat3x2,
            .kw_mat3x4, .kw_mat4x2, .kw_mat4x3,
            .kw_array, .kw_atomic, .kw_ptr,
            .kw_sampler, .kw_texture_2d,
            => return self.parseParameterizedType(),

            // Scalar types.
            .kw_f32, .kw_f16, .kw_u32, .kw_i32, .kw_bool,
            => {
                const tok = self.token_idx;
                self.advance();
                return self.tree.addNode(.{
                    .tag = .type_name,
                    .main_token = tok,
                    .data = .{},
                });
            },

            // User-defined type.
            .ident => {
                if (self.token_idx + 1 < self.tree.tokens.items.len and
                    self.tree.tokens.items[self.token_idx + 1].tag == .@"<")
                {
                    return self.parseParameterizedType();
                }
                const tok = self.token_idx;
                self.advance();
                return self.tree.addNode(.{
                    .tag = .type_name,
                    .main_token = tok,
                    .data = .{},
                });
            },

            else => {
                // Unexpected — return a placeholder.
                const tok = self.token_idx;
                self.advance();
                return self.tree.addNode(.{
                    .tag = .type_name,
                    .main_token = tok,
                    .data = .{},
                });
            },
        }
    }

    fn parseParameterizedType(self: *Parser) ParseError!u32 {
        const main_token = self.token_idx;
        self.advance(); // consume type keyword

        if (self.peekTag() != .@"<") {
            return self.tree.addNode(.{
                .tag = .type_name,
                .main_token = main_token,
                .data = .{},
            });
        }

        self.advance(); // consume `<`

        const scratch_top = self.scratch.items.len;
        defer self.scratch.shrinkRetainingCapacity(scratch_top);

        while (self.peekTag() != .@">" and self.peekTag() != .eof) {
            // Type params can be types or integer expressions (array size).
            if (self.peekTag() == .int_literal) {
                const tok = self.token_idx;
                self.advance();
                const node = try self.tree.addNode(.{
                    .tag = .int_literal,
                    .main_token = tok,
                    .data = .{},
                });
                try self.scratch.append(self.allocator,node);
            } else {
                const param = try self.parseTypeExpr();
                try self.scratch.append(self.allocator,param);
            }
            if (self.peekTag() == .@",") self.advance();
        }
        _ = try self.expect(.@">");

        const params = self.scratch.items[scratch_top..];
        const extra_start = try self.tree.addExtraSlice(params);
        const count: u32 = @intCast(params.len);

        return self.tree.addNode(.{
            .tag = .type_parameterized,
            .main_token = main_token,
            .data = .{ .lhs = extra_start, .rhs = count },
        });
    }

    // ============================================================
    // Attributes
    // ============================================================

    const AttrSpan = struct {
        start: u32,
        len: u32,
    };

    fn parseAttributes(self: *Parser) ParseError!AttrSpan {
        const scratch_top = self.scratch.items.len;
        defer self.scratch.shrinkRetainingCapacity(scratch_top);

        while (self.peekTag() == .@"@") {
            const at_token = self.token_idx;
            self.advance(); // consume `@`
            const name_token = self.token_idx;
            self.advance(); // consume attribute name

            var args_start: u32 = 0;
            var args_len: u32 = 0;
            if (self.peekTag() == .@"(") {
                self.advance(); // consume `(`
                const scratch_args_top = self.scratch.items.len;

                while (self.peekTag() != .@")" and self.peekTag() != .eof) {
                    const arg = try self.parseExpr();
                    try self.scratch.append(self.allocator,arg);
                    if (self.peekTag() == .@",") self.advance();
                }
                _ = try self.expect(.@")");

                const args = self.scratch.items[scratch_args_top..];
                args_start = try self.tree.addExtraSlice(args);
                args_len = @intCast(args.len);
                self.scratch.shrinkRetainingCapacity(scratch_args_top);
            }

            const attr_node = try self.tree.addNode(.{
                .tag = .attribute,
                .main_token = at_token,
                .data = .{ .lhs = name_token, .rhs = args_start | (args_len << 16) },
            });
            try self.scratch.append(self.allocator,attr_node);
        }

        const attrs = self.scratch.items[scratch_top..];
        if (attrs.len == 0) return .{ .start = 0, .len = 0 };

        const start = try self.tree.addExtraSlice(attrs);
        return .{ .start = start, .len = @intCast(attrs.len) };
    }

    // ============================================================
    // Token helpers
    // ============================================================

    fn peekTag(self: *const Parser) Tag {
        if (self.token_idx >= self.tree.tokens.items.len) return .eof;
        return self.tree.tokens.items[self.token_idx].tag;
    }

    fn advance(self: *Parser) void {
        if (self.token_idx < self.tree.tokens.items.len) {
            self.token_idx += 1;
        }
    }

    fn expect(self: *Parser, expected: Tag) ParseError!u32 {
        if (self.peekTag() == expected) {
            const tok = self.token_idx;
            self.advance();
            return tok;
        }
        return ParseError.UnexpectedToken;
    }

    fn skipSemicolon(self: *Parser) void {
        if (self.peekTag() == .@";") self.advance();
    }

    fn isAssignOp(tag: Tag) bool {
        return switch (tag) {
            .@"=", .plus_eq, .minus_eq, .star_eq, .slash_eq,
            .percent_eq, .amp_eq, .pipe_eq, .caret_eq,
            => true,
            else => false,
        };
    }
};

// ============================================================
// Public API
// ============================================================

pub fn parseSource(allocator: std.mem.Allocator, source: []const u8) !Ast {
    var tree = Ast.init(allocator);
    errdefer tree.deinit();

    try Parser.tokenize(&tree, source);

    var parser = Parser.init(&tree, allocator);
    defer parser.deinit();

    _ = try parser.parse();
    return tree;
}

// ============================================================
// Tests
// ============================================================

test "parse simple compute shader" {
    const source =
        \\enable f16;
        \\
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(64)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    data[id.x] = data[id.x] * 2.0;
        \\}
    ;

    var tree = try parseSource(std.testing.allocator, source);
    defer tree.deinit();

    // Root node should have declarations.
    const root = tree.nodes.items[0];
    try std.testing.expectEqual(NodeTag.root, root.tag);
    const decl_count = root.data.rhs;
    try std.testing.expect(decl_count >= 3); // enable + var + fn
}

test "parse struct" {
    const source =
        \\struct Params {
        \\    size: u32,
        \\    data: array<f32, 16>,
        \\}
    ;
    var tree = try parseSource(std.testing.allocator, source);
    defer tree.deinit();
    const root = tree.nodes.items[0];
    try std.testing.expect(root.data.rhs >= 1);
}

test "parse override" {
    const source =
        \\override BLOCK_SIZE: u32 = 64u;
        \\override USE_F16: bool = false;
    ;
    var tree = try parseSource(std.testing.allocator, source);
    defer tree.deinit();
    const root = tree.nodes.items[0];
    try std.testing.expectEqual(@as(u32, 2), root.data.rhs);
}

test "parse multiple entry points" {
    const source =
        \\fn helper(x: f32) -> f32 {
        \\    return x * 2.0;
        \\}
        \\
        \\@compute @workgroup_size(64)
        \\fn main_a(@builtin(global_invocation_id) id: vec3u) {
        \\    let x = helper(1.0);
        \\}
        \\
        \\@compute @workgroup_size(128)
        \\fn main_b(@builtin(global_invocation_id) id: vec3u) {
        \\    let y = helper(2.0);
        \\}
    ;
    var tree = try parseSource(std.testing.allocator, source);
    defer tree.deinit();
    const root = tree.nodes.items[0];
    try std.testing.expectEqual(@as(u32, 3), root.data.rhs);
}
