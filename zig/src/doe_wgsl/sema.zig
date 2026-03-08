const std = @import("std");
const ast_mod = @import("ast.zig");
const token_mod = @import("token.zig");
const ir = @import("ir.zig");

const Ast = ast_mod.Ast;
const Node = ast_mod.Node;
const NodeTag = ast_mod.NodeTag;
const NULL_NODE = ast_mod.NULL_NODE;
const Tag = token_mod.Tag;

pub const AnalyzeError = error{
    OutOfMemory,
    DuplicateSymbol,
    InvalidAttribute,
    InvalidType,
    InvalidWgsl,
    TypeMismatch,
    UnknownIdentifier,
    UnknownType,
    UnsupportedConstruct,
    UnsupportedBuiltin,
};

pub const SymbolRef = union(enum) {
    none,
    global: u32,
    function: u32,
    param: u32,
    local: u32,
};

pub const NodeInfo = struct {
    ty: ir.TypeId = ir.INVALID_TYPE,
    symbol: SymbolRef = .none,
    category: ir.ExprCategory = .value,
};

pub const AliasInfo = struct {
    name: []const u8,
    ty: ir.TypeId,

    fn deinit(self: *AliasInfo, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
    }
};

pub const StructFieldInfo = struct {
    name: []const u8,
    ty: ir.TypeId,
    io: ?ir.IoAttr = null,

    fn deinit(self: *StructFieldInfo, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
    }
};

pub const StructInfo = struct {
    name: []const u8,
    struct_id: ir.StructId,
    ty: ir.TypeId,
    fields: std.ArrayListUnmanaged(StructFieldInfo) = .{},

    fn deinit(self: *StructInfo, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
        for (self.fields.items) |*field| field.deinit(allocator);
        self.fields.deinit(allocator);
    }
};

pub const GlobalInfo = struct {
    name: []const u8,
    node_idx: u32,
    ty: ir.TypeId,
    class: ir.GlobalClass,
    addr_space: ?ir.AddressSpace = null,
    access: ?ir.AccessMode = null,
    binding: ?ir.BindingPoint = null,
    io: ?ir.IoAttr = null,

    fn deinit(self: *GlobalInfo, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
    }
};

pub const ParamInfo = struct {
    name: []const u8,
    ty: ir.TypeId,
    io: ?ir.IoAttr = null,

    fn deinit(self: *ParamInfo, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
    }
};

pub const LocalInfo = struct {
    name: []const u8,
    ty: ir.TypeId,
    mutable: bool,

    fn deinit(self: *LocalInfo, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
    }
};

pub const FunctionInfo = struct {
    name: []const u8,
    node_idx: u32,
    return_type: ir.TypeId,
    stage: ?ir.ShaderStage = null,
    workgroup_size: [3]u32 = .{ 1, 1, 1 },
    params: std.ArrayListUnmanaged(ParamInfo) = .{},
    locals: std.ArrayListUnmanaged(LocalInfo) = .{},

    fn deinit(self: *FunctionInfo, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
        for (self.params.items) |*param| param.deinit(allocator);
        self.params.deinit(allocator);
        for (self.locals.items) |*local| local.deinit(allocator);
        self.locals.deinit(allocator);
    }
};

pub const SemanticModule = struct {
    allocator: std.mem.Allocator,
    tree: *const Ast,
    types: ir.TypeStore,
    node_info: std.ArrayListUnmanaged(NodeInfo) = .{},
    globals: std.ArrayListUnmanaged(GlobalInfo) = .{},
    functions: std.ArrayListUnmanaged(FunctionInfo) = .{},
    structs: std.ArrayListUnmanaged(StructInfo) = .{},
    aliases: std.ArrayListUnmanaged(AliasInfo) = .{},
    global_map: std.StringHashMapUnmanaged(u32) = .{},
    function_map: std.StringHashMapUnmanaged(u32) = .{},
    struct_map: std.StringHashMapUnmanaged(u32) = .{},
    alias_map: std.StringHashMapUnmanaged(u32) = .{},
    void_type: ir.TypeId = ir.INVALID_TYPE,
    bool_type: ir.TypeId = ir.INVALID_TYPE,
    abstract_int_type: ir.TypeId = ir.INVALID_TYPE,
    abstract_float_type: ir.TypeId = ir.INVALID_TYPE,
    i32_type: ir.TypeId = ir.INVALID_TYPE,
    u32_type: ir.TypeId = ir.INVALID_TYPE,
    f32_type: ir.TypeId = ir.INVALID_TYPE,
    f16_type: ir.TypeId = ir.INVALID_TYPE,
    sampler_type: ir.TypeId = ir.INVALID_TYPE,

    pub fn deinit(self: *SemanticModule) void {
        self.node_info.deinit(self.allocator);
        for (self.globals.items) |*global| global.deinit(self.allocator);
        self.globals.deinit(self.allocator);
        for (self.functions.items) |*function| function.deinit(self.allocator);
        self.functions.deinit(self.allocator);
        for (self.structs.items) |*struct_info| struct_info.deinit(self.allocator);
        self.structs.deinit(self.allocator);
        for (self.aliases.items) |*alias_info| alias_info.deinit(self.allocator);
        self.aliases.deinit(self.allocator);
        self.global_map.deinit(self.allocator);
        self.function_map.deinit(self.allocator);
        self.struct_map.deinit(self.allocator);
        self.alias_map.deinit(self.allocator);
        self.types.deinit();
    }

    pub fn nodeType(self: *const SemanticModule, node_idx: u32) ir.TypeId {
        return self.node_info.items[node_idx].ty;
    }

    pub fn nodeSymbol(self: *const SemanticModule, node_idx: u32) SymbolRef {
        return self.node_info.items[node_idx].symbol;
    }

    pub fn nodeCategory(self: *const SemanticModule, node_idx: u32) ir.ExprCategory {
        return self.node_info.items[node_idx].category;
    }
};

