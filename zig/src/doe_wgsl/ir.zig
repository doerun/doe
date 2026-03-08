const std = @import("std");

pub const TypeId = u32;
pub const ExprId = u32;
pub const StmtId = u32;
pub const StructId = u32;
pub const FunctionId = u32;
pub const GlobalId = u32;
pub const INVALID_TYPE: TypeId = std.math.maxInt(u32);

pub const Range = struct {
    start: u32 = 0,
    len: u32 = 0,
};

pub const AddressSpace = enum {
    function,
    private,
    workgroup,
    uniform,
    storage,
    handle,
};

pub const AccessMode = enum {
    read,
    write,
    read_write,
};

pub const ShaderStage = enum {
    compute,
    vertex,
    fragment,
};

pub const Builtin = enum {
    none,
    position,
    frag_depth,
    front_facing,
    global_invocation_id,
    local_invocation_id,
    local_invocation_index,
    workgroup_id,
    num_workgroups,
    sample_index,
    sample_mask,
    vertex_index,
    instance_index,
};

pub const Interpolation = enum {
    perspective,
    linear,
    flat,
};

pub const IoAttr = struct {
    builtin: Builtin = .none,
    location: ?u32 = null,
    interpolation: ?Interpolation = null,
    invariant: bool = false,
};

pub const BindingPoint = struct {
    group: u32,
    binding: u32,
};

pub const GlobalClass = enum {
    var_,
    const_,
    override_,
    input,
    output,
};

pub const ScalarType = enum {
    void,
    bool,
    abstract_int,
    abstract_float,
    i32,
    u32,
    f32,
    f16,
};

pub const TextureFormat = enum {
    rgba8unorm,
};

pub const Type = union(enum) {
    scalar: ScalarType,
    vector: struct {
        elem: TypeId,
        len: u8,
    },
    matrix: struct {
        elem: TypeId,
        columns: u8,
        rows: u8,
    },
    array: struct {
        elem: TypeId,
        len: ?u32,
    },
    atomic: TypeId,
    struct_: StructId,
    sampler: void,
    texture_2d: TypeId,
    storage_texture_2d: struct {
        format: TextureFormat,
        access: AccessMode,
    },
    ref: struct {
        elem: TypeId,
        addr_space: AddressSpace,
        access: AccessMode,
    },
};

pub const TypeStore = struct {
    allocator: std.mem.Allocator,
    items: std.ArrayListUnmanaged(Type) = .{},

    pub fn init(allocator: std.mem.Allocator) TypeStore {
        return .{ .allocator = allocator };
    }

    pub fn deinit(self: *TypeStore) void {
        self.items.deinit(self.allocator);
    }

    pub fn intern(self: *TypeStore, candidate: Type) !TypeId {
        for (self.items.items, 0..) |existing, index| {
            if (type_eql(existing, candidate)) return @intCast(index);
        }
        const next_index: TypeId = @intCast(self.items.items.len);
        try self.items.append(self.allocator, candidate);
        return next_index;
    }

    pub fn get(self: *const TypeStore, ty: TypeId) Type {
        return self.items.items[ty];
    }
};

fn type_eql(lhs: Type, rhs: Type) bool {
    return switch (lhs) {
        .scalar => |lhs_scalar| switch (rhs) {
            .scalar => |rhs_scalar| lhs_scalar == rhs_scalar,
            else => false,
        },
        .vector => |lhs_vec| switch (rhs) {
            .vector => |rhs_vec| lhs_vec.elem == rhs_vec.elem and lhs_vec.len == rhs_vec.len,
            else => false,
        },
        .matrix => |lhs_mat| switch (rhs) {
            .matrix => |rhs_mat| lhs_mat.elem == rhs_mat.elem and lhs_mat.columns == rhs_mat.columns and lhs_mat.rows == rhs_mat.rows,
            else => false,
        },
        .array => |lhs_arr| switch (rhs) {
            .array => |rhs_arr| lhs_arr.elem == rhs_arr.elem and lhs_arr.len == rhs_arr.len,
            else => false,
        },
        .atomic => |lhs_child| switch (rhs) {
            .atomic => |rhs_child| lhs_child == rhs_child,
            else => false,
        },
        .struct_ => |lhs_struct| switch (rhs) {
            .struct_ => |rhs_struct| lhs_struct == rhs_struct,
            else => false,
        },
        .sampler => switch (rhs) {
            .sampler => true,
            else => false,
        },
        .texture_2d => |lhs_sample| switch (rhs) {
            .texture_2d => |rhs_sample| lhs_sample == rhs_sample,
            else => false,
        },
        .storage_texture_2d => |lhs_storage| switch (rhs) {
            .storage_texture_2d => |rhs_storage| lhs_storage.format == rhs_storage.format and lhs_storage.access == rhs_storage.access,
            else => false,
        },
        .ref => |lhs_ref| switch (rhs) {
            .ref => |rhs_ref| lhs_ref.elem == rhs_ref.elem and lhs_ref.addr_space == rhs_ref.addr_space and lhs_ref.access == rhs_ref.access,
            else => false,
        },
    };
}

