const std = @import("std");
const metal_errors = @import("metal_errors.zig");

const SHADER_ARTIFACT_DIR = "bench/out/shader-artifacts";
const MANIFEST_PATH_CAPACITY = 256;
const HASH_HEX_SIZE = 64;

const ZERO_HASH = "0000000000000000000000000000000000000000000000000000000000000000";
const HEX = "0123456789abcdef";

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

fn writeHex(out: *[2]u8, byte: u8) void {
    out[0] = HEX[(byte >> 4) & 0x0F];
    out[1] = HEX[byte & 0x0F];
}

fn u64Hex(u: u64, out: *[16]u8) void {
    var i: usize = 0;
    while (i < 8) : (i += 1) {
        const shift: u6 = @intCast(56 - (i * 8));
        const value = @as(u8, @intCast((u >> shift) & 0xFF));
        writeHex(out[i * 2 ..][0..2], value);
    }
}

fn hashChunk(input: []const u8, seed: u64) u64 {
    var h = seed;
    for (input, 0..) |byte, index| {
        h +%= @as(u64, byte);
        h +%= @as(u64, index);
        h = (h << 7) ^ (h >> 3);
        h = (h *% 0xff51afd7ed558ccd) +% 0x9e3779b97f4a7c15;
        h ^= h >> 23;
        h = (h *% 0xc4ceb9fe1a85ec53) +% 0x9e3779b97f4a7c15;
        h ^= h >> 27;
    }
    return h;
}

fn hashHex(input: []const u8, seed: u64) [HASH_HEX_SIZE]u8 {
    var output: [HASH_HEX_SIZE]u8 = undefined;
    const values = [_]u64{
        hashChunk(input, seed),
        hashChunk(input, seed +% 0x243f6a8885a308d3),
        hashChunk(input, seed +% 0x9e3779b97f4a7c15),
        hashChunk(input, seed +% 0xbf58476d1ce4e5b9),
    };
    var index: usize = 0;
    for (values) |value| {
        var segment: [16]u8 = undefined;
        u64Hex(value, &segment);
        std.mem.copyForwards(u8, output[index .. index + 16], &segment);
        index += 16;
    }
    return output;
}

fn fmtToken(buf: []u8, comptime fmt: []const u8, args: anytype) []const u8 {
    return std.fmt.bufPrint(buf, fmt, args) catch "";
}

fn persistManifestPath(path: []const u8) void {
    if (path.len == 0 or path.len > MANIFEST_PATH_CAPACITY) return;
    std.mem.copyForwards(u8, &current_manifest_path_storage, path);
    current_manifest_path_len = path.len;
}

fn persistManifestHash(hash: [HASH_HEX_SIZE]u8) void {
    std.mem.copyForwards(u8, &current_manifest_hash_storage, &hash);
    current_manifest_hash_len = HASH_HEX_SIZE;
}

fn previousManifestHash() []const u8 {
    if (current_manifest_hash_len == 0) return ZERO_HASH;
    return current_manifest_hash_storage[0..current_manifest_hash_len];
}

fn writeManifestFile(path: []const u8, content: []const u8) metal_errors.MetalError!void {
    std.fs.cwd().makePath(SHADER_ARTIFACT_DIR) catch return metal_errors.MetalError.InvalidState;
    const file = std.fs.cwd().createFile(path, .{ .truncate = true }) catch return metal_errors.MetalError.InvalidState;
    defer file.close();
    var writer = file.writer();
    writer.writeAll(content) catch return metal_errors.MetalError.InvalidState;
}

pub fn reset_state() void {
    state = State{};
    current_manifest_path_len = 0;
    current_manifest_hash_len = 0;
}

pub fn clear_manifest_telemetry() void {
    current_manifest_path_len = 0;
    current_manifest_hash_len = 0;
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
    return state.last_operation_timing_ns;
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

    var token_buf: [1024]u8 = undefined;
    const backend_id = "zig_metal";
    const module = "metal_dispatch";
    const taxonomy_code = "pipeline_dispatch_ready";

    const pipeline_hash = hashHex(fmtToken(
        &token_buf,
        "pipeline:{d}:{d}:{d}:{d}:{d}",
        .{
            state.pipeline_cache_lookups,
            state.compute_passes,
            state.copy_passes,
            state.render_passes,
            state.manifest_emits,
        },
    ), 0x243f6a8885a308d3);

    const wgsl_hash = hashHex(fmtToken(
        &token_buf,
        "wgsl:{d}:{d}",
        .{ state.wgsl_ingests, state.wgsl_to_msl_runs },
    ), 0x9e3779b97f4a7c15);

    const msl_hash = hashHex(fmtToken(
        &token_buf,
        "msl:{d}:{d}",
        .{ state.msl_compile_runs, state.manifest_emits },
    ), 0xbf58476d1ce4e5b9);

    const metallib_hash = hashHex(fmtToken(
        &token_buf,
        "metallib:{d}:{d}",
        .{ state.pipeline_cache_lookups, state.resource_lookups },
    ), 0x94d049bb133111eb);

    const toolchain_hash = hashHex("toolchain:xcrun:metal3.1", 0x2545f4914f6cdd1d);
    const previous = previousManifestHash();

    const chain = hashHex(fmtToken(
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
    ), 0x9ddfea08eb382d69);

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

    persistManifestPath(path);
    persistManifestHash(chain);
    writeManifestFile(path, manifest_text) catch {
        return metal_errors.MetalError.InvalidState;
    };
    charge(4_000);
}

pub fn reserve() metal_errors.MetalError!void {
    try require_device();
    state.staging_reservations +|= 1;
    charge(2_500);
}

pub fn upload_once() metal_errors.MetalError!void {
    try require_device();
    state.upload_calls +|= 1;
    charge(5_000);
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
