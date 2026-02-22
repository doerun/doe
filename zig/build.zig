const std = @import("std");

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const exe = b.addExecutable(.{
        .name = "fawn-zig-runtime",
        .root_source_file = b.path("src/main.zig"),
        .target = target,
        .optimize = optimize,
    });
    exe.linkLibC();
    exe.linkSystemLibrary("dl");

    b.installArtifact(exe);

    const run_cmd = b.addRunArtifact(exe);
    if (b.args) |args| {
        run_cmd.addArgs(args);
    }
    const run_step = b.step("run", "Run the sample runtime dispatcher");
    run_step.dependOn(&run_cmd.step);

    const test_step = b.step("test", "Run Zig unit tests");
    const test_exec = b.addTest(.{
        .root_source_file = b.path("src/model.zig"),
        .target = target,
        .optimize = optimize,
    });
    test_step.dependOn(&test_exec.step);
}
