const std = @import("std");

pub const EmitError = error{
    OutOfMemory,
    OutputTooLarge,
    UnsupportedConstruct,
};

pub const WORD_BYTES: usize = 4;
pub const MAGIC: u32 = 0x07230203;
const VERSION_1_3: u32 = 0x00010300;
const GENERATOR_ID: u32 = 0;
const SCHEMA: u32 = 0;

pub const Capability = struct {
    pub const Shader: u32 = 1;
};

pub const AddressingModel = struct {
    pub const Logical: u32 = 0;
};

pub const MemoryModel = struct {
    pub const GLSL450: u32 = 1;
};

pub const Dim = struct {
    pub const _2D: u32 = 1;
};

pub const ImageFormat = struct {
    pub const Unknown: u32 = 0;
    pub const Rgba8: u32 = 4;
};

pub const ImageOperandsMask = struct {
    pub const Lod: u32 = 0x00000002;
};

pub const ExecutionModel = struct {
    pub const GLCompute: u32 = 5;
};

pub const ExecutionMode = struct {
    pub const LocalSize: u32 = 17;
};

pub const Scope = struct {
    pub const CrossDevice: u32 = 0;
    pub const Device: u32 = 1;
    pub const Workgroup: u32 = 2;
    pub const Subgroup: u32 = 3;
    pub const Invocation: u32 = 4;
};

pub const MemorySemantics = struct {
    pub const None: u32 = 0x00000000;
    pub const AcquireRelease: u32 = 0x00000008;
    pub const SequentiallyConsistent: u32 = 0x00000010;
    pub const UniformMemory: u32 = 0x00000040;
    pub const WorkgroupMemory: u32 = 0x00000100;
    pub const ImageMemory: u32 = 0x00000800;
};

pub const StorageClass = struct {
    pub const UniformConstant: u32 = 0;
    pub const Input: u32 = 1;
    pub const Uniform: u32 = 2;
    pub const Workgroup: u32 = 4;
    pub const Private: u32 = 6;
    pub const Function: u32 = 7;
    pub const StorageBuffer: u32 = 12;
};

pub const Decoration = struct {
    pub const Block: u32 = 2;
    pub const ArrayStride: u32 = 6;
    pub const BuiltIn: u32 = 11;
    pub const NonWritable: u32 = 24;
    pub const NonReadable: u32 = 25;
    pub const Binding: u32 = 33;
    pub const DescriptorSet: u32 = 34;
    pub const Offset: u32 = 35;
};

pub const Builtin = struct {
    pub const NumWorkgroups: u32 = 25;
    pub const WorkgroupId: u32 = 26;
    pub const GlobalInvocationId: u32 = 28;
    pub const LocalInvocationId: u32 = 29;
    pub const LocalInvocationIndex: u32 = 30;
};

pub const FunctionControl = struct {
    pub const None: u32 = 0;
};

pub const SelectionControl = struct {
    pub const None: u32 = 0;
};

pub const LoopControl = struct {
    pub const None: u32 = 0;
};

