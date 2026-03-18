const std = @import("std");
const artifact_meta = @import("artifact_meta.zig");
const artifact_state = @import("artifact_state.zig");
const common_errors = @import("errors.zig");
const hash_utils = @import("hash_utils.zig");

const SHADER_ARTIFACT_DIR = "bench/out/shader-artifacts";
const SHADER_TOOLCHAIN_PATH = "config/shader-toolchain.json";
const MAX_TOOLCHAIN_BYTES: usize = 64 * 1024;
const HASH_INPUT_CAPACITY: usize = 512;
const TAXONOMY_CODE_CAPACITY: usize = 128;
const ZERO_HASH = "0000000000000000000000000000000000000000000000000000000000000000";

pub const StageDescriptor = struct {
    stage: []const u8,
    hash_label: []const u8,
    manifest_field: ?[]const u8 = null,
};

pub const ManifestSpec = struct {
    backend_id: []const u8,
    file_prefix: []const u8,
    stages: []const StageDescriptor,
};

pub fn manifest_path(self: anytype) ?[]const u8 {
    if (self.manifest_path_len == 0) return null;
    return self.manifest_path_storage[0..self.manifest_path_len];
}

pub fn manifest_hash(self: anytype) ?[]const u8 {
    if (self.manifest_hash_len == 0) return null;
    return self.manifest_hash_storage[0..self.manifest_hash_len];
}

pub fn flush_pending_artifact(self: anytype, spec: ManifestSpec) void {
    if (!self.pending_artifact_write) return;
    self.pending_artifact_write = false;
    const status_code = self.pending_artifact_status_storage[0..self.pending_artifact_status_len];
    if (artifact_state.manifest_signature_matches(
        self.last_manifest_meta,
        self.last_manifest_module_storage[0..self.last_manifest_module_len],
        self.last_manifest_status_storage[0..self.last_manifest_status_len],
        self.pending_artifact_module,
        self.pending_artifact_meta,
        status_code,
    )) return;
    emit_shader_artifact_manifest_for_signature(
        self,
        spec,
        self.pending_artifact_module,
        self.pending_artifact_meta,
        status_code,
    ) catch {};
}

pub fn emit_shader_artifact_manifest_for_signature(
    self: anytype,
    spec: ManifestSpec,
    module: []const u8,
    meta: artifact_meta.ArtifactMeta,
    status_code: []const u8,
) common_errors.BackendNativeError!void {
    self.manifest_emit_count +|= 1;

    var path_buffer: [256]u8 = undefined;
    const path = std.fmt.bufPrint(
        &path_buffer,
        "{s}/{s}_shader_artifact_{d}.json",
        .{ SHADER_ARTIFACT_DIR, spec.file_prefix, self.manifest_emit_count },
    ) catch return common_errors.BackendNativeError.ShaderCompileFailed;

    const toolchain_hash = load_toolchain_sha256(self.allocator) catch return common_errors.BackendNativeError.ShaderCompileFailed;

    var taxonomy_buffer: [TAXONOMY_CODE_CAPACITY]u8 = undefined;
    const taxonomy_code = normalize_taxonomy_code(&taxonomy_buffer, status_code);

    var pipeline_seed_buffer: [HASH_INPUT_CAPACITY]u8 = undefined;
    const pipeline_seed = std.fmt.bufPrint(
        &pipeline_seed_buffer,
        "{s}|{s}|{s}|{s}|{s}|{}",
        .{
            spec.backend_id,
            module,
            taxonomy_code,
            meta.backend_kind.name(),
            meta.timing_source.name(),
            meta.is_claimable(),
        },
    ) catch return common_errors.BackendNativeError.ShaderCompileFailed;

    const pipeline_hash = hash_utils.sha256_hex(pipeline_seed);
    const wgsl_hash = hash_utils.sha256_hex(module);
    const stage_hashes = derive_stage_hashes(self.allocator, spec.stages, wgsl_hash) catch {
        return common_errors.BackendNativeError.ShaderCompileFailed;
    };
    defer self.allocator.free(stage_hashes);

    const stages_json = build_stages_json(self.allocator, spec.stages, wgsl_hash, stage_hashes) catch {
        return common_errors.BackendNativeError.ShaderCompileFailed;
    };
    defer self.allocator.free(stages_json);

    const prehash = build_prehash_json(
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
    ) catch return common_errors.BackendNativeError.ShaderCompileFailed;
    defer self.allocator.free(prehash);

    const hash = hash_utils.sha256_hex(prehash);
    const content = std.fmt.allocPrint(
        self.allocator,
        "{s},\"hash\":\"{s}\"}}\n",
        .{
            prehash[0 .. prehash.len - 1],
            hash[0..],
        },
    ) catch return common_errors.BackendNativeError.ShaderCompileFailed;
    defer self.allocator.free(content);

    std.fs.cwd().makePath(SHADER_ARTIFACT_DIR) catch return common_errors.BackendNativeError.ShaderCompileFailed;
    const file = std.fs.cwd().createFile(path, .{ .truncate = true }) catch return common_errors.BackendNativeError.ShaderCompileFailed;
    defer file.close();
    file.writeAll(content) catch return common_errors.BackendNativeError.ShaderCompileFailed;

    artifact_state.persist_value(self.manifest_path_storage[0..], &self.manifest_path_len, path);
    artifact_state.persist_value(self.manifest_hash_storage[0..], &self.manifest_hash_len, hash[0..]);
    artifact_state.persist_manifest_signature(
        &self.last_manifest_meta,
        self.last_manifest_module_storage[0..],
        &self.last_manifest_module_len,
        self.last_manifest_status_storage[0..],
        &self.last_manifest_status_len,
        module,
        meta,
        status_code,
    );
}

