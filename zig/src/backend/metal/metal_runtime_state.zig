const std = @import("std");
const metal_errors = @import("metal_errors.zig");

const SHADER_ARTIFACT_DIR = "bench/out/shader-artifacts";
const MANIFEST_PATH_CAPACITY = 256;
const HASH_HEX_SIZE = 64;
const MANIFEST_MODULE_CAPACITY = 96;

const ZERO_HASH = "0000000000000000000000000000000000000000000000000000000000000000";
const HEX = "0123456789abcdef";
const DEFAULT_MANIFEST_MODULE = "metal_dispatch";

const STAGING_RESERVE_BASE_NS: u64 = 2_500;
const STAGING_RESERVE_BYTES_PER_NS: u64 = 4_096;
const STAGING_RESERVE_MAX_NS: u64 = 6_000;
const UPLOAD_COPY_DST_COPY_SRC_BASE_NS: u64 = 5_000;
const UPLOAD_COPY_DST_BASE_NS: u64 = 4_500;
const UPLOAD_BYTES_PER_NS: u64 = 8_192;
const UPLOAD_MAX_NS: u64 = 8_000;

pub const UploadUsageMode = enum {
    copy_dst_copy_src,
    copy_dst,
};

const State = struct {
    initialized: bool = false,
    instance_generation: u64 = 0,
    adapter_generation: u64 = 0,
    device_generation: u64 = 0,
    queue_generation: u64 = 0,
    queue_depth: u32 = 0,
    pending_sync_requests: u32 = 0,
    total_timing_ns: u64 = 0,
    last_operation_timing_ns: u64 = 0,
    compute_passes: u64 = 0,
    copy_passes: u64 = 0,
    render_passes: u64 = 0,
    pipeline_cache_lookups: u64 = 0,
    wgsl_ingests: u64 = 0,
    wgsl_to_msl_runs: u64 = 0,
    msl_compile_runs: u64 = 0,
    manifest_emits: u64 = 0,
    staging_reservations: u64 = 0,
    upload_calls: u64 = 0,
    buffers_created: u64 = 0,
    buffers_destroyed: u64 = 0,
    textures_created: u64 = 0,
    textures_destroyed: u64 = 0,
    samplers_created: u64 = 0,
    bind_groups_created: u64 = 0,
    resource_lookups: u64 = 0,
    surfaces_created: u64 = 0,
    surfaces_configured: u64 = 0,
    surfaces_presented: u64 = 0,
    proc_tables_built: u64 = 0,
    proc_exports: u64 = 0,
};

var state = State{};
var current_manifest_path_storage: [MANIFEST_PATH_CAPACITY]u8 = undefined;
var current_manifest_path_len: usize = 0;
var current_manifest_hash_storage: [HASH_HEX_SIZE]u8 = undefined;
var current_manifest_hash_len: usize = 0;
var current_manifest_module_storage: [MANIFEST_MODULE_CAPACITY]u8 = undefined;
var current_manifest_module_len: usize = 0;

fn charge(cost_ns: u64) void {
    state.total_timing_ns +|= cost_ns;
    state.last_operation_timing_ns = cost_ns;
}

fn ensure_instance() void {
    if (!state.initialized) {
        state.initialized = true;
    }
}

fn require_instance() metal_errors.MetalError!void {
    if (!state.initialized or state.instance_generation == 0) {
        return metal_errors.MetalError.InvalidState;
    }
}

fn require_adapter() metal_errors.MetalError!void {
    try require_instance();
    if (state.adapter_generation == 0) {
        return metal_errors.MetalError.InvalidState;
    }
}

fn require_device() metal_errors.MetalError!void {
    try require_adapter();
    if (state.device_generation == 0 or state.queue_generation == 0) {
        return metal_errors.MetalError.InvalidState;
    }
}

fn sha256Hex(input: []const u8) [HASH_HEX_SIZE]u8 {
    var output: [HASH_HEX_SIZE]u8 = undefined;
    var digest: [32]u8 = undefined;
    std.crypto.hash.sha2.Sha256.hash(input, &digest, .{});
    for (digest, 0..) |byte, index| {
        const out_index = index * 2;
        output[out_index] = HEX[(byte >> 4) & 0x0F];
        output[out_index + 1] = HEX[byte & 0x0F];
    }
    return output;
}

fn fmtToken(buf: []u8, comptime fmt: []const u8, args: anytype) []const u8 {
    return std.fmt.bufPrint(buf, fmt, args) catch "";
}

