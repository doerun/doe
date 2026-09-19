const std = @import("std");
const artifact = @import("../../contracts/artifact.zig");
const artifact_state = @import("artifact_state.zig");

const MAX_TOOLCHAIN_BYTES: usize = 64 * 1024;
const TAXONOMY_CODE_CAPACITY: usize = 128;
const ZERO_HASH = "0000000000000000000000000000000000000000000000000000000000000000";

pub const StageImplementation = enum {
    unobserved,
    native_zig,
    external_tool,

    pub fn name(self: StageImplementation) []const u8 {
        return switch (self) {
            .native_zig => "native_zig",
            .unobserved => "unobserved",
            .external_tool => "external_tool",
        };
    }
};

pub const StageDescriptor = struct {
    stage: []const u8,
    hash_label: []const u8,
    manifest_field: ?[]const u8 = null,
    implementation: StageImplementation = .unobserved,
    tool: ?[]const u8 = null,
    version: ?[]const u8 = null,
    args: []const []const u8 = &.{},
};

pub const ManifestSpec = struct {
    backend_id: []const u8,
    file_prefix: []const u8,
    stages: []const StageDescriptor,
};

/// Runtime-side payload associated with a stage: when the backend has the
/// real compiled artifact bytes (e.g. a SPIR-V module), the manifest emitter
/// writes them to a sibling file and records the path on the matching stage
/// record so downstream gates (`shader_artifact_gate.py --require-spirv-validation`)
/// can run spirv-val against the binary.
pub const StageArtifact = struct {
    manifest_field: []const u8,
    bytes: []const u8,
    extension: []const u8,
};

pub fn flushPending(state: *artifact_state.State, spec: ManifestSpec) !void {
    if (state.capture_error) |err| return err;
    const pending = state.pending orelse return;
    var artifacts: [1]StageArtifact = undefined;
    const views: []const StageArtifact = if (pending.spirv) |bytes| blk: {
        artifacts[0] = .{ .manifest_field = "spirvSha256", .bytes = bytes, .extension = ".spv" };
        break :blk &artifacts;
    } else &.{};
    try emit_shader_artifact_manifest_for_signature_with_artifacts(
        state,
        spec,
        pending.module,
        pending.meta,
        pending.status,
        views,
    );
    state.clearPending();
}

pub fn emit_shader_artifact_manifest_for_signature_with_artifacts(
    self: *artifact_state.State,
    spec: ManifestSpec,
    module: []const u8,
    meta: artifact.ArtifactMeta,
    status_code: []const u8,
    stage_artifacts: []const StageArtifact,
) anyerror!void {
    const toolchain_hash = try load_toolchain_sha256(self.allocator, self.output.toolchain_path);

    var taxonomy_buffer: [TAXONOMY_CODE_CAPACITY]u8 = undefined;
    const taxonomy_code = normalize_taxonomy_code(&taxonomy_buffer, status_code);
    const source_hash = if (self.pending) |pending| pending.source_hash else null;
    const wgsl_hash = source_hash orelse artifact.sha256_hex(module);
    try std.fs.cwd().makePath(self.output.directory);

    const stage_artifact_paths = try write_stage_artifact_blobs(
        self.allocator,
        self.output.directory,
        spec,
        stage_artifacts,
    );
    defer free_stage_artifact_paths(self.allocator, stage_artifact_paths);

    const stage_hashes = try derive_stage_hashes(
        self.allocator,
        spec.stages,
        wgsl_hash,
        stage_artifact_paths,
    );
    defer self.allocator.free(stage_hashes);

    const pipeline_stage_hash = if (stage_hashes.len > 0)
        stage_hashes[stage_hashes.len - 1][0..]
    else
        wgsl_hash[0..];

    const stages_json = try build_stages_json(
        self.allocator,
        spec.stages,
        wgsl_hash,
        stage_hashes,
        stage_artifact_paths,
    );
    defer self.allocator.free(stages_json);

    const pipeline_seed = try std.fmt.allocPrint(
        self.allocator,
        "{s}|{s}|{s}|{s}|{s}|{s}|{s}|{s}|{s}|{}|{s}",
        .{
            spec.backend_id,
            module,
            pipeline_stage_hash,
            taxonomy_code,
            meta.backend_kind.name(),
            meta.timing_source.name(),
            meta.comparability.name(),
            toolchain_hash,
            wgsl_hash,
            source_hash != null,
            stages_json,
        },
    );

    defer self.allocator.free(pipeline_seed);
    const pipeline_hash = artifact.sha256_hex(pipeline_seed);
    if (self.last_signature) |last| {
        if (std.mem.eql(u8, &last, &pipeline_hash)) return;
    }

    const prehash = try build_prehash_json(
        self.allocator,
        spec,
        module,
        meta,
        taxonomy_code,
        previous_manifest_hash(self),
        toolchain_hash,
        pipeline_hash,
        wgsl_hash,
        stage_hashes,
        stages_json,
        source_hash != null,
    );
    defer self.allocator.free(prehash);

    const hash = artifact.sha256_hex(prehash);
    const content = try std.fmt.allocPrint(
        self.allocator,
        "{s},\"hash\":\"{s}\"}}\n",
        .{
            prehash[0 .. prehash.len - 1],
            hash[0..],
        },
    );
    defer self.allocator.free(content);

    const path = try std.fmt.allocPrint(self.allocator, "{s}/{s}_shader_artifact_{s}.json", .{ self.output.directory, spec.file_prefix, hash });
    errdefer self.allocator.free(path);
    try writeAtomically(path, content);

    if (self.manifest_path) |old| self.allocator.free(old);
    self.manifest_path = path;
    self.manifest_hash = hash;
    self.last_signature = pipeline_hash;
    self.manifest_emit_count +|= 1;
}

