const mod_test = @import("src/doe_wgsl/mod_test.zig");
const shader_emit_test = @import("src/doe_wgsl/shader_emit_test.zig");
const shader_sema_test = @import("src/doe_wgsl/shader_sema_test.zig");
const shader_hlsl_spirv_test = @import("src/doe_wgsl/shader_hlsl_spirv_test.zig");
const shader_coverage_test = @import("src/doe_wgsl/shader_coverage_test.zig");
const shader_coverage_test_2 = @import("src/doe_wgsl/shader_coverage_test_2.zig");

comptime {
    _ = mod_test;
    _ = shader_emit_test;
    _ = shader_sema_test;
    _ = shader_hlsl_spirv_test;
    _ = shader_coverage_test;
    _ = shader_coverage_test_2;
}
