const std = @import("std");
const APP_BUNDLE_NAME = "Doe Runtime.app";
const APP_ICON_BASENAME = "DoeRuntime";
const APP_ICON_SOURCE_SVG = "../../browser/chromium/assets/logo/source/fawn-icon-main.svg";
const APP_ICON_PRECOMPILED_ICNS = "../../browser/chromium/assets/logo/compiled/macos/fawn-icon-main.icns";

fn fileExists(path: []const u8) bool {
    std.fs.cwd().access(path, .{}) catch return false;
    return true;
}

fn firstExistingPath(candidates: []const []const u8) []const u8 {
    for (candidates) |candidate| {
        if (fileExists(candidate)) return candidate;
    }
    @panic("required include path not found");
}

fn addExistingIncludePaths(
    artifact: *std.Build.Step.Compile,
    b: *std.Build,
    candidates: []const []const u8,
) void {
    for (candidates) |candidate| {
        if (fileExists(candidate)) {
            if (std.fs.path.isAbsolute(candidate)) {
                artifact.addIncludePath(.{ .cwd_relative = candidate });
            } else {
                artifact.addIncludePath(b.path(candidate));
            }
        }
    }
}

fn addBackendBridgeIncludePaths(artifact: *std.Build.Step.Compile, b: *std.Build) void {
    artifact.addIncludePath(b.path("src/backend/d3d12"));
    artifact.addIncludePath(b.path("src/backend/metal"));
}

fn sha256HexAlloc(allocator: std.mem.Allocator, input: []const u8) []u8 {
    var digest: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(input, &digest, .{});
    return hexEncodeAlloc(allocator, &digest);
}

fn hexEncodeAlloc(allocator: std.mem.Allocator, bytes: []const u8) []u8 {
    const hex = allocator.alloc(u8, bytes.len * 2) catch
        @panic("failed to allocate sha256 hex");
    const alphabet = "0123456789abcdef";
    for (bytes, 0..) |byte, idx| {
        hex[idx * 2] = alphabet[byte >> 4];
        hex[idx * 2 + 1] = alphabet[byte & 0x0f];
    }
    return hex;
}

const ProofProvenance = struct {
    lean_toolchain_ref: []const u8,
    extract_program_sha256: []const u8,
    lean_source_tree_sha256: []const u8,
    generated_comparability_contract_sha256: []const u8,
    proof_pattern_spec_sha256: []const u8,
};

fn readFileAlloc(allocator: std.mem.Allocator, path: []const u8, max_bytes: usize) []u8 {
    const file = std.fs.cwd().openFile(path, .{}) catch
        @panic("required file not found");
    defer file.close();
    return file.readToEndAlloc(allocator, max_bytes) catch
        @panic("failed to read required file");
}

fn hashFileAlloc(allocator: std.mem.Allocator, path: []const u8, max_bytes: usize) []u8 {
    const contents = readFileAlloc(allocator, path, max_bytes);
    defer allocator.free(contents);
    return sha256HexAlloc(allocator, contents);
}

fn lessThanString(_: void, lhs: []const u8, rhs: []const u8) bool {
    return std.mem.lessThan(u8, lhs, rhs);
}

fn hashLeanSourceTreeAlloc(allocator: std.mem.Allocator, root_path: []const u8) []u8 {
    var dir = std.fs.cwd().openDir(root_path, .{ .iterate = true }) catch
        @panic("failed to open Lean source tree");
    defer dir.close();

    var walker = dir.walk(allocator) catch
        @panic("failed to walk Lean source tree");
    defer walker.deinit();

    var rel_paths = std.ArrayList([]u8).initCapacity(allocator, 0) catch
        @panic("failed to allocate Lean path list");
    defer {
        for (rel_paths.items) |path| allocator.free(path);
        rel_paths.deinit(allocator);
    }

    while (walker.next() catch @panic("failed to iterate Lean source tree")) |entry| {
        if (entry.kind != .file) continue;
        if (!std.mem.endsWith(u8, entry.path, ".lean")) continue;
        rel_paths.append(allocator, allocator.dupe(u8, entry.path) catch @panic("failed to dupe Lean path")) catch
            @panic("failed to collect Lean paths");
    }

    std.sort.heap([]u8, rel_paths.items, {}, lessThanString);

    var hasher = std.crypto.hash.sha2.Sha256.init(.{});
    for (rel_paths.items) |rel_path| {
        const repo_rel_path = std.fmt.allocPrint(allocator, "pipeline/lean/Doe/{s}", .{rel_path}) catch
            @panic("failed to format Lean source path");
        defer allocator.free(repo_rel_path);
        hasher.update(repo_rel_path);
        hasher.update("\n");

        const full_path = std.fmt.allocPrint(allocator, "{s}/{s}", .{ root_path, rel_path }) catch
            @panic("failed to format Lean source full path");
        defer allocator.free(full_path);
        const contents = readFileAlloc(allocator, full_path, 512 * 1024);
        defer allocator.free(contents);
        hasher.update(contents);
        hasher.update("\n");
    }

    var digest: [32]u8 = undefined;
    hasher.final(&digest);
    return hexEncodeAlloc(allocator, &digest);
}

