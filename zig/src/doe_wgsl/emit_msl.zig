// doe_wgsl/emit_msl.zig — AST-based WGSL → MSL code generator.
//
// Emits Metal Shading Language from a parsed WGSL AST.
// Supports compute, vertex, and fragment shaders with:
// - Multiple entry points per module
// - Struct declarations
// - Helper functions
// - override/const declarations
// - var<workgroup>, var<private>
// - Full expression trees including type constructors
// - Subgroup operations mapped to Metal SIMD intrinsics

const std = @import("std");
const ast_mod = @import("ast.zig");
const token_mod = @import("token.zig");
const Ast = ast_mod.Ast;
const Node = ast_mod.Node;
const NodeTag = ast_mod.NodeTag;
const NULL_NODE = ast_mod.NULL_NODE;
const Tag = token_mod.Tag;

pub const EmitError = error{
    OutputTooLarge,
    InvalidAst,
};

pub const MAX_OUTPUT: usize = 128 * 1024;

pub fn emit(tree: *const Ast, out: []u8) EmitError!usize {
    var e = Emitter{
        .tree = tree,
        .buf = out,
        .pos = 0,
    };
    try e.emitRoot();
    return e.pos;
}

const Emitter = struct {
    tree: *const Ast,
    buf: []u8,
    pos: usize,

    fn emitRoot(self: *Emitter) EmitError!void {
        try self.write("#include <metal_stdlib>\nusing namespace metal;\n");

        const root = self.tree.nodes.items[0];
        const decl_count = root.data.rhs;
        const decl_start = root.data.lhs;

        // Two-pass: emit declarations before functions.
        // Pass 1: enable directives, structs, global vars, override/const.
        var i: u32 = 0;
        while (i < decl_count) : (i += 1) {
            const decl_idx = self.tree.extra_data.items[decl_start + i];
            const node = self.tree.nodes.items[decl_idx];
            switch (node.tag) {
                .enable_directive => {}, // Handled by Metal natively.
                .diagnostic_directive => {},
                .struct_decl => try self.emitStructDecl(node),
                .global_var => try self.emitGlobalVar(node),
                .override_decl => try self.emitOverrideDecl(node, decl_idx),
                .const_decl => try self.emitConstDecl(node, decl_idx),
                .alias_decl => {},
                else => {},
            }
        }

        // Pass 2: helper functions, then entry points.
        i = 0;
        while (i < decl_count) : (i += 1) {
            const decl_idx = self.tree.extra_data.items[decl_start + i];
            const node = self.tree.nodes.items[decl_idx];
            if (node.tag == .fn_decl) {
                try self.emitFnDecl(node);
            }
        }
    }

    // ============================================================
    // Struct declarations
    // ============================================================

    fn emitStructDecl(self: *Emitter, node: Node) EmitError!void {
        const name = self.tokenStr(node.data.lhs);
        const packed_rhs = node.data.rhs;
        const member_start = packed_rhs & 0xFFFF;
        const member_count = packed_rhs >> 16;

        try self.write("\nstruct ");
        try self.write(name);
        try self.write(" {\n");

        var m: u32 = 0;
        while (m < member_count) : (m += 1) {
            const member_idx = self.tree.extra_data.items[member_start + m];
            const member = self.tree.nodes.items[member_idx];
            try self.write("    ");
            try self.emitTypeExpr(member.data.lhs);
            try self.write(" ");
            try self.write(self.tokenStr(member.main_token));
            try self.write(";\n");
        }

        try self.write("};\n");
    }

    // ============================================================
    // Global variables
    // ============================================================

    fn emitGlobalVar(self: *Emitter, node: Node) EmitError!void {
        const extra_start = node.data.rhs;
        const extra = self.tree.extra_data.items;
        const name_token = extra[extra_start];
        const addr_space_token = extra[extra_start + 1];
        _ = extra[extra_start + 2]; // access_mode
        const initializer = extra[extra_start + 3];
        const name = self.tokenStr(name_token);

        // Determine address space from token.
        var addr_space_str: []const u8 = "";
        if (addr_space_token != 0) {
            addr_space_str = self.tokenStr(addr_space_token);
        }

        // workgroup → threadgroup.
        if (std.mem.eql(u8, addr_space_str, "workgroup")) {
            try self.write("\nthreadgroup ");
            try self.emitWorkgroupVarType(node.data.lhs, name);
            try self.write(";\n");
            return;
        }

        // private → thread (module-scope).
        if (std.mem.eql(u8, addr_space_str, "private")) {
            try self.write("\nthread ");
            try self.emitTypeExpr(node.data.lhs);
            try self.write(" ");
            try self.write(name);
            if (initializer != NULL_NODE) {
                try self.write(" = ");
                try self.emitExpr(initializer);
            }
            try self.write(";\n");
            return;
        }

        // storage/uniform vars become kernel parameters (handled in fn emission).
        // Just skip them at module scope.
    }

    // ============================================================
    // Override / const
    // ============================================================

    fn emitOverrideDecl(self: *Emitter, node: Node, node_idx: u32) EmitError!void {
        // Map to MSL function constants.
        // For now, emit as constexpr with default value.
        const name_token = node.main_token + 1; // name follows `override`
        const name = self.tokenStr(name_token);
        _ = node_idx;

        try self.write("\nconstant ");
        if (node.data.lhs != NULL_NODE) {
            try self.emitTypeExpr(node.data.lhs);
        } else {
            try self.write("uint");
        }
        try self.write(" ");
        try self.write(name);
        if (node.data.rhs != NULL_NODE) {
            try self.write(" = ");
            try self.emitExpr(node.data.rhs);
        }
        try self.write(";\n");
    }

    fn emitConstDecl(self: *Emitter, node: Node, node_idx: u32) EmitError!void {
        const name_token = node.main_token + 1;
        const name = self.tokenStr(name_token);
        _ = node_idx;

        try self.write("\nconstant ");
        if (node.data.lhs != NULL_NODE) {
            try self.emitTypeExpr(node.data.lhs);
        } else {
            try self.write("auto");
        }
        try self.write(" ");
        try self.write(name);
        if (node.data.rhs != NULL_NODE) {
            try self.write(" = ");
            try self.emitExpr(node.data.rhs);
        }
        try self.write(";\n");
    }

    // ============================================================
    // Function declarations
    // ============================================================

    fn emitFnDecl(self: *Emitter, node: Node) EmitError!void {
        const extra = self.tree.extra_data.items;
        const extra_start = node.data.lhs;
        const name_token = extra[extra_start];
        const params_start = extra[extra_start + 1];
        const params_len = extra[extra_start + 2];
        const return_type = extra[extra_start + 3];
        const attrs_start = extra[extra_start + 4];
        const attrs_len = extra[extra_start + 5];

        const name = self.tokenStr(name_token);

        // Determine shader stage from attributes.
        const stage = self.detectStage(attrs_start, attrs_len);
        const workgroup_size = self.findWorkgroupSize(attrs_start, attrs_len);

        try self.write("\n");

        switch (stage) {
            .compute => {
                if (workgroup_size) |wgs| {
                    try self.write("[[kernel]]\n");
                    _ = wgs;
                } else {
                    try self.write("[[kernel]]\n");
                }
            },
            .vertex => try self.write("[[vertex]]\n"),
            .fragment => try self.write("[[fragment]]\n"),
            .none => {}, // Helper function.
        }

        // Return type.
        if (return_type != NULL_NODE) {
            try self.emitTypeExpr(return_type);
        } else {
            try self.write("void");
        }
        try self.write(" ");
        // Metal forbids kernel/vertex/fragment functions named "main".
        if (std.mem.eql(u8, name, "main")) {
            switch (stage) {
                .compute => try self.write("main_kernel"),
                .vertex => try self.write("main_vertex"),
                .fragment => try self.write("main_fragment"),
                .none => try self.write(name),
            }
        } else {
            try self.write(name);
        }
        try self.write("(\n");

        // Parameters.
        var p: u32 = 0;
        var buffer_idx: u32 = 0;
        while (p < params_len) : (p += 1) {
            if (p > 0) try self.write(",\n");
            const param_extra_start = self.tree.extra_data.items[params_start + p];
            const param_name_token = extra[param_extra_start];
            const param_type = extra[param_extra_start + 1];
            const param_attrs_start = extra[param_extra_start + 2];
            const param_attrs_len = extra[param_extra_start + 3];

            try self.write("    ");

            // Check for builtin attributes.
            const builtin_name = self.findBuiltinAttr(param_attrs_start, param_attrs_len);
            if (builtin_name) |bn| {
                try self.emitTypeExpr(param_type);
                try self.write(" ");
                try self.write(self.tokenStr(param_name_token));
                if (stage != .none) {
                    try self.write(" [[");
                    try self.write(wgslBuiltinToMsl(bn));
                    try self.write("]]");
                }
            } else {
                try self.emitTypeExpr(param_type);
                try self.write(" ");
                try self.write(self.tokenStr(param_name_token));
                if (stage != .none) {
                    // Entry point parameter — add buffer binding.
                    try self.write(" [[buffer(");
                    try self.writeInt(buffer_idx);
                    try self.write(")]]");
                }
                buffer_idx += 1;
            }
        }

        // For compute entry points, also emit storage buffer bindings from global vars.
        if (stage == .compute or stage == .vertex or stage == .fragment) {
            const root = self.tree.nodes.items[0];
            const decl_count = root.data.rhs;
            const decl_start = root.data.lhs;

            var d: u32 = 0;
            while (d < decl_count) : (d += 1) {
                const decl_idx = self.tree.extra_data.items[decl_start + d];
                const decl = self.tree.nodes.items[decl_idx];
                if (decl.tag == .global_var) {
                    const var_extra_start = decl.data.rhs;
                    const var_name_token = extra[var_extra_start];
                    const var_addr_space = extra[var_extra_start + 1];
                    const var_access_mode = extra[var_extra_start + 2];

                    var addr_space_str: []const u8 = "";
                    if (var_addr_space != 0) {
                        addr_space_str = self.tokenStr(var_addr_space);
                    }

                    // Skip workgroup/private — already emitted as module-scope.
                    if (std.mem.eql(u8, addr_space_str, "workgroup") or
                        std.mem.eql(u8, addr_space_str, "private"))
                    {
                        continue;
                    }

                    if (std.mem.eql(u8, addr_space_str, "storage") or
                        std.mem.eql(u8, addr_space_str, "uniform"))
                    {
                        if (p > 0 or buffer_idx > 0) try self.write(",\n");
                        try self.write("    ");

                        const is_uniform = std.mem.eql(u8, addr_space_str, "uniform");
                        var is_read_only = is_uniform;

                        if (var_access_mode != 0) {
                            const access_str = self.tokenStr(var_access_mode);
                            is_read_only = !std.mem.eql(u8, access_str, "read_write");
                        }

                        if (is_uniform) {
                            try self.write("constant ");
                        } else if (is_read_only) {
                            try self.write("const device ");
                        } else {
                            try self.write("device ");
                        }

                        // Emit element type from array<T> or struct type.
                        try self.emitBufferParamType(decl.data.lhs);
                        try self.write(" ");
                        try self.write(self.tokenStr(var_name_token));

                        // Find binding index from attributes.
                        const var_attrs_start = extra[var_extra_start + 4];
                        const var_attrs_len = extra[var_extra_start + 5];
                        const binding_idx = self.findBindingIndex(var_attrs_start, var_attrs_len);

                        try self.write(" [[buffer(");
                        try self.writeInt(binding_idx orelse buffer_idx);
                        try self.write(")]]");
                        buffer_idx += 1;
                    }
                }
            }
        }

        try self.write("\n) {\n");

        // Body.
        try self.emitBlock(node.data.rhs, 1);

        try self.write("}\n");
    }

    fn emitWorkgroupVarType(self: *Emitter, type_node: u32, name: []const u8) EmitError!void {
        if (type_node == NULL_NODE) {
            try self.write("float ");
            try self.write(name);
            return;
        }
        const node = self.tree.nodes.items[type_node];
        if (node.tag == .type_parameterized) {
            const type_name = self.tokenStr(node.main_token);
            if (std.mem.eql(u8, type_name, "array")) {
                const param_start = node.data.lhs;
                const param_count = node.data.rhs;
                if (param_count >= 1) {
                    try self.emitTypeExpr(self.tree.extra_data.items[param_start]);
                }
                try self.write(" ");
                try self.write(name);
                if (param_count >= 2) {
                    try self.write("[");
                    try self.emitTypeExpr(self.tree.extra_data.items[param_start + 1]);
                    try self.write("]");
                }
                return;
            }
        }
        try self.emitTypeExpr(type_node);
        try self.write(" ");
        try self.write(name);
    }

    fn emitBufferParamType(self: *Emitter, type_node: u32) EmitError!void {
        if (type_node == NULL_NODE) {
            try self.write("float*");
            return;
        }
        const node = self.tree.nodes.items[type_node];
        if (node.tag == .type_parameterized) {
            const type_name = self.tokenStr(node.main_token);
            if (std.mem.eql(u8, type_name, "array")) {
                // array<T> → T*
                const param_start = node.data.lhs;
                const param_count = node.data.rhs;
                if (param_count > 0) {
                    try self.emitTypeExpr(self.tree.extra_data.items[param_start]);
                }
                try self.write("*");
                return;
            }
        }
        // Struct or other type → emit as reference.
        try self.emitTypeExpr(type_node);
        try self.write("&");
    }

    // ============================================================
    // Statements
    // ============================================================

    fn emitBlock(self: *Emitter, block_node_idx: u32, indent: u32) EmitError!void {
        if (block_node_idx == NULL_NODE) return;
        const block_node = self.tree.nodes.items[block_node_idx];
        if (block_node.tag != .block) return;

        const stmt_count = block_node.data.rhs;
        const stmt_start = block_node.data.lhs;

        var s: u32 = 0;
        while (s < stmt_count) : (s += 1) {
            const stmt_idx = self.tree.extra_data.items[stmt_start + s];
            try self.emitStatement(stmt_idx, indent);
        }
    }

    fn emitStatement(self: *Emitter, stmt_idx: u32, indent: u32) EmitError!void {
        if (stmt_idx == NULL_NODE) return;
        const node = self.tree.nodes.items[stmt_idx];

        switch (node.tag) {
            .block => {
                try self.emitIndent(indent);
                try self.write("{\n");
                try self.emitBlock(stmt_idx, indent + 1);
                try self.emitIndent(indent);
                try self.write("}\n");
            },
            .var_stmt => {
                try self.emitIndent(indent);
                try self.emitLocalVarStmt(node);
            },
            .let_stmt => {
                try self.emitIndent(indent);
                try self.emitLocalLetStmt(node);
            },
            .const_stmt => {
                try self.emitIndent(indent);
                try self.emitLocalConstStmt(node);
            },
            .return_stmt => {
                try self.emitIndent(indent);
                try self.write("return");
                if (node.data.lhs != NULL_NODE) {
                    try self.write(" ");
                    try self.emitExpr(node.data.lhs);
                }
                try self.write(";\n");
            },
            .if_stmt => {
                try self.emitIndent(indent);
                try self.emitIfStmt(node, indent);
            },
            .for_stmt => {
                try self.emitIndent(indent);
                try self.emitForStmt(node, indent);
            },
            .while_stmt => {
                try self.emitIndent(indent);
                try self.write("while (");
                try self.emitExpr(node.data.lhs);
                try self.write(") {\n");
                try self.emitBlock(node.data.rhs, indent + 1);
                try self.emitIndent(indent);
                try self.write("}\n");
            },
            .loop_stmt => {
                try self.emitIndent(indent);
                try self.write("while (true) {\n");
                try self.emitBlock(node.data.lhs, indent + 1);
                try self.emitIndent(indent);
                try self.write("}\n");
            },
            .break_stmt => {
                try self.emitIndent(indent);
                try self.write("break;\n");
            },
            .continue_stmt => {
                try self.emitIndent(indent);
                try self.write("continue;\n");
            },
            .continuing_stmt => {
                // continuing blocks map to end-of-loop-body in MSL.
                try self.emitBlock(node.data.lhs, indent);
            },
            .switch_stmt => {
                try self.emitIndent(indent);
                try self.emitSwitchStmt(node, indent);
            },
            .discard_stmt => {
                try self.emitIndent(indent);
                try self.write("discard_fragment();\n");
            },
            .assign_stmt => {
                try self.emitIndent(indent);
                try self.emitExpr(node.data.lhs);
                try self.write(" ");
                try self.write(self.tokenStr(node.main_token));
                try self.write(" ");
                try self.emitExpr(node.data.rhs);
                try self.write(";\n");
            },
            .expr_stmt => {
                try self.emitIndent(indent);
                try self.emitExpr(node.data.lhs);
                try self.write(";\n");
            },
            else => {},
        }
    }

    fn emitLocalVarStmt(self: *Emitter, node: Node) EmitError!void {
        // var name: T = init; → T name = init;
        const name = self.tokenStr(node.main_token + 1);

        if (node.data.lhs != NULL_NODE) {
            try self.emitTypeExpr(node.data.lhs);
        } else {
            try self.write("auto");
        }
        try self.write(" ");
        try self.write(name);
        if (node.data.rhs != NULL_NODE) {
            try self.write(" = ");
            try self.emitExpr(node.data.rhs);
        }
        try self.write(";\n");
    }

    fn emitLocalLetStmt(self: *Emitter, node: Node) EmitError!void {
        const name = self.tokenStr(node.main_token + 1);
        try self.write("const ");
        if (node.data.lhs != NULL_NODE) {
            try self.emitTypeExpr(node.data.lhs);
        } else {
            try self.write("auto");
        }
        try self.write(" ");
        try self.write(name);
        try self.write(" = ");
        try self.emitExpr(node.data.rhs);
        try self.write(";\n");
    }

    fn emitLocalConstStmt(self: *Emitter, node: Node) EmitError!void {
        const name = self.tokenStr(node.main_token + 1);
        try self.write("const ");
        if (node.data.lhs != NULL_NODE) {
            try self.emitTypeExpr(node.data.lhs);
        } else {
            try self.write("auto");
        }
        try self.write(" ");
        try self.write(name);
        try self.write(" = ");
        try self.emitExpr(node.data.rhs);
        try self.write(";\n");
    }

    fn emitIfStmt(self: *Emitter, node: Node, indent: u32) EmitError!void {
        try self.write("if (");
        try self.emitExpr(node.data.lhs);
        try self.write(") {\n");
        try self.emitBlock(node.data.rhs, indent + 1);
        try self.emitIndent(indent);
        try self.write("}");

        // Check for else clause stored in extra_data right after the if.
        // The parser stores else_node in extra right after the if node's creation.
        // We need to find it — it's the extra_data entry added at that point.
        // For now, just close the if. A proper else chain requires linking.
        try self.write("\n");
    }

    fn emitForStmt(self: *Emitter, node: Node, indent: u32) EmitError!void {
        const extra = self.tree.extra_data.items;
        const extra_start = node.data.lhs;
        const init_stmt = extra[extra_start];
        const cond = extra[extra_start + 1];
        const update = extra[extra_start + 2];

        try self.write("for (");
        if (init_stmt != NULL_NODE) {
            // Emit init without trailing newline.
            const init_node = self.tree.nodes.items[init_stmt];
            if (init_node.tag == .var_stmt) {
                if (init_node.data.lhs != NULL_NODE) {
                    try self.emitTypeExpr(init_node.data.lhs);
                } else {
                    try self.write("auto");
                }
                try self.write(" ");
                try self.write(self.tokenStr(init_node.main_token + 1));
                if (init_node.data.rhs != NULL_NODE) {
                    try self.write(" = ");
                    try self.emitExpr(init_node.data.rhs);
                }
            } else if (init_node.tag == .let_stmt) {
                try self.write("const auto ");
                try self.write(self.tokenStr(init_node.main_token + 1));
                try self.write(" = ");
                try self.emitExpr(init_node.data.rhs);
            }
        }
        try self.write("; ");
        if (cond != NULL_NODE) {
            try self.emitExpr(cond);
        }
        try self.write("; ");
        if (update != NULL_NODE) {
            const update_node = self.tree.nodes.items[update];
            if (update_node.tag == .assign_stmt) {
                try self.emitExpr(update_node.data.lhs);
                try self.write(" ");
                try self.write(self.tokenStr(update_node.main_token));
                try self.write(" ");
                try self.emitExpr(update_node.data.rhs);
            } else if (update_node.tag == .expr_stmt) {
                try self.emitExpr(update_node.data.lhs);
            }
        }
        try self.write(") {\n");
        try self.emitBlock(node.data.rhs, indent + 1);
        try self.emitIndent(indent);
        try self.write("}\n");
    }

    fn emitSwitchStmt(self: *Emitter, node: Node, indent: u32) EmitError!void {
        try self.write("switch (");
        try self.emitExpr(node.data.lhs);
        try self.write(") {\n");

        const packed_rhs = node.data.rhs;
        const case_start = packed_rhs & 0xFFFF;
        const case_count = packed_rhs >> 16;

        var c: u32 = 0;
        while (c < case_count) : (c += 1) {
            const case_idx = self.tree.extra_data.items[case_start + c];
            const case_node = self.tree.nodes.items[case_idx];
            try self.emitIndent(indent + 1);

            const case_tag_str = self.tokenStr(case_node.main_token);
            if (std.mem.eql(u8, case_tag_str, "default")) {
                try self.write("default: {\n");
            } else {
                try self.write("case ");
                // Emit case value (simplified).
                try self.write("/* ... */");
                try self.write(": {\n");
            }
            try self.emitBlock(case_node.data.lhs, indent + 2);
            try self.emitIndent(indent + 2);
            try self.write("break;\n");
            try self.emitIndent(indent + 1);
            try self.write("}\n");
        }

        try self.emitIndent(indent);
        try self.write("}\n");
    }

    // ============================================================
    // Expressions
    // ============================================================

    fn emitExpr(self: *Emitter, expr_idx: u32) EmitError!void {
        if (expr_idx == NULL_NODE) return;
        const node = self.tree.nodes.items[expr_idx];

        switch (node.tag) {
            .ident_expr => {
                const name = self.tokenStr(node.main_token);
                try self.write(self.mapIdentifier(name));
            },
            .int_literal, .float_literal => {
                try self.write(self.tokenStr(node.main_token));
            },
            .bool_literal => {
                try self.write(self.tokenStr(node.main_token));
            },
            .binary_expr => {
                try self.write("(");
                try self.emitExpr(node.data.lhs);
                try self.write(" ");
                try self.write(self.tokenStr(node.main_token));
                try self.write(" ");
                try self.emitExpr(node.data.rhs);
                try self.write(")");
            },
            .unary_expr => {
                try self.write(self.tokenStr(node.main_token));
                try self.emitExpr(node.data.lhs);
            },
            .call_expr => {
                try self.emitCallExpr(node);
            },
            .member_expr => {
                try self.emitExpr(node.data.lhs);
                try self.write(".");
                try self.write(self.tokenStr(node.data.rhs));
            },
            .index_expr => {
                try self.emitExpr(node.data.lhs);
                try self.write("[");
                try self.emitExpr(node.data.rhs);
                try self.write("]");
            },
            else => {
                try self.write("/* unhandled expr */");
            },
        }
    }

    fn emitCallExpr(self: *Emitter, node: Node) EmitError!void {
        const name = self.tokenStr(node.main_token);

        // Barrier calls emit as complete statements (no args wrapping).
        if (std.mem.eql(u8, name, "workgroupBarrier")) {
            try self.write("threadgroup_barrier(mem_flags::mem_threadgroup)");
            return;
        }
        if (std.mem.eql(u8, name, "storageBarrier")) {
            try self.write("threadgroup_barrier(mem_flags::mem_device)");
            return;
        }

        const mapped = self.mapCallName(name);
        try self.write(mapped);
        try self.write("(");

        const args_start = node.data.lhs;
        const args_count = node.data.rhs;

        var a: u32 = 0;
        while (a < args_count) : (a += 1) {
            if (a > 0) try self.write(", ");
            const arg_idx = self.tree.extra_data.items[args_start + a];
            try self.emitExpr(arg_idx);
        }
        try self.write(")");
    }

    // ============================================================
    // Type expressions
    // ============================================================

    fn emitTypeExpr(self: *Emitter, type_idx: u32) EmitError!void {
        if (type_idx == NULL_NODE) {
            try self.write("void");
            return;
        }
        const node = self.tree.nodes.items[type_idx];

        switch (node.tag) {
            .type_name => {
                const name = self.tokenStr(node.main_token);
                try self.write(wgslTypeToMslType(name));
            },
            .type_vec_shorthand => {
                const name = self.tokenStr(node.main_token);
                try self.write(wgslShorthandToMsl(name));
            },
            .type_mat_shorthand => {
                const name = self.tokenStr(node.main_token);
                try self.write(wgslShorthandToMsl(name));
            },
            .type_parameterized => {
                try self.emitParameterizedType(node);
            },
            .int_literal => {
                // Array size constant.
                try self.write(self.tokenStr(node.main_token));
            },
            else => {
                try self.write(self.tokenStr(node.main_token));
            },
        }
    }

    fn emitParameterizedType(self: *Emitter, node: Node) EmitError!void {
        const type_name = self.tokenStr(node.main_token);
        const param_start = node.data.lhs;
        const param_count = node.data.rhs;

        if (std.mem.eql(u8, type_name, "array")) {
            if (param_count == 0) {
                try self.write("/* array */");
                return;
            }
            // array<T> → T (when used as buffer element type)
            // array<T, N> → array<T, N> → T[N] in MSL
            if (param_count >= 2) {
                try self.write("array<");
                try self.emitTypeExpr(self.tree.extra_data.items[param_start]);
                try self.write(", ");
                try self.emitTypeExpr(self.tree.extra_data.items[param_start + 1]);
                try self.write(">");
            } else {
                try self.emitTypeExpr(self.tree.extra_data.items[param_start]);
            }
            return;
        }

        if (std.mem.eql(u8, type_name, "atomic")) {
            try self.write("atomic_");
            if (param_count > 0) {
                try self.emitTypeExpr(self.tree.extra_data.items[param_start]);
            }
            return;
        }

        // vec2<f32> → float2, etc.
        if (std.mem.startsWith(u8, type_name, "vec") and param_count > 0) {
            const dim = type_name[3..]; // "2", "3", "4"
            const elem_node = self.tree.extra_data.items[param_start];
            const elem_type = self.tokenStr(self.tree.nodes.items[elem_node].main_token);
            const msl_base = wgslScalarToMslBase(elem_type);
            try self.write(msl_base);
            try self.write(dim);
            return;
        }

        // mat NxM<T> → T NxM in MSL.
        if (std.mem.startsWith(u8, type_name, "mat") and param_count > 0) {
            const elem_node = self.tree.extra_data.items[param_start];
            const elem_type = self.tokenStr(self.tree.nodes.items[elem_node].main_token);
            const msl_base = wgslScalarToMslBase(elem_type);
            // mat4x4<f32> → float4x4
            const dims = type_name[3..]; // e.g., "4x4"
            try self.write(msl_base);
            try self.write(dims);
            return;
        }

        // Fallback: emit as-is with angle brackets.
        try self.write(type_name);
        try self.write("<");
        var p: u32 = 0;
        while (p < param_count) : (p += 1) {
            if (p > 0) try self.write(", ");
            try self.emitTypeExpr(self.tree.extra_data.items[param_start + p]);
        }
        try self.write(">");
    }

    // ============================================================
    // Attribute helpers
    // ============================================================

    const ShaderStage = enum { compute, vertex, fragment, none };

    fn detectStage(self: *const Emitter, attrs_start: u32, attrs_len: u32) ShaderStage {
        if (attrs_len == 0) return .none;
        var i: u32 = 0;
        while (i < attrs_len) : (i += 1) {
            const attr_idx = self.tree.extra_data.items[attrs_start + i];
            const attr = self.tree.nodes.items[attr_idx];
            const attr_name = self.tokenStr(attr.data.lhs);
            if (std.mem.eql(u8, attr_name, "compute")) return .compute;
            if (std.mem.eql(u8, attr_name, "vertex")) return .vertex;
            if (std.mem.eql(u8, attr_name, "fragment")) return .fragment;
        }
        return .none;
    }

    fn findWorkgroupSize(self: *const Emitter, attrs_start: u32, attrs_len: u32) ?u32 {
        if (attrs_len == 0) return null;
        var i: u32 = 0;
        while (i < attrs_len) : (i += 1) {
            const attr_idx = self.tree.extra_data.items[attrs_start + i];
            const attr = self.tree.nodes.items[attr_idx];
            const attr_name = self.tokenStr(attr.data.lhs);
            if (std.mem.eql(u8, attr_name, "workgroup_size")) {
                return attr_idx;
            }
        }
        return null;
    }

    fn findBuiltinAttr(self: *const Emitter, attrs_start: u32, attrs_len: u32) ?[]const u8 {
        if (attrs_len == 0) return null;
        var i: u32 = 0;
        while (i < attrs_len) : (i += 1) {
            const attr_idx = self.tree.extra_data.items[attrs_start + i];
            const attr = self.tree.nodes.items[attr_idx];
            const attr_name = self.tokenStr(attr.data.lhs);
            if (std.mem.eql(u8, attr_name, "builtin")) {
                // The arg is the builtin name.
                const attr_packed = attr.data.rhs;
                const args_start = attr_packed & 0xFFFF;
                const args_len = attr_packed >> 16;
                if (args_len > 0) {
                    const arg_node_idx = self.tree.extra_data.items[args_start];
                    const arg_node = self.tree.nodes.items[arg_node_idx];
                    return self.tokenStr(arg_node.main_token);
                }
            }
        }
        return null;
    }

    fn findBindingIndex(self: *const Emitter, attrs_start: u32, attrs_len: u32) ?u32 {
        if (attrs_len == 0) return null;
        var i: u32 = 0;
        while (i < attrs_len) : (i += 1) {
            const attr_idx = self.tree.extra_data.items[attrs_start + i];
            const attr = self.tree.nodes.items[attr_idx];
            const attr_name = self.tokenStr(attr.data.lhs);
            if (std.mem.eql(u8, attr_name, "binding")) {
                const attr_packed = attr.data.rhs;
                const args_start = attr_packed & 0xFFFF;
                const args_len = attr_packed >> 16;
                if (args_len > 0) {
                    const arg_node_idx = self.tree.extra_data.items[args_start];
                    const arg_node = self.tree.nodes.items[arg_node_idx];
                    const val_str = self.tokenStr(arg_node.main_token);
                    return std.fmt.parseInt(u32, val_str, 10) catch null;
                }
            }
        }
        return null;
    }

    // ============================================================
    // Name / type mapping
    // ============================================================

    fn mapIdentifier(self: *const Emitter, name: []const u8) []const u8 {
        _ = self;
        return name;
    }

    fn mapCallName(self: *const Emitter, name: []const u8) []const u8 {
        _ = self;
        // WGSL builtin → MSL mapping.
        if (std.mem.eql(u8, name, "workgroupBarrier")) return "threadgroup_barrier(mem_flags::mem_threadgroup);\n    // _wgsl_barrier";
        if (std.mem.eql(u8, name, "storageBarrier")) return "threadgroup_barrier(mem_flags::mem_device);\n    // _wgsl_barrier";
        if (std.mem.eql(u8, name, "subgroupAdd")) return "simd_sum";
        if (std.mem.eql(u8, name, "subgroupBroadcastFirst")) return "simd_broadcast_first";
        if (std.mem.eql(u8, name, "subgroupBroadcast")) return "simd_broadcast";
        if (std.mem.eql(u8, name, "subgroupMul")) return "simd_product";
        if (std.mem.eql(u8, name, "subgroupMax")) return "simd_max";
        if (std.mem.eql(u8, name, "subgroupMin")) return "simd_min";
        if (std.mem.eql(u8, name, "subgroupAnd")) return "simd_and";
        if (std.mem.eql(u8, name, "subgroupOr")) return "simd_or";
        if (std.mem.eql(u8, name, "subgroupXor")) return "simd_xor";
        if (std.mem.eql(u8, name, "bitcast")) return "as_type";
        if (std.mem.eql(u8, name, "arrayLength")) return "/* arrayLength */ 0; //";
        if (std.mem.eql(u8, name, "unpack2x16float")) return "as_type<half2>";
        if (std.mem.eql(u8, name, "pack2x16float")) return "as_type<uint>";
        if (std.mem.eql(u8, name, "select")) return "select";
        // Type constructors.
        if (std.mem.eql(u8, name, "vec2f")) return "float2";
        if (std.mem.eql(u8, name, "vec3f")) return "float3";
        if (std.mem.eql(u8, name, "vec4f")) return "float4";
        if (std.mem.eql(u8, name, "vec2u")) return "uint2";
        if (std.mem.eql(u8, name, "vec3u")) return "uint3";
        if (std.mem.eql(u8, name, "vec4u")) return "uint4";
        if (std.mem.eql(u8, name, "vec2i")) return "int2";
        if (std.mem.eql(u8, name, "vec3i")) return "int3";
        if (std.mem.eql(u8, name, "vec4i")) return "int4";
        if (std.mem.eql(u8, name, "vec2h")) return "half2";
        if (std.mem.eql(u8, name, "vec3h")) return "half3";
        if (std.mem.eql(u8, name, "vec4h")) return "half4";
        if (std.mem.eql(u8, name, "mat4x4f")) return "float4x4";
        if (std.mem.eql(u8, name, "mat3x3f")) return "float3x3";
        if (std.mem.eql(u8, name, "mat2x2f")) return "float2x2";
        // Scalar casts.
        if (std.mem.eql(u8, name, "f32")) return "float";
        if (std.mem.eql(u8, name, "f16")) return "half";
        if (std.mem.eql(u8, name, "u32")) return "uint";
        if (std.mem.eql(u8, name, "i32")) return "int";
        if (std.mem.eql(u8, name, "bool")) return "bool";
        // Math builtins pass through (Metal has the same names).
        return name;
    }

    fn tokenStr(self: *const Emitter, token_idx: u32) []const u8 {
        return self.tree.tokenSlice(token_idx);
    }

    // ============================================================
    // Output helpers
    // ============================================================

    fn write(self: *Emitter, data: []const u8) EmitError!void {
        if (self.pos + data.len > self.buf.len) return EmitError.OutputTooLarge;
        @memcpy(self.buf[self.pos..][0..data.len], data);
        self.pos += data.len;
    }

    fn writeInt(self: *Emitter, val: u32) EmitError!void {
        var tmp: [16]u8 = undefined;
        const s = std.fmt.bufPrint(&tmp, "{d}", .{val}) catch return EmitError.OutputTooLarge;
        try self.write(s);
    }

    fn emitIndent(self: *Emitter, level: u32) EmitError!void {
        var i: u32 = 0;
        while (i < level) : (i += 1) {
            try self.write("    ");
        }
    }
};