fn previous_manifest_hash(self: *artifact_state.State) []const u8 {
    if (self.manifest_hash) |*hash| return hash;
    return ZERO_HASH;
}

fn derive_stage_hash(seed: []const u8, label: []const u8) [artifact.SHA256_HEX_SIZE]u8 {
    var hasher = std.crypto.hash.sha2.Sha256.init(.{});
    hasher.update(seed);
    hasher.update("|");
    hasher.update(label);
    return artifact.sha256_digest_hex(hasher.finalResult());
}

fn derive_stage_hashes(
    allocator: std.mem.Allocator,
    stages: []const StageDescriptor,
    wgsl_hash: [artifact.SHA256_HEX_SIZE]u8,
    stage_artifact_paths: []const StageArtifactPath,
) ![][artifact.SHA256_HEX_SIZE]u8 {
    const hashes = try allocator.alloc([artifact.SHA256_HEX_SIZE]u8, stages.len);
    var previous = wgsl_hash;
    for (stages, 0..) |stage, index| {
        hashes[index] = lookup_artifact_hash(stage, stage_artifact_paths) orelse
            derive_stage_hash(previous[0..], stage.hash_label);
        previous = hashes[index];
    }
    return hashes;
}

const StageArtifactPath = struct {
    manifest_field: []const u8,
    filename: []u8,
    artifact_hash: [artifact.SHA256_HEX_SIZE]u8,
};

fn write_stage_artifact_blobs(
    allocator: std.mem.Allocator,
    output_directory: []const u8,
    spec: ManifestSpec,
    stage_artifacts: []const StageArtifact,
) ![]StageArtifactPath {
    if (stage_artifacts.len == 0) return allocator.alloc(StageArtifactPath, 0);
    var out = try allocator.alloc(StageArtifactPath, stage_artifacts.len);
    var written: usize = 0;
    errdefer {
        for (out[0..written]) |entry| allocator.free(entry.filename);
        allocator.free(out);
    }
    for (stage_artifacts) |blob| {
        const artifact_hash = artifact.sha256_hex(blob.bytes);
        const filename = try std.fmt.allocPrint(
            allocator,
            "{s}_shader_artifact_{s}{s}",
            .{ spec.file_prefix, artifact_hash[0..], blob.extension },
        );
        errdefer allocator.free(filename);
        const full_path = try std.fmt.allocPrint(
            allocator,
            "{s}/{s}",
            .{ output_directory, filename },
        );
        defer allocator.free(full_path);
        try writeAtomically(full_path, blob.bytes);
        out[written] = .{
            .manifest_field = blob.manifest_field,
            .filename = filename,
            .artifact_hash = artifact_hash,
        };
        written += 1;
    }
    return out;
}

