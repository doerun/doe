const std = @import("std");
const ir = @import("ir.zig");
const spirv = @import("spirv_builder.zig");

pub const EmitError = spirv.EmitError || error{
    InvalidIr,
};

pub const MAX_OUTPUT: usize = 256 * 1024;

pub fn emit(module: *const ir.Module, out: []u8) EmitError!usize {
    var emitter = try Emitter.init(module);
    defer emitter.deinit();
    try emitter.emit_module();
    return emitter.builder.write_binary(out);
}

const Emitter = struct {
    module: *const ir.Module,
    alloc: std.mem.Allocator,
    builder: spirv.Builder,
    type_ids: []u32,
    global_ids: []u32,
    global_buffer_wrapped: []bool,
    function_ids: []u32,
    entry_wrapper_ids: []u32,
    decorated_array_types: std.AutoHashMapUnmanaged(u32, void) = .{},
    decorated_struct_types: std.AutoHashMapUnmanaged(u32, void) = .{},

    fn init(module: *const ir.Module) EmitError!Emitter {
        const alloc = module.allocator;
        const type_ids = try alloc.alloc(u32, module.types.items.items.len);
        errdefer alloc.free(type_ids);
        @memset(type_ids, 0);

        const global_ids = try alloc.alloc(u32, module.globals.items.len);
        errdefer alloc.free(global_ids);
        @memset(global_ids, 0);

        const global_buffer_wrapped = try alloc.alloc(bool, module.globals.items.len);
        errdefer alloc.free(global_buffer_wrapped);
        @memset(global_buffer_wrapped, false);

        const function_ids = try alloc.alloc(u32, module.functions.items.len);
        errdefer alloc.free(function_ids);
        @memset(function_ids, 0);

        const entry_wrapper_ids = try alloc.alloc(u32, module.functions.items.len);
        errdefer alloc.free(entry_wrapper_ids);
        @memset(entry_wrapper_ids, 0);

        return .{
            .module = module,
            .alloc = alloc,
            .builder = spirv.Builder.init(alloc),
            .type_ids = type_ids,
            .global_ids = global_ids,
            .global_buffer_wrapped = global_buffer_wrapped,
            .function_ids = function_ids,
            .entry_wrapper_ids = entry_wrapper_ids,
        };
    }

    fn deinit(self: *Emitter) void {
        self.decorated_struct_types.deinit(self.alloc);
        self.decorated_array_types.deinit(self.alloc);
        self.alloc.free(self.entry_wrapper_ids);
        self.alloc.free(self.function_ids);
        self.alloc.free(self.global_buffer_wrapped);
        self.alloc.free(self.global_ids);
        self.alloc.free(self.type_ids);
        self.builder.deinit();
    }

    fn emit_module(self: *Emitter) EmitError!void {
        for (self.function_ids) |*slot| slot.* = self.builder.reserve_id();
        for (self.module.entry_points.items) |entry| {
            self.entry_wrapper_ids[entry.function] = self.builder.reserve_id();
        }

        try self.emit_globals();

        var function_index: usize = 0;
        while (function_index < self.module.functions.items.len) : (function_index += 1) {
            try self.emit_function(@intCast(function_index));
        }

        for (self.module.entry_points.items) |entry| {
            try self.emit_entry_wrapper(entry);
        }
    }

    fn emit_globals(self: *Emitter) EmitError!void {
        for (self.module.globals.items, 0..) |global, index| {
            if (global.class == .input or global.class == .output) return error.UnsupportedConstruct;

            if (self.is_bound_buffer_global(global)) {
                self.global_ids[index] = try self.emit_bound_buffer_global(global);
                self.global_buffer_wrapped[index] = true;
                continue;
            }
            if (self.is_bound_handle_global(global)) {
                self.global_ids[index] = try self.emit_bound_handle_global(global);
                continue;
            }
            if (global.binding != null) return error.UnsupportedConstruct;

            const value_type = try self.lower_type(global.ty);
            const storage_class = try self.global_storage_class(global);
            const ptr_type = try self.builder.type_pointer(storage_class, value_type);

            const var_id = if (global.initializer) |initializer|
                try self.builder.variable_global_init(ptr_type, storage_class, try self.lower_constant(initializer, global.ty))
            else
                try self.builder.variable_global(ptr_type, storage_class);

            try self.builder.emit_name(var_id, global.name);
            self.global_ids[index] = var_id;
        }
    }

    fn emit_bound_handle_global(self: *Emitter, global: ir.Global) EmitError!u32 {
        const binding = global.binding orelse return error.InvalidIr;
        if (global.initializer != null) return error.UnsupportedConstruct;

        const storage_class = try self.global_storage_class(global);
        if (storage_class != spirv.StorageClass.UniformConstant) return error.InvalidIr;

        const value_type = try self.lower_type(global.ty);
        const ptr_type = try self.builder.type_pointer(storage_class, value_type);
        const var_id = try self.builder.variable_global(ptr_type, storage_class);
        try self.builder.emit_name(var_id, global.name);
        try self.builder.emit_descriptor_set_decoration(var_id, binding.group);
        try self.builder.emit_binding_decoration(var_id, binding.binding);

        switch (self.module.types.get(global.ty)) {
            .storage_texture_2d => |storage_tex| switch (storage_tex.access) {
                .read => try self.builder.emit_non_writable_decoration(var_id),
                .write => try self.builder.emit_non_readable_decoration(var_id),
                .read_write => {},
            },
            else => {},
        }

        return var_id;
    }

    fn emit_bound_buffer_global(self: *Emitter, global: ir.Global) EmitError!u32 {
        const binding = global.binding orelse return error.InvalidIr;
        if (global.initializer != null) return error.UnsupportedConstruct;
        const addr_space = global.addr_space orelse return error.InvalidIr;
        if (addr_space != .uniform and addr_space != .storage) return error.UnsupportedConstruct;

        _ = try self.decorate_memory_type(global.ty, addr_space);
        const block_member_type = try self.lower_type(global.ty);
        const block_type = try self.builder.type_struct(&.{block_member_type});
        try self.builder.emit_block_decoration(block_type);
        try self.builder.emit_member_offset_decoration(block_type, 0, 0);

        const storage_class = try self.global_storage_class(global);
        const ptr_type = try self.builder.type_pointer(storage_class, block_type);
        const var_id = try self.builder.variable_global(ptr_type, storage_class);
        try self.builder.emit_name(var_id, global.name);
        try self.builder.emit_descriptor_set_decoration(var_id, binding.group);
        try self.builder.emit_binding_decoration(var_id, binding.binding);
        if (addr_space == .storage and (global.access orelse .read_write) == .read) {
            try self.builder.emit_non_writable_decoration(var_id);
        }
        return var_id;
    }

    fn emit_function(self: *Emitter, function_index: ir.FunctionId) EmitError!void {
        const function = &self.module.functions.items[function_index];
        const fn_id = self.function_ids[function_index];
        const return_type = try self.lower_type(function.return_type);

        var param_types = std.ArrayListUnmanaged(u32){};
        defer param_types.deinit(self.alloc);
        for (function.params.items) |param| {
            try param_types.append(self.alloc, try self.lower_type(param.ty));
        }

        const fn_type = try self.builder.type_function(return_type, param_types.items);
        try self.builder.emit_name(fn_id, function.name);
        try self.builder.begin_function(return_type, fn_id, fn_type);

        const param_value_ids = try self.alloc.alloc(u32, function.params.items.len);
        defer self.alloc.free(param_value_ids);
        for (param_value_ids, function.params.items) |*slot, param| {
            slot.* = try self.builder.function_parameter(try self.lower_type(param.ty));
        }

        _ = try self.builder.label();

        var state = try FunctionState.init(self, function_index);
        defer state.deinit();

        for (function.params.items, 0..) |param, param_index| {
            const ptr_type = try self.builder.type_pointer(spirv.StorageClass.Function, try self.lower_type(param.ty));
            const ptr_id = try self.builder.variable_function(ptr_type);
            state.param_ptr_ids[param_index] = ptr_id;
            try self.builder.emit_name(ptr_id, param.name);
            try self.emit_store(ptr_id, param_value_ids[param_index]);
        }

        for (function.locals.items, 0..) |local, local_index| {
            const ptr_type = try self.builder.type_pointer(spirv.StorageClass.Function, try self.lower_type(local.ty));
            const ptr_id = try self.builder.variable_function(ptr_type);
            state.local_ptr_ids[local_index] = ptr_id;
            try self.builder.emit_name(ptr_id, local.name);
        }

        const terminated = try state.emit_stmt(function.root_stmt);
        if (!terminated) {
            if (ir.is_scalar(&self.module.types, function.return_type, .void)) {
                try self.builder.append_function_inst(spirv.Opcode.Return, &.{});
            } else {
                return error.InvalidIr;
            }
        }

        try self.builder.finish_function();
    }

    fn emit_entry_wrapper(self: *Emitter, entry: ir.EntryPoint) EmitError!void {
        const function = &self.module.functions.items[entry.function];
        if (!ir.is_scalar(&self.module.types, function.return_type, .void)) return error.UnsupportedConstruct;

        const wrapper_id = self.entry_wrapper_ids[entry.function];
        const void_type = try self.builder.type_void();
        const fn_type = try self.builder.type_function(void_type, &.{});
        const wrapper_name = try std.fmt.allocPrint(self.alloc, "{s}_entry", .{function.name});
        defer self.alloc.free(wrapper_name);

        var interface_ids = std.ArrayListUnmanaged(u32){};
        defer interface_ids.deinit(self.alloc);

        for (function.params.items) |param| {
            const io = param.io orelse return error.UnsupportedConstruct;
            if (io.builtin == .none) return error.UnsupportedConstruct;
            const value_type = try self.lower_type(param.ty);
            const ptr_type = try self.builder.type_pointer(spirv.StorageClass.Input, value_type);
            const var_id = try self.builder.variable_global(ptr_type, spirv.StorageClass.Input);
            try self.builder.emit_name(var_id, param.name);
            try self.builder.emit_builtin_decoration(var_id, try builtin_to_spirv(io.builtin));
            try interface_ids.append(self.alloc, var_id);
        }

        for (self.module.globals.items, 0..) |global, index| {
            if (global.binding == null) continue;
            const global_id = self.global_ids[index];
            if (global_id == 0) return error.InvalidIr;
            try interface_ids.append(self.alloc, global_id);
        }

        try self.builder.emit_name(wrapper_id, wrapper_name);
        try self.builder.emit_entry_point(wrapper_id, function.name, interface_ids.items);
        try self.builder.emit_execution_mode_local_size(wrapper_id, entry.workgroup_size[0], entry.workgroup_size[1], entry.workgroup_size[2]);

        try self.builder.begin_function(void_type, wrapper_id, fn_type);
        _ = try self.builder.label();
        var call_args = std.ArrayListUnmanaged(u32){};
        defer call_args.deinit(self.alloc);
        for (function.params.items, interface_ids.items) |param, interface_id| {
            try call_args.append(self.alloc, try self.emit_function_load(try self.lower_type(param.ty), interface_id));
        }
        _ = try self.emit_function_call(void_type, self.function_ids[entry.function], call_args.items);
        try self.builder.append_function_inst(spirv.Opcode.Return, &.{});
        try self.builder.finish_function();
    }

    fn lower_type(self: *Emitter, ty: ir.TypeId) EmitError!u32 {
        if (ty == ir.INVALID_TYPE) return error.InvalidIr;
        if (self.type_ids[ty] != 0) return self.type_ids[ty];

        const lowered = switch (self.module.types.get(ty)) {
            .scalar => |scalar| switch (scalar) {
                .void => try self.builder.type_void(),
                .bool => try self.builder.type_bool(),
                .i32, .abstract_int => try self.builder.type_i32(),
                .u32 => try self.builder.type_u32(),
                .f32, .abstract_float => try self.builder.type_f32(),
                else => return error.UnsupportedConstruct,
            },
            .vector => |vec| try self.builder.type_vector(try self.lower_type(vec.elem), vec.len),
            .array => |arr| if (arr.len) |len|
                try self.builder.type_array(try self.lower_type(arr.elem), try self.builder.const_u32(len))
            else
                try self.builder.type_runtime_array(try self.lower_type(arr.elem)),
            .texture_2d => |sample_ty| blk: {
                switch (self.module.types.get(sample_ty)) {
                    .scalar => |scalar| {
                        if (scalar != .f32) return error.UnsupportedConstruct;
                    },
                    else => return error.UnsupportedConstruct,
                }
                break :blk try self.builder.type_image(
                    try self.lower_type(sample_ty),
                    spirv.Dim._2D,
                    0,
                    0,
                    0,
                    1,
                    spirv.ImageFormat.Unknown,
                );
            },
            .storage_texture_2d => |storage_tex| blk: {
                if (storage_tex.format != .rgba8unorm) return error.UnsupportedConstruct;
                break :blk try self.builder.type_image(
                    try self.builder.type_f32(),
                    spirv.Dim._2D,
                    0,
                    0,
                    0,
                    2,
                    spirv.ImageFormat.Rgba8,
                );
            },
            .struct_ => |struct_id| blk: {
                const struct_def = self.module.structs.items[struct_id];
                var member_types = std.ArrayListUnmanaged(u32){};
                defer member_types.deinit(self.alloc);
                for (struct_def.fields.items) |field| {
                    try member_types.append(self.alloc, try self.lower_type(field.ty));
                }
                break :blk try self.builder.type_struct(member_types.items);
            },
            .atomic => |inner| try self.lower_type(inner),
            .ref => |ref_ty| try self.lower_type(ref_ty.elem),
            else => return error.UnsupportedConstruct,
        };

        self.type_ids[ty] = lowered;
        return lowered;
    }

    fn lower_constant(self: *Emitter, constant: ir.ConstantValue, ty: ir.TypeId) EmitError!u32 {
        switch (constant) {
            .bool => |value| return try self.builder.const_bool(value),
            .int => |value| switch (self.module.types.get(ty)) {
                .scalar => |scalar| switch (scalar) {
                    .u32 => return try self.builder.const_u32(@truncate(value)),
                    .i32, .abstract_int => return try self.builder.const_i32_bits(@truncate(value)),
                    else => return error.InvalidIr,
                },
                else => return error.InvalidIr,
            },
            .float => |value| switch (self.module.types.get(ty)) {
                .scalar => |scalar| switch (scalar) {
                    .f32, .abstract_float => return try self.builder.const_f32_bits(@bitCast(@as(f32, @floatCast(value)))),
                    else => return error.InvalidIr,
                },
                else => return error.InvalidIr,
            },
        }
    }

    fn global_storage_class(self: *Emitter, global: ir.Global) EmitError!u32 {
        _ = self;
        return switch (global.class) {
            .const_, .override_ => spirv.StorageClass.Private,
            .var_ => switch (global.addr_space orelse .private) {
                .handle => spirv.StorageClass.UniformConstant,
                .private => spirv.StorageClass.Private,
                .workgroup => spirv.StorageClass.Workgroup,
                .uniform => spirv.StorageClass.Uniform,
                .storage => spirv.StorageClass.StorageBuffer,
                else => error.UnsupportedConstruct,
            },
            else => error.UnsupportedConstruct,
        };
    }

    fn is_bound_buffer_global(self: *Emitter, global: ir.Global) bool {
        _ = self;
        if (global.binding == null) return false;
        const addr_space = global.addr_space orelse return false;
        return addr_space == .uniform or addr_space == .storage;
    }

    fn is_bound_handle_global(self: *Emitter, global: ir.Global) bool {
        if (global.binding == null) return false;
        const addr_space = global.addr_space orelse return false;
        if (addr_space != .handle) return false;
        return switch (self.module.types.get(global.ty)) {
            .texture_2d, .storage_texture_2d => true,
            else => false,
        };
    }

    const Layout = struct {
        alignment: u32,
        size: u32,
    };

    fn decorate_memory_type(self: *Emitter, ty: ir.TypeId, addr_space: ir.AddressSpace) EmitError!Layout {
        return switch (self.module.types.get(ty)) {
            .scalar => |scalar| switch (scalar) {
                .bool, .i32, .u32, .f32, .abstract_int, .abstract_float => .{ .alignment = 4, .size = 4 },
                .f16 => .{ .alignment = 2, .size = 2 },
                else => return error.UnsupportedConstruct,
            },
            .vector => |vec| blk: {
                const elem_layout = try self.decorate_memory_type(vec.elem, addr_space);
                const layout = switch (vec.len) {
                    2 => Layout{ .alignment = elem_layout.alignment * 2, .size = elem_layout.size * 2 },
                    3 => Layout{ .alignment = elem_layout.alignment * 4, .size = elem_layout.size * 3 },
                    4 => Layout{ .alignment = elem_layout.alignment * 4, .size = elem_layout.size * 4 },
                    else => return error.UnsupportedConstruct,
                };
                break :blk layout;
            },
            .array => |arr| blk: {
                const elem_layout = try self.decorate_memory_type(arr.elem, addr_space);
                const alignment = adjusted_memory_align(addr_space, self.module.types.get(arr.elem), elem_layout.alignment);
                const stride = round_up(alignment, elem_layout.size);
                const array_type = try self.lower_type(ty);
                const gop = try self.decorated_array_types.getOrPut(self.alloc, array_type);
                if (!gop.found_existing) {
                    try self.builder.emit_array_stride_decoration(array_type, stride);
                }
                if (arr.len == null) {
                    if (addr_space != .storage) return error.UnsupportedConstruct;
                    break :blk .{
                        .alignment = alignment,
                        .size = stride,
                    };
                }
                const len = arr.len.?;
                break :blk .{
                    .alignment = alignment,
                    .size = stride * len,
                };
            },
            .struct_ => |struct_id| blk: {
                const struct_type = try self.lower_type(ty);
                const gop = try self.decorated_struct_types.getOrPut(self.alloc, struct_type);
                const struct_def = self.module.structs.items[struct_id];
                var offset: u32 = 0;
                var max_align: u32 = 1;
                for (struct_def.fields.items, 0..) |field, field_index| {
                    const field_layout = try self.decorate_memory_type(field.ty, addr_space);
                    const field_alignment = adjusted_memory_align(addr_space, self.module.types.get(field.ty), field_layout.alignment);
                    offset = round_up(field_alignment, offset);
                    if (!gop.found_existing) {
                        try self.builder.emit_member_offset_decoration(struct_type, @intCast(field_index), offset);
                    }
                    max_align = @max(max_align, field_alignment);
                    offset += field_layout.size;
                }
                max_align = adjusted_memory_align(addr_space, .{ .struct_ = struct_id }, max_align);
                break :blk .{
                    .alignment = max_align,
                    .size = round_up(max_align, offset),
                };
            },
            .atomic => |inner| try self.decorate_memory_type(inner, addr_space),
            .matrix, .sampler, .texture_2d, .storage_texture_2d, .ref => return error.UnsupportedConstruct,
        };
    }

    fn emit_function_load(self: *Emitter, value_type: u32, ptr_id: u32) EmitError!u32 {
        const result_id = self.builder.reserve_id();
        try self.builder.append_function_inst(spirv.Opcode.Load, &.{ value_type, result_id, ptr_id });
        return result_id;
    }

    fn emit_store(self: *Emitter, ptr_id: u32, value_id: u32) EmitError!void {
        try self.builder.append_function_inst(spirv.Opcode.Store, &.{ ptr_id, value_id });
    }

    fn emit_function_call(self: *Emitter, result_type: u32, fn_id: u32, args: []const u32) EmitError!u32 {
        var operands = std.ArrayListUnmanaged(u32){};
        defer operands.deinit(self.alloc);
        const result_id = self.builder.reserve_id();
        try operands.append(self.alloc, result_type);
        try operands.append(self.alloc, result_id);
        try operands.append(self.alloc, fn_id);
        try operands.appendSlice(self.alloc, args);
        try self.builder.append_function_inst(spirv.Opcode.FunctionCall, operands.items);
        return result_id;
    }

    fn function_id_by_name(self: *Emitter, name: []const u8) ?u32 {
        for (self.module.functions.items, 0..) |function, index| {
            if (std.mem.eql(u8, function.name, name)) return self.function_ids[index];
        }
        return null;
    }
};