pub const Opcode = struct {
    pub const Name: u16 = 5;
    pub const ExtInstImport: u16 = 11;
    pub const ExtInst: u16 = 12;
    pub const EntryPoint: u16 = 15;
    pub const ExecutionMode: u16 = 16;
    pub const Capability: u16 = 17;
    pub const TypeVoid: u16 = 19;
    pub const TypeBool: u16 = 20;
    pub const TypeInt: u16 = 21;
    pub const TypeFloat: u16 = 22;
    pub const TypeVector: u16 = 23;
    pub const TypeMatrix: u16 = 24;
    pub const TypeImage: u16 = 25;
    pub const TypeArray: u16 = 28;
    pub const TypeRuntimeArray: u16 = 29;
    pub const TypeStruct: u16 = 30;
    pub const TypePointer: u16 = 32;
    pub const TypeFunction: u16 = 33;
    pub const ConstantTrue: u16 = 41;
    pub const ConstantFalse: u16 = 42;
    pub const Constant: u16 = 43;
    pub const ConstantComposite: u16 = 44;
    pub const Function: u16 = 54;
    pub const FunctionParameter: u16 = 55;
    pub const FunctionEnd: u16 = 56;
    pub const FunctionCall: u16 = 57;
    pub const Variable: u16 = 59;
    pub const Load: u16 = 61;
    pub const Store: u16 = 62;
    pub const AccessChain: u16 = 65;
    pub const Decorate: u16 = 71;
    pub const MemberDecorate: u16 = 72;
    pub const CompositeConstruct: u16 = 80;
    pub const CompositeExtract: u16 = 81;
    pub const ImageFetch: u16 = 95;
    pub const ImageWrite: u16 = 99;
    pub const SNegate: u16 = 126;
    pub const FNegate: u16 = 127;
    pub const IAdd: u16 = 128;
    pub const FAdd: u16 = 129;
    pub const ISub: u16 = 130;
    pub const FSub: u16 = 131;
    pub const IMul: u16 = 132;
    pub const FMul: u16 = 133;
    pub const UDiv: u16 = 134;
    pub const SDiv: u16 = 135;
    pub const FDiv: u16 = 136;
    pub const UMod: u16 = 137;
    pub const SRem: u16 = 138;
    pub const FRem: u16 = 140;
    pub const Dot: u16 = 148;
    pub const LogicalEqual: u16 = 164;
    pub const LogicalNotEqual: u16 = 165;
    pub const LogicalOr: u16 = 166;
    pub const LogicalAnd: u16 = 167;
    pub const LogicalNot: u16 = 168;
    pub const Select: u16 = 169;
    pub const IEqual: u16 = 170;
    pub const INotEqual: u16 = 171;
    pub const UGreaterThan: u16 = 172;
    pub const SGreaterThan: u16 = 173;
    pub const UGreaterThanEqual: u16 = 174;
    pub const SGreaterThanEqual: u16 = 175;
    pub const ULessThan: u16 = 176;
    pub const SLessThan: u16 = 177;
    pub const ULessThanEqual: u16 = 178;
    pub const SLessThanEqual: u16 = 179;
    pub const FOrdEqual: u16 = 180;
    pub const FOrdNotEqual: u16 = 181;
    pub const FOrdLessThan: u16 = 182;
    pub const FOrdGreaterThan: u16 = 183;
    pub const FOrdLessThanEqual: u16 = 184;
    pub const FOrdGreaterThanEqual: u16 = 185;
    pub const ShiftRightLogical: u16 = 194;
    pub const ShiftRightArithmetic: u16 = 195;
    pub const ShiftLeftLogical: u16 = 196;
    pub const BitwiseOr: u16 = 197;
    pub const BitwiseXor: u16 = 198;
    pub const BitwiseAnd: u16 = 199;
    pub const Not: u16 = 200;
    pub const ControlBarrier: u16 = 224;
    pub const MemoryBarrier: u16 = 225;
    pub const AtomicLoad: u16 = 227;
    pub const AtomicStore: u16 = 228;
    pub const AtomicExchange: u16 = 229;
    pub const AtomicIAdd: u16 = 234;
    pub const AtomicISub: u16 = 235;
    pub const AtomicSMin: u16 = 236;
    pub const AtomicUMin: u16 = 237;
    pub const AtomicSMax: u16 = 238;
    pub const AtomicUMax: u16 = 239;
    pub const AtomicAnd: u16 = 240;
    pub const AtomicOr: u16 = 241;
    pub const AtomicXor: u16 = 242;
    pub const Label: u16 = 248;
    pub const Branch: u16 = 249;
    pub const BranchConditional: u16 = 250;
    pub const Switch: u16 = 251;
    pub const Return: u16 = 253;
    pub const ReturnValue: u16 = 254;
    pub const FunctionCallResult: u16 = 57;
    pub const LoopMerge: u16 = 246;
    pub const SelectionMerge: u16 = 247;
    pub const MemoryModel: u16 = 14;
};