pub const StructField = struct {
    name: []const u8,
    ty: TypeId,
    io: ?IoAttr = null,

    fn deinit(self: *StructField, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
    }
};

pub const StructDef = struct {
    name: []const u8,
    fields: std.ArrayListUnmanaged(StructField) = .{},

    pub fn deinit(self: *StructDef, allocator: std.mem.Allocator) void {
        for (self.fields.items) |*field| field.deinit(allocator);
        self.fields.deinit(allocator);
        allocator.free(self.name);
    }
};

pub const ConstantValue = union(enum) {
    bool: bool,
    int: u64,
    float: f64,
};

pub const Global = struct {
    name: []const u8,
    ty: TypeId,
    class: GlobalClass,
    addr_space: ?AddressSpace = null,
    access: ?AccessMode = null,
    binding: ?BindingPoint = null,
    io: ?IoAttr = null,
    initializer: ?ConstantValue = null,

    pub fn deinit(self: *Global, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
    }
};

pub const Param = struct {
    name: []const u8,
    ty: TypeId,
    io: ?IoAttr = null,

    fn deinit(self: *Param, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
    }
};

pub const Local = struct {
    name: []const u8,
    ty: TypeId,
    mutable: bool,

    fn deinit(self: *Local, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
    }
};

pub const ExprCategory = enum {
    value,
    ref,
};

pub const UnaryOp = enum {
    neg,
    not,
    bit_not,
};

pub const BinaryOp = enum {
    add,
    sub,
    mul,
    div,
    rem,
    bit_and,
    bit_or,
    bit_xor,
    shift_left,
    shift_right,
    equal,
    not_equal,
    less,
    less_equal,
    greater,
    greater_equal,
    logical_and,
    logical_or,
};

pub const AssignOp = enum {
    assign,
    add,
    sub,
    mul,
    div,
    rem,
    bit_and,
    bit_or,
    bit_xor,
};

pub const CallKind = enum {
    user,
    builtin,
};

pub const Expr = union(enum) {
    bool_lit: bool,
    int_lit: u64,
    float_lit: f64,
    param_ref: u32,
    local_ref: u32,
    global_ref: u32,
    load: ExprId,
    unary: struct {
        op: UnaryOp,
        operand: ExprId,
    },
    binary: struct {
        op: BinaryOp,
        lhs: ExprId,
        rhs: ExprId,
    },
    call: struct {
        name: []const u8,
        kind: CallKind,
        args: Range,
    },
    construct: struct {
        ty: TypeId,
        args: Range,
    },
    member: struct {
        base: ExprId,
        field_name: []const u8,
        field_index: u32,
    },
    index: struct {
        base: ExprId,
        index: ExprId,
    },
};

pub const ExprNode = struct {
    ty: TypeId,
    category: ExprCategory,
    data: Expr,

    fn deinit(self: *ExprNode, allocator: std.mem.Allocator) void {
        switch (self.data) {
            .call => |*call| allocator.free(call.name),
            .member => |*member| allocator.free(member.field_name),
            else => {},
        }
    }
};

pub const LoopKind = enum {
    loop,
    while_loop,
    for_loop,
};

pub const SwitchCase = struct {
    selectors: std.ArrayListUnmanaged(ExprId) = .{},
    body: StmtId,
    is_default: bool,

    fn deinit(self: *SwitchCase, allocator: std.mem.Allocator) void {
        self.selectors.deinit(allocator);
    }
};

pub const Stmt = union(enum) {
    block: Range,
    local_decl: struct {
        local: u32,
        initializer: ?ExprId,
        is_const: bool,
    },
    expr: ExprId,
    assign: struct {
        op: AssignOp,
        lhs: ExprId,
        rhs: ExprId,
    },
    return_: ?ExprId,
    if_: struct {
        cond: ExprId,
        then_block: StmtId,
        else_block: ?StmtId,
    },
    loop_: struct {
        kind: LoopKind,
        init: ?StmtId,
        cond: ?ExprId,
        continuing: ?StmtId,
        body: StmtId,
    },
    switch_: struct {
        expr: ExprId,
        cases: Range,
    },
    break_: void,
    continue_: void,
    discard_: void,
};