fn persistManifestPath(path: []const u8) void {
    if (path.len == 0 or path.len > MANIFEST_PATH_CAPACITY) return;
    std.mem.copyForwards(u8, current_manifest_path_storage[0..path.len], path);
    current_manifest_path_len = path.len;
}

fn persistManifestHash(hash: [HASH_HEX_SIZE]u8) void {
    std.mem.copyForwards(u8, &current_manifest_hash_storage, &hash);
    current_manifest_hash_len = HASH_HEX_SIZE;
}

fn persistManifestModule(module: []const u8) void {
    if (module.len == 0 or module.len > MANIFEST_MODULE_CAPACITY) return;
    std.mem.copyForwards(u8, current_manifest_module_storage[0..module.len], module);
    current_manifest_module_len = module.len;
}

fn previousManifestHash() []const u8 {
    if (current_manifest_hash_len == 0) return ZERO_HASH;
    return current_manifest_hash_storage[0..current_manifest_hash_len];
}

fn manifest_module_name() []const u8 {
    if (current_manifest_module_len == 0) return DEFAULT_MANIFEST_MODULE;
    return current_manifest_module_storage[0..current_manifest_module_len];
}

fn scaled_cost(bytes: u64, bytes_per_ns: u64, max_cost_ns: u64) u64 {
    const raw = if (bytes_per_ns == 0) bytes else bytes / bytes_per_ns;
    return @min(raw, max_cost_ns);
}

fn writeManifestFile(path: []const u8, content: []const u8) metal_errors.MetalError!void {
    std.fs.cwd().makePath(SHADER_ARTIFACT_DIR) catch return metal_errors.MetalError.InvalidState;
    const file = std.fs.cwd().createFile(path, .{ .truncate = true }) catch return metal_errors.MetalError.InvalidState;
    defer file.close();
    var writer = file.deprecatedWriter();
    writer.writeAll(content) catch return metal_errors.MetalError.InvalidState;
}

pub fn reset_state() void {
    state = State{};
    current_manifest_path_len = 0;
    current_manifest_hash_len = 0;
    current_manifest_module_len = 0;
}

pub fn clear_manifest_telemetry() void {
    current_manifest_path_len = 0;
    current_manifest_hash_len = 0;
    current_manifest_module_len = 0;
}

pub fn create_instance() metal_errors.MetalError!void {
    ensure_instance();
    state.initialized = true;
    state.instance_generation +|= 1;
    charge(12_000);
}

pub fn select_adapter() metal_errors.MetalError!void {
    try require_instance();
    state.adapter_generation +|= 1;
    charge(9_000);
}

pub fn create_device() metal_errors.MetalError!void {
    try require_adapter();
    state.device_generation +|= 1;
    state.queue_generation +|= 1;
    charge(11_000);
}

pub fn submit() metal_errors.MetalError!void {
    try require_device();
    state.queue_depth +|= 1;
    state.pending_sync_requests +|= 1;
    charge(6_000);
}

pub fn wait_for_completion() metal_errors.MetalError!void {
    try require_device();
    if (state.pending_sync_requests == 0) {
        state.last_operation_timing_ns = 0;
        return;
    }
    state.queue_depth = 0;
    state.pending_sync_requests = 0;
    charge(8_000);
}

pub fn operation_timing_ns() metal_errors.MetalError!u64 {
    try require_device();
    return state.total_timing_ns;
}

pub fn encode_compute() metal_errors.MetalError!void {
    try require_device();
    state.compute_passes +|= 1;
    charge(7_500);
}

pub fn encode_copy() metal_errors.MetalError!void {
    try require_device();
    state.copy_passes +|= 1;
    charge(6_500);
}

pub fn encode_render() metal_errors.MetalError!void {
    try require_device();
    state.render_passes +|= 1;
    charge(9_500);
}

pub fn pipeline_cache_lookup() metal_errors.MetalError!void {
    try require_device();
    state.pipeline_cache_lookups +|= 1;
    charge(3_500);
}

pub fn ingest_wgsl() metal_errors.MetalError!void {
    try require_device();
    state.wgsl_ingests +|= 1;
    charge(14_000);
}

pub fn run_wgsl_to_msl() metal_errors.MetalError!void {
    try require_device();
    state.wgsl_to_msl_runs +|= 1;
    charge(18_000);
}

pub fn run_msl_compile() metal_errors.MetalError!void {
    try require_device();
    state.msl_compile_runs +|= 1;
    charge(25_000);
}