fn writeAtomically(path: []const u8, bytes: []const u8) !void {
    var file = try std.fs.cwd().atomicFile(path, .{ .write_buffer = &.{} });
    defer file.deinit();
    try file.file_writer.interface.writeAll(bytes);
    try file.finish();
}

fn free_stage_artifact_paths(allocator: std.mem.Allocator, paths: []StageArtifactPath) void {
    for (paths) |entry| allocator.free(entry.filename);
    allocator.free(paths);
}

fn lookup_artifact_path(
    stage: StageDescriptor,
    stage_artifact_paths: []const StageArtifactPath,
) ?[]const u8 {
    const field = stage.manifest_field orelse return null;
    for (stage_artifact_paths) |entry| {
        if (std.mem.eql(u8, entry.manifest_field, field)) return entry.filename;
    }
    return null;
}

fn lookup_artifact_hash(
    stage: StageDescriptor,
    stage_artifact_paths: []const StageArtifactPath,
) ?[artifact.SHA256_HEX_SIZE]u8 {
    const field = stage.manifest_field orelse return null;
    for (stage_artifact_paths) |entry| {
        if (std.mem.eql(u8, entry.manifest_field, field)) return entry.artifact_hash;
    }
    return null;
}

fn build_stages_json(
    allocator: std.mem.Allocator,
    stages: []const StageDescriptor,
    wgsl_hash: [artifact.SHA256_HEX_SIZE]u8,
    stage_hashes: []const [artifact.SHA256_HEX_SIZE]u8,
    stage_artifact_paths: []const StageArtifactPath,
) ![]u8 {
    var list = try std.ArrayList(u8).initCapacity(allocator, 0);
    errdefer list.deinit(allocator);
    const writer = list.writer(allocator);

    try writer.writeByte('[');
    try write_stage_json(allocator, writer, .{
        .stage = "wgsl_parse",
        .hash_label = "wgsl_parse",
    }, wgsl_hash, null);
    for (stages, 0..) |stage, index| {
        try writer.writeByte(',');
        try write_stage_json(allocator, writer, stage, stage_hashes[index], lookup_artifact_path(stage, stage_artifact_paths));
    }
    try writer.writeByte(']');
    return list.toOwnedSlice(allocator);
}

fn write_stage_json(
    allocator: std.mem.Allocator,
    writer: anytype,
    stage: StageDescriptor,
    artifact_hash: [artifact.SHA256_HEX_SIZE]u8,
    artifact_path: ?[]const u8,
) !void {
    const stage_json = try artifact.jsonStringifyAlloc(allocator, stage.stage);
    defer allocator.free(stage_json);
    try writer.print("{{\"stage\":{s},\"implementation\":\"{s}\",\"artifactSha256\":\"{s}\"", .{ stage_json, stage.implementation.name(), artifact_hash });
    try writer.print(",\"hashKind\":\"{s}\"", .{if (artifact_path != null) @as([]const u8, "content") else "derived"});
    if (artifact_path) |path| {
        const path_json = try artifact.jsonStringifyAlloc(allocator, path);
        defer allocator.free(path_json);
        try writer.print(",\"artifactPath\":{s}", .{path_json});
    }
    switch (stage.implementation) {
        .unobserved, .native_zig => {},
        .external_tool => {
            const tool = stage.tool orelse return error.InvalidArgument;
            const version = stage.version orelse return error.InvalidArgument;
            const tool_json = try artifact.jsonStringifyAlloc(allocator, tool);
            defer allocator.free(tool_json);
            const version_json = try artifact.jsonStringifyAlloc(allocator, version);
            defer allocator.free(version_json);
            try writer.print(",\"tool\":{s},\"version\":{s},\"args\":[", .{ tool_json, version_json });
            for (stage.args, 0..) |arg, index| {
                if (index > 0) try writer.writeByte(',');
                const arg_json = try artifact.jsonStringifyAlloc(allocator, arg);
                defer allocator.free(arg_json);
                try writer.writeAll(arg_json);
            }
            try writer.writeByte(']');
        },
    }
    try writer.writeByte('}');
}