pub fn analyze(allocator: std.mem.Allocator, tree: *const Ast) !SemanticModule {
    var module = SemanticModule{
        .allocator = allocator,
        .tree = tree,
        .types = ir.TypeStore.init(allocator),
    };
    errdefer module.deinit();

    try init_builtin_types(&module);
    try module.node_info.resize(allocator, tree.nodes.items.len);
    @memset(module.node_info.items, NodeInfo{});

    var analyzer = Analyzer{ .module = &module };
    try analyzer.run();
    return module;
}

const Scope = struct {
    bindings: std.StringHashMapUnmanaged(SymbolRef) = .{},

    fn deinit(self: *Scope, allocator: std.mem.Allocator) void {
        self.bindings.deinit(allocator);
    }
};

const BodyAnalyzer = struct {
    parent: *Analyzer,
    function_index: u32,
    scopes: std.ArrayListUnmanaged(Scope) = .{},

    fn deinit(self: *BodyAnalyzer) void {
        for (self.scopes.items) |*scope| scope.deinit(self.parent.module.allocator);
        self.scopes.deinit(self.parent.module.allocator);
    }

    fn function(self: *BodyAnalyzer) *FunctionInfo {
        return &self.parent.module.functions.items[self.function_index];
    }

    fn push_scope(self: *BodyAnalyzer) !void {
        try self.scopes.append(self.parent.module.allocator, .{});
    }

    fn pop_scope(self: *BodyAnalyzer) void {
        var scope = self.scopes.pop();
        scope.deinit(self.parent.module.allocator);
    }

    fn bind_name(self: *BodyAnalyzer, name: []const u8, symbol: SymbolRef) !void {
        var scope = &self.scopes.items[self.scopes.items.len - 1];
        if (scope.bindings.contains(name)) return error.DuplicateSymbol;
        try scope.bindings.put(self.parent.module.allocator, name, symbol);
    }

    fn resolve_name(self: *BodyAnalyzer, name: []const u8) ?SymbolRef {
        var i: usize = self.scopes.items.len;
        while (i > 0) {
            i -= 1;
            if (self.scopes.items[i].bindings.get(name)) |symbol| return symbol;
        }
        if (self.parent.module.global_map.get(name)) |global_index| return .{ .global = global_index };
        if (self.parent.module.function_map.get(name)) |fn_index| return .{ .function = fn_index };
        return null;
    }
};