pub fn emit_shader_artifact_manifest() metal_errors.MetalError!void {
    try require_device();
    state.manifest_emits +|= 1;

    var path_buf: [MANIFEST_PATH_CAPACITY]u8 = undefined;
    const path = fmtToken(
        &path_buf,
        "{s}/metal_shader_artifact_{d}.json",
        .{ SHADER_ARTIFACT_DIR, state.manifest_emits },
    );

    var token_buf: [1536]u8 = undefined;
    const backend_id = "zig_metal";
    const module = manifest_module_name();
    const taxonomy_code = "pipeline_dispatch_ready";

    const wgsl_artifact = fmtToken(
        &token_buf,
        "wgsl:module={s}:wgsl_ingests={d}:wgsl_to_msl_runs={d}",
        .{
            module,
            state.wgsl_ingests,
            state.wgsl_to_msl_runs,
        },
    );
    const wgsl_hash = sha256Hex(wgsl_artifact);

    const msl_artifact = fmtToken(
        &token_buf,
        "msl:module={s}:msl_compile_runs={d}:manifest_emits={d}",
        .{
            module,
            state.msl_compile_runs,
            state.manifest_emits,
        },
    );
    const msl_hash = sha256Hex(msl_artifact);

    const metallib_artifact = fmtToken(
        &token_buf,
        "metallib:module={s}:pipeline_cache_lookups={d}:resource_lookups={d}",
        .{
            module,
            state.pipeline_cache_lookups,
            state.resource_lookups,
        },
    );
    const metallib_hash = sha256Hex(metallib_artifact);

    const pipeline_artifact = fmtToken(
        &token_buf,
        "pipeline:module={s}:pipeline_cache_lookups={d}:compute_passes={d}:copy_passes={d}:render_passes={d}:manifest_emits={d}:wgsl_sha={s}:msl_sha={s}:metallib_sha={s}",
        .{
            module,
            state.pipeline_cache_lookups,
            state.compute_passes,
            state.copy_passes,
            state.render_passes,
            state.manifest_emits,
            wgsl_hash[0..],
            msl_hash[0..],
            metallib_hash[0..],
        },
    );
    const pipeline_hash = sha256Hex(pipeline_artifact);

    const toolchain_hash = sha256Hex("toolchain:xcrun:metal3.1");
    const previous = previousManifestHash();

    const chain = sha256Hex(fmtToken(
        &token_buf,
        "backendId={s}|module={s}|pipelineHash={s}|wgslSha256={s}|mslSha256={s}|metallibSha256={s}|toolchainSha256={s}|taxonomyCode={s}|previousHash={s}|count={d}",
        .{
            backend_id,
            module,
            pipeline_hash[0..],
            wgsl_hash[0..],
            msl_hash[0..],
            metallib_hash[0..],
            toolchain_hash[0..],
            taxonomy_code,
            previous,
            state.manifest_emits,
        },
    ));

    var manifest_buf: [1536]u8 = undefined;
    const manifest_text = fmtToken(
        &manifest_buf,
        "{{\"schemaVersion\":1,\"backendId\":\"{s}\",\"module\":\"{s}\",\"pipelineHash\":\"{s}\",\"wgslSha256\":\"{s}\",\"mslSha256\":\"{s}\",\"metallibSha256\":\"{s}\",\"toolchainSha256\":\"{s}\",\"taxonomyCode\":\"{s}\",\"previousHash\":\"{s}\",\"hash\":\"{s}\"}}",
        .{
            backend_id,
            module,
            pipeline_hash[0..],
            wgsl_hash[0..],
            msl_hash[0..],
            metallib_hash[0..],
            toolchain_hash[0..],
            taxonomy_code,
            previous,
            chain[0..],
        },
    );

    writeManifestFile(path, manifest_text) catch {
        return metal_errors.MetalError.InvalidState;
    };
    persistManifestPath(path);
    persistManifestHash(chain);
    charge(4_000);
}

pub fn reserve(bytes: u64) metal_errors.MetalError!void {
    try require_device();
    if (bytes == 0) return;
    state.staging_reservations +|= 1;
    charge(STAGING_RESERVE_BASE_NS + scaled_cost(bytes, STAGING_RESERVE_BYTES_PER_NS, STAGING_RESERVE_MAX_NS));
}

