const std = @import("std");
const APP_BUNDLE_NAME = "Doe Runtime.app";
const APP_ICON_BASENAME = "DoeRuntime";
const APP_ICON_SOURCE_SVG = "../nursery/fawn-browser/artifacts/fawn-icon-main.svg";

fn fileExists(path: []const u8) bool {
    std.fs.cwd().access(path, .{}) catch return false;
    return true;
}

fn sha256HexAlloc(allocator: std.mem.Allocator, input: []const u8) []u8 {
    var digest: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(input, &digest, .{});
    const hex = allocator.alloc(u8, digest.len * 2) catch
        @panic("failed to allocate sha256 hex");
    const alphabet = "0123456789abcdef";
    for (digest, 0..) |byte, idx| {
        hex[idx * 2] = alphabet[byte >> 4];
        hex[idx * 2 + 1] = alphabet[byte & 0x0f];
    }
    return hex;
}

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const lean_verified = b.option(bool, "lean-verified", "Embed Lean proof artifact and validate at comptime") orelse false;
    const build_options = b.addOptions();
    build_options.addOption(bool, "lean_verified", lean_verified);

    var proof_artifact_sha256: ?[]const u8 = null;
    if (lean_verified) {
        const proof_artifact = std.fs.cwd().openFile("../lean/artifacts/proven-conditions.json", .{}) catch
            @panic("lean-verified=true but lean/artifacts/proven-conditions.json not found. Run lean/extract.sh first.");
        defer proof_artifact.close();
        const proof_json = proof_artifact.readToEndAlloc(b.allocator, 64 * 1024) catch
            @panic("failed to read lean proof artifact");
        build_options.addOption([]const u8, "lean_proof_json", proof_json);
        proof_artifact_sha256 = sha256HexAlloc(b.allocator, proof_json);
    }
    const build_options_module = build_options.createModule();

    const dropin_lib = b.addLibrary(.{
        .name = "webgpu_doe",
        .linkage = .dynamic,
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/wgpu_dropin_lib.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = build_options_module },
            },
        }),
    });
    dropin_lib.linkLibC();
    if (target.result.os.tag == .windows) {
        dropin_lib.linkSystemLibrary("d3d12");
        dropin_lib.linkSystemLibrary("dxgi");
        dropin_lib.linkSystemLibrary("dxguid");
        dropin_lib.addCSourceFile(.{
            .file = b.path("src/backend/d3d12/d3d12_bridge.c"),
            .flags = &.{},
        });
    } else {
        dropin_lib.linkSystemLibrary("dl");
        if (target.result.os.tag == .linux) {
            dropin_lib.linkSystemLibrary("vulkan");
        }
        if (target.result.os.tag == .macos) {
            dropin_lib.linkFramework("Metal");
            dropin_lib.linkFramework("Foundation");
            dropin_lib.addCSourceFile(.{
                .file = b.path("src/backend/metal/metal_bridge.m"),
                .flags = &.{"-fobjc-arc"},
            });
        }
    }
    const install_dropin = b.addInstallArtifact(dropin_lib, .{});

    const dropin_step = b.step("dropin", "Build the drop-in WebGPU shared library");
    dropin_step.dependOn(&install_dropin.step);
    const dropin_build_metadata_files = b.addWriteFiles();
    const proof_artifact_sha256_json = if (proof_artifact_sha256) |value|
        std.fmt.allocPrint(b.allocator, "\"{s}\"", .{value}) catch @panic("failed to format proof artifact sha256")
    else
        "null";
    const dropin_build_metadata_json = std.fmt.allocPrint(
        b.allocator,
        "{{\n  \"schemaVersion\": 1,\n  \"artifact\": \"libwebgpu_doe\",\n  \"leanVerifiedBuild\": {s},\n  \"proofArtifactSha256\": {s}\n}}\n",
        .{
            if (lean_verified) "true" else "false",
            proof_artifact_sha256_json,
        },
    ) catch @panic("failed to format drop-in build metadata");
    const dropin_build_metadata = dropin_build_metadata_files.add(
        "doe-build-metadata.json",
        dropin_build_metadata_json,
    );
    const install_dropin_build_metadata = b.addInstallFileWithDir(
        dropin_build_metadata,
        .prefix,
        "share/doe-build-metadata.json",
    );
    dropin_step.dependOn(&install_dropin_build_metadata.step);
    const dawn_sidecar = switch (target.result.os.tag) {
        .macos => "../bench/vendor/dawn/out/Release/libwebgpu_dawn.dylib",
        .linux => "../bench/vendor/dawn/out/Release/libwebgpu_dawn.so",
        .windows => "../bench/vendor/dawn/out/Release/webgpu_dawn.dll",
        else => "",
    };
    const dawn_sidecar_install_name = switch (target.result.os.tag) {
        .macos => "libwebgpu_dawn.dylib",
        .linux => "libwebgpu_dawn.so",
        .windows => "webgpu_dawn.dll",
        else => "",
    };
    const webgpu_sidecar = switch (target.result.os.tag) {
        .macos => "../bench/vendor/dawn/out/Release/libwebgpu.dylib",
        .linux => "../bench/vendor/dawn/out/Release/libwebgpu.so",
        .windows => "../bench/vendor/dawn/out/Release/webgpu.dll",
        else => "",
    };
    const webgpu_sidecar_install_name = switch (target.result.os.tag) {
        .macos => "libwebgpu.dylib",
        .linux => "libwebgpu.so",
        .windows => "webgpu.dll",
        else => "",
    };
    const wgpu_native_sidecar = switch (target.result.os.tag) {
        .linux => "../bench/vendor/dawn/out/Release/libwgpu_native.so",
        else => "",
    };
    if (dawn_sidecar.len != 0 and fileExists(dawn_sidecar)) {
        const install_webgpu_dawn = b.addInstallFileWithDir(
            b.path(dawn_sidecar),
            .lib,
            dawn_sidecar_install_name,
        );
        dropin_step.dependOn(&install_webgpu_dawn.step);
    }
    if (webgpu_sidecar.len != 0 and fileExists(webgpu_sidecar)) {
        const install_webgpu = b.addInstallFileWithDir(
            b.path(webgpu_sidecar),
            .lib,
            webgpu_sidecar_install_name,
        );
        dropin_step.dependOn(&install_webgpu.step);
    }
    if (wgpu_native_sidecar.len != 0 and fileExists(wgpu_native_sidecar)) {
        const install_wgpu_native = b.addInstallFileWithDir(
            b.path(wgpu_native_sidecar),
            .lib,
            "libwgpu_native.so",
        );
        dropin_step.dependOn(&install_wgpu_native.step);
    }
    b.getInstallStep().dependOn(dropin_step);

    const exe = b.addExecutable(.{
        .name = "doe-zig-runtime",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/main.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = build_options_module },
            },
        }),
    });
    exe.linkLibC();
    if (target.result.os.tag == .windows) {
        exe.linkSystemLibrary("d3d12");
        exe.linkSystemLibrary("dxgi");
        exe.linkSystemLibrary("dxguid");
        exe.addCSourceFile(.{
            .file = b.path("src/backend/d3d12/d3d12_bridge.c"),
            .flags = &.{},
        });
    } else {
        exe.linkSystemLibrary("dl");
        if (target.result.os.tag == .linux) {
            exe.linkSystemLibrary("vulkan");
        }
        if (target.result.os.tag == .macos) {
            exe.linkFramework("Metal");
            exe.linkFramework("Foundation");
            exe.addCSourceFile(.{
                .file = b.path("src/backend/metal/metal_bridge.m"),
                .flags = &.{"-fobjc-arc"},
            });
        }
    }

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

        if (!fileExists(APP_ICON_SOURCE_SVG)) {
            const missing_icon = b.addFail("Missing required macOS icon source: " ++ APP_ICON_SOURCE_SVG);
            app_step.dependOn(&missing_icon.step);
        } else {
            const make_icon = b.addSystemCommand(&.{ "python3", "tools/generate_macos_icon.py", "--out", "--source-svg", APP_ICON_SOURCE_SVG });
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
        }
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
            .root_source_file = b.path("test_suite.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    test_exec.linkLibC();
    if (target.result.os.tag == .windows) {
        test_exec.linkSystemLibrary("d3d12");
        test_exec.linkSystemLibrary("dxgi");
        test_exec.linkSystemLibrary("dxguid");
        test_exec.addCSourceFile(.{
            .file = b.path("src/backend/d3d12/d3d12_bridge.c"),
            .flags = &.{},
        });
    } else {
        test_exec.linkSystemLibrary("dl");
        if (target.result.os.tag == .linux) {
            test_exec.linkSystemLibrary("vulkan");
        }
        if (target.result.os.tag == .macos) {
            test_exec.linkFramework("Metal");
            test_exec.linkFramework("Foundation");
            test_exec.addCSourceFile(.{
                .file = b.path("src/backend/metal/metal_bridge.m"),
                .flags = &.{"-fobjc-arc"},
            });
        }
    }
    const run_tests = b.addRunArtifact(test_exec);
    test_step.dependOn(&run_tests.step);

    const d3d12_test_step = b.step("test-d3d12", "Run D3D12-focused Zig tests (no Metal test suite)");
    const d3d12_test_exec = b.addTest(.{
        .root_module = b.createModule(.{
            .root_source_file = b.path("test_suite_d3d12.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    d3d12_test_exec.linkLibC();
    if (target.result.os.tag == .windows) {
        d3d12_test_exec.linkSystemLibrary("d3d12");
        d3d12_test_exec.linkSystemLibrary("dxgi");
        d3d12_test_exec.linkSystemLibrary("dxguid");
        d3d12_test_exec.addCSourceFile(.{
            .file = b.path("src/backend/d3d12/d3d12_bridge.c"),
            .flags = &.{},
        });
    } else {
        d3d12_test_exec.linkSystemLibrary("dl");
        if (target.result.os.tag == .linux) {
            d3d12_test_exec.linkSystemLibrary("vulkan");
        }
    }
    const run_d3d12_tests = b.addRunArtifact(d3d12_test_exec);
    d3d12_test_step.dependOn(&run_d3d12_tests.step);
}
