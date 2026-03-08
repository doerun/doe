const ir = @import("ir.zig");

pub const MAX_OUTPUT: usize = 256 * 1024;

pub const Error = error{
    OutputTooLarge,
    InvalidIr,
    UnsupportedConstruct,
    OutOfMemory,
};

pub const ShaderModel = struct {
    major: u8 = 6,
    minor: u8 = 0,
};

pub const Stage = enum {
    compute,
};

pub const EntryPoint = struct {
    stage: Stage = .compute,
    name: []const u8 = "main",
    workgroup_size: [3]u32 = .{ 1, 1, 1 },
};

pub const Module = struct {
    shader_model: ShaderModel = .{},
    entry_point: EntryPoint = .{},
};

pub fn lower(module: *const ir.Module) Error!Module {
    _ = module;
    return .{};
}

pub fn emit(module: *const ir.Module, out: []u8) Error!usize {
    _ = out;
    _ = try lower(module);
    return error.UnsupportedConstruct;
}