const Analyzer = struct {
    module: *SemanticModule,

    fn run(self: *Analyzer) !void {
        const root = self.module.tree.nodes.items[0];
        const decl_start = root.data.lhs;
        const decl_count = root.data.rhs;

        var i: u32 = 0;
        while (i < decl_count) : (i += 1) {
            const decl_idx = self.module.tree.extra_data.items[decl_start + i];
            try self.register_top_level(decl_idx);
        }

        i = 0;
        while (i < decl_count) : (i += 1) {
            const decl_idx = self.module.tree.extra_data.items[decl_start + i];
            try self.resolve_top_level(decl_idx);
        }

        i = 0;
        while (i < decl_count) : (i += 1) {
            const decl_idx = self.module.tree.extra_data.items[decl_start + i];
            const node = self.module.tree.nodes.items[decl_idx];
            if (node.tag == .fn_decl) {
                const name = self.module.tree.tokenSlice(self.module.tree.extra_data.items[node.data.lhs]);
                const fn_index = self.module.function_map.get(name) orelse return error.InvalidWgsl;
                try self.analyze_function_body(fn_index);
            }
        }
    }

    fn register_top_level(self: *Analyzer, node_idx: u32) !void {
        const node = self.module.tree.nodes.items[node_idx];
        switch (node.tag) {
            .struct_decl => try self.register_struct(node),
            .alias_decl => try self.register_alias(node),
            .global_var, .const_decl, .override_decl => try self.register_global(node, node_idx),
            .fn_decl => try self.register_function(node, node_idx),
            else => {},
        }
    }

    fn resolve_top_level(self: *Analyzer, node_idx: u32) !void {
        const node = self.module.tree.nodes.items[node_idx];
        switch (node.tag) {
            .struct_decl => try self.resolve_struct(node),
            .alias_decl => try self.resolve_alias(node),
            .global_var, .const_decl, .override_decl => try self.resolve_global(node, node_idx),
            .fn_decl => try self.resolve_function_signature(node, node_idx),
            else => {},
        }
    }

    fn register_struct(self: *Analyzer, node: Node) !void {
        const name = self.module.tree.tokenSlice(node.data.lhs);
        if (self.module.struct_map.contains(name)) return error.DuplicateSymbol;
        const name_copy = try ir.dup_string(self.module.allocator, name);
        const struct_id: ir.StructId = @intCast(self.module.structs.items.len);
        const ty = try self.module.types.intern(.{ .struct_ = struct_id });
        try self.module.structs.append(self.module.allocator, .{
            .name = name_copy,
            .struct_id = struct_id,
            .ty = ty,
        });
        try self.module.struct_map.put(self.module.allocator, name_copy, struct_id);
    }

    fn register_alias(self: *Analyzer, node: Node) !void {
        const name = self.module.tree.tokenSlice(node.main_token + 1);
        if (self.module.alias_map.contains(name)) return error.DuplicateSymbol;
        const copy = try ir.dup_string(self.module.allocator, name);
        const idx: u32 = @intCast(self.module.aliases.items.len);
        try self.module.aliases.append(self.module.allocator, .{ .name = copy, .ty = ir.INVALID_TYPE });
        try self.module.alias_map.put(self.module.allocator, copy, idx);
    }

    fn register_global(self: *Analyzer, node: Node, node_idx: u32) !void {
        const name = switch (node.tag) {
            .global_var => self.module.tree.tokenSlice(self.module.tree.extra_data.items[node.data.rhs]),
            .const_decl, .override_decl => self.module.tree.tokenSlice(node.main_token + 1),
            else => return error.InvalidWgsl,
        };
        if (self.module.global_map.contains(name)) return error.DuplicateSymbol;
        const copy = try ir.dup_string(self.module.allocator, name);
        const idx: u32 = @intCast(self.module.globals.items.len);
        try self.module.globals.append(self.module.allocator, .{
            .name = copy,
            .node_idx = node_idx,
            .ty = ir.INVALID_TYPE,
            .class = switch (node.tag) {
                .global_var => .var_,
                .const_decl => .const_,
                .override_decl => .override_,
                else => .var_,
            },
        });
        try self.module.global_map.put(self.module.allocator, copy, idx);
    }

    fn register_function(self: *Analyzer, node: Node, node_idx: u32) !void {
        const name = self.module.tree.tokenSlice(self.module.tree.extra_data.items[node.data.lhs]);
        if (self.module.function_map.contains(name)) return error.DuplicateSymbol;
        const copy = try ir.dup_string(self.module.allocator, name);
        const idx: u32 = @intCast(self.module.functions.items.len);
        try self.module.functions.append(self.module.allocator, .{
            .name = copy,
            .node_idx = node_idx,
            .return_type = self.module.void_type,
        });
        try self.module.function_map.put(self.module.allocator, copy, idx);
    }

    fn resolve_struct(self: *Analyzer, node: Node) !void {
        const packed = node.data.rhs;
        const member_start = packed & 0xFFFF;
        const member_count = packed >> 16;
        const struct_id = self.module.struct_map.get(self.module.tree.tokenSlice(node.data.lhs)) orelse return error.InvalidWgsl;
        var struct_info = &self.module.structs.items[struct_id];

        var i: u32 = 0;
        while (i < member_count) : (i += 1) {
            const member_idx = self.module.tree.extra_data.items[member_start + i];
            const member = self.module.tree.nodes.items[member_idx];
            const field_ty = try self.resolve_type_node(member.data.lhs);
            const field_name = try ir.dup_string(self.module.allocator, self.module.tree.tokenSlice(member.main_token));
            const io = try self.parse_io_attr(member.data.rhs & 0xFFFF, member.data.rhs >> 16);
            try struct_info.fields.append(self.module.allocator, .{
                .name = field_name,
                .ty = field_ty,
                .io = io,
            });
        }
    }

    fn resolve_alias(self: *Analyzer, node: Node) !void {
        const name = self.module.tree.tokenSlice(node.main_token + 1);
        const alias_index = self.module.alias_map.get(name) orelse return error.InvalidWgsl;
        self.module.aliases.items[alias_index].ty = try self.resolve_type_node(node.data.lhs);
    }

    fn resolve_global(self: *Analyzer, node: Node, _: u32) !void {
        const global_name = switch (node.tag) {
            .global_var => self.module.tree.tokenSlice(self.module.tree.extra_data.items[node.data.rhs]),
            .const_decl, .override_decl => self.module.tree.tokenSlice(node.main_token + 1),
            else => return error.InvalidWgsl,
        };
        const global_index = self.module.global_map.get(global_name) orelse return error.InvalidWgsl;
        var global_info = &self.module.globals.items[global_index];

        switch (node.tag) {
            .global_var => {
                const extra = self.module.tree.extra_data.items;
                const base = node.data.rhs;
                global_info.ty = try self.resolve_type_node(node.data.lhs);
                if (extra[base + 1] != 0) global_info.addr_space = try parse_address_space(self.module.tree.tokenSlice(extra[base + 1]));
                if (extra[base + 2] != 0) global_info.access = try parse_access(self.module.tree.tokenSlice(extra[base + 2]));
                global_info.binding = try self.parse_binding(extra[base + 4], extra[base + 5]);
            },
            .const_decl, .override_decl => {
                global_info.ty = if (node.data.lhs != NULL_NODE) try self.resolve_type_node(node.data.lhs) else ir.INVALID_TYPE;
                if (node.data.rhs != NULL_NODE) {
                    const init_ty = try self.analyze_expr(node.data.rhs, null);
                    if (global_info.ty == ir.INVALID_TYPE) {
                        global_info.ty = init_ty;
                    } else if (!self.type_compatible(global_info.ty, init_ty)) {
                        return error.TypeMismatch;
                    }
                }
                if (global_info.ty == ir.INVALID_TYPE) return error.InvalidType;
            },
            else => return error.InvalidWgsl,
        }
    }

    fn resolve_function_signature(self: *Analyzer, node: Node, _: u32) !void {
        const extra = self.module.tree.extra_data.items;
        const extra_start = node.data.lhs;
        const name = self.module.tree.tokenSlice(extra[extra_start + 0]);
        const function_index = self.module.function_map.get(name) orelse return error.InvalidWgsl;
        var function_info = &self.module.functions.items[function_index];

        const params_start = extra[extra_start + 1];
        const params_len = extra[extra_start + 2];
        const return_type_node = extra[extra_start + 3];
        const attrs_start = extra[extra_start + 4];
        const attrs_len = extra[extra_start + 5];

        function_info.return_type = if (return_type_node != NULL_NODE) try self.resolve_type_node(return_type_node) else self.module.void_type;
        function_info.stage = try self.parse_stage(attrs_start, attrs_len);
        function_info.workgroup_size = try self.parse_workgroup_size(attrs_start, attrs_len);

        var i: u32 = 0;
        while (i < params_len) : (i += 1) {
            const param_extra_start = extra[params_start + i];
            const param_name = try ir.dup_string(self.module.allocator, self.module.tree.tokenSlice(extra[param_extra_start + 0]));
            const param_ty = try self.resolve_type_node(extra[param_extra_start + 1]);
            const param_io = try self.parse_io_attr(extra[param_extra_start + 2], extra[param_extra_start + 3]);
            try function_info.params.append(self.module.allocator, .{
                .name = param_name,
                .ty = param_ty,
                .io = param_io,
            });
        }
    }

    fn analyze_function_body(self: *Analyzer, function_index: u32) !void {
        var body = BodyAnalyzer{ .parent = self, .function_index = function_index };
        defer body.deinit();
        try body.push_scope();
        for (body.function().params.items, 0..) |param, index| {
            try body.bind_name(param.name, .{ .param = @intCast(index) });
        }

        const fn_node = self.module.tree.nodes.items[body.function().node_idx];
        try self.analyze_stmt(fn_node.data.rhs, &body);
        body.pop_scope();
    }

    fn analyze_stmt(self: *Analyzer, node_idx: u32, body: *BodyAnalyzer) !void {
        const node = self.module.tree.nodes.items[node_idx];
        switch (node.tag) {
            .block => {
                try body.push_scope();
                const stmt_start = node.data.lhs;
                const stmt_count = node.data.rhs;
                var i: u32 = 0;
                while (i < stmt_count) : (i += 1) {
                    try self.analyze_stmt(self.module.tree.extra_data.items[stmt_start + i], body);
                }
                body.pop_scope();
            },
            .var_stmt, .let_stmt, .const_stmt => try self.analyze_local_decl(node, body),
            .return_stmt => {
                const expr_node = node.data.lhs;
                if (expr_node != NULL_NODE) {
                    const expr_ty = try self.analyze_expr(expr_node, body);
                    if (!self.type_compatible(body.function().return_type, expr_ty)) return error.TypeMismatch;
                }
            },
            .if_stmt => {
                _ = try self.analyze_expr(node.data.lhs, body);
                try self.analyze_stmt(node.data.rhs, body);
            },
            .for_stmt => {
                const extra = self.module.tree.extra_data.items;
                const base = node.data.lhs;
                try body.push_scope();
                if (extra[base + 0] != NULL_NODE) try self.analyze_stmt(extra[base + 0], body);
                if (extra[base + 1] != NULL_NODE) _ = try self.analyze_expr(extra[base + 1], body);
                if (extra[base + 2] != NULL_NODE) try self.analyze_stmt(extra[base + 2], body);
                try self.analyze_stmt(node.data.rhs, body);
                body.pop_scope();
            },
            .while_stmt => {
                _ = try self.analyze_expr(node.data.lhs, body);
                try self.analyze_stmt(node.data.rhs, body);
            },
            .loop_stmt => try self.analyze_stmt(node.data.lhs, body),
            .break_stmt => { if (node.data.lhs != NULL_NODE) return error.UnsupportedConstruct; },
            .continue_stmt, .discard_stmt => {},
            .continuing_stmt, .switch_stmt, .switch_case => return error.UnsupportedConstruct,
            .expr_stmt => _ = try self.analyze_expr(node.data.lhs, body),
            .assign_stmt => {
                const lhs_ty = try self.analyze_expr(node.data.lhs, body);
                const lhs_info = self.module.node_info.items[node.data.lhs];
                if (lhs_info.category != .ref) return error.InvalidWgsl;
                const rhs_ty = try self.analyze_expr(node.data.rhs, body);
                if (!self.type_compatible(lhs_ty, rhs_ty)) return error.TypeMismatch;
                self.module.node_info.items[node_idx].ty = lhs_ty;
            },
            else => {},
        }
    }

    fn analyze_local_decl(self: *Analyzer, node: Node, body: *BodyAnalyzer) !void {
        const name = self.module.tree.tokenSlice(node.main_token + 1);
        const explicit_type = if (node.data.lhs != NULL_NODE) try self.resolve_type_node(node.data.lhs) else ir.INVALID_TYPE;
        const init_ty = if (node.data.rhs != NULL_NODE) try self.analyze_expr(node.data.rhs, body) else ir.INVALID_TYPE;
        const resolved_type = blk: {
            if (explicit_type != ir.INVALID_TYPE) break :blk explicit_type;
            if (init_ty != ir.INVALID_TYPE) break :blk init_ty;
            return error.InvalidType;
        };
        if (explicit_type != ir.INVALID_TYPE and init_ty != ir.INVALID_TYPE and !self.type_compatible(explicit_type, init_ty)) {
            return error.TypeMismatch;
        }
        const local_index: u32 = @intCast(body.function().locals.items.len);
        try body.function().locals.append(self.module.allocator, .{
            .name = try ir.dup_string(self.module.allocator, name),
            .ty = resolved_type,
            .mutable = node.tag == .var_stmt,
        });
        try body.bind_name(body.function().locals.items[local_index].name, .{ .local = local_index });
    }

    fn analyze_expr(self: *Analyzer, node_idx: u32, body: ?*BodyAnalyzer) !ir.TypeId {
        const existing = self.module.node_info.items[node_idx];
        if (existing.ty != ir.INVALID_TYPE) return existing.ty;

        const node = self.module.tree.nodes.items[node_idx];
        var info = NodeInfo{};
        info.ty = switch (node.tag) {
            .int_literal => self.module.abstract_int_type,
            .float_literal => self.module.abstract_float_type,
            .bool_literal => self.module.bool_type,
            .ident_expr => try self.resolve_ident_expr(node, body, &info),
            .unary_expr => try self.analyze_unary(node, body),
            .binary_expr => try self.analyze_binary(node, body),
            .call_expr => try self.analyze_call(node, body),
            .member_expr => try self.analyze_member(node, body, &info),
            .index_expr => try self.analyze_index(node, body, &info),
            else => return error.UnsupportedConstruct,
        };
        if (node.tag != .ident_expr and node.tag != .member_expr and node.tag != .index_expr) {
            info.category = .value;
        }
        self.module.node_info.items[node_idx] = info;
        return info.ty;
    }

    fn resolve_ident_expr(self: *Analyzer, node: Node, body: ?*BodyAnalyzer, out: *NodeInfo) !ir.TypeId {
        const name = self.module.tree.tokenSlice(node.main_token);
        const symbol = if (body) |ctx| ctx.resolve_name(name) else null;
        if (symbol == null) return error.UnknownIdentifier;
        out.symbol = symbol.?;
        return switch (symbol.?) {
            .global => |index| blk: {
                out.category = .ref;
                break :blk self.module.globals.items[index].ty;
            },
            .param => |index| blk: {
                out.category = .ref;
                break :blk body.?.function().params.items[index].ty;
            },
            .local => |index| blk: {
                out.category = .ref;
                break :blk body.?.function().locals.items[index].ty;
            },
            .function => |index| self.module.functions.items[index].return_type,
            .none => return error.UnknownIdentifier,
        };
    }

    fn analyze_unary(self: *Analyzer, node: Node, body: ?*BodyAnalyzer) !ir.TypeId {
        const operand_ty = try self.analyze_expr(node.data.lhs, body);
        return switch (self.module.tree.tokens.items[node.main_token].tag) {
            .@"-", .@"~" => operand_ty,
            .@"!" => self.module.bool_type,
            else => error.InvalidWgsl,
        };
    }

    fn analyze_binary(self: *Analyzer, node: Node, body: ?*BodyAnalyzer) !ir.TypeId {
        const lhs_ty = try self.analyze_expr(node.data.lhs, body);
        const rhs_ty = try self.analyze_expr(node.data.rhs, body);
        const op = self.module.tree.tokens.items[node.main_token].tag;
        return switch (op) {
            .eq_eq, .not_eq, .@"<", .lte, .@">", .gte, .and_and, .or_or => self.module.bool_type,
            else => if (self.type_compatible(lhs_ty, rhs_ty)) concrete_numeric_type(self.module, lhs_ty, rhs_ty) else error.TypeMismatch,
        };
    }

    fn analyze_call(self: *Analyzer, node: Node, body: ?*BodyAnalyzer) !ir.TypeId {
        const name = self.module.tree.tokenSlice(node.main_token);
        const args_start = node.data.lhs;
        const args_len = node.data.rhs;

        var arg_types_buf: [16]ir.TypeId = undefined;
        if (args_len > arg_types_buf.len) return error.UnsupportedConstruct;
        var i: u32 = 0;
        while (i < args_len) : (i += 1) {
            arg_types_buf[i] = try self.analyze_expr(self.module.tree.extra_data.items[args_start + i], body);
        }

        if (self.try_resolve_named_type(name)) |ty| {
            return ty;
        }
        if (self.module.function_map.get(name)) |function_index| {
            const fn_info = self.module.functions.items[function_index];
            if (fn_info.params.items.len != args_len) return error.TypeMismatch;
            for (fn_info.params.items, 0..) |param, arg_index| {
                if (!self.type_compatible(param.ty, arg_types_buf[arg_index])) return error.TypeMismatch;
            }
            return fn_info.return_type;
        }
        return try self.infer_builtin_call(name, arg_types_buf[0..args_len]);
    }

    fn analyze_member(self: *Analyzer, node: Node, body: ?*BodyAnalyzer, out: *NodeInfo) !ir.TypeId {
        const base_ty = try self.analyze_expr(node.data.lhs, body);
        const field_name = self.module.tree.tokenSlice(node.data.rhs);
        switch (self.module.types.get(base_ty)) {
            .struct_ => |struct_id| {
                const struct_info = self.module.structs.items[struct_id];
                for (struct_info.fields.items) |field| {
                    if (std.mem.eql(u8, field.name, field_name)) {
                        out.category = self.module.node_info.items[node.data.lhs].category;
                        return field.ty;
                    }
                }
                return error.UnknownIdentifier;
            },
            .vector => |vec| {
                const swizzle_len = field_name.len;
                if (swizzle_len == 0 or swizzle_len > 4) return error.InvalidWgsl;
                if (swizzle_len == 1) return vec.elem;
                return try self.module.types.intern(.{ .vector = .{ .elem = vec.elem, .len = @intCast(swizzle_len) } });
            },
            else => return error.InvalidWgsl,
        }
    }

    fn analyze_index(self: *Analyzer, node: Node, body: ?*BodyAnalyzer, out: *NodeInfo) !ir.TypeId {
        const base_ty = try self.analyze_expr(node.data.lhs, body);
        _ = try self.analyze_expr(node.data.rhs, body);
        out.category = self.module.node_info.items[node.data.lhs].category;
        return switch (self.module.types.get(base_ty)) {
            .array => |arr| arr.elem,
            .vector => |vec| vec.elem,
            .matrix => |mat| try self.module.types.intern(.{ .vector = .{ .elem = mat.elem, .len = mat.rows } }),
            else => error.InvalidWgsl,
        };
    }

    fn resolve_type_node(self: *Analyzer, node_idx: u32) !ir.TypeId {
        const node = self.module.tree.nodes.items[node_idx];
        return switch (node.tag) {
            .type_name => try self.resolve_type_name(self.module.tree.tokenSlice(node.main_token)),
            .type_vec_shorthand => try self.resolve_type_name(self.module.tree.tokenSlice(node.main_token)),
            .type_mat_shorthand => try self.resolve_type_name(self.module.tree.tokenSlice(node.main_token)),
            .type_parameterized => try self.resolve_type_parameterized(node),
            else => error.InvalidType,
        };
    }

    fn resolve_type_name(self: *Analyzer, name: []const u8) !ir.TypeId {
        if (std.mem.eql(u8, name, "void")) return self.module.void_type;
        if (std.mem.eql(u8, name, "bool")) return self.module.bool_type;
        if (std.mem.eql(u8, name, "i32")) return self.module.i32_type;
        if (std.mem.eql(u8, name, "u32")) return self.module.u32_type;
        if (std.mem.eql(u8, name, "f32")) return self.module.f32_type;
        if (std.mem.eql(u8, name, "f16")) return self.module.f16_type;
        if (std.mem.eql(u8, name, "sampler")) return self.module.sampler_type;
        if (std.mem.eql(u8, name, "texture_2d")) return try self.module.types.intern(.{ .texture_2d = self.module.f32_type });
        if (self.try_resolve_named_type(name)) |ty| return ty;
        return error.UnknownType;
    }

    pub fn try_resolve_named_type(self: *Analyzer, name: []const u8) ?ir.TypeId {
        if (self.module.struct_map.get(name)) |struct_id| return self.module.structs.items[struct_id].ty;
        if (self.module.alias_map.get(name)) |alias_index| {
            const ty = self.module.aliases.items[alias_index].ty;
            if (ty != ir.INVALID_TYPE) return ty;
        }
        return switch (token_mod.lookupIdent(name)) {
            .kw_vec2f => self.module.types.intern(.{ .vector = .{ .elem = self.module.f32_type, .len = 2 } }) catch null,
            .kw_vec3f => self.module.types.intern(.{ .vector = .{ .elem = self.module.f32_type, .len = 3 } }) catch null,
            .kw_vec4f => self.module.types.intern(.{ .vector = .{ .elem = self.module.f32_type, .len = 4 } }) catch null,
            .kw_vec2u => self.module.types.intern(.{ .vector = .{ .elem = self.module.u32_type, .len = 2 } }) catch null,
            .kw_vec3u => self.module.types.intern(.{ .vector = .{ .elem = self.module.u32_type, .len = 3 } }) catch null,
            .kw_vec4u => self.module.types.intern(.{ .vector = .{ .elem = self.module.u32_type, .len = 4 } }) catch null,
            .kw_vec2i => self.module.types.intern(.{ .vector = .{ .elem = self.module.i32_type, .len = 2 } }) catch null,
            .kw_vec3i => self.module.types.intern(.{ .vector = .{ .elem = self.module.i32_type, .len = 3 } }) catch null,
            .kw_vec4i => self.module.types.intern(.{ .vector = .{ .elem = self.module.i32_type, .len = 4 } }) catch null,
            .kw_vec2h => self.module.types.intern(.{ .vector = .{ .elem = self.module.f16_type, .len = 2 } }) catch null,
            .kw_vec3h => self.module.types.intern(.{ .vector = .{ .elem = self.module.f16_type, .len = 3 } }) catch null,
            .kw_vec4h => self.module.types.intern(.{ .vector = .{ .elem = self.module.f16_type, .len = 4 } }) catch null,
            .kw_mat2x2f => self.module.types.intern(.{ .matrix = .{ .elem = self.module.f32_type, .columns = 2, .rows = 2 } }) catch null,
            .kw_mat3x3f => self.module.types.intern(.{ .matrix = .{ .elem = self.module.f32_type, .columns = 3, .rows = 3 } }) catch null,
            .kw_mat4x4f => self.module.types.intern(.{ .matrix = .{ .elem = self.module.f32_type, .columns = 4, .rows = 4 } }) catch null,
            .kw_mat2x2h => self.module.types.intern(.{ .matrix = .{ .elem = self.module.f16_type, .columns = 2, .rows = 2 } }) catch null,
            .kw_mat3x3h => self.module.types.intern(.{ .matrix = .{ .elem = self.module.f16_type, .columns = 3, .rows = 3 } }) catch null,
            .kw_mat4x4h => self.module.types.intern(.{ .matrix = .{ .elem = self.module.f16_type, .columns = 4, .rows = 4 } }) catch null,
            else => null,
        };
    }

    fn resolve_type_parameterized(self: *Analyzer, node: Node) !ir.TypeId {
        const name = self.module.tree.tokenSlice(node.main_token);
        const params_start = node.data.lhs;
        const params_len = node.data.rhs;
        if (std.mem.eql(u8, name, "vec2") or std.mem.eql(u8, name, "vec3") or std.mem.eql(u8, name, "vec4")) {
            if (params_len != 1) return error.InvalidType;
            const elem = try self.resolve_type_node(self.module.tree.extra_data.items[params_start]);
            const len: u8 = if (std.mem.eql(u8, name, "vec2")) 2 else if (std.mem.eql(u8, name, "vec3")) 3 else 4;
            return try self.module.types.intern(.{ .vector = .{ .elem = elem, .len = len } });
        }
        if (std.mem.eql(u8, name, "mat2x2") or std.mem.eql(u8, name, "mat3x3") or std.mem.eql(u8, name, "mat4x4")) {
            if (params_len != 1) return error.InvalidType;
            const elem = try self.resolve_type_node(self.module.tree.extra_data.items[params_start]);
            const dim: u8 = if (std.mem.eql(u8, name, "mat2x2")) 2 else if (std.mem.eql(u8, name, "mat3x3")) 3 else 4;
            return try self.module.types.intern(.{ .matrix = .{ .elem = elem, .columns = dim, .rows = dim } });
        }
        if (std.mem.eql(u8, name, "array")) {
            if (params_len < 1 or params_len > 2) return error.InvalidType;
            const elem = try self.resolve_type_node(self.module.tree.extra_data.items[params_start]);
            var len: ?u32 = null;
            if (params_len == 2) {
                const len_node = self.module.tree.nodes.items[self.module.tree.extra_data.items[params_start + 1]];
                if (len_node.tag != .int_literal) return error.InvalidType;
                len = try std.fmt.parseInt(u32, self.module.tree.tokenSlice(len_node.main_token), 10);
            }
            return try self.module.types.intern(.{ .array = .{ .elem = elem, .len = len } });
        }
        if (std.mem.eql(u8, name, "atomic")) {
            if (params_len != 1) return error.InvalidType;
            return try self.module.types.intern(.{ .atomic = try self.resolve_type_node(self.module.tree.extra_data.items[params_start]) });
        }
        if (std.mem.eql(u8, name, "texture_2d")) {
            if (params_len != 1) return error.InvalidType;
            return try self.module.types.intern(.{ .texture_2d = try self.resolve_type_node(self.module.tree.extra_data.items[params_start]) });
        }
        if (std.mem.eql(u8, name, "ptr")) {
            if (params_len < 2 or params_len > 3) return error.InvalidType;
            const addr_node = self.module.tree.nodes.items[self.module.tree.extra_data.items[params_start]];
            if (addr_node.tag != .type_name) return error.InvalidType;
            const addr_space = try parse_address_space(self.module.tree.tokenSlice(addr_node.main_token));
            const elem = try self.resolve_type_node(self.module.tree.extra_data.items[params_start + 1]);
            const access = if (params_len == 3) blk: {
                const access_node = self.module.tree.nodes.items[self.module.tree.extra_data.items[params_start + 2]];
                if (access_node.tag != .type_name) return error.InvalidType;
                break :blk try parse_access(self.module.tree.tokenSlice(access_node.main_token));
            } else .read_write;
            return try self.module.types.intern(.{ .ref = .{ .elem = elem, .addr_space = addr_space, .access = access } });
        }
        return error.UnknownType;
    }

    fn parse_stage(self: *Analyzer, attrs_start: u32, attrs_len: u32) !?ir.ShaderStage {
        var stage: ?ir.ShaderStage = null;
        for (self.module.tree.extra_data.items[attrs_start .. attrs_start + attrs_len]) |attr_idx| {
            const attr = self.module.tree.nodes.items[attr_idx];
            const name = self.module.tree.tokenSlice(attr.data.lhs);
            if (std.mem.eql(u8, name, "compute")) stage = .compute;
            if (std.mem.eql(u8, name, "vertex")) stage = .vertex;
            if (std.mem.eql(u8, name, "fragment")) stage = .fragment;
        }
        return stage;
    }

    fn parse_workgroup_size(self: *Analyzer, attrs_start: u32, attrs_len: u32) ![3]u32 {
        var result: [3]u32 = .{ 1, 1, 1 };
        for (self.module.tree.extra_data.items[attrs_start .. attrs_start + attrs_len]) |attr_idx| {
            const attr = self.module.tree.nodes.items[attr_idx];
            if (!std.mem.eql(u8, self.module.tree.tokenSlice(attr.data.lhs), "workgroup_size")) continue;
            const span = decode_packed_span(attr.data.rhs);
            var i: usize = 0;
            while (i < span.len and i < result.len) : (i += 1) {
                const arg_node = self.module.tree.nodes.items[self.module.tree.extra_data.items[span.start + i]];
                if (arg_node.tag != .int_literal) return error.InvalidAttribute;
                result[i] = try std.fmt.parseInt(u32, self.module.tree.tokenSlice(arg_node.main_token), 10);
            }
        }
        return result;
    }

    fn parse_binding(self: *Analyzer, attrs_start: u32, attrs_len: u32) !?ir.BindingPoint {
        var group: ?u32 = null;
        var binding: ?u32 = null;
        for (self.module.tree.extra_data.items[attrs_start .. attrs_start + attrs_len]) |attr_idx| {
            const attr = self.module.tree.nodes.items[attr_idx];
            const name = self.module.tree.tokenSlice(attr.data.lhs);
            const value = try parse_single_int_attr(self.module.tree, attr_idx);
            if (std.mem.eql(u8, name, "group")) group = value;
            if (std.mem.eql(u8, name, "binding")) binding = value;
        }
        if (group != null and binding != null) return .{ .group = group.?, .binding = binding.? };
        return null;
    }

    fn parse_io_attr(self: *Analyzer, attrs_start: u32, attrs_len: u32) !?ir.IoAttr {
        if (attrs_len == 0) return null;
        var result = ir.IoAttr{};
        var seen = false;
        for (self.module.tree.extra_data.items[attrs_start .. attrs_start + attrs_len]) |attr_idx| {
            const attr = self.module.tree.nodes.items[attr_idx];
            const name = self.module.tree.tokenSlice(attr.data.lhs);
            if (std.mem.eql(u8, name, "builtin")) {
                result.builtin = try parse_builtin_attr(self.module.tree, attr_idx);
                seen = true;
            } else if (std.mem.eql(u8, name, "location")) {
                result.location = try parse_single_int_attr(self.module.tree, attr_idx);
                seen = true;
            } else if (std.mem.eql(u8, name, "flat")) {
                result.interpolation = .flat;
                seen = true;
            } else if (std.mem.eql(u8, name, "invariant")) {
                result.invariant = true;
                seen = true;
            }
        }
        return if (seen) result else null;
    }

    fn infer_builtin_call(self: *Analyzer, name: []const u8, arg_types: []const ir.TypeId) !ir.TypeId {
        if (std.mem.eql(u8, name, "workgroupBarrier") or std.mem.eql(u8, name, "storageBarrier")) return self.module.void_type;
        if (std.mem.eql(u8, name, "arrayLength")) return self.module.u32_type;
        if (std.mem.eql(u8, name, "dot")) {
            if (arg_types.len == 0) return error.UnsupportedBuiltin;
            const first = self.module.types.get(arg_types[0]);
            return switch (first) {
                .vector => |vec| vec.elem,
                else => error.UnsupportedBuiltin,
            };
        }
        if (std.mem.eql(u8, name, "textureLoad")) {
            if (arg_types.len == 0) return error.UnsupportedBuiltin;
            const first = self.module.types.get(arg_types[0]);
            return switch (first) {
                .texture_2d => |sample_ty| try self.module.types.intern(.{ .vector = .{ .elem = sample_ty, .len = 4 } }),
                else => error.UnsupportedBuiltin,
            };
        }
        if (std.mem.eql(u8, name, "atomicLoad") or std.mem.eql(u8, name, "atomicStore") or std.mem.eql(u8, name, "atomicAdd") or std.mem.eql(u8, name, "atomicSub") or std.mem.eql(u8, name, "atomicMax") or std.mem.eql(u8, name, "atomicMin") or std.mem.eql(u8, name, "atomicAnd") or std.mem.eql(u8, name, "atomicOr") or std.mem.eql(u8, name, "atomicXor") or std.mem.eql(u8, name, "atomicExchange")) {
            if (arg_types.len == 0) return error.UnsupportedBuiltin;
            return switch (self.module.types.get(arg_types[0])) {
                .atomic => |inner| inner,
                else => arg_types[0],
            };
        }
        if (std.mem.eql(u8, name, "min") or std.mem.eql(u8, name, "max") or std.mem.eql(u8, name, "clamp") or std.mem.eql(u8, name, "select") or std.mem.eql(u8, name, "abs") or std.mem.eql(u8, name, "sqrt") or std.mem.eql(u8, name, "sin") or std.mem.eql(u8, name, "cos") or std.mem.eql(u8, name, "normalize") or std.mem.eql(u8, name, "length") or std.mem.eql(u8, name, "distance")) {
            if (arg_types.len == 0) return error.UnsupportedBuiltin;
            return arg_types[0];
        }
        return error.UnsupportedBuiltin;
    }

    fn type_compatible(self: *Analyzer, expected: ir.TypeId, actual: ir.TypeId) bool {
        if (expected == actual) return true;
        if (expected == ir.INVALID_TYPE or actual == ir.INVALID_TYPE) return false;
        return switch (self.module.types.get(actual)) {
            .scalar => |actual_scalar| switch (self.module.types.get(expected)) {
                .scalar => |expected_scalar| (actual_scalar == .abstract_int and (expected_scalar == .i32 or expected_scalar == .u32)) or
                    (actual_scalar == .abstract_float and (expected_scalar == .f32 or expected_scalar == .f16)),
                else => false,
            },
            else => false,
        };
    }
};