fn loadLeanToolchainRefAlloc(allocator: std.mem.Allocator) []u8 {
    const ToolchainConfig = struct {
        toolchains: struct {
            lean: struct {
                version: []const u8,
            },
        },
    };

    const json = readFileAlloc(allocator, "../../config/toolchains.json", 64 * 1024);
    defer allocator.free(json);
    const parsed = std.json.parseFromSlice(ToolchainConfig, allocator, json, .{
        .ignore_unknown_fields = true,
    }) catch @panic("failed to parse config/toolchains.json");
    defer parsed.deinit();

    const version = parsed.value.toolchains.lean.version;
    return if (std.mem.startsWith(u8, version, "v"))
        std.fmt.allocPrint(allocator, "leanprover/lean4:{s}", .{version}) catch @panic("failed to format Lean toolchain ref")
    else
        std.fmt.allocPrint(allocator, "leanprover/lean4:v{s}", .{version}) catch @panic("failed to format Lean toolchain ref");
}

fn loadProofProvenance(allocator: std.mem.Allocator) ProofProvenance {
    return .{
        .lean_toolchain_ref = loadLeanToolchainRefAlloc(allocator),
        .extract_program_sha256 = hashFileAlloc(allocator, "../../pipeline/lean/Doe/Extract.lean", 64 * 1024),
        .lean_source_tree_sha256 = hashLeanSourceTreeAlloc(allocator, "../../pipeline/lean/Doe"),
        .generated_comparability_contract_sha256 = hashFileAlloc(allocator, "../../pipeline/lean/Doe/Generated/ComparabilityContract.lean", 256 * 1024),
        .proof_pattern_spec_sha256 = hashFileAlloc(allocator, "../../config/lean-proof-patterns.json", 64 * 1024),
    };
}

fn addProofProvenanceOptions(options: *std.Build.Step.Options, provenance: ProofProvenance) void {
    options.addOption([]const u8, "lean_toolchain_ref", provenance.lean_toolchain_ref);
    options.addOption([]const u8, "lean_extract_program_sha256", provenance.extract_program_sha256);
    options.addOption([]const u8, "lean_source_tree_sha256", provenance.lean_source_tree_sha256);
    options.addOption([]const u8, "generated_comparability_contract_sha256", provenance.generated_comparability_contract_sha256);
    options.addOption([]const u8, "proof_pattern_spec_sha256", provenance.proof_pattern_spec_sha256);
}

fn configure_non_windows_graphics(artifact: *std.Build.Step.Compile, b: *std.Build, target: std.Build.ResolvedTarget) void {
    artifact.linkSystemLibrary("dl");
    addBackendBridgeIncludePaths(artifact, b);
    artifact.addCSourceFile(.{
        .file = b.path("src/backend/d3d12/d3d12_bridge_stubs.c"),
        .flags = &.{},
    });
    if (target.result.os.tag == .linux) {
        artifact.linkSystemLibrary("vulkan");
    }
    if (target.result.os.tag == .macos) {
        artifact.linkFramework("Metal");
        artifact.linkFramework("Foundation");
        artifact.linkFramework("QuartzCore");
        artifact.linkFramework("AppKit");
        artifact.linkFramework("CoreVideo");
        artifact.linkFramework("IOSurface");
        artifact.addCSourceFile(.{
            .file = b.path("src/backend/metal/metal_bridge.m"),
            .flags = &.{"-fobjc-arc"},
        });
        artifact.addCSourceFile(.{
            .file = b.path("src/backend/metal/metal_render_state_bridge.m"),
            .flags = &.{"-fobjc-arc"},
        });
        artifact.addCSourceFile(.{
            .file = b.path("src/backend/metal/metal_surface_bridge.m"),
            .flags = &.{"-fobjc-arc"},
        });
        artifact.addCSourceFile(.{
            .file = b.path("src/backend/metal/metal_external_texture_bridge.m"),
            .flags = &.{"-fobjc-arc"},
        });
    } else {
        artifact.addCSourceFile(.{
            .file = b.path("src/backend/metal/metal_bridge_stubs.c"),
            .flags = &.{},
        });
    }
}