fn build_prehash_json(
    allocator: std.mem.Allocator,
    spec: ManifestSpec,
    module: []const u8,
    meta: artifact.ArtifactMeta,
    taxonomy_code: []const u8,
    previous_hash: []const u8,
    toolchain_hash: [artifact.SHA256_HEX_SIZE]u8,
    pipeline_hash: [artifact.SHA256_HEX_SIZE]u8,
    wgsl_hash: [artifact.SHA256_HEX_SIZE]u8,
    stage_hashes: []const [artifact.SHA256_HEX_SIZE]u8,
    stages_json: []const u8,
    has_source_hash: bool,
) ![]u8 {
    var list = try std.ArrayList(u8).initCapacity(allocator, 0);
    errdefer list.deinit(allocator);
    const writer = list.writer(allocator);

    _ = meta;
    const module_json = try artifact.jsonStringifyAlloc(allocator, module);
    defer allocator.free(module_json);
    try writer.print(
        "{{\"schemaVersion\":3,\"backendId\":\"{s}\",\"module\":{s},\"pipelineHash\":\"{s}\",\"wgslSha256\":\"{s}\"",
        .{ spec.backend_id, module_json, pipeline_hash[0..], wgsl_hash[0..] },
    );
    try writer.print(",\"wgslHashKind\":\"{s}\"", .{if (has_source_hash) @as([]const u8, "source_observation") else "module_label"});
    for (spec.stages, 0..) |stage, index| {
        if (stage.manifest_field) |field| {
            try writer.print(",\"{s}\":\"{s}\"", .{ field, stage_hashes[index][0..] });
        }
    }
    try writer.print(
        ",\"toolchainSha256\":\"{s}\",\"taxonomyCode\":\"{s}\",\"previousHash\":\"{s}\",\"stages\":{s}}}",
        .{ toolchain_hash[0..], taxonomy_code, previous_hash, stages_json },
    );
    return list.toOwnedSlice(allocator);
}

fn load_toolchain_sha256(allocator: std.mem.Allocator, path: []const u8) ![artifact.SHA256_HEX_SIZE]u8 {
    const bytes = try std.fs.cwd().readFileAlloc(allocator, path, MAX_TOOLCHAIN_BYTES);
    defer allocator.free(bytes);
    return artifact.sha256_hex(bytes);
}

fn normalize_taxonomy_code(buffer: []u8, raw: []const u8) []const u8 {
    var out_len: usize = 0;
    var previous_underscore = false;
    for (raw) |byte| {
        if (out_len >= buffer.len) break;
        const lowered = std.ascii.toLower(byte);
        const is_valid = (lowered >= 'a' and lowered <= 'z') or (lowered >= '0' and lowered <= '9');
        if (is_valid) {
            buffer[out_len] = lowered;
            out_len += 1;
            previous_underscore = false;
            continue;
        }
        if (!previous_underscore and out_len < buffer.len) {
            buffer[out_len] = '_';
            out_len += 1;
            previous_underscore = true;
        }
    }
    if (out_len == 0) {
        return "error";
    }
    while (out_len > 1 and buffer[out_len - 1] == '_') out_len -= 1;
    return buffer[0..out_len];
}

test "normalize_taxonomy_code normalizes punctuation and case" {
    var buffer: [64]u8 = undefined;
    const value = normalize_taxonomy_code(&buffer, "Shader Compile Failed!");
    try std.testing.expectEqualStrings("shader_compile_failed", value);
}

test "derive_stage_hashes builds deterministic chained hashes" {
    const stages = [_]StageDescriptor{
        .{ .stage = "sema", .hash_label = "sema" },
        .{ .stage = "ir_build", .hash_label = "ir_build", .manifest_field = "irSha256" },
    };
    const wgsl_hash = artifact.sha256_hex("module");
    const hashes = try derive_stage_hashes(std.testing.allocator, &stages, wgsl_hash, &.{});
    defer std.testing.allocator.free(hashes);

    try std.testing.expectEqual(derive_stage_hash(wgsl_hash[0..], "sema"), hashes[0]);
    try std.testing.expectEqual(derive_stage_hash(hashes[0][0..], "ir_build"), hashes[1]);
}