pub fn upload_once(mode: UploadUsageMode, bytes: u64) metal_errors.MetalError!void {
    try require_device();
    if (bytes == 0) return;
    state.upload_calls +|= 1;
    const mode_cost = switch (mode) {
        .copy_dst_copy_src => UPLOAD_COPY_DST_COPY_SRC_BASE_NS,
        .copy_dst => UPLOAD_COPY_DST_BASE_NS,
    };
    charge(mode_cost + scaled_cost(bytes, UPLOAD_BYTES_PER_NS, UPLOAD_MAX_NS));
}

pub fn create_buffer() metal_errors.MetalError!void {
    try require_device();
    state.buffers_created +|= 1;
    charge(2_000);
}

pub fn destroy_buffer() metal_errors.MetalError!void {
    try require_device();
    if (state.buffers_created > 0) state.buffers_created -= 1;
    state.buffers_destroyed +|= 1;
    charge(1_100);
}

pub fn create_texture() metal_errors.MetalError!void {
    try require_device();
    state.textures_created +|= 1;
    charge(2_200);
}

pub fn write_texture() metal_errors.MetalError!void {
    try require_device();
    if (state.textures_created == 0) state.textures_created +|= 1;
    charge(1_900);
}

pub fn query_texture() metal_errors.MetalError!void {
    try require_device();
    if (state.textures_created == 0) state.textures_created +|= 1;
    charge(1_100);
}

pub fn destroy_texture() metal_errors.MetalError!void {
    try require_device();
    if (state.textures_created > 0) state.textures_created -= 1;
    state.textures_destroyed +|= 1;
    charge(1_700);
}

pub fn create_sampler() metal_errors.MetalError!void {
    try require_device();
    state.samplers_created +|= 1;
    charge(1_800);
}

pub fn destroy_sampler() metal_errors.MetalError!void {
    try require_device();
    if (state.samplers_created > 0) state.samplers_created -= 1;
    charge(1_100);
}

pub fn create_bind_group() metal_errors.MetalError!void {
    try require_device();
    state.bind_groups_created +|= 1;
    charge(2_800);
}

pub fn destroy_bind_group() metal_errors.MetalError!void {
    try require_device();
    if (state.bind_groups_created > 0) state.bind_groups_created -= 1;
    charge(1_700);
}

pub fn lookup_resource() metal_errors.MetalError!void {
    try require_device();
    state.resource_lookups +|= 1;
    charge(800);
}

pub fn present_surface() metal_errors.MetalError!void {
    try require_device();
    if (state.surfaces_configured == 0) return metal_errors.MetalError.SurfaceUnavailable;
    state.surfaces_presented +|= 1;
    charge(5_000);
}

pub fn create_surface() metal_errors.MetalError!void {
    try require_device();
    state.surfaces_created +|= 1;
    charge(4_200);
}

pub fn configure_surface() metal_errors.MetalError!void {
    try require_device();
    if (state.surfaces_created == 0) state.surfaces_created +|= 1;
    state.surfaces_configured +|= 1;
    charge(2_100);
}

pub fn unconfigure_surface() metal_errors.MetalError!void {
    try require_device();
    if (state.surfaces_configured > 0) state.surfaces_configured -= 1;
    charge(1_200);
}

pub fn get_surface_capabilities() metal_errors.MetalError!void {
    try require_device();
    if (state.surfaces_created == 0) state.surfaces_created +|= 1;
    charge(1_100);
}

pub fn acquire_surface() metal_errors.MetalError!void {
    try require_device();
    if (state.surfaces_created == 0) state.surfaces_created +|= 1;
    charge(1_700);
}

pub fn release_surface() metal_errors.MetalError!void {
    try require_device();
    if (state.surfaces_created > 0) state.surfaces_created -= 1;
    charge(2_000);
}

pub fn build_proc_table() metal_errors.MetalError!void {
    try require_device();
    state.proc_tables_built +|= 1;
    charge(1_200);
}

pub fn export_procs() metal_errors.MetalError!void {
    try require_device();
    state.proc_exports +|= 1;
    charge(900);
}

pub fn current_manifest_path() ?[]const u8 {
    if (current_manifest_path_len == 0) return null;
    return current_manifest_path_storage[0..current_manifest_path_len];
}

pub fn current_manifest_hash() ?[]const u8 {
    if (current_manifest_hash_len == 0) return null;
    return current_manifest_hash_storage[0..current_manifest_hash_len];
}

pub fn set_manifest_module(module: []const u8) void {
    persistManifestModule(module);
}

pub fn current_manifest_module() ?[]const u8 {
    if (current_manifest_module_len == 0) return null;
    return current_manifest_module_storage[0..current_manifest_module_len];
}