fn previous_manifest_hash(self: anytype) []const u8 {
    return manifest_hash(self) orelse ZERO_HASH;
}

fn derive_stage_hash(seed: []const u8, label: []const u8) [hash_utils.SHA256_HEX_SIZE]u8 {
    var buffer: [HASH_INPUT_CAPACITY]u8 = undefined;
    const input = std.fmt.bufPrint(&buffer, "{s}|{s}", .{ seed, label }) catch label;
    return hash_utils.sha256_hex(input);
}

fn derive_stage_hashes(
    allocator: std.mem.Allocator,
    stages: []const StageDescriptor,
    wgsl_hash: [hash_utils.SHA256_HEX_SIZE]u8,
) ![][hash_utils.SHA256_HEX_SIZE]u8 {
    const hashes = try allocator.alloc([hash_utils.SHA256_HEX_SIZE]u8, stages.len);
    var previous = wgsl_hash;
    for (stages, 0..) |stage, index| {
        hashes[index] = derive_stage_hash(previous[0..], stage.hash_label);
        previous = hashes[index];
    }
    return hashes;
}

fn build_stages_json(
    allocator: std.mem.Allocator,
    stages: []const StageDescriptor,
    wgsl_hash: [hash_utils.SHA256_HEX_SIZE]u8,
    stage_hashes: []const [hash_utils.SHA256_HEX_SIZE]u8,
) ![]u8 {
    var list = try std.ArrayList(u8).initCapacity(allocator, 0);
    errdefer list.deinit(allocator);
    const writer = list.writer(allocator);

    try writer.print(
        "[{{\"stage\":\"wgsl_parse\",\"implementation\":\"native_zig\",\"artifactSha256\":\"{s}\"}}",
        .{wgsl_hash[0..]},
    );
    for (stages, 0..) |stage, index| {
        try writer.print(
            ",{{\"stage\":\"{s}\",\"implementation\":\"native_zig\",\"artifactSha256\":\"{s}\"}}",
            .{ stage.stage, stage_hashes[index][0..] },
        );
    }
    try writer.writeByte(']');
    return list.toOwnedSlice(allocator);
}

fn build_prehash_json(
    allocator: std.mem.Allocator,
    spec: ManifestSpec,
    module: []const u8,
    meta: artifact_meta.ArtifactMeta,
    taxonomy_code: []const u8,
    previous_hash: []const u8,
    toolchain_hash: [hash_utils.SHA256_HEX_SIZE]u8,
    pipeline_hash: [hash_utils.SHA256_HEX_SIZE]u8,
    wgsl_hash: [hash_utils.SHA256_HEX_SIZE]u8,
    stage_hashes: []const [hash_utils.SHA256_HEX_SIZE]u8,
    stages_json: []const u8,
) ![]u8 {
    var list = try std.ArrayList(u8).initCapacity(allocator, 0);
    errdefer list.deinit(allocator);
    const writer = list.writer(allocator);

    _ = meta;
    try writer.print(
        "{{\"schemaVersion\":2,\"backendId\":\"{s}\",\"module\":\"{s}\",\"pipelineHash\":\"{s}\",\"wgslSha256\":\"{s}\"",
        .{ spec.backend_id, module, pipeline_hash[0..], wgsl_hash[0..] },
    );
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

fn load_toolchain_sha256(allocator: std.mem.Allocator) ![hash_utils.SHA256_HEX_SIZE]u8 {
    const bytes = try std.fs.cwd().readFileAlloc(allocator, SHADER_TOOLCHAIN_PATH, MAX_TOOLCHAIN_BYTES);
    defer allocator.free(bytes);
    return hash_utils.sha256_hex(bytes);
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
        const fallback = "error";
        std.mem.copyForwards(u8, buffer[0..fallback.len], fallback);
        return buffer[0..fallback.len];
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
    const wgsl_hash = hash_utils.sha256_hex("module");
    const hashes = try derive_stage_hashes(std.testing.allocator, &stages, wgsl_hash);
    defer std.testing.allocator.free(hashes);

    try std.testing.expectEqual(derive_stage_hash(wgsl_hash[0..], "sema"), hashes[0]);
    try std.testing.expectEqual(derive_stage_hash(hashes[0][0..], "ir_build"), hashes[1]);
}