const FunctionState = struct {
    emitter: *Emitter,
    function: *const ir.Function,
    param_ptr_ids: []u32,
    local_ptr_ids: []u32,
    break_targets: std.ArrayListUnmanaged(u32) = .{},
    continue_targets: std.ArrayListUnmanaged(u32) = .{},

    fn init(emitter: *Emitter, function_index: ir.FunctionId) EmitError!FunctionState {
        const function = &emitter.module.functions.items[function_index];
        const param_ptr_ids = try emitter.alloc.alloc(u32, function.params.items.len);
        errdefer emitter.alloc.free(param_ptr_ids);
        @memset(param_ptr_ids, 0);
        const local_ptr_ids = try emitter.alloc.alloc(u32, function.locals.items.len);
        errdefer emitter.alloc.free(local_ptr_ids);
        @memset(local_ptr_ids, 0);
        return .{
            .emitter = emitter,
            .function = function,
            .param_ptr_ids = param_ptr_ids,
            .local_ptr_ids = local_ptr_ids,
        };
    }

    fn deinit(self: *FunctionState) void {
        self.break_targets.deinit(self.emitter.alloc);
        self.continue_targets.deinit(self.emitter.alloc);
        self.emitter.alloc.free(self.local_ptr_ids);
        self.emitter.alloc.free(self.param_ptr_ids);
    }

    fn emit_stmt(self: *FunctionState, stmt_id: ir.StmtId) EmitError!bool {
        const stmt = self.function.stmts.items[stmt_id];
        switch (stmt) {
            .block => |range| {
                var i: u32 = 0;
                while (i < range.len) : (i += 1) {
                    if (try self.emit_stmt(self.function.stmt_children.items[range.start + i])) return true;
                }
                return false;
            },
            .local_decl => |decl| {
                if (decl.initializer) |expr_id| {
                    try self.emitter.emit_store(self.local_ptr_ids[decl.local], try self.emit_value_expr(expr_id));
                }
                return false;
            },
            .expr => |expr_id| {
                _ = try self.emit_value_expr(expr_id);
                return false;
            },
            .assign => |assign| {
                const ptr_id = try self.emit_ref_expr(assign.lhs);
                var value_id = try self.emit_value_expr(assign.rhs);
                if (assign.op != .assign) {
                    const current = try self.emit_load_from_ref(assign.lhs);
                    value_id = try self.emit_binary(
                        assign_op_to_binary(assign.op),
                        current,
                        value_id,
                        self.function.exprs.items[assign.lhs].ty,
                        self.function.exprs.items[assign.lhs].ty,
                    );
                }
                try self.emitter.emit_store(ptr_id, value_id);
                return false;
            },
            .return_ => |value| {
                if (value) |expr_id| {
                    try self.emitter.builder.append_function_inst(spirv.Opcode.ReturnValue, &.{try self.emit_value_expr(expr_id)});
                } else {
                    try self.emitter.builder.append_function_inst(spirv.Opcode.Return, &.{});
                }
                return true;
            },
            .if_ => |if_stmt| {
                const cond_id = try self.emit_value_expr(if_stmt.cond);
                const then_label = self.emitter.builder.reserve_id();
                const else_label = if (if_stmt.else_block != null) self.emitter.builder.reserve_id() else 0;
                const merge_label = self.emitter.builder.reserve_id();
                try self.emitter.builder.append_function_inst(spirv.Opcode.SelectionMerge, &.{ merge_label, spirv.SelectionControl.None });
                try self.emitter.builder.append_function_inst(
                    spirv.Opcode.BranchConditional,
                    &.{ cond_id, then_label, if (else_label != 0) else_label else merge_label },
                );

                try self.emit_label(then_label);
                const then_terminated = try self.emit_stmt(if_stmt.then_block);
                if (!then_terminated) try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{merge_label});

                if (if_stmt.else_block) |else_block| {
                    try self.emit_label(else_label);
                    const else_terminated = try self.emit_stmt(else_block);
                    if (!else_terminated) try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{merge_label});
                }

                try self.emit_label(merge_label);
                return false;
            },
            .loop_ => |loop_stmt| {
                if (loop_stmt.init) |init_stmt| _ = try self.emit_stmt(init_stmt);

                const header_label = self.emitter.builder.reserve_id();
                const body_label = self.emitter.builder.reserve_id();
                const continue_label = self.emitter.builder.reserve_id();
                const merge_label = self.emitter.builder.reserve_id();

                try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{header_label});
                try self.emit_label(header_label);
                try self.emitter.builder.append_function_inst(spirv.Opcode.LoopMerge, &.{ merge_label, continue_label, spirv.LoopControl.None });
                if (loop_stmt.cond) |cond| {
                    try self.emitter.builder.append_function_inst(
                        spirv.Opcode.BranchConditional,
                        &.{ try self.emit_value_expr(cond), body_label, merge_label },
                    );
                } else {
                    try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{body_label});
                }

                try self.break_targets.append(self.emitter.alloc, merge_label);
                try self.continue_targets.append(self.emitter.alloc, continue_label);

                try self.emit_label(body_label);
                const body_terminated = try self.emit_stmt(loop_stmt.body);
                if (!body_terminated) try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{continue_label});

                try self.emit_label(continue_label);
                const continuing_terminated = if (loop_stmt.continuing) |cont| try self.emit_stmt(cont) else false;
                if (!continuing_terminated) try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{header_label});

                _ = self.break_targets.pop();
                _ = self.continue_targets.pop();

                try self.emit_label(merge_label);
                return false;
            },
            .switch_ => |switch_stmt| {
                const selector_id = try self.emit_value_expr(switch_stmt.expr);
                const merge_label = self.emitter.builder.reserve_id();
                var labels = try self.emitter.alloc.alloc(u32, switch_stmt.cases.len);
                defer self.emitter.alloc.free(labels);
                @memset(labels, 0);

                var default_label = merge_label;
                var case_index: u32 = 0;
                while (case_index < switch_stmt.cases.len) : (case_index += 1) {
                    const case_node = self.function.switch_cases.items[switch_stmt.cases.start + case_index];
                    labels[case_index] = self.emitter.builder.reserve_id();
                    if (case_node.is_default) default_label = labels[case_index];
                }

                var operands = std.ArrayListUnmanaged(u32){};
                defer operands.deinit(self.emitter.alloc);
                try operands.append(self.emitter.alloc, selector_id);
                try operands.append(self.emitter.alloc, default_label);
                case_index = 0;
                while (case_index < switch_stmt.cases.len) : (case_index += 1) {
                    const case_node = self.function.switch_cases.items[switch_stmt.cases.start + case_index];
                    if (case_node.is_default) continue;
                    for (case_node.selectors.items) |selector_expr| {
                        try operands.append(self.emitter.alloc, try self.switch_selector_literal(selector_expr));
                        try operands.append(self.emitter.alloc, labels[case_index]);
                    }
                }

                try self.emitter.builder.append_function_inst(spirv.Opcode.SelectionMerge, &.{ merge_label, spirv.SelectionControl.None });
                try self.emitter.builder.append_function_inst(spirv.Opcode.Switch, operands.items);

                try self.break_targets.append(self.emitter.alloc, merge_label);
                case_index = 0;
                while (case_index < switch_stmt.cases.len) : (case_index += 1) {
                    const case_node = self.function.switch_cases.items[switch_stmt.cases.start + case_index];
                    try self.emit_label(labels[case_index]);
                    const terminated = try self.emit_stmt(case_node.body);
                    if (!terminated) try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{merge_label});
                }
                _ = self.break_targets.pop();

                try self.emit_label(merge_label);
                return false;
            },
            .break_ => {
                if (self.break_targets.items.len == 0) return error.InvalidIr;
                try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{self.break_targets.items[self.break_targets.items.len - 1]});
                return true;
            },
            .continue_ => {
                if (self.continue_targets.items.len == 0) return error.InvalidIr;
                try self.emitter.builder.append_function_inst(spirv.Opcode.Branch, &.{self.continue_targets.items[self.continue_targets.items.len - 1]});
                return true;
            },
            .discard_ => return error.UnsupportedConstruct,
        }
    }

    fn emit_label(self: *FunctionState, label_id: u32) EmitError!void {
        try self.emitter.builder.append_function_inst(spirv.Opcode.Label, &.{label_id});
    }

    fn emit_value_expr(self: *FunctionState, expr_id: ir.ExprId) EmitError!u32 {
        const expr = self.function.exprs.items[expr_id];
        return switch (expr.data) {
            .bool_lit => |value| try self.emitter.builder.const_bool(value),
            .int_lit => |value| switch (self.emitter.module.types.get(expr.ty)) {
                .scalar => |scalar| switch (scalar) {
                    .u32 => try self.emitter.builder.const_u32(@truncate(value)),
                    .i32, .abstract_int => try self.emitter.builder.const_i32_bits(@truncate(value)),
                    else => return error.InvalidIr,
                },
                else => return error.InvalidIr,
            },
            .float_lit => |value| try self.emitter.builder.const_f32_bits(@bitCast(@as(f32, @floatCast(value)))),
            .param_ref, .local_ref => return error.InvalidIr,
            .global_ref => |index| blk: {
                const global = self.emitter.module.globals.items[index];
                switch (self.emitter.module.types.get(global.ty)) {
                    .texture_2d, .storage_texture_2d => {
                        break :blk try self.emitter.emit_function_load(
                            try self.emitter.lower_type(expr.ty),
                            self.emitter.global_ids[index],
                        );
                    },
                    else => return error.InvalidIr,
                }
            },
            .load => |inner| try self.emit_load_from_ref(inner),
            .unary => |unary| try self.emit_unary(unary.op, try self.emit_value_expr(unary.operand), expr.ty),
            .binary => |binary| try self.emit_binary(
                binary.op,
                try self.emit_value_expr(binary.lhs),
                try self.emit_value_expr(binary.rhs),
                self.function.exprs.items[binary.lhs].ty,
                expr.ty,
            ),
            .call => |call| try self.emit_call(call, expr.ty),
            .construct => |construct| try self.emit_construct(construct.ty, construct.args),
            .member => |member| if (expr.category == .ref)
                return error.InvalidIr
            else
                try self.emit_composite_extract(try self.emit_value_expr(member.base), expr.ty, member.field_index),
            .index => |index| if (expr.category == .ref)
                return error.InvalidIr
            else
                try self.emit_composite_extract(try self.emit_value_expr(index.base), expr.ty, try self.literal_index(index.index)),
        };
    }

    fn emit_ref_expr(self: *FunctionState, expr_id: ir.ExprId) EmitError!u32 {
        const expr = self.function.exprs.items[expr_id];
        return switch (expr.data) {
            .param_ref => |index| self.param_ptr_ids[index],
            .local_ref => |index| self.local_ptr_ids[index],
            .global_ref => |index| blk: {
                if (!self.emitter.global_buffer_wrapped[index]) break :blk self.emitter.global_ids[index];
                const global = self.emitter.module.globals.items[index];
                const ptr_type = try self.emitter.builder.type_pointer(
                    try self.emitter.global_storage_class(global),
                    try self.emitter.lower_type(expr.ty),
                );
                const result_id = self.emitter.builder.reserve_id();
                try self.emitter.builder.append_function_inst(
                    spirv.Opcode.AccessChain,
                    &.{ ptr_type, result_id, self.emitter.global_ids[index], try self.emitter.builder.const_u32(0) },
                );
                break :blk result_id;
            },
            .member => |member| blk: {
                const base_ptr = try self.emit_ref_expr(member.base);
                const ptr_type = try self.emitter.builder.type_pointer(try self.ref_storage_class(member.base), try self.emitter.lower_type(expr.ty));
                const result_id = self.emitter.builder.reserve_id();
                try self.emitter.builder.append_function_inst(
                    spirv.Opcode.AccessChain,
                    &.{ ptr_type, result_id, base_ptr, try self.emitter.builder.const_u32(member.field_index) },
                );
                break :blk result_id;
            },
            .index => |index| blk: {
                const base_ptr = try self.emit_ref_expr(index.base);
                const ptr_type = try self.emitter.builder.type_pointer(try self.ref_storage_class(index.base), try self.emitter.lower_type(expr.ty));
                const result_id = self.emitter.builder.reserve_id();
                try self.emitter.builder.append_function_inst(
                    spirv.Opcode.AccessChain,
                    &.{ ptr_type, result_id, base_ptr, try self.emit_value_expr(index.index) },
                );
                break :blk result_id;
            },
            else => return error.InvalidIr,
        };
    }

    fn emit_load_from_ref(self: *FunctionState, ref_expr_id: ir.ExprId) EmitError!u32 {
        const ref_expr = self.function.exprs.items[ref_expr_id];
        return try self.emitter.emit_function_load(try self.emitter.lower_type(ref_expr.ty), try self.emit_ref_expr(ref_expr_id));
    }

    fn emit_unary(self: *FunctionState, op: ir.UnaryOp, operand_id: u32, result_ty: ir.TypeId) EmitError!u32 {
        const opcode: u16 = switch (op) {
            .neg => switch (self.scalar_kind(result_ty)) {
                .signed => spirv.Opcode.SNegate,
                .float => spirv.Opcode.FNegate,
                else => return error.UnsupportedConstruct,
            },
            .not => spirv.Opcode.LogicalNot,
            .bit_not => spirv.Opcode.Not,
        };
        return try self.emit_result_inst(opcode, try self.emitter.lower_type(result_ty), &.{operand_id});
    }

    fn emit_binary(self: *FunctionState, op: ir.BinaryOp, lhs_id: u32, rhs_id: u32, operand_ty: ir.TypeId, result_ty: ir.TypeId) EmitError!u32 {
        const opcode: u16 = switch (op) {
            .add => switch (self.scalar_kind(operand_ty)) { .float => spirv.Opcode.FAdd, else => spirv.Opcode.IAdd },
            .sub => switch (self.scalar_kind(operand_ty)) { .float => spirv.Opcode.FSub, else => spirv.Opcode.ISub },
            .mul => switch (self.scalar_kind(operand_ty)) { .float => spirv.Opcode.FMul, else => spirv.Opcode.IMul },
            .div => switch (self.scalar_kind(operand_ty)) {
                .float => spirv.Opcode.FDiv,
                .unsigned => spirv.Opcode.UDiv,
                .signed => spirv.Opcode.SDiv,
                else => return error.UnsupportedConstruct,
            },
            .rem => switch (self.scalar_kind(operand_ty)) {
                .float => spirv.Opcode.FRem,
                .unsigned => spirv.Opcode.UMod,
                .signed => spirv.Opcode.SRem,
                else => return error.UnsupportedConstruct,
            },
            .bit_and => spirv.Opcode.BitwiseAnd,
            .bit_or => spirv.Opcode.BitwiseOr,
            .bit_xor => spirv.Opcode.BitwiseXor,
            .shift_left => spirv.Opcode.ShiftLeftLogical,
            .shift_right => switch (self.scalar_kind(operand_ty)) {
                .unsigned => spirv.Opcode.ShiftRightLogical,
                else => spirv.Opcode.ShiftRightArithmetic,
            },
            .equal => return try self.emit_compare(op, lhs_id, rhs_id, operand_ty),
            .not_equal => return try self.emit_compare(op, lhs_id, rhs_id, operand_ty),
            .less => return try self.emit_compare(op, lhs_id, rhs_id, operand_ty),
            .less_equal => return try self.emit_compare(op, lhs_id, rhs_id, operand_ty),
            .greater => return try self.emit_compare(op, lhs_id, rhs_id, operand_ty),
            .greater_equal => return try self.emit_compare(op, lhs_id, rhs_id, operand_ty),
            .logical_and => spirv.Opcode.LogicalAnd,
            .logical_or => spirv.Opcode.LogicalOr,
        };
        return try self.emit_result_inst(opcode, try self.emitter.lower_type(result_ty), &.{ lhs_id, rhs_id });
    }

    fn emit_compare(self: *FunctionState, op: ir.BinaryOp, lhs_id: u32, rhs_id: u32, operand_ty: ir.TypeId) EmitError!u32 {
        const opcode: u16 = switch (self.scalar_kind(operand_ty)) {
            .bool => switch (op) {
                .equal => spirv.Opcode.LogicalEqual,
                .not_equal => spirv.Opcode.LogicalNotEqual,
                else => return error.UnsupportedConstruct,
            },
            .unsigned => switch (op) {
                .equal => spirv.Opcode.IEqual,
                .not_equal => spirv.Opcode.INotEqual,
                .less => spirv.Opcode.ULessThan,
                .less_equal => spirv.Opcode.ULessThanEqual,
                .greater => spirv.Opcode.UGreaterThan,
                .greater_equal => spirv.Opcode.UGreaterThanEqual,
                else => return error.UnsupportedConstruct,
            },
            .signed => switch (op) {
                .equal => spirv.Opcode.IEqual,
                .not_equal => spirv.Opcode.INotEqual,
                .less => spirv.Opcode.SLessThan,
                .less_equal => spirv.Opcode.SLessThanEqual,
                .greater => spirv.Opcode.SGreaterThan,
                .greater_equal => spirv.Opcode.SGreaterThanEqual,
                else => return error.UnsupportedConstruct,
            },
            .float => switch (op) {
                .equal => spirv.Opcode.FOrdEqual,
                .not_equal => spirv.Opcode.FOrdNotEqual,
                .less => spirv.Opcode.FOrdLessThan,
                .less_equal => spirv.Opcode.FOrdLessThanEqual,
                .greater => spirv.Opcode.FOrdGreaterThan,
                .greater_equal => spirv.Opcode.FOrdGreaterThanEqual,
                else => return error.UnsupportedConstruct,
            },
        };
        return try self.emit_result_inst(opcode, try self.emitter.builder.type_bool(), &.{ lhs_id, rhs_id });
    }

    fn emit_call(self: *FunctionState, call: anytype, result_ty: ir.TypeId) EmitError!u32 {
        if (call.kind == .builtin) return try self.emit_builtin_call(call, result_ty);
        const fn_id = self.emitter.function_id_by_name(call.name) orelse return error.InvalidIr;
        var args = std.ArrayListUnmanaged(u32){};
        defer args.deinit(self.emitter.alloc);
        var i: u32 = 0;
        while (i < call.args.len) : (i += 1) {
            try args.append(self.emitter.alloc, try self.emit_value_expr(self.function.expr_args.items[call.args.start + i]));
        }
        return try self.emitter.emit_function_call(try self.emitter.lower_type(result_ty), fn_id, args.items);
    }

    fn emit_builtin_call(self: *FunctionState, call: anytype, result_ty: ir.TypeId) EmitError!u32 {
        if (std.mem.eql(u8, call.name, "workgroupBarrier")) {
            try self.emit_control_barrier(
                spirv.MemorySemantics.AcquireRelease |
                    spirv.MemorySemantics.WorkgroupMemory,
            );
            return 0;
        }
        if (std.mem.eql(u8, call.name, "storageBarrier")) {
            try self.emit_control_barrier(
                spirv.MemorySemantics.AcquireRelease |
                    spirv.MemorySemantics.UniformMemory |
                    spirv.MemorySemantics.ImageMemory,
            );
            return 0;
        }
        if (std.mem.startsWith(u8, call.name, "atomic")) {
            return try self.emit_atomic_call(call, result_ty);
        }
        if (std.mem.eql(u8, call.name, "textureLoad")) {
            return try self.emit_texture_load(call, result_ty);
        }
        if (std.mem.eql(u8, call.name, "textureStore")) {
            try self.emit_texture_store(call);
            return 0;
        }
        if (std.mem.eql(u8, call.name, "dot")) {
            return try self.emit_dot(call, result_ty);
        }
        if (std.mem.eql(u8, call.name, "sin")) {
            return try self.emit_glsl_ext_inst(call, result_ty, 13);
        }
        if (std.mem.eql(u8, call.name, "fract")) {
            return try self.emit_glsl_ext_inst(call, result_ty, 10);
        }
        return error.UnsupportedConstruct;
    }

    fn emit_control_barrier(self: *FunctionState, memory_semantics: u32) EmitError!void {
        const scope_id = try self.emitter.builder.const_u32(spirv.Scope.Workgroup);
        const semantics_id = try self.emitter.builder.const_u32(memory_semantics);
        try self.emitter.builder.append_function_inst(
            spirv.Opcode.ControlBarrier,
            &.{ scope_id, scope_id, semantics_id },
        );
    }

    const AtomicMemoryOperands = struct {
        scope_id: u32,
        semantics_id: u32,
    };

    fn emit_atomic_call(self: *FunctionState, call: anytype, result_ty: ir.TypeId) EmitError!u32 {
        if (call.args.len == 0) return error.InvalidIr;
        const ptr_expr = self.function.expr_args.items[call.args.start];
        const ptr_id = try self.emit_ref_expr(ptr_expr);
        const memory = try self.atomic_memory_operands(ptr_expr);

        if (std.mem.eql(u8, call.name, "atomicLoad")) {
            return try self.emit_result_inst(
                spirv.Opcode.AtomicLoad,
                try self.emitter.lower_type(result_ty),
                &.{ ptr_id, memory.scope_id, memory.semantics_id },
            );
        }

        if (call.args.len < 2) return error.InvalidIr;
        const value_id = try self.emit_value_expr(self.function.expr_args.items[call.args.start + 1]);

        if (std.mem.eql(u8, call.name, "atomicStore")) {
            try self.emitter.builder.append_function_inst(
                spirv.Opcode.AtomicStore,
                &.{ ptr_id, memory.scope_id, memory.semantics_id, value_id },
            );
            return 0;
        }

        const opcode: u16 = if (std.mem.eql(u8, call.name, "atomicAdd"))
            spirv.Opcode.AtomicIAdd
        else if (std.mem.eql(u8, call.name, "atomicSub"))
            spirv.Opcode.AtomicISub
        else if (std.mem.eql(u8, call.name, "atomicMax")) switch (self.scalar_kind(result_ty)) {
            .signed => spirv.Opcode.AtomicSMax,
            .unsigned => spirv.Opcode.AtomicUMax,
            else => return error.UnsupportedConstruct,
        } else if (std.mem.eql(u8, call.name, "atomicMin")) switch (self.scalar_kind(result_ty)) {
            .signed => spirv.Opcode.AtomicSMin,
            .unsigned => spirv.Opcode.AtomicUMin,
            else => return error.UnsupportedConstruct,
        } else if (std.mem.eql(u8, call.name, "atomicAnd"))
            spirv.Opcode.AtomicAnd
        else if (std.mem.eql(u8, call.name, "atomicOr"))
            spirv.Opcode.AtomicOr
        else if (std.mem.eql(u8, call.name, "atomicXor"))
            spirv.Opcode.AtomicXor
        else if (std.mem.eql(u8, call.name, "atomicExchange"))
            spirv.Opcode.AtomicExchange
        else
            return error.UnsupportedConstruct;

        return try self.emit_result_inst(
            opcode,
            try self.emitter.lower_type(result_ty),
            &.{ ptr_id, memory.scope_id, memory.semantics_id, value_id },
        );
    }

    fn emit_texture_load(self: *FunctionState, call: anytype, result_ty: ir.TypeId) EmitError!u32 {
        if (call.args.len != 3) return error.InvalidIr;

        const texture_expr = self.function.expr_args.items[call.args.start];
        const coords_expr = self.function.expr_args.items[call.args.start + 1];
        const level_expr = self.function.expr_args.items[call.args.start + 2];

        switch (self.emitter.module.types.get(self.function.exprs.items[texture_expr].ty)) {
            .texture_2d => |sample_ty| switch (self.emitter.module.types.get(sample_ty)) {
                .scalar => |scalar| {
                    if (scalar != .f32) return error.UnsupportedConstruct;
                },
                else => return error.UnsupportedConstruct,
            },
            else => return error.UnsupportedConstruct,
        }

        return try self.emit_result_inst(
            spirv.Opcode.ImageFetch,
            try self.emitter.lower_type(result_ty),
            &.{
                try self.emit_value_expr(texture_expr),
                try self.emit_value_expr(coords_expr),
                spirv.ImageOperandsMask.Lod,
                try self.emit_value_expr(level_expr),
            },
        );
    }

    fn emit_texture_store(self: *FunctionState, call: anytype) EmitError!void {
        if (call.args.len != 3) return error.InvalidIr;

        const texture_expr = self.function.expr_args.items[call.args.start];
        switch (self.emitter.module.types.get(self.function.exprs.items[texture_expr].ty)) {
            .storage_texture_2d => |storage_tex| {
                if (storage_tex.format != .rgba8unorm or storage_tex.access == .read) {
                    return error.UnsupportedConstruct;
                }
            },
            else => return error.UnsupportedConstruct,
        }

        try self.emitter.builder.append_function_inst(
            spirv.Opcode.ImageWrite,
            &.{
                try self.emit_value_expr(texture_expr),
                try self.emit_value_expr(self.function.expr_args.items[call.args.start + 1]),
                try self.emit_value_expr(self.function.expr_args.items[call.args.start + 2]),
            },
        );
    }

    fn emit_dot(self: *FunctionState, call: anytype, result_ty: ir.TypeId) EmitError!u32 {
        if (call.args.len != 2) return error.InvalidIr;

        const lhs_expr = self.function.expr_args.items[call.args.start];
        const rhs_expr = self.function.expr_args.items[call.args.start + 1];
        const lhs_ty = self.function.exprs.items[lhs_expr].ty;
        const rhs_ty = self.function.exprs.items[rhs_expr].ty;

        switch (self.emitter.module.types.get(lhs_ty)) {
            .vector => |lhs_vec| {
                const rhs_vec = switch (self.emitter.module.types.get(rhs_ty)) {
                    .vector => |vec| vec,
                    else => return error.UnsupportedConstruct,
                };
                if (lhs_vec.len != rhs_vec.len) return error.UnsupportedConstruct;
                if (lhs_vec.elem != rhs_vec.elem) return error.UnsupportedConstruct;
                switch (self.emitter.module.types.get(lhs_vec.elem)) {
                    .scalar => |scalar| if (scalar != .f32 and scalar != .abstract_float) return error.UnsupportedConstruct,
                    else => return error.UnsupportedConstruct,
                }
            },
            else => return error.UnsupportedConstruct,
        }

        return try self.emit_result_inst(
            spirv.Opcode.Dot,
            try self.emitter.lower_type(result_ty),
            &.{
                try self.emit_value_expr(lhs_expr),
                try self.emit_value_expr(rhs_expr),
            },
        );
    }

    fn emit_glsl_ext_inst(self: *FunctionState, call: anytype, result_ty: ir.TypeId, inst: u32) EmitError!u32 {
        if (call.args.len != 1) return error.InvalidIr;
        try self.validate_glsl_ext_operand(result_ty);

        const arg_expr = self.function.expr_args.items[call.args.start];
        const arg_ty = self.function.exprs.items[arg_expr].ty;
        if (arg_ty != result_ty) return error.UnsupportedConstruct;
        try self.validate_glsl_ext_operand(arg_ty);

        const result_type = try self.emitter.lower_type(result_ty);
        const result_id = self.emitter.builder.reserve_id();
        const import_id = try self.emitter.builder.glsl450_import_id();
        const operand_id = try self.emit_value_expr(arg_expr);

        try self.emitter.builder.append_function_inst(
            spirv.Opcode.ExtInst,
            &.{ result_type, result_id, import_id, inst, operand_id },
        );
        return result_id;
    }

    fn validate_glsl_ext_operand(self: *FunctionState, ty: ir.TypeId) EmitError!void {
        switch (self.emitter.module.types.get(ty)) {
            .scalar => |scalar| switch (scalar) {
                .f32, .abstract_float => return,
                else => return error.UnsupportedConstruct,
            },
            .vector => |vec| {
                if (vec.len < 2 or vec.len > 4) return error.UnsupportedConstruct;
                return switch (self.emitter.module.types.get(vec.elem)) {
                    .scalar => |scalar| switch (scalar) {
                        .f32, .abstract_float => {},
                        else => error.UnsupportedConstruct,
                    },
                    else => error.UnsupportedConstruct,
                };
            },
            else => return error.UnsupportedConstruct,
        }
    }

    fn atomic_memory_operands(self: *FunctionState, ref_expr_id: ir.ExprId) EmitError!AtomicMemoryOperands {
        const storage_class = try self.ref_storage_class(ref_expr_id);
        const scope = switch (storage_class) {
            spirv.StorageClass.Workgroup => spirv.Scope.Workgroup,
            spirv.StorageClass.StorageBuffer => spirv.Scope.Device,
            else => return error.UnsupportedConstruct,
        };
        const semantics = switch (storage_class) {
            spirv.StorageClass.Workgroup => spirv.MemorySemantics.SequentiallyConsistent | spirv.MemorySemantics.WorkgroupMemory,
            spirv.StorageClass.StorageBuffer => spirv.MemorySemantics.SequentiallyConsistent | spirv.MemorySemantics.UniformMemory,
            else => return error.UnsupportedConstruct,
        };
        return .{
            .scope_id = try self.emitter.builder.const_u32(scope),
            .semantics_id = try self.emitter.builder.const_u32(semantics),
        };
    }

    fn emit_construct(self: *FunctionState, ty: ir.TypeId, range: ir.Range) EmitError!u32 {
        var operands = std.ArrayListUnmanaged(u32){};
        defer operands.deinit(self.emitter.alloc);
        const result_ty = try self.emitter.lower_type(ty);
        const result_id = self.emitter.builder.reserve_id();
        try operands.append(self.emitter.alloc, result_ty);
        try operands.append(self.emitter.alloc, result_id);
        var i: u32 = 0;
        while (i < range.len) : (i += 1) {
            try operands.append(self.emitter.alloc, try self.emit_value_expr(self.function.expr_args.items[range.start + i]));
        }
        try self.emitter.builder.append_function_inst(spirv.Opcode.CompositeConstruct, operands.items);
        return result_id;
    }

    fn emit_composite_extract(self: *FunctionState, composite_id: u32, result_ty: ir.TypeId, index: u32) EmitError!u32 {
        return try self.emit_result_inst(spirv.Opcode.CompositeExtract, try self.emitter.lower_type(result_ty), &.{ composite_id, index });
    }

    fn emit_result_inst(self: *FunctionState, opcode: u16, result_type: u32, operands: []const u32) EmitError!u32 {
        var full = std.ArrayListUnmanaged(u32){};
        defer full.deinit(self.emitter.alloc);
        const result_id = self.emitter.builder.reserve_id();
        try full.append(self.emitter.alloc, result_type);
        try full.append(self.emitter.alloc, result_id);
        try full.appendSlice(self.emitter.alloc, operands);
        try self.emitter.builder.append_function_inst(opcode, full.items);
        return result_id;
    }

    fn ref_storage_class(self: *FunctionState, expr_id: ir.ExprId) EmitError!u32 {
        const expr = self.function.exprs.items[expr_id];
        return switch (expr.data) {
            .param_ref, .local_ref => spirv.StorageClass.Function,
            .global_ref => |index| try self.emitter.global_storage_class(self.emitter.module.globals.items[index]),
            .member => |member| try self.ref_storage_class(member.base),
            .index => |index| try self.ref_storage_class(index.base),
            else => error.InvalidIr,
        };
    }

    fn literal_index(self: *FunctionState, expr_id: ir.ExprId) EmitError!u32 {
        const expr = self.function.exprs.items[expr_id];
        return switch (expr.data) {
            .int_lit => |value| @truncate(value),
            else => error.UnsupportedConstruct,
        };
    }

    fn switch_selector_literal(self: *FunctionState, expr_id: ir.ExprId) EmitError!u32 {
        const expr = self.function.exprs.items[expr_id];
        return switch (expr.data) {
            .int_lit => |value| @truncate(value),
            .bool_lit => |value| if (value) 1 else 0,
            .unary => |unary| if (unary.op == .neg) blk: {
                const inner = self.function.exprs.items[unary.operand];
                switch (inner.data) {
                    .int_lit => |value| break :blk @as(u32, @bitCast(-@as(i32, @intCast(value)))),
                    else => return error.UnsupportedConstruct,
                }
            } else error.UnsupportedConstruct,
            else => error.UnsupportedConstruct,
        };
    }

    const ScalarKind = enum { bool, signed, unsigned, float };

    fn scalar_kind(self: *FunctionState, ty: ir.TypeId) ScalarKind {
        return switch (self.emitter.module.types.get(ty)) {
            .scalar => |scalar| switch (scalar) {
                .bool => .bool,
                .u32 => .unsigned,
                .f32, .abstract_float => .float,
                else => .signed,
            },
            .vector => |vec| switch (self.emitter.module.types.get(vec.elem)) {
                .scalar => |scalar| switch (scalar) {
                    .bool => .bool,
                    .u32 => .unsigned,
                    .f32, .abstract_float => .float,
                    else => .signed,
                },
                else => .signed,
            },
            else => .signed,
        };
    }
};

