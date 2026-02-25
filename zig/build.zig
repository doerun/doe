const std = @import("std");
const APP_BUNDLE_NAME = "Doe Runtime.app";
const APP_ICON_BASENAME = "DoeRuntime";

fn fileExists(path: []const u8) bool {
    std.fs.cwd().access(path, .{}) catch return false;
    return true;
}

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const dropin_lib = b.addLibrary(.{
        .name = "doe_webgpu",
        .linkage = .dynamic,
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/wgpu_dropin_lib.zig"),
            .target = target,
            .optimize = optimize,
        }),
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
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/main.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    exe.linkLibC();
    exe.linkSystemLibrary("dl");

    b.installArtifact(exe);

    const app_step = b.step("app", "Build macOS Doe Runtime .app bundle with generated icon");
    if (target.result.os.tag == .macos) {
        const app_info_plist =
            \\<?xml version="1.0" encoding="UTF-8"?>
            \\<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
            \\<plist version="1.0">
            \\  <dict>
            \\    <key>CFBundleDevelopmentRegion</key>
            \\    <string>en</string>
            \\    <key>CFBundleExecutable</key>
            \\    <string>doe-zig-runtime</string>
            \\    <key>CFBundleIconFile</key>
            \\    <string>DoeRuntime</string>
            \\    <key>CFBundleIdentifier</key>
            \\    <string>dev.fawn.doe-runtime</string>
            \\    <key>CFBundleInfoDictionaryVersion</key>
            \\    <string>6.0</string>
            \\    <key>CFBundleName</key>
            \\    <string>Doe Runtime</string>
            \\    <key>CFBundlePackageType</key>
            \\    <string>APPL</string>
            \\    <key>CFBundleShortVersionString</key>
            \\    <string>0.1.0</string>
            \\    <key>CFBundleVersion</key>
            \\    <string>1</string>
            \\    <key>LSMinimumSystemVersion</key>
            \\    <string>13.0</string>
            \\  </dict>
            \\</plist>
        ;
        const app_files = b.addWriteFiles();
        const info_plist = app_files.add("Info.plist", app_info_plist);

        const make_icon = b.addSystemCommand(&.{ "python3", "tools/generate_macos_icon.py", "--out" });
        make_icon.setCwd(b.path("."));
        const icon_icns = make_icon.addOutputFileArg(APP_ICON_BASENAME ++ ".icns");

        const app_prefix = "app/" ++ APP_BUNDLE_NAME ++ "/Contents";
        const install_app_exe = b.addInstallFileWithDir(
            exe.getEmittedBin(),
            .prefix,
            app_prefix ++ "/MacOS/doe-zig-runtime",
        );
        const install_app_icon = b.addInstallFileWithDir(
            icon_icns,
            .prefix,
            app_prefix ++ "/Resources/" ++ APP_ICON_BASENAME ++ ".icns",
        );
        const install_app_plist = b.addInstallFileWithDir(
            info_plist,
            .prefix,
            app_prefix ++ "/Info.plist",
        );

        app_step.dependOn(&install_app_exe.step);
        app_step.dependOn(&install_app_icon.step);
        app_step.dependOn(&install_app_plist.step);
        b.getInstallStep().dependOn(&install_app_exe.step);
        b.getInstallStep().dependOn(&install_app_icon.step);
        b.getInstallStep().dependOn(&install_app_plist.step);
    } else {
        const unsupported = b.addFail("zig build app is only supported when target os is macOS.");
        app_step.dependOn(&unsupported.step);
    }

    const run_cmd = b.addRunArtifact(exe);
    if (b.args) |args| {
        run_cmd.addArgs(args);
    }
    const run_step = b.step("run", "Run the sample runtime dispatcher");
    run_step.dependOn(&run_cmd.step);

    const test_step = b.step("test", "Run Zig unit tests");
    const test_exec = b.addTest(.{
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/model.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    test_step.dependOn(&test_exec.step);
}