test "derive_stage_hashes uses actual stage artifact hash when present" {
    const stages = [_]StageDescriptor{
        .{ .stage = "ir_to_spirv", .hash_label = "ir_to_spirv", .manifest_field = "spirvSha256" },
    };
    const wgsl_hash = artifact.sha256_hex("module");
    const filename_owned = try std.testing.allocator.dupe(u8, "shader.spv");
    defer std.testing.allocator.free(filename_owned);
    const artifact_hash = artifact.sha256_hex("spirv-bytes");
    const paths = [_]StageArtifactPath{
        .{
            .manifest_field = "spirvSha256",
            .filename = filename_owned,
            .artifact_hash = artifact_hash,
        },
    };
    const hashes = try derive_stage_hashes(std.testing.allocator, &stages, wgsl_hash, &paths);
    defer std.testing.allocator.free(hashes);

    try std.testing.expectEqual(artifact_hash, hashes[0]);
}

test "build_stages_json preserves external tool stage metadata" {
    const stages = [_]StageDescriptor{
        .{
            .stage = "dxil_validate",
            .hash_label = "dxil_validate",
            .implementation = .external_tool,
            .tool = "dxv",
            .version = "1.x",
            .args = &.{},
        },
    };
    const wgsl_hash = artifact.sha256_hex("module");
    const stage_hashes = [_][artifact.SHA256_HEX_SIZE]u8{artifact.sha256_hex("dxil_validate")};
    const json = try build_stages_json(std.testing.allocator, &stages, wgsl_hash, &stage_hashes, &.{});
    defer std.testing.allocator.free(json);

    try std.testing.expect(std.mem.indexOf(u8, json, "\"implementation\":\"external_tool\"") != null);
    try std.testing.expect(std.mem.indexOf(u8, json, "\"tool\":\"dxv\"") != null);
    try std.testing.expect(std.mem.indexOf(u8, json, "\"version\":\"1.x\"") != null);
    try std.testing.expect(std.mem.indexOf(u8, json, "\"args\":[]") != null);
}

test "build_stages_json includes artifactPath when provided" {
    const stages = [_]StageDescriptor{
        .{ .stage = "ir_to_spirv", .hash_label = "ir_to_spirv", .manifest_field = "spirvSha256" },
    };
    const wgsl_hash = artifact.sha256_hex("module");
    const stage_hashes = [_][artifact.SHA256_HEX_SIZE]u8{artifact.sha256_hex("ir_to_spirv")};
    const filename_owned = try std.testing.allocator.dupe(u8, "vulkan_shader_artifact_1.spv");
    defer std.testing.allocator.free(filename_owned);
    const paths = [_]StageArtifactPath{
        .{
            .manifest_field = "spirvSha256",
            .filename = filename_owned,
            .artifact_hash = artifact.sha256_hex("spirv"),
        },
    };
    const json = try build_stages_json(std.testing.allocator, &stages, wgsl_hash, &stage_hashes, &paths);
    defer std.testing.allocator.free(json);

    try std.testing.expect(std.mem.indexOf(u8, json, "\"stage\":\"ir_to_spirv\"") != null);
    try std.testing.expect(std.mem.indexOf(u8, json, "\"artifactPath\":\"vulkan_shader_artifact_1.spv\"") != null);
}

const TEST_SPEC: ManifestSpec = .{
    .backend_id = "doe_vulkan",
    .file_prefix = "vulkan",
    .stages = &.{
        .{ .stage = "ir_build", .hash_label = "ir_build", .manifest_field = "irSha256" },
        .{ .stage = "ir_to_spirv", .hash_label = "ir_to_spirv", .manifest_field = "spirvSha256" },
    },
};
const TEST_META: artifact.ArtifactMeta = .{
    .backend_kind = .native_vulkan,
    .timing_source = .cpu_submit_wait,
    .comparability = .directional,
};