pub fn build(b: *std.Build) void {
    const target = b.standardTargetOptions(.{});
    const optimize = b.standardOptimizeOption(.{});

    const BuildTier = enum { compute, headless, full };
    const build_tier = b.option(BuildTier, "tier", "Build tier: compute (dispatch+buffer only), headless (full WebGPU sans presentation), full (Dawn drop-in)") orelse .headless;
    const proof_provenance = loadProofProvenance(b.allocator);

    const lean_verified = b.option(bool, "lean-verified", "Embed Lean proof artifact and validate at comptime") orelse false;
    const build_options = b.addOptions();
    build_options.addOption(bool, "lean_verified", lean_verified);
    build_options.addOption(BuildTier, "build_tier", build_tier);
    addProofProvenanceOptions(build_options, proof_provenance);
    {
        const f = std.fs.cwd().openFile("../../config/comparability-obligations.json", .{}) catch
            @panic("config/comparability-obligations.json not found");
        defer f.close();
        const json = f.readToEndAlloc(b.allocator, 128 * 1024) catch
            @panic("failed to read comparability-obligations.json");
        build_options.addOption([]const u8, "comparability_obligations_json", json);
        build_options.addOption([]const u8, "comparability_obligations_sha256", sha256HexAlloc(b.allocator, json));
    }

    var proof_json: ?[]const u8 = null;
    var proof_artifact_sha256: ?[]const u8 = null;
    if (lean_verified) {
        const proof_artifact = std.fs.cwd().openFile("../../pipeline/lean/artifacts/proven-conditions.json", .{}) catch
            @panic("lean-verified=true but pipeline/lean/artifacts/proven-conditions.json not found. Run pipeline/lean/extract.sh first.");
        defer proof_artifact.close();
        proof_json = proof_artifact.readToEndAlloc(b.allocator, 64 * 1024) catch
            @panic("failed to read lean proof artifact");
        build_options.addOption([]const u8, "lean_proof_json", proof_json.?);
        proof_artifact_sha256 = sha256HexAlloc(b.allocator, proof_json.?);
    }

    {
        const f = std.fs.cwd().openFile("../../config/dropin-abi-behavior.json", .{}) catch
            @panic("config/dropin-abi-behavior.json not found");
        defer f.close();
        const json = f.readToEndAlloc(b.allocator, 64 * 1024) catch
            @panic("failed to read dropin-abi-behavior.json");
        build_options.addOption([]const u8, "dropin_behavior_config_json", json);
    }
    {
        const f = std.fs.cwd().openFile("../../config/dropin-symbol-ownership.json", .{}) catch
            @panic("config/dropin-symbol-ownership.json not found");
        defer f.close();
        const json = f.readToEndAlloc(b.allocator, 64 * 1024) catch
            @panic("failed to read dropin-symbol-ownership.json");
        build_options.addOption([]const u8, "dropin_symbol_ownership_config_json", json);
    }
    {
        const f = std.fs.cwd().openFile("../../config/quirk-toggle-registry.json", .{}) catch
            @panic("config/quirk-toggle-registry.json not found");
        defer f.close();
        const json = f.readToEndAlloc(b.allocator, 64 * 1024) catch
            @panic("failed to read quirk-toggle-registry.json");
        build_options.addOption([]const u8, "quirk_toggle_registry_json", json);
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
        configure_non_windows_graphics(dropin_lib, b, target);
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
        .macos => "../../bench/vendor/dawn/out/Release/libwebgpu_dawn.dylib",
        .linux => "../../bench/vendor/dawn/out/Release/libwebgpu_dawn.so",
        .windows => "../../bench/vendor/dawn/out/Release/webgpu_dawn.dll",
        else => "",
    };
    const dawn_sidecar_install_name = switch (target.result.os.tag) {
        .macos => "libwebgpu_dawn.dylib",
        .linux => "libwebgpu_dawn.so",
        .windows => "webgpu_dawn.dll",
        else => "",
    };
    const webgpu_sidecar = switch (target.result.os.tag) {
        .macos => "../../bench/vendor/dawn/out/Release/libwebgpu.dylib",
        .linux => "../../bench/vendor/dawn/out/Release/libwebgpu.so",
        .windows => "../../bench/vendor/dawn/out/Release/webgpu.dll",
        else => "",
    };
    const webgpu_sidecar_install_name = switch (target.result.os.tag) {
        .macos => "libwebgpu.dylib",
        .linux => "libwebgpu.so",
        .windows => "webgpu.dll",
        else => "",
    };
    const wgpu_native_sidecar = switch (target.result.os.tag) {
        .linux => "../../bench/vendor/dawn/out/Release/libwgpu_native.so",
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
        configure_non_windows_graphics(exe, b, target);
    }

    const install_exe = b.addInstallArtifact(exe, .{});
    const runtime_step = b.step("doe-runtime", "Build the Doe runtime binary");
    runtime_step.dependOn(&install_exe.step);
    b.getInstallStep().dependOn(&install_exe.step);

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

        if (!fileExists(APP_ICON_PRECOMPILED_ICNS) and !fileExists(APP_ICON_SOURCE_SVG)) {
            const missing_icon = b.addFail(
                "Missing required macOS icon asset: " ++ APP_ICON_PRECOMPILED_ICNS ++
                    " (or source SVG " ++ APP_ICON_SOURCE_SVG ++ ")",
            );
            app_step.dependOn(&missing_icon.step);
        } else {
            const icon_icns = if (fileExists(APP_ICON_PRECOMPILED_ICNS))
                b.path(APP_ICON_PRECOMPILED_ICNS)
            else blk: {
                const make_icon = b.addSystemCommand(&.{ "python3", "tools/generate_macos_icon.py", "--out" });
                const generated_icns = make_icon.addOutputFileArg(APP_ICON_BASENAME ++ ".icns");
                make_icon.addArgs(&.{ "--source-svg", APP_ICON_SOURCE_SVG });
                make_icon.setCwd(b.path("."));
                break :blk generated_icns;
            };

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

    const module_runner = b.addExecutable(.{
        .name = "module-core-runner",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/cli/module_runner_main.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = build_options_module },
            },
        }),
    });
    module_runner.linkLibC();
    if (target.result.os.tag == .windows) {
        module_runner.linkSystemLibrary("d3d12");
        module_runner.linkSystemLibrary("dxgi");
        module_runner.linkSystemLibrary("dxguid");
        module_runner.addCSourceFile(.{
            .file = b.path("src/backend/d3d12/d3d12_bridge.c"),
            .flags = &.{},
        });
    } else {
        configure_non_windows_graphics(module_runner, b, target);
    }
    const install_module_runner = b.addInstallArtifact(module_runner, .{});
    const module_runner_step = b.step("module-core-runner", "Build the module core runner");
    module_runner_step.dependOn(&install_module_runner.step);
    b.getInstallStep().dependOn(module_runner_step);

    const emit_msl_exe = b.addExecutable(.{
        .name = "doe-emit-msl",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/cli/main_emit_msl.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = build_options_module },
            },
        }),
    });
    emit_msl_exe.linkLibC();
    const install_emit_msl = b.addInstallArtifact(emit_msl_exe, .{});
    const emit_msl_step = b.step("emit-msl", "Build the WGSL-to-MSL emitter tool");
    emit_msl_step.dependOn(&install_emit_msl.step);
    b.getInstallStep().dependOn(emit_msl_step);

    const emit_spirv_exe = b.addExecutable(.{
        .name = "doe-emit-spirv",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/cli/main_emit_spirv.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = build_options_module },
            },
        }),
    });
    emit_spirv_exe.linkLibC();
    const install_emit_spirv = b.addInstallArtifact(emit_spirv_exe, .{});
    const emit_spirv_step = b.step("emit-spirv", "Build the WGSL-to-SPIR-V emitter tool");
    emit_spirv_step.dependOn(&install_emit_spirv.step);
    b.getInstallStep().dependOn(emit_spirv_step);

    const webgpu_plan_executor = b.addExecutable(.{
        .name = "webgpu-plan-executor",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/cli/main_webgpu_plan_executor.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    webgpu_plan_executor.linkLibC();
    const dawn_webgpu_include = firstExistingPath(&.{
        "../../bench/vendor/dawn/third_party/webgpu-headers/src",
        "../../browser/chromium_webgpu_lane/.local_volume/chromium_webgpu_lane/src/third_party/dawn/include/webgpu",
        "/Volumes/MACOS/fawn-browser/src/third_party/dawn/include/webgpu",
    });
    const dawn_shared_include_candidates = [_][]const u8{
        "../../bench/vendor/dawn/third_party/webgpu-headers/src",
        "../../browser/chromium_webgpu_lane/.local_volume/chromium_webgpu_lane/src/third_party/dawn/include",
        "../../browser/chromium_webgpu_lane/.local_volume/chromium_webgpu_lane/src/out/fawn_release/gen/third_party/dawn/include",
        "/Volumes/MACOS/fawn-browser/src/third_party/dawn/include",
        "/Volumes/MACOS/fawn-browser/src/out/fawn_release/gen/third_party/dawn/include",
    };
    webgpu_plan_executor.addIncludePath(b.path(dawn_webgpu_include));
    addExistingIncludePaths(webgpu_plan_executor, b, &dawn_shared_include_candidates);
    const install_webgpu_plan_executor = b.addInstallArtifact(webgpu_plan_executor, .{});
    const webgpu_plan_executor_step = b.step("webgpu-plan-executor", "Build the standalone direct WebGPU plan executor");
    webgpu_plan_executor_step.dependOn(&install_webgpu_plan_executor.step);
    b.getInstallStep().dependOn(webgpu_plan_executor_step);

    const doe_plan_executor = b.addExecutable(.{
        .name = "doe-plan-executor",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/cli/main_doe_plan_executor.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = build_options_module },
            },
        }),
    });
    doe_plan_executor.linkLibC();
    if (target.result.os.tag == .windows) {
        doe_plan_executor.linkSystemLibrary("d3d12");
        doe_plan_executor.linkSystemLibrary("dxgi");
        doe_plan_executor.linkSystemLibrary("dxguid");
        doe_plan_executor.addCSourceFile(.{
            .file = b.path("src/backend/d3d12/d3d12_bridge.c"),
            .flags = &.{},
        });
    } else {
        configure_non_windows_graphics(doe_plan_executor, b, target);
    }
    const install_doe_plan_executor = b.addInstallArtifact(doe_plan_executor, .{});
    const doe_plan_executor_step = b.step("doe-plan-executor", "Build the standalone Doe direct plan executor");
    doe_plan_executor_step.dependOn(&install_doe_plan_executor.step);
    b.getInstallStep().dependOn(doe_plan_executor_step);

    const csl_sim_runner = b.addExecutable(.{
        .name = "doe-csl-sim-runner",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/cli/csl_sim_runner.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    csl_sim_runner.linkLibC();
    const install_csl_sim_runner = b.addInstallArtifact(csl_sim_runner, .{});
    const csl_sim_runner_step = b.step("csl-sim-runner", "Build the CSL simulator contract runner");
    csl_sim_runner_step.dependOn(&install_csl_sim_runner.step);
    b.getInstallStep().dependOn(csl_sim_runner_step);

    const csl_bundle_emitter = b.addExecutable(.{
        .name = "doe-csl-bundle-emitter",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/cli/csl_bundle_emitter.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = build_options_module },
            },
        }),
    });
    const install_csl_bundle_emitter = b.addInstallArtifact(csl_bundle_emitter, .{});
    const csl_bundle_emitter_step = b.step("csl-bundle-emitter", "Build the WGSL-to-CSL bundle emitter");
    csl_bundle_emitter_step.dependOn(&install_csl_bundle_emitter.step);
    b.getInstallStep().dependOn(csl_bundle_emitter_step);

    const csl_host_plan_tool = b.addExecutable(.{
        .name = "doe-csl-host-plan-tool",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/cli/csl_host_plan_tool.zig"),
            .target = target,
            .optimize = optimize,
        }),
    });
    csl_host_plan_tool.linkLibC();
    const install_csl_host_plan_tool = b.addInstallArtifact(csl_host_plan_tool, .{});
    const csl_host_plan_tool_step = b.step("csl-host-plan-tool", "Build the CSL host-plan lowering tool");
    csl_host_plan_tool_step.dependOn(&install_csl_host_plan_tool.step);
    b.getInstallStep().dependOn(csl_host_plan_tool_step);

    const import_fence_check = b.addSystemCommand(&.{ "python3", "tools/check_core_import_fence.py" });
    const import_fence_step = b.step("import-fence", "Validate core/full one-way import boundaries");
    import_fence_step.dependOn(&import_fence_check.step);

    const line_limit_check = b.addSystemCommand(&.{ "python3", "tools/check_line_limits.py" });
    const line_limit_step = b.step("line-limits", "Validate Zig source line-count policy");
    line_limit_step.dependOn(&line_limit_check.step);
    b.getInstallStep().dependOn(&line_limit_check.step);

    const bridge_manifest_check = b.addSystemCommand(&.{ "python3", "tools/check_metal_bridge_manifest.py" });
    const bridge_manifest_step = b.step("bridge-manifest", "Validate the Metal bridge manifest against Zig declarations and bridge sources");
    bridge_manifest_step.dependOn(&bridge_manifest_check.step);

    const coverage_gate_check = b.addSystemCommand(&.{ "python3", "bench/gates/split_coverage_gate.py", "--surface", "both" });
    coverage_gate_check.setCwd(b.path("../.."));
    const coverage_gate_step = b.step("coverage-gate", "Validate split core/full coverage ledgers against Zig partitions");
    coverage_gate_step.dependOn(&coverage_gate_check.step);

    const spirv_val_check = b.addSystemCommand(&.{ "python3", "../../bench/gates/spirv_val_gate.py" });
    const spirv_val_step = b.step("spirv-val", "Validate SPIR-V artifacts with spirv-val (skips gracefully if not installed)");
    spirv_val_step.dependOn(&spirv_val_check.step);

    // Tiered build variants: compute-only and full Dawn drop-in.
    // The default `dropin` step uses the --tier option (default: headless).
    // These named steps override tier for convenience.
    const compute_build_options = b.addOptions();
    compute_build_options.addOption(bool, "lean_verified", lean_verified);
    compute_build_options.addOption(BuildTier, "build_tier", .compute);
    addProofProvenanceOptions(compute_build_options, proof_provenance);
    // Re-embed required config for the compute variant.
    {
        const f = std.fs.cwd().openFile("../../config/comparability-obligations.json", .{}) catch @panic("config/comparability-obligations.json not found");
        defer f.close();
        const json = f.readToEndAlloc(b.allocator, 128 * 1024) catch @panic("failed to read comparability-obligations.json");
        compute_build_options.addOption([]const u8, "comparability_obligations_json", json);
        compute_build_options.addOption([]const u8, "comparability_obligations_sha256", sha256HexAlloc(b.allocator, json));
    }
    if (lean_verified) compute_build_options.addOption([]const u8, "lean_proof_json", proof_json orelse @panic("lean proof json missing for compute build options"));
    {
        const f = std.fs.cwd().openFile("../../config/dropin-abi-behavior.json", .{}) catch @panic("config/dropin-abi-behavior.json not found");
        defer f.close();
        compute_build_options.addOption([]const u8, "dropin_behavior_config_json", f.readToEndAlloc(b.allocator, 64 * 1024) catch @panic("failed to read dropin-abi-behavior.json"));
    }
    {
        const f = std.fs.cwd().openFile("../../config/dropin-symbol-ownership.json", .{}) catch @panic("config/dropin-symbol-ownership.json not found");
        defer f.close();
        compute_build_options.addOption([]const u8, "dropin_symbol_ownership_config_json", f.readToEndAlloc(b.allocator, 64 * 1024) catch @panic("failed to read dropin-symbol-ownership.json"));
    }
    {
        const f = std.fs.cwd().openFile("../../config/quirk-toggle-registry.json", .{}) catch @panic("config/quirk-toggle-registry.json not found");
        defer f.close();
        compute_build_options.addOption([]const u8, "quirk_toggle_registry_json", f.readToEndAlloc(b.allocator, 64 * 1024) catch @panic("failed to read quirk-toggle-registry.json"));
    }

    const core_dropin_lib = b.addLibrary(.{
        .name = "webgpu_doe_compute",
        .linkage = .dynamic,
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/wgpu_dropin_lib.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = compute_build_options.createModule() },
            },
        }),
    });
    core_dropin_lib.linkLibC();
    if (target.result.os.tag == .windows) {
        core_dropin_lib.linkSystemLibrary("d3d12");
        core_dropin_lib.linkSystemLibrary("dxgi");
        core_dropin_lib.linkSystemLibrary("dxguid");
        core_dropin_lib.addCSourceFile(.{
            .file = b.path("src/backend/d3d12/d3d12_bridge.c"),
            .flags = &.{},
        });
    } else {
        configure_non_windows_graphics(core_dropin_lib, b, target);
    }
    const install_core_dropin = b.addInstallArtifact(core_dropin_lib, .{});
    const core_dropin_step = b.step("dropin-compute", "Build compute-only drop-in library (dispatch + buffer, no render)");
    core_dropin_step.dependOn(&install_core_dropin.step);

    // Alias the old name for backwards compatibility.
    const core_dropin_compat_step = b.step("dropin-core", "Alias for dropin-compute");
    core_dropin_compat_step.dependOn(&install_core_dropin.step);

    // Full Dawn drop-in variant (tier=full).
    const full_build_options = b.addOptions();
    full_build_options.addOption(bool, "lean_verified", lean_verified);
    full_build_options.addOption(BuildTier, "build_tier", .full);
    addProofProvenanceOptions(full_build_options, proof_provenance);
    {
        const f = std.fs.cwd().openFile("../../config/comparability-obligations.json", .{}) catch @panic("config/comparability-obligations.json not found");
        defer f.close();
        const json = f.readToEndAlloc(b.allocator, 128 * 1024) catch @panic("failed to read comparability-obligations.json");
        full_build_options.addOption([]const u8, "comparability_obligations_json", json);
        full_build_options.addOption([]const u8, "comparability_obligations_sha256", sha256HexAlloc(b.allocator, json));
    }
    if (lean_verified) full_build_options.addOption([]const u8, "lean_proof_json", proof_json orelse @panic("lean proof json missing for full build options"));
    {
        const f = std.fs.cwd().openFile("../../config/dropin-abi-behavior.json", .{}) catch @panic("config/dropin-abi-behavior.json not found");
        defer f.close();
        full_build_options.addOption([]const u8, "dropin_behavior_config_json", f.readToEndAlloc(b.allocator, 64 * 1024) catch @panic("failed to read dropin-abi-behavior.json"));
    }
    {
        const f = std.fs.cwd().openFile("../../config/dropin-symbol-ownership.json", .{}) catch @panic("config/dropin-symbol-ownership.json not found");
        defer f.close();
        full_build_options.addOption([]const u8, "dropin_symbol_ownership_config_json", f.readToEndAlloc(b.allocator, 64 * 1024) catch @panic("failed to read dropin-symbol-ownership.json"));
    }
    {
        const f = std.fs.cwd().openFile("../../config/quirk-toggle-registry.json", .{}) catch @panic("config/quirk-toggle-registry.json not found");
        defer f.close();
        full_build_options.addOption([]const u8, "quirk_toggle_registry_json", f.readToEndAlloc(b.allocator, 64 * 1024) catch @panic("failed to read quirk-toggle-registry.json"));
    }

    const full_dropin_lib = b.addLibrary(.{
        .name = "webgpu_doe_full",
        .linkage = .dynamic,
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/wgpu_dropin_lib.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = full_build_options.createModule() },
            },
        }),
    });
    full_dropin_lib.linkLibC();
    if (target.result.os.tag == .windows) {
        full_dropin_lib.linkSystemLibrary("d3d12");
        full_dropin_lib.linkSystemLibrary("dxgi");
        full_dropin_lib.linkSystemLibrary("dxguid");
        full_dropin_lib.addCSourceFile(.{
            .file = b.path("src/backend/d3d12/d3d12_bridge.c"),
            .flags = &.{},
        });
    } else {
        configure_non_windows_graphics(full_dropin_lib, b, target);
    }
    const install_full_dropin = b.addInstallArtifact(full_dropin_lib, .{});
    const full_dropin_step = b.step("dropin-full", "Build full Dawn drop-in library (all procs, surface, external textures)");
    full_dropin_step.dependOn(&install_full_dropin.step);

    const test_step = b.step("test", "Run Zig unit tests");
    const test_exec = b.addTest(.{
        .root_module = b.createModule(.{
            .root_source_file = b.path("test_suite.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = build_options_module },
            },
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
        configure_non_windows_graphics(test_exec, b, target);
    }
    const run_tests = b.addRunArtifact(test_exec);
    test_step.dependOn(&import_fence_check.step);
    test_step.dependOn(&line_limit_check.step);
    test_step.dependOn(&bridge_manifest_check.step);
    test_step.dependOn(&run_tests.step);

    const core_test_step = b.step("test-core", "Run core-lane Zig unit tests");
    const core_test_exec = b.addTest(.{
        .root_module = b.createModule(.{
            .root_source_file = b.path("test_suite_core.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = build_options_module },
            },
        }),
    });
    core_test_exec.linkLibC();
    if (target.result.os.tag == .windows) {
        core_test_exec.linkSystemLibrary("d3d12");
        core_test_exec.linkSystemLibrary("dxgi");
        core_test_exec.linkSystemLibrary("dxguid");
        core_test_exec.addCSourceFile(.{
            .file = b.path("src/backend/d3d12/d3d12_bridge.c"),
            .flags = &.{},
        });
    } else {
        configure_non_windows_graphics(core_test_exec, b, target);
    }
    const run_core_tests = b.addRunArtifact(core_test_exec);
    core_test_step.dependOn(&import_fence_check.step);
    core_test_step.dependOn(&line_limit_check.step);
    core_test_step.dependOn(&bridge_manifest_check.step);
    core_test_step.dependOn(&run_core_tests.step);

    const full_test_step = b.step("test-full", "Run full-lane Zig unit tests");
    const full_test_exec = b.addTest(.{
        .root_module = b.createModule(.{
            .root_source_file = b.path("test_suite_full.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = build_options_module },
            },
        }),
    });
    full_test_exec.linkLibC();
    if (target.result.os.tag == .windows) {
        full_test_exec.linkSystemLibrary("d3d12");
        full_test_exec.linkSystemLibrary("dxgi");
        full_test_exec.linkSystemLibrary("dxguid");
        full_test_exec.addCSourceFile(.{
            .file = b.path("src/backend/d3d12/d3d12_bridge.c"),
            .flags = &.{},
        });
    } else {
        configure_non_windows_graphics(full_test_exec, b, target);
    }
    const run_full_tests = b.addRunArtifact(full_test_exec);
    full_test_step.dependOn(&import_fence_check.step);
    full_test_step.dependOn(&line_limit_check.step);
    full_test_step.dependOn(&bridge_manifest_check.step);
    full_test_step.dependOn(&run_full_tests.step);

    const d3d12_test_step = b.step("test-d3d12", "Run D3D12-focused Zig tests (no Metal test suite)");
    const d3d12_test_exec = b.addTest(.{
        .root_module = b.createModule(.{
            .root_source_file = b.path("test_suite_d3d12.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = build_options_module },
            },
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
        configure_non_windows_graphics(d3d12_test_exec, b, target);
    }
    const run_d3d12_tests = b.addRunArtifact(d3d12_test_exec);
    d3d12_test_step.dependOn(&import_fence_check.step);
    d3d12_test_step.dependOn(&line_limit_check.step);
    d3d12_test_step.dependOn(&run_d3d12_tests.step);

    const wgsl_test_step = b.step("test-wgsl", "Run WGSL shader compiler tests");
    const wgsl_test_exec = b.addTest(.{
        .root_module = b.createModule(.{
            .root_source_file = b.path("test_suite_wgsl.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = build_options_module },
            },
        }),
    });
    wgsl_test_exec.linkLibC();
    const run_wgsl_tests = b.addRunArtifact(wgsl_test_exec);
    wgsl_test_step.dependOn(&run_wgsl_tests.step);

    const shader_bench_exe = b.addExecutable(.{
        .name = "doe-shader-bench",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/doe_wgsl/bench.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = build_options_module },
                .{
                    .name = "lean_proof",
                    .module = b.createModule(.{
                        .root_source_file = b.path("src/lean_proof.zig"),
                        .target = target,
                        .optimize = optimize,
                        .imports = &.{
                            .{ .name = "build_options", .module = build_options_module },
                        },
                    }),
                },
            },
        }),
    });
    shader_bench_exe.linkLibC();
    const install_shader_bench = b.addInstallArtifact(shader_bench_exe, .{});
    const shader_bench_step = b.step("bench-shader", "Build the WGSL shader compiler stage microbenchmark");
    shader_bench_step.dependOn(&install_shader_bench.step);

    const run_shader_bench = b.addRunArtifact(shader_bench_exe);
    if (b.args) |args| run_shader_bench.addArgs(args);
    const shader_bench_run_step = b.step("bench-shader-run", "Build and run the WGSL shader compiler stage microbenchmark");
    shader_bench_run_step.dependOn(&install_shader_bench.step);
    shader_bench_run_step.dependOn(&run_shader_bench.step);

    const host_hotpath_bench_exe = b.addExecutable(.{
        .name = "doe-host-hotpath-bench",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/cli/main_host_hotpath_bench.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = build_options_module },
            },
        }),
    });
    host_hotpath_bench_exe.linkLibC();
    const install_host_hotpath_bench = b.addInstallArtifact(host_hotpath_bench_exe, .{});
    const host_hotpath_bench_step = b.step("bench-host-hotpaths", "Build the host hotpath scalar-vs-SIMD benchmark");
    host_hotpath_bench_step.dependOn(&install_host_hotpath_bench.step);

    const run_host_hotpath_bench = b.addRunArtifact(host_hotpath_bench_exe);
    if (b.args) |args| run_host_hotpath_bench.addArgs(args);
    const host_hotpath_bench_run_step = b.step("bench-host-hotpaths-run", "Build and run the host hotpath scalar-vs-SIMD benchmark");
    host_hotpath_bench_run_step.dependOn(&install_host_hotpath_bench.step);
    host_hotpath_bench_run_step.dependOn(&run_host_hotpath_bench.step);

    const compilation_bench_exe = b.addExecutable(.{
        .name = "doe-compilation-bench",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/cli/main_bench_compilation.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = build_options_module },
            },
        }),
    });
    compilation_bench_exe.linkLibC();
    const install_compilation_bench = b.addInstallArtifact(compilation_bench_exe, .{});
    const compilation_bench_step = b.step("bench-compilation", "Build the WGSL compilation latency benchmark");
    compilation_bench_step.dependOn(&install_compilation_bench.step);

    const run_compilation_bench = b.addRunArtifact(compilation_bench_exe);
    if (b.args) |args| run_compilation_bench.addArgs(args);
    const compilation_bench_run_step = b.step("bench-compilation-run", "Build and run the WGSL compilation latency benchmark");
    compilation_bench_run_step.dependOn(&install_compilation_bench.step);
    compilation_bench_run_step.dependOn(&run_compilation_bench.step);

    const runtime_compile_report_exe = b.addExecutable(.{
        .name = "doe-runtime-compile-report",
        .root_module = b.createModule(.{
            .root_source_file = b.path("src/cli/main_runtime_compile_report.zig"),
            .target = target,
            .optimize = optimize,
            .imports = &.{
                .{ .name = "build_options", .module = build_options_module },
            },
        }),
    });
    runtime_compile_report_exe.linkLibC();
    const install_runtime_compile_report = b.addInstallArtifact(runtime_compile_report_exe, .{});
    const runtime_compile_report_step = b.step("runtime-compile-report", "Build the WGSL runtime compile structural report CLI");
    runtime_compile_report_step.dependOn(&install_runtime_compile_report.step);

    const run_runtime_compile_report = b.addRunArtifact(runtime_compile_report_exe);
    if (b.args) |args| run_runtime_compile_report.addArgs(args);
    const runtime_compile_report_run_step = b.step("runtime-compile-report-run", "Build and run the WGSL runtime compile structural report CLI");
    runtime_compile_report_run_step.dependOn(&install_runtime_compile_report.step);
    runtime_compile_report_run_step.dependOn(&run_runtime_compile_report.step);
}