fn init_builtin_types(module: *SemanticModule) !void {
    module.void_type = try module.types.intern(.{ .scalar = .void });
    module.bool_type = try module.types.intern(.{ .scalar = .bool });
    module.abstract_int_type = try module.types.intern(.{ .scalar = .abstract_int });
    module.abstract_float_type = try module.types.intern(.{ .scalar = .abstract_float });
    module.i32_type = try module.types.intern(.{ .scalar = .i32 });
    module.u32_type = try module.types.intern(.{ .scalar = .u32 });
    module.f32_type = try module.types.intern(.{ .scalar = .f32 });
    module.f16_type = try module.types.intern(.{ .scalar = .f16 });
    module.sampler_type = try module.types.intern(.{ .sampler = {} });
}

fn concrete_numeric_type(module: *SemanticModule, lhs: ir.TypeId, rhs: ir.TypeId) ir.TypeId {
    if (lhs == rhs) return lhs;
    if (lhs == module.abstract_int_type) return rhs;
    if (rhs == module.abstract_int_type) return lhs;
    if (lhs == module.abstract_float_type) return rhs;
    if (rhs == module.abstract_float_type) return lhs;
    return lhs;
}

fn decode_packed_span(raw: u32) struct { start: u32, len: u32 } {
    return .{ .start = raw & 0xFFFF, .len = raw >> 16 };
}