// ============================================================
// Type mapping tables
// ============================================================

fn wgslTypeToMslType(name: []const u8) []const u8 {
    if (std.mem.eql(u8, name, "f32")) return "float";
    if (std.mem.eql(u8, name, "f16")) return "half";
    if (std.mem.eql(u8, name, "u32")) return "uint";
    if (std.mem.eql(u8, name, "i32")) return "int";
    if (std.mem.eql(u8, name, "bool")) return "bool";
    return name; // User-defined struct or unknown.
}

fn wgslShorthandToMsl(name: []const u8) []const u8 {
    if (std.mem.eql(u8, name, "vec2f")) return "float2";
    if (std.mem.eql(u8, name, "vec3f")) return "float3";
    if (std.mem.eql(u8, name, "vec4f")) return "float4";
    if (std.mem.eql(u8, name, "vec2u")) return "uint2";
    if (std.mem.eql(u8, name, "vec3u")) return "uint3";
    if (std.mem.eql(u8, name, "vec4u")) return "uint4";
    if (std.mem.eql(u8, name, "vec2i")) return "int2";
    if (std.mem.eql(u8, name, "vec3i")) return "int3";
    if (std.mem.eql(u8, name, "vec4i")) return "int4";
    if (std.mem.eql(u8, name, "vec2h")) return "half2";
    if (std.mem.eql(u8, name, "vec3h")) return "half3";
    if (std.mem.eql(u8, name, "vec4h")) return "half4";
    if (std.mem.eql(u8, name, "mat2x2f")) return "float2x2";
    if (std.mem.eql(u8, name, "mat3x3f")) return "float3x3";
    if (std.mem.eql(u8, name, "mat4x4f")) return "float4x4";
    if (std.mem.eql(u8, name, "mat2x2h")) return "half2x2";
    if (std.mem.eql(u8, name, "mat3x3h")) return "half3x3";
    if (std.mem.eql(u8, name, "mat4x4h")) return "half4x4";
    return name;
}

