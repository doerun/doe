const std = @import("std");

fn fileExists(path: []const u8) bool {
    std.fs.cwd().access(path, .{}) catch return false;
    return true;
}

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const dropin_lib = b.addSharedLibrary(.{
        .name = "doe_webgpu",
        .root_source_file = b.path("src/wgpu_dropin_lib.zig"),
        .target = target,
        .optimize = optimize,
    });
    dropin_lib.linkLibC();
    dropin_lib.linkSystemLibrary("dl");
    const install_dropin = b.addInstallArtifact(dropin_lib, .{});

    const dropin_step = b.step("dropin", "Build the drop-in WebGPU shared library");
    dropin_step.dependOn(&install_dropin.step);
    const dawn_sidecar = "../bench/vendor/dawn/out/Release/libwebgpu_dawn.so";
    const webgpu_sidecar = "../bench/vendor/dawn/out/Release/libwebgpu.so";
    const wgpu_native_sidecar = "../bench/vendor/dawn/out/Release/libwgpu_native.so";
    if (fileExists(dawn_sidecar)) {
        const install_webgpu_dawn = b.addInstallFileWithDir(
            b.path(dawn_sidecar),
            .lib,
            "libwebgpu_dawn.so",
        );
        const install_webgpu = b.addInstallFileWithDir(
            b.path(dawn_sidecar),
            .lib,
            "libwebgpu.so",
        );
        const install_wgpu_native = b.addInstallFileWithDir(
            b.path(dawn_sidecar),
            .lib,
            "libwgpu_native.so",
        );
        dropin_step.dependOn(&install_webgpu_dawn.step);
        dropin_step.dependOn(&install_webgpu.step);
        dropin_step.dependOn(&install_wgpu_native.step);
    } else {
        if (fileExists(webgpu_sidecar)) {
            const install_webgpu = b.addInstallFileWithDir(
                b.path(webgpu_sidecar),
                .lib,
                "libwebgpu.so",
            );
            dropin_step.dependOn(&install_webgpu.step);
        }
        if (fileExists(wgpu_native_sidecar)) {
            const install_wgpu_native = b.addInstallFileWithDir(
                b.path(wgpu_native_sidecar),
                .lib,
                "libwgpu_native.so",
            );
            dropin_step.dependOn(&install_wgpu_native.step);
        }
    }

    const exe = b.addExecutable(.{
        .name = "doe-zig-runtime",
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