fn parse_single_int_attr(tree: *const Ast, attr_idx: u32) !u32 {
    const attr = tree.nodes.items[attr_idx];
    const span = decode_packed_span(attr.data.rhs);
    if (span.len == 0) return error.InvalidAttribute;
    const arg = tree.nodes.items[tree.extra_data.items[span.start]];
    if (arg.tag != .int_literal) return error.InvalidAttribute;
    return try std.fmt.parseInt(u32, tree.tokenSlice(arg.main_token), 10);
}

fn parse_builtin_attr(tree: *const Ast, attr_idx: u32) !ir.Builtin {
    const attr = tree.nodes.items[attr_idx];
    const span = decode_packed_span(attr.data.rhs);
    if (span.len == 0) return error.InvalidAttribute;
    const arg = tree.nodes.items[tree.extra_data.items[span.start]];
    if (arg.tag != .ident_expr) return error.InvalidAttribute;
    const name = tree.tokenSlice(arg.main_token);
    if (std.mem.eql(u8, name, "position")) return .position;
    if (std.mem.eql(u8, name, "frag_depth")) return .frag_depth;
    if (std.mem.eql(u8, name, "front_facing")) return .front_facing;
    if (std.mem.eql(u8, name, "global_invocation_id")) return .global_invocation_id;
    if (std.mem.eql(u8, name, "local_invocation_id")) return .local_invocation_id;
    if (std.mem.eql(u8, name, "local_invocation_index")) return .local_invocation_index;
    if (std.mem.eql(u8, name, "workgroup_id")) return .workgroup_id;
    if (std.mem.eql(u8, name, "num_workgroups")) return .num_workgroups;
    if (std.mem.eql(u8, name, "sample_index")) return .sample_index;
    if (std.mem.eql(u8, name, "sample_mask")) return .sample_mask;
    if (std.mem.eql(u8, name, "vertex_index")) return .vertex_index;
    if (std.mem.eql(u8, name, "instance_index")) return .instance_index;
    return error.InvalidAttribute;
}

fn parse_address_space(name: []const u8) !ir.AddressSpace {
    if (std.mem.eql(u8, name, "function")) return .function;
    if (std.mem.eql(u8, name, "private")) return .private;
    if (std.mem.eql(u8, name, "workgroup")) return .workgroup;
    if (std.mem.eql(u8, name, "uniform")) return .uniform;
    if (std.mem.eql(u8, name, "storage")) return .storage;
    return error.InvalidAttribute;
}

fn parse_access(name: []const u8) !ir.AccessMode {
    if (std.mem.eql(u8, name, "read")) return .read;
    if (std.mem.eql(u8, name, "write")) return .write;
    if (std.mem.eql(u8, name, "read_write")) return .read_write;
    return error.InvalidAttribute;
}