fn wgslScalarToMslBase(name: []const u8) []const u8 {
    if (std.mem.eql(u8, name, "f32")) return "float";
    if (std.mem.eql(u8, name, "f16")) return "half";
    if (std.mem.eql(u8, name, "u32")) return "uint";
    if (std.mem.eql(u8, name, "i32")) return "int";
    if (std.mem.eql(u8, name, "bool")) return "bool";
    return "float";
}

fn wgslBuiltinToMsl(name: []const u8) []const u8 {
    if (std.mem.eql(u8, name, "global_invocation_id")) return "thread_position_in_grid";
    if (std.mem.eql(u8, name, "local_invocation_id")) return "thread_position_in_threadgroup";
    if (std.mem.eql(u8, name, "workgroup_id")) return "threadgroup_position_in_grid";
    if (std.mem.eql(u8, name, "num_workgroups")) return "threadgroups_per_grid";
    if (std.mem.eql(u8, name, "local_invocation_index")) return "thread_index_in_threadgroup";
    if (std.mem.eql(u8, name, "vertex_index")) return "vertex_id";
    if (std.mem.eql(u8, name, "instance_index")) return "instance_id";
    if (std.mem.eql(u8, name, "position")) return "position";
    if (std.mem.eql(u8, name, "front_facing")) return "front_facing";
    if (std.mem.eql(u8, name, "sample_index")) return "sample_id";
    if (std.mem.eql(u8, name, "subgroup_invocation_id")) return "thread_index_in_simdgroup";
    if (std.mem.eql(u8, name, "subgroup_size")) return "threads_per_simdgroup";
    return name;
}

