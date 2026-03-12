const std = @import("std");
const artifact_meta = @import("../common/artifact_meta.zig");
const artifact_state = @import("../common/artifact_state.zig");
const common_errors = @import("../common/errors.zig");
const hash_utils = @import("../common/hash_utils.zig");

const SHADER_ARTIFACT_DIR = "bench/out/shader-artifacts";
const SHADER_TOOLCHAIN_PATH = "config/shader-toolchain.json";
const MAX_TOOLCHAIN_BYTES: usize = 64 * 1024;
const HASH_INPUT_CAPACITY: usize = 512;
const STAGES_JSON_CAPACITY: usize = 1024;
const MANIFEST_CONTENT_CAPACITY: usize = 4096;
const TAXONOMY_CODE_CAPACITY: usize = 128;
const ZERO_HASH = "0000000000000000000000000000000000000000000000000000000000000000";

pub fn manifest_path(self: anytype) ?[]const u8 {
    if (self.manifest_path_len == 0) return null;
    return self.manifest_path_storage[0..self.manifest_path_len];
}

pub fn manifest_hash(self: anytype) ?[]const u8 {
    if (self.manifest_hash_len == 0) return null;
    return self.manifest_hash_storage[0..self.manifest_hash_len];
}

pub fn flush_pending_artifact(self: anytype) void {
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
    emit_shader_artifact_manifest_for_signature(self, self.pending_artifact_module, self.pending_artifact_meta, status_code) catch {};
}

pub fn emit_shader_artifact_manifest_for_signature(
    self: anytype,
    module: []const u8,
    meta: artifact_meta.ArtifactMeta,
    status_code: []const u8,
) common_errors.BackendNativeError!void {
    self.manifest_emit_count +|= 1;

    var path_buffer: [256]u8 = undefined;
    const path = std.fmt.bufPrint(
        &path_buffer,
        "{s}/vulkan_shader_artifact_{d}.json",
        .{ SHADER_ARTIFACT_DIR, self.manifest_emit_count },
    ) catch return common_errors.BackendNativeError.ShaderCompileFailed;

    const toolchain_hash = load_toolchain_sha256(self.allocator) catch return common_errors.BackendNativeError.ShaderCompileFailed;

    var taxonomy_buffer: [TAXONOMY_CODE_CAPACITY]u8 = undefined;
    const taxonomy_code = normalize_taxonomy_code(&taxonomy_buffer, status_code);

    var pipeline_seed_buffer: [HASH_INPUT_CAPACITY]u8 = undefined;
    const pipeline_seed = std.fmt.bufPrint(
        &pipeline_seed_buffer,
        "doe_vulkan|{s}|{s}|{s}|{s}|{}",
        .{
            module,
            taxonomy_code,
            meta.backend_kind.name(),
            meta.timing_source.name(),
            meta.is_claimable(),
        },
    ) catch return common_errors.BackendNativeError.ShaderCompileFailed;

    const pipeline_hash = hash_utils.sha256_hex(pipeline_seed);
    const wgsl_hash = hash_utils.sha256_hex(module);
    const sema_hash = derive_stage_hash(wgsl_hash[0..], "sema");
    const ir_hash = derive_stage_hash(sema_hash[0..], "ir_build");
    const ir_validate_hash = derive_stage_hash(ir_hash[0..], "ir_validate");
    const spirv_hash = derive_stage_hash(ir_validate_hash[0..], "ir_to_spirv");

    var stages_buffer: [STAGES_JSON_CAPACITY]u8 = undefined;
    const stages_json = std.fmt.bufPrint(
        &stages_buffer,
        "[{{\"stage\":\"wgsl_parse\",\"implementation\":\"native_zig\",\"artifactSha256\":\"{s}\"}},{{\"stage\":\"sema\",\"implementation\":\"native_zig\",\"artifactSha256\":\"{s}\"}},{{\"stage\":\"ir_build\",\"implementation\":\"native_zig\",\"artifactSha256\":\"{s}\"}},{{\"stage\":\"ir_validate\",\"implementation\":\"native_zig\",\"artifactSha256\":\"{s}\"}},{{\"stage\":\"ir_to_spirv\",\"implementation\":\"native_zig\",\"artifactSha256\":\"{s}\"}}]",
        .{
            wgsl_hash[0..],
            sema_hash[0..],
            ir_hash[0..],
            ir_validate_hash[0..],
            spirv_hash[0..],
        },
    ) catch return common_errors.BackendNativeError.ShaderCompileFailed;

    var prehash_buffer: [MANIFEST_CONTENT_CAPACITY]u8 = undefined;
    const prehash = std.fmt.bufPrint(
        &prehash_buffer,
        "{{\"schemaVersion\":2,\"backendId\":\"doe_vulkan\",\"module\":\"{s}\",\"pipelineHash\":\"{s}\",\"wgslSha256\":\"{s}\",\"irSha256\":\"{s}\",\"spirvSha256\":\"{s}\",\"toolchainSha256\":\"{s}\",\"taxonomyCode\":\"{s}\",\"previousHash\":\"{s}\",\"stages\":{s}}}",
        .{
            module,
            pipeline_hash[0..],
            wgsl_hash[0..],
            ir_hash[0..],
            spirv_hash[0..],
            toolchain_hash[0..],
            taxonomy_code,
            previous_manifest_hash(self),
            stages_json,
        },
    ) catch return common_errors.BackendNativeError.ShaderCompileFailed;

    const hash = hash_utils.sha256_hex(prehash);

    var content_buffer: [MANIFEST_CONTENT_CAPACITY]u8 = undefined;
    const content = std.fmt.bufPrint(
        &content_buffer,
        "{s},\"hash\":\"{s}\"}}\n",
        .{
            prehash[0 .. prehash.len - 1],
            hash[0..],
        },
    ) catch return common_errors.BackendNativeError.ShaderCompileFailed;

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