pub const Function = struct {
    name: []const u8,
    return_type: TypeId,
    stage: ?ShaderStage = null,
    workgroup_size: [3]u32 = .{ 1, 1, 1 },
    params: std.ArrayListUnmanaged(Param) = .{},
    locals: std.ArrayListUnmanaged(Local) = .{},
    exprs: std.ArrayListUnmanaged(ExprNode) = .{},
    expr_args: std.ArrayListUnmanaged(ExprId) = .{},
    stmts: std.ArrayListUnmanaged(Stmt) = .{},
    stmt_children: std.ArrayListUnmanaged(StmtId) = .{},
    switch_cases: std.ArrayListUnmanaged(SwitchCase) = .{},
    root_stmt: StmtId = 0,

    pub fn deinit(self: *Function, allocator: std.mem.Allocator) void {
        allocator.free(self.name);
        for (self.params.items) |*param| param.deinit(allocator);
        self.params.deinit(allocator);
        for (self.locals.items) |*local| local.deinit(allocator);
        self.locals.deinit(allocator);
        for (self.exprs.items) |*expr| expr.deinit(allocator);
        self.exprs.deinit(allocator);
        self.expr_args.deinit(allocator);
        self.stmts.deinit(allocator);
        self.stmt_children.deinit(allocator);
        for (self.switch_cases.items) |*case_node| case_node.deinit(allocator);
        self.switch_cases.deinit(allocator);
    }

    pub fn append_expr(self: *Function, allocator: std.mem.Allocator, expr: ExprNode) !ExprId {
        const next: ExprId = @intCast(self.exprs.items.len);
        try self.exprs.append(allocator, expr);
        return next;
    }

    pub fn append_stmt(self: *Function, allocator: std.mem.Allocator, stmt: Stmt) !StmtId {
        const next: StmtId = @intCast(self.stmts.items.len);
        try self.stmts.append(allocator, stmt);
        return next;
    }

    pub fn append_expr_args(self: *Function, allocator: std.mem.Allocator, args: []const ExprId) !Range {
        const start: u32 = @intCast(self.expr_args.items.len);
        try self.expr_args.appendSlice(allocator, args);
        return .{ .start = start, .len = @intCast(args.len) };
    }

    pub fn append_stmt_children(self: *Function, allocator: std.mem.Allocator, children: []const StmtId) !Range {
        const start: u32 = @intCast(self.stmt_children.items.len);
        try self.stmt_children.appendSlice(allocator, children);
        return .{ .start = start, .len = @intCast(children.len) };
    }
}

pub const EntryPoint = struct {
    function: FunctionId,
    stage: ShaderStage,
    workgroup_size: [3]u32,
};

pub const Module = struct {
    allocator: std.mem.Allocator,
    types: TypeStore,
    structs: std.ArrayListUnmanaged(StructDef) = .{},
    globals: std.ArrayListUnmanaged(Global) = .{},
    functions: std.ArrayListUnmanaged(Function) = .{},
    entry_points: std.ArrayListUnmanaged(EntryPoint) = .{},

    pub fn init(allocator: std.mem.Allocator) Module {
        return .{
            .allocator = allocator,
            .types = TypeStore.init(allocator),
        };
    }

    pub fn deinit(self: *Module) void {
        for (self.structs.items) |*struct_def| struct_def.deinit(self.allocator);
        self.structs.deinit(self.allocator);
        for (self.globals.items) |*global| global.deinit(self.allocator);
        self.globals.deinit(self.allocator);
        for (self.functions.items) |*function| function.deinit(self.allocator);
        self.functions.deinit(self.allocator);
        self.entry_points.deinit(self.allocator);
        self.types.deinit();
    }
};

pub fn dup_string(allocator: std.mem.Allocator, value: []const u8) ![]const u8 {
    return try allocator.dupe(u8, value);
}

pub fn is_scalar(store: *const TypeStore, ty: TypeId, scalar: ScalarType) bool {
    if (ty == INVALID_TYPE) return false;
    return switch (store.get(ty)) {
        .scalar => |kind| kind == scalar,
        else => false,
    };
}