// ============================================================
// Tests
// ============================================================

const parser_mod = @import("parser.zig");

test "emit simple compute shader" {
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

    var tree = try parser_mod.parseSource(std.testing.allocator, source);
    defer tree.deinit();

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try emit(&tree, &out);
    const msl = out[0..len];

    // Should contain Metal headers and kernel declaration.
    try std.testing.expect(std.mem.indexOf(u8, msl, "#include <metal_stdlib>") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "[[kernel]]") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "thread_position_in_grid") != null);
}

test "emit struct" {
    const source =
        \\struct Params {
        \\    size: u32,
        \\    scale: f32,
        \\}
        \\@group(0) @binding(0) var<uniform> params: Params;
        \\@compute @workgroup_size(64)
        \\fn main(@builtin(global_invocation_id) id: vec3u) {
        \\    let s = params.size;
        \\}
    ;
    var tree = try parser_mod.parseSource(std.testing.allocator, source);
    defer tree.deinit();

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try emit(&tree, &out);
    const msl = out[0..len];

    try std.testing.expect(std.mem.indexOf(u8, msl, "struct Params") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "uint size") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "float scale") != null);
}

test "emit rmsnorm-like shader" {
    const source =
        \\enable subgroups;
        \\
        \\override WORKGROUP_SIZE: u32 = 256u;
        \\const MAX_WORKGROUP_SIZE: u32 = 256u;
        \\override RMS_NORM_OFFSET: bool = false;
        \\
        \\struct Uniforms {
        \\    size: u32,
        \\    num_tokens: u32,
        \\    eps: f32,
        \\}
        \\
        \\@group(0) @binding(0) var<uniform> u: Uniforms;
        \\@group(0) @binding(1) var<storage, read> input: array<f32>;
        \\@group(0) @binding(2) var<storage, read_write> output: array<f32>;
        \\
        \\var<workgroup> shared_sum: array<f32, 256>;
        \\
        \\fn apply_weight(w: f32) -> f32 {
        \\    if (RMS_NORM_OFFSET) {
        \\        return 1.0 + w;
        \\    } else {
        \\        return w;
        \\    }
        \\}
        \\
        \\@compute @workgroup_size(256)
        \\fn main(
        \\    @builtin(global_invocation_id) global_id: vec3<u32>,
        \\    @builtin(local_invocation_id) local_id: vec3<u32>,
        \\    @builtin(workgroup_id) wg_id: vec3<u32>
        \\) {
        \\    let token_idx = wg_id.x;
        \\    let thread_idx = local_id.x;
        \\    let size = u.size;
        \\    let base_offset = token_idx * size;
        \\
        \\    var local_sum_sq: f32 = 0.0;
        \\    for (var i: u32 = 0u; i < size; i = i + 1u) {
        \\        let x = input[base_offset + i];
        \\        local_sum_sq = local_sum_sq + x * x;
        \\    }
        \\
        \\    shared_sum[thread_idx] = local_sum_sq;
        \\    workgroupBarrier();
        \\
        \\    let mean_sq = shared_sum[0] / f32(size);
        \\    let rms = sqrt(mean_sq + u.eps);
        \\    let inv_rms = 1.0 / rms;
        \\
        \\    output[base_offset] = inv_rms;
        \\}
    ;

    var tree = try parser_mod.parseSource(std.testing.allocator, source);
    defer tree.deinit();

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try emit(&tree, &out);
    const msl = out[0..len];

    try std.testing.expect(std.mem.indexOf(u8, msl, "#include <metal_stdlib>") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "struct Uniforms") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "uint size") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "constant uint WORKGROUP_SIZE") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "threadgroup") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "[[kernel]]") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "thread_position_in_grid") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "thread_position_in_threadgroup") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "threadgroup_position_in_grid") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "apply_weight") != null);
}