fn exerciseManifest(allocator: std.mem.Allocator) !void {
    var temp = std.testing.tmpDir(.{});
    defer temp.cleanup();
    const root = try temp.dir.realpathAlloc(std.testing.allocator, ".");
    defer std.testing.allocator.free(root);
    const toolchain = try std.fs.path.join(std.testing.allocator, &.{ root, "toolchain.json" });
    defer std.testing.allocator.free(toolchain);
    var state = artifact_state.State{ .allocator = allocator, .output = .{ .directory = root, .toolchain_path = toolchain } };
    defer state.deinit();
    const module = "shader\"with\\escapes\n.wgsl";
    try state.capture(module, TEST_META, "ok", "spirv bytes", null);
    try std.testing.expect(state.path() == null);
    try std.testing.expect(state.hash() == null);
    try std.testing.expectEqual(@as(u64, 0), state.manifest_emit_count);
    flushPending(&state, TEST_SPEC) catch |err| {
        if (err != error.FileNotFound) return err;
        try std.testing.expect(state.pending != null);
    };
    try temp.dir.writeFile(.{ .sub_path = "toolchain.json", .data = "{}" });
    try flushPending(&state, TEST_SPEC);
    const original_hash = state.manifest_hash.?;
    const bytes = try std.fs.cwd().readFileAlloc(allocator, state.path().?, 64 * 1024);
    defer allocator.free(bytes);
    var parsed = try std.json.parseFromSlice(std.json.Value, allocator, bytes, .{});
    defer parsed.deinit();
    const object = parsed.value.object;
    try std.testing.expectEqual(@as(i64, 3), object.get("schemaVersion").?.integer);
    try std.testing.expectEqualStrings(module, object.get("module").?.string);
    try std.testing.expectEqualStrings("module_label", object.get("wgslHashKind").?.string);
    const stages = object.get("stages").?.array.items;
    try std.testing.expectEqualStrings("derived", stages[1].object.get("hashKind").?.string);
    try std.testing.expectEqualStrings("content", stages[2].object.get("hashKind").?.string);
    try state.capture(module, TEST_META, "ok", "spirv bytes", null);
    try flushPending(&state, TEST_SPEC);
    try std.testing.expectEqual(original_hash, state.manifest_hash.?);
    try std.testing.expectEqual(@as(u64, 1), state.manifest_emit_count);
    try state.capture(module, TEST_META, "ok", "changed bytes", null);
    try flushPending(&state, TEST_SPEC);
    try std.testing.expect(!std.mem.eql(u8, &original_hash, &state.manifest_hash.?));
    const before_source_hash = state.manifest_hash.?;
    const source_hash = artifact.sha256_hex("changed source with same compiled bytes");
    try state.capture(module, TEST_META, "ok", "changed bytes", source_hash);
    try flushPending(&state, TEST_SPEC);
    try std.testing.expect(!std.mem.eql(u8, &before_source_hash, &state.manifest_hash.?));
    const changed_hash = state.manifest_hash.?;
    try temp.dir.writeFile(.{ .sub_path = "toolchain.json", .data = "{\"revision\":2}" });
    try state.capture(module, TEST_META, "ok", "changed bytes", source_hash);
    try flushPending(&state, TEST_SPEC);
    try std.testing.expect(!std.mem.eql(u8, &changed_hash, &state.manifest_hash.?));
}

test "artifact collection retries failures and owns content identities across allocation failures" {
    try std.testing.checkAllAllocationFailures(std.testing.allocator, exerciseManifest, .{});
}

test "derived identity hashes the complete long label without fallback" {
    const label = [_]u8{'x'} ** 1024;
    const joined = try std.fmt.allocPrint(std.testing.allocator, "seed|{s}", .{label});
    defer std.testing.allocator.free(joined);
    try std.testing.expectEqual(artifact.sha256_hex(joined), derive_stage_hash("seed", &label));
    var empty: [0]u8 = .{};
    try std.testing.expectEqualStrings("error", normalize_taxonomy_code(&empty, ""));
}