const VecKey = struct { elem: u32, len: u32 };
const ArrayKey = struct { elem: u32, len_const: u32 };
const RuntimeArrayKey = struct { elem: u32 };
const ImageKey = struct {
    sampled_type: u32,
    dim: u32,
    depth: u32,
    arrayed: u32,
    multisampled: u32,
    sampled: u32,
    image_format: u32,
};
const PtrKey = struct { storage_class: u32, pointee: u32 };
const FnKey = struct { return_type: u32, params_start: u32, params_len: u32 };
const StructKey = struct { members_start: u32, members_len: u32 };
const ScalarConstKey = struct { ty: u32, bits: u32 };

pub const Builder = struct {
    allocator: std.mem.Allocator,
    next_id: u32 = 1,
    entry_point_fn: u32 = 0,
    entry_point_name: []const u8 = "main",
    glsl450_import: u32 = 0,

    params_scratch: std.ArrayListUnmanaged(u32) = .{},
    members_scratch: std.ArrayListUnmanaged(u32) = .{},

    capabilities: std.ArrayListUnmanaged(u32) = .{},
    ext_inst_imports: std.ArrayListUnmanaged(u32) = .{},
    memory_model: std.ArrayListUnmanaged(u32) = .{},
    entry_points: std.ArrayListUnmanaged(u32) = .{},
    execution_modes: std.ArrayListUnmanaged(u32) = .{},
    debug: std.ArrayListUnmanaged(u32) = .{},
    annotations: std.ArrayListUnmanaged(u32) = .{},
    types_globals: std.ArrayListUnmanaged(u32) = .{},
    functions: std.ArrayListUnmanaged(u32) = .{},

    vector_types: std.AutoHashMapUnmanaged(VecKey, u32) = .{},
    array_types: std.AutoHashMapUnmanaged(ArrayKey, u32) = .{},
    runtime_array_types: std.AutoHashMapUnmanaged(RuntimeArrayKey, u32) = .{},
    image_types: std.AutoHashMapUnmanaged(ImageKey, u32) = .{},
    pointer_types: std.AutoHashMapUnmanaged(PtrKey, u32) = .{},
    function_types: std.AutoHashMapUnmanaged(FnKey, u32) = .{},
    struct_types: std.AutoHashMapUnmanaged(StructKey, u32) = .{},
    scalar_constants: std.AutoHashMapUnmanaged(ScalarConstKey, u32) = .{},

    void_type: u32 = 0,
    bool_type: u32 = 0,
    u32_type: u32 = 0,
    i32_type: u32 = 0,
    f32_type: u32 = 0,

    pub fn init(allocator: std.mem.Allocator) Builder {
        var builder = Builder{ .allocator = allocator };
        builder.emit_capability(Capability.Shader) catch {};
        builder.emit_memory_model() catch {};
        return builder;
    }

    pub fn deinit(self: *Builder) void {
        self.params_scratch.deinit(self.allocator);
        self.members_scratch.deinit(self.allocator);
        self.capabilities.deinit(self.allocator);
        self.ext_inst_imports.deinit(self.allocator);
        self.memory_model.deinit(self.allocator);
        self.entry_points.deinit(self.allocator);
        self.execution_modes.deinit(self.allocator);
        self.debug.deinit(self.allocator);
        self.annotations.deinit(self.allocator);
        self.types_globals.deinit(self.allocator);
        self.functions.deinit(self.allocator);
        self.vector_types.deinit(self.allocator);
        self.array_types.deinit(self.allocator);
        self.runtime_array_types.deinit(self.allocator);
        self.image_types.deinit(self.allocator);
        self.pointer_types.deinit(self.allocator);
        self.function_types.deinit(self.allocator);
        self.struct_types.deinit(self.allocator);
        self.scalar_constants.deinit(self.allocator);
    }

    pub fn reserve_id(self: *Builder) u32 {
        const id = self.next_id;
        self.next_id += 1;
        return id;
    }

    fn append_inst(self: *Builder, list: *std.ArrayListUnmanaged(u32), opcode: u16, operands: []const u32) EmitError!void {
        const word_count: u32 = @intCast(operands.len + 1);
        try list.append(self.allocator, (@as(u32, word_count) << 16) | opcode);
        try list.appendSlice(self.allocator, operands);
    }

    pub fn append_function_inst(self: *Builder, opcode: u16, operands: []const u32) EmitError!void {
        try self.append_inst(&self.functions, opcode, operands);
    }

    pub fn emit_capability(self: *Builder, capability: u32) EmitError!void {
        try self.append_inst(&self.capabilities, Opcode.Capability, &.{capability});
    }

    fn emit_memory_model(self: *Builder) EmitError!void {
        try self.append_inst(&self.memory_model, Opcode.MemoryModel, &.{ AddressingModel.Logical, MemoryModel.GLSL450 });
    }

    pub fn glsl450_import_id(self: *Builder) EmitError!u32 {
        if (self.glsl450_import != 0) return self.glsl450_import;
        const import_id = self.reserve_id();
        try self.ext_inst_imports.append(
            self.allocator,
            (@as(u32, @intCast(2 + string_word_len("GLSL.std.450"))) << 16) | Opcode.ExtInstImport,
        );
        try self.ext_inst_imports.append(self.allocator, import_id);
        try append_string_words(&self.ext_inst_imports, self.allocator, "GLSL.std.450");
        self.glsl450_import = import_id;
        return import_id;
    }

    pub fn emit_name(self: *Builder, target_id: u32, name: []const u8) EmitError!void {
        try self.debug.append(self.allocator, (@as(u32, @intCast(2 + string_word_len(name))) << 16) | Opcode.Name);
        try self.debug.append(self.allocator, target_id);
        try append_string_words(&self.debug, self.allocator, name);
    }

    pub fn emit_entry_point(self: *Builder, fn_id: u32, name: []const u8, interfaces: []const u32) EmitError!void {
        self.entry_point_fn = fn_id;
        self.entry_point_name = name;
        try self.entry_points.append(self.allocator, (@as(u32, @intCast(3 + string_word_len(name) + interfaces.len)) << 16) | Opcode.EntryPoint);
        try self.entry_points.append(self.allocator, ExecutionModel.GLCompute);
        try self.entry_points.append(self.allocator, fn_id);
        try append_string_words(&self.entry_points, self.allocator, name);
        try self.entry_points.appendSlice(self.allocator, interfaces);
    }

    pub fn emit_execution_mode_local_size(self: *Builder, fn_id: u32, x: u32, y: u32, z: u32) EmitError!void {
        try self.append_inst(&self.execution_modes, Opcode.ExecutionMode, &.{ fn_id, ExecutionMode.LocalSize, x, y, z });
    }

    pub fn type_void(self: *Builder) EmitError!u32 {
        if (self.void_type != 0) return self.void_type;
        const id = self.reserve_id();
        try self.append_inst(&self.types_globals, Opcode.TypeVoid, &.{id});
        self.void_type = id;
        return id;
    }

    pub fn type_bool(self: *Builder) EmitError!u32 {
        if (self.bool_type != 0) return self.bool_type;
        const id = self.reserve_id();
        try self.append_inst(&self.types_globals, Opcode.TypeBool, &.{id});
        self.bool_type = id;
        return id;
    }

    pub fn type_u32(self: *Builder) EmitError!u32 {
        if (self.u32_type != 0) return self.u32_type;
        const id = self.reserve_id();
        try self.append_inst(&self.types_globals, Opcode.TypeInt, &.{ id, 32, 0 });
        self.u32_type = id;
        return id;
    }

    pub fn type_i32(self: *Builder) EmitError!u32 {
        if (self.i32_type != 0) return self.i32_type;
        const id = self.reserve_id();
        try self.append_inst(&self.types_globals, Opcode.TypeInt, &.{ id, 32, 1 });
        self.i32_type = id;
        return id;
    }

    pub fn type_f32(self: *Builder) EmitError!u32 {
        if (self.f32_type != 0) return self.f32_type;
        const id = self.reserve_id();
        try self.append_inst(&self.types_globals, Opcode.TypeFloat, &.{ id, 32 });
        self.f32_type = id;
        return id;
    }

    pub fn type_vector(self: *Builder, elem_type: u32, len: u32) EmitError!u32 {
        const key = VecKey{ .elem = elem_type, .len = len };
        if (self.vector_types.get(key)) |id| return id;
        const id = self.reserve_id();
        try self.append_inst(&self.types_globals, Opcode.TypeVector, &.{ id, elem_type, len });
        try self.vector_types.put(self.allocator, key, id);
        return id;
    }

    pub fn type_array(self: *Builder, elem_type: u32, len_const_id: u32) EmitError!u32 {
        const key = ArrayKey{ .elem = elem_type, .len_const = len_const_id };
        if (self.array_types.get(key)) |id| return id;
        const id = self.reserve_id();
        try self.append_inst(&self.types_globals, Opcode.TypeArray, &.{ id, elem_type, len_const_id });
        try self.array_types.put(self.allocator, key, id);
        return id;
    }

    pub fn type_runtime_array(self: *Builder, elem_type: u32) EmitError!u32 {
        const key = RuntimeArrayKey{ .elem = elem_type };
        if (self.runtime_array_types.get(key)) |id| return id;
        const id = self.reserve_id();
        try self.append_inst(&self.types_globals, Opcode.TypeRuntimeArray, &.{ id, elem_type });
        try self.runtime_array_types.put(self.allocator, key, id);
        return id;
    }

    pub fn type_image(
        self: *Builder,
        sampled_type: u32,
        dim: u32,
        depth: u32,
        arrayed: u32,
        multisampled: u32,
        sampled: u32,
        image_format: u32,
    ) EmitError!u32 {
        const key = ImageKey{
            .sampled_type = sampled_type,
            .dim = dim,
            .depth = depth,
            .arrayed = arrayed,
            .multisampled = multisampled,
            .sampled = sampled,
            .image_format = image_format,
        };
        if (self.image_types.get(key)) |id| return id;
        const id = self.reserve_id();
        try self.append_inst(
            &self.types_globals,
            Opcode.TypeImage,
            &.{ id, sampled_type, dim, depth, arrayed, multisampled, sampled, image_format },
        );
        try self.image_types.put(self.allocator, key, id);
        return id;
    }

    pub fn type_struct(self: *Builder, member_types: []const u32) EmitError!u32 {
        const members_start: u32 = @intCast(self.members_scratch.items.len);
        try self.members_scratch.appendSlice(self.allocator, member_types);
        const key = StructKey{ .members_start = members_start, .members_len = @intCast(member_types.len) };
        if (self.find_struct_type(member_types)) |id| return id;
        const id = self.reserve_id();
        try self.types_globals.append(self.allocator, (@as(u32, @intCast(2 + member_types.len)) << 16) | Opcode.TypeStruct);
        try self.types_globals.append(self.allocator, id);
        try self.types_globals.appendSlice(self.allocator, member_types);
        try self.struct_types.put(self.allocator, key, id);
        return id;
    }

    pub fn type_pointer(self: *Builder, storage_class: u32, pointee_type: u32) EmitError!u32 {
        const key = PtrKey{ .storage_class = storage_class, .pointee = pointee_type };
        if (self.pointer_types.get(key)) |id| return id;
        const id = self.reserve_id();
        try self.append_inst(&self.types_globals, Opcode.TypePointer, &.{ id, storage_class, pointee_type });
        try self.pointer_types.put(self.allocator, key, id);
        return id;
    }

    pub fn type_function(self: *Builder, return_type: u32, params: []const u32) EmitError!u32 {
        const params_start: u32 = @intCast(self.params_scratch.items.len);
        try self.params_scratch.appendSlice(self.allocator, params);
        const key = FnKey{ .return_type = return_type, .params_start = params_start, .params_len = @intCast(params.len) };
        if (self.find_function_type(return_type, params)) |id| return id;
        const id = self.reserve_id();
        try self.types_globals.append(self.allocator, (@as(u32, @intCast(3 + params.len)) << 16) | Opcode.TypeFunction);
        try self.types_globals.append(self.allocator, id);
        try self.types_globals.append(self.allocator, return_type);
        try self.types_globals.appendSlice(self.allocator, params);
        try self.function_types.put(self.allocator, key, id);
        return id;
    }

    fn find_function_type(self: *Builder, return_type: u32, params: []const u32) ?u32 {
        var it = self.function_types.iterator();
        while (it.next()) |entry| {
            const key = entry.key_ptr.*;
            if (key.return_type != return_type or key.params_len != params.len) continue;
            const slice = self.params_scratch.items[key.params_start .. key.params_start + key.params_len];
            if (std.mem.eql(u32, slice, params)) return entry.value_ptr.*;
        }
        return null;
    }

    fn find_struct_type(self: *Builder, member_types: []const u32) ?u32 {
        var it = self.struct_types.iterator();
        while (it.next()) |entry| {
            const key = entry.key_ptr.*;
            if (key.members_len != member_types.len) continue;
            const slice = self.members_scratch.items[key.members_start .. key.members_start + key.members_len];
            if (std.mem.eql(u32, slice, member_types)) return entry.value_ptr.*;
        }
        return null;
    }

    pub fn const_bool(self: *Builder, value: bool) EmitError!u32 {
        const ty = try self.type_bool();
        const key = ScalarConstKey{ .ty = ty, .bits = if (value) 1 else 0 };
        if (self.scalar_constants.get(key)) |id| return id;
        const id = self.reserve_id();
        try self.append_inst(&self.types_globals, if (value) Opcode.ConstantTrue else Opcode.ConstantFalse, &.{ ty, id });
        try self.scalar_constants.put(self.allocator, key, id);
        return id;
    }

    pub fn const_u32(self: *Builder, value: u32) EmitError!u32 {
        const ty = try self.type_u32();
        return try self.scalar_constant(ty, value);
    }

    pub fn const_i32_bits(self: *Builder, bits: u32) EmitError!u32 {
        const ty = try self.type_i32();
        return try self.scalar_constant(ty, bits);
    }

    pub fn const_f32_bits(self: *Builder, bits: u32) EmitError!u32 {
        const ty = try self.type_f32();
        return try self.scalar_constant(ty, bits);
    }

    fn scalar_constant(self: *Builder, ty: u32, bits: u32) EmitError!u32 {
        const key = ScalarConstKey{ .ty = ty, .bits = bits };
        if (self.scalar_constants.get(key)) |id| return id;
        const id = self.reserve_id();
        try self.append_inst(&self.types_globals, Opcode.Constant, &.{ ty, id, bits });
        try self.scalar_constants.put(self.allocator, key, id);
        return id;
    }

    pub fn variable_global(self: *Builder, ptr_type: u32, storage_class: u32) EmitError!u32 {
        const id = self.reserve_id();
        try self.append_inst(&self.types_globals, Opcode.Variable, &.{ ptr_type, id, storage_class });
        return id;
    }

    pub fn variable_global_init(self: *Builder, ptr_type: u32, storage_class: u32, initializer: u32) EmitError!u32 {
        const id = self.reserve_id();
        try self.append_inst(&self.types_globals, Opcode.Variable, &.{ ptr_type, id, storage_class, initializer });
        return id;
    }

    pub fn variable_function(self: *Builder, ptr_type: u32) EmitError!u32 {
        const id = self.reserve_id();
        try self.append_function_inst(Opcode.Variable, &.{ ptr_type, id, StorageClass.Function });
        return id;
    }

    pub fn emit_builtin_decoration(self: *Builder, target_id: u32, builtin: u32) EmitError!void {
        try self.append_inst(&self.annotations, Opcode.Decorate, &.{ target_id, Decoration.BuiltIn, builtin });
    }

    pub fn emit_block_decoration(self: *Builder, target_id: u32) EmitError!void {
        try self.append_inst(&self.annotations, Opcode.Decorate, &.{ target_id, Decoration.Block });
    }

    pub fn emit_array_stride_decoration(self: *Builder, target_id: u32, stride: u32) EmitError!void {
        try self.append_inst(&self.annotations, Opcode.Decorate, &.{ target_id, Decoration.ArrayStride, stride });
    }

    pub fn emit_descriptor_set_decoration(self: *Builder, target_id: u32, descriptor_set: u32) EmitError!void {
        try self.append_inst(&self.annotations, Opcode.Decorate, &.{ target_id, Decoration.DescriptorSet, descriptor_set });
    }

    pub fn emit_binding_decoration(self: *Builder, target_id: u32, binding: u32) EmitError!void {
        try self.append_inst(&self.annotations, Opcode.Decorate, &.{ target_id, Decoration.Binding, binding });
    }

    pub fn emit_non_writable_decoration(self: *Builder, target_id: u32) EmitError!void {
        try self.append_inst(&self.annotations, Opcode.Decorate, &.{ target_id, Decoration.NonWritable });
    }

    pub fn emit_non_readable_decoration(self: *Builder, target_id: u32) EmitError!void {
        try self.append_inst(&self.annotations, Opcode.Decorate, &.{ target_id, Decoration.NonReadable });
    }

    pub fn emit_member_offset_decoration(self: *Builder, target_id: u32, member_index: u32, offset: u32) EmitError!void {
        try self.append_inst(&self.annotations, Opcode.MemberDecorate, &.{ target_id, member_index, Decoration.Offset, offset });
    }

    pub fn begin_function(self: *Builder, result_type: u32, fn_id: u32, function_type: u32) EmitError!void {
        try self.append_function_inst(Opcode.Function, &.{ result_type, fn_id, FunctionControl.None, function_type });
    }

    pub fn function_parameter(self: *Builder, param_type: u32) EmitError!u32 {
        const id = self.reserve_id();
        try self.append_function_inst(Opcode.FunctionParameter, &.{ param_type, id });
        return id;
    }

    pub fn label(self: *Builder) EmitError!u32 {
        const id = self.reserve_id();
        try self.append_function_inst(Opcode.Label, &.{id});
        return id;
    }

    pub fn finish_function(self: *Builder) EmitError!void {
        try self.append_function_inst(Opcode.FunctionEnd, &.{});
    }

    pub fn write_binary(self: *Builder, out: []u8) EmitError!usize {
        const total_words = 5 +
            self.capabilities.items.len +
            self.ext_inst_imports.items.len +
            self.memory_model.items.len +
            self.entry_points.items.len +
            self.execution_modes.items.len +
            self.debug.items.len +
            self.annotations.items.len +
            self.types_globals.items.len +
            self.functions.items.len;
        const total_bytes = total_words * WORD_BYTES;
        if (total_bytes > out.len) return error.OutputTooLarge;

        var cursor: usize = 0;
        const header = [_]u32{ MAGIC, VERSION_1_3, GENERATOR_ID, self.next_id, SCHEMA };
        cursor += write_words(out[cursor..], &header);
        cursor += write_words(out[cursor..], self.capabilities.items);
        cursor += write_words(out[cursor..], self.ext_inst_imports.items);
        cursor += write_words(out[cursor..], self.memory_model.items);
        cursor += write_words(out[cursor..], self.entry_points.items);
        cursor += write_words(out[cursor..], self.execution_modes.items);
        cursor += write_words(out[cursor..], self.debug.items);
        cursor += write_words(out[cursor..], self.annotations.items);
        cursor += write_words(out[cursor..], self.types_globals.items);
        cursor += write_words(out[cursor..], self.functions.items);
        return cursor;
    }
};

fn string_word_len(text: []const u8) usize {
    return (text.len + 1 + 3) / 4;
}

fn append_string_words(list: *std.ArrayListUnmanaged(u32), allocator: std.mem.Allocator, text: []const u8) !void {
    var i: usize = 0;
    while (i < text.len) : (i += 4) {
        var word: u32 = 0;
        var j: usize = 0;
        while (j < 4 and i + j < text.len) : (j += 1) {
            word |= @as(u32, text[i + j]) << @intCast(j * 8);
        }
        try list.append(allocator, word);
    }
    if ((text.len % 4) == 0) {
        try list.append(allocator, 0);
    } else {
        const last_index = list.items.len - 1;
        list.items[last_index] &= ~(@as(u32, 0xFF) << @intCast((text.len % 4) * 8));
    }
}

fn write_words(out: []u8, words: []const u32) usize {
    for (words, 0..) |word, i| {
        std.mem.writeInt(u32, @as(*[4]u8, @ptrCast(out[i * 4 .. i * 4 + 4].ptr)), word, .little);
    }
    return words.len * WORD_BYTES;
}