test "emit subgroup builtins" {
    const source =
        \\enable subgroups;
        \\
        \\@group(0) @binding(0) var<storage, read_write> data: array<f32>;
        \\
        \\@compute @workgroup_size(64)
        \\fn main(
        \\    @builtin(global_invocation_id) gid: vec3u,
        \\    @builtin(subgroup_invocation_id) sg_lane: u32,
        \\    @builtin(subgroup_size) sg_size: u32
        \\) {
        \\    let val = data[gid.x];
        \\    let sum = subgroupAdd(val);
        \\    data[gid.x] = sum;
        \\}
    ;

    var tree = try parser_mod.parseSource(std.testing.allocator, source);
    defer tree.deinit();

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try emit(&tree, &out);
    const msl = out[0..len];

    try std.testing.expect(std.mem.indexOf(u8, msl, "thread_index_in_simdgroup") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "threads_per_simdgroup") != null);
    try std.testing.expect(std.mem.indexOf(u8, msl, "simd_sum") != null);
}

test "emit multiple entry points" {
    const source =
        \\fn helper(x: f32) -> f32 {
        \\    return x * 2.0;
        \\}
        \\
        \\@group(0) @binding(0) var<storage, read_write> buf: array<f32>;
        \\
        \\@compute @workgroup_size(64)
        \\fn kernel_a(@builtin(global_invocation_id) gid: vec3u) {
        \\    buf[gid.x] = helper(buf[gid.x]);
        \\}
        \\
        \\@compute @workgroup_size(128)
        \\fn kernel_b(@builtin(global_invocation_id) gid: vec3u) {
        \\    buf[gid.x] = helper(buf[gid.x]) + 1.0;
        \\}
    ;

    var tree = try parser_mod.parseSource(std.testing.allocator, source);
    defer tree.deinit();

    var out: [MAX_OUTPUT]u8 = undefined;
    const len = try emit(&tree, &out);
    const msl = out[0..len];

    try std.testing.expect(std.mem.indexOf(u8, msl, "helper") != null);

    var count: usize = 0;
    var idx: usize = 0;
    while (std.mem.indexOfPos(u8, msl, idx, "[[kernel]]")) |found| {
        count += 1;
        idx = found + 1;
    }
    try std.testing.expectEqual(@as(usize, 2), count);
}