fn adjusted_memory_align(addr_space: ir.AddressSpace, ty: ir.Type, base_align: u32) u32 {
    return switch (addr_space) {
        .uniform => switch (ty) {
            .array, .struct_ => @max(base_align, 16),
            else => base_align,
        },
        else => base_align,
    };
}

fn round_up(alignment: u32, value: u32) u32 {
    if (alignment <= 1) return value;
    const remainder = value % alignment;
    if (remainder == 0) return value;
    return value + alignment - remainder;
}

fn assign_op_to_binary(op: ir.AssignOp) ir.BinaryOp {
    return switch (op) {
        .assign => .add,
        .add => .add,
        .sub => .sub,
        .mul => .mul,
        .div => .div,
        .rem => .rem,
        .bit_and => .bit_and,
        .bit_or => .bit_or,
        .bit_xor => .bit_xor,
    };
}

fn builtin_to_spirv(builtin: ir.Builtin) EmitError!u32 {
    return switch (builtin) {
        .global_invocation_id => spirv.Builtin.GlobalInvocationId,
        .local_invocation_id => spirv.Builtin.LocalInvocationId,
        .local_invocation_index => spirv.Builtin.LocalInvocationIndex,
        .workgroup_id => spirv.Builtin.WorkgroupId,
        .num_workgroups => spirv.Builtin.NumWorkgroups,
        else => error.UnsupportedConstruct,
    };
}
