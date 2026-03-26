// Thin entry point for the compilation benchmark. Lives at src/ level so that
// doe_wgsl/ files can reach ../lean_proof.zig within the module root.
pub const main = @import("doe_wgsl/bench_compilation.zig").main;
