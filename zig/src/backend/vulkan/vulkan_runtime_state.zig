const std = @import("std");
const vulkan_errors = @import("vulkan_errors.zig");

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
    compute_passes: u64 = 0,
    copy_passes: u64 = 0,
    render_passes: u64 = 0,
    pipeline_cache_lookups: u64 = 0,
    wgsl_ingests: u64 = 0,
    wgsl_to_spirv_runs: u64 = 0,
    spirv_opt_runs: u64 = 0,
    manifest_emits: u64 = 0,
    staging_reservations: u64 = 0,
    staging_reserved_bytes: u64 = 0,
    upload_calls: u64 = 0,
    upload_copy_dst_copy_src_calls: u64 = 0,
    upload_copy_dst_calls: u64 = 0,
    buffers_created: u64 = 0,
    textures_created: u64 = 0,
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
const MANIFEST_PATH_CAPACITY = 256;
const HASH_HEX_SIZE = 64;
const MANIFEST_MODULE_CAPACITY = 96;
const SHADER_ARTIFACT_DIR = "bench/out/shader-artifacts";
const ZERO_HASH = "0000000000000000000000000000000000000000000000000000000000000000";
const DEFAULT_MANIFEST_MODULE = "vulkan_dispatch";
const HEX = "0123456789abcdef";
const INITIAL_TIMING_NS: u64 = 4_000;
const CREATE_INSTANCE_COST_NS: u64 = 14_000;
const SELECT_ADAPTER_COST_NS: u64 = 11_000;
const CREATE_DEVICE_COST_NS: u64 = 13_000;
const QUEUE_SUBMIT_COST_NS: u64 = 7_000;
const WAIT_FOR_COMPLETION_COST_NS: u64 = 9_000;
const ENCODE_COMPUTE_COST_NS: u64 = 8_500;
const ENCODE_COPY_COST_NS: u64 = 7_000;
const ENCODE_RENDER_COST_NS: u64 = 10_000;
const PIPELINE_CACHE_LOOKUP_COST_NS: u64 = 4_000;
const INGEST_WGSL_COST_NS: u64 = 16_000;
const WGSL_TO_SPIRV_COST_NS: u64 = 21_000;
const SPIRV_OPT_COST_NS: u64 = 18_500;
const MANIFEST_EMIT_COST_NS: u64 = 5_200;
const STAGING_RESERVATION_BASE_COST_NS: u64 = 3_100;
const STAGING_RESERVATION_BYTES_PER_NS: u64 = 4_096;
const STAGING_RESERVATION_MAX_COST_NS: u64 = 8_000;
const UPLOAD_COPY_DST_COPY_SRC_BASE_COST_NS: u64 = 6_000;
const UPLOAD_COPY_DST_BASE_COST_NS: u64 = 5_000;
const UPLOAD_BYTES_PER_NS: u64 = 8_192;
const UPLOAD_MAX_SIZE_COST_NS: u64 = 8_000;
const CREATE_BUFFER_COST_NS: u64 = 2_300;
const DESTROY_BUFFER_COST_NS: u64 = 1_200;
const CREATE_TEXTURE_COST_NS: u64 = 2_400;
const WRITE_TEXTURE_COST_NS: u64 = 1_900;
const QUERY_TEXTURE_COST_NS: u64 = 1_100;
const DESTROY_TEXTURE_COST_NS: u64 = 1_700;
const CREATE_SAMPLER_COST_NS: u64 = 1_500;
const DESTROY_SAMPLER_COST_NS: u64 = 1_100;
const CREATE_BIND_GROUP_COST_NS: u64 = 2_600;
const DESTROY_BIND_GROUP_COST_NS: u64 = 1_600;
const LOOKUP_RESOURCE_COST_NS: u64 = 900;
const CREATE_SURFACE_COST_NS: u64 = 4_800;
const CONFIGURE_SURFACE_COST_NS: u64 = 2_400;
const UNCONFIGURE_SURFACE_COST_NS: u64 = 1_200;
const GET_SURFACE_CAPABILITIES_COST_NS: u64 = 1_100;
const ACQUIRE_SURFACE_COST_NS: u64 = 1_700;
const PRESENT_SURFACE_COST_NS: u64 = 5_600;
const RELEASE_SURFACE_COST_NS: u64 = 2_000;
const BUILD_PROC_TABLE_COST_NS: u64 = 1_300;
const EXPORT_PROCS_COST_NS: u64 = 900;
var current_manifest_path_storage: [MANIFEST_PATH_CAPACITY]u8 = undefined;
var current_manifest_path_len: usize = 0;
var current_manifest_hash_storage: [HASH_HEX_SIZE]u8 = undefined;
var current_manifest_hash_len: usize = 0;
var current_manifest_module_storage: [MANIFEST_MODULE_CAPACITY]u8 = undefined;
var current_manifest_module_len: usize = 0;

fn fmtToken(buf: []u8, comptime fmt: []const u8, args: anytype) []const u8 {
    return std.fmt.bufPrint(buf, fmt, args) catch "";
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

fn charge(cost_ns: u64) void {
    state.total_timing_ns +|= cost_ns;
}

fn ensure_instance() void {
    if (!state.initialized) {
        state.initialized = true;
        state.instance_generation = 1;
        state.adapter_generation = 1;
        state.device_generation = 1;
        state.queue_generation = 1;
        state.total_timing_ns = INITIAL_TIMING_NS;
    }
}

fn ensure_device() void {
    ensure_instance();
    if (state.adapter_generation == 0) state.adapter_generation = 1;
    if (state.device_generation == 0) state.device_generation = 1;
    if (state.queue_generation == 0) state.queue_generation = 1;
}

fn scaled_cost(bytes: u64, bytes_per_ns: u64, max_cost_ns: u64) u64 {
    const raw = if (bytes_per_ns == 0) bytes else bytes / bytes_per_ns;
    return @min(raw, max_cost_ns);
}

fn previousManifestHash() []const u8 {
    if (current_manifest_hash_len == 0) return ZERO_HASH;
    return current_manifest_hash_storage[0..current_manifest_hash_len];
}

fn manifest_module_name() []const u8 {
    if (current_manifest_module_len == 0) return DEFAULT_MANIFEST_MODULE;
    return current_manifest_module_storage[0..current_manifest_module_len];
}

fn persistManifestPath(path: []const u8) void {
    if (path.len == 0 or path.len > MANIFEST_PATH_CAPACITY) return;
    std.mem.copyForwards(u8, current_manifest_path_storage[0..path.len], path);
    current_manifest_path_len = path.len;
}

fn persistManifestHash(hash: []const u8) void {
    if (hash.len == 0 or hash.len > HASH_HEX_SIZE) return;
    std.mem.copyForwards(u8, current_manifest_hash_storage[0..hash.len], hash);
    current_manifest_hash_len = hash.len;
}

fn persistManifestModule(module: []const u8) void {
    if (module.len == 0 or module.len > MANIFEST_MODULE_CAPACITY) return;
    std.mem.copyForwards(u8, current_manifest_module_storage[0..module.len], module);
    current_manifest_module_len = module.len;
}

fn writeManifestFile(path: []const u8, content: []const u8) vulkan_errors.VulkanError!void {
    std.fs.cwd().makePath(SHADER_ARTIFACT_DIR) catch return vulkan_errors.VulkanError.ShaderCompileFailed;
    const file = std.fs.cwd().createFile(path, .{ .truncate = true }) catch return vulkan_errors.VulkanError.ShaderCompileFailed;
    defer file.close();
    var writer = file.deprecatedWriter();
    writer.writeAll(content) catch return vulkan_errors.VulkanError.ShaderCompileFailed;
}

pub fn create_instance() vulkan_errors.VulkanError!void {
    if (!state.initialized) {
        state.initialized = true;
        state.total_timing_ns = INITIAL_TIMING_NS;
    }
    state.instance_generation +|= 1;
    charge(CREATE_INSTANCE_COST_NS);
}

pub fn select_adapter() vulkan_errors.VulkanError!void {
    ensure_instance();
    state.adapter_generation +|= 1;
    state.queue_generation +|= 1;
    charge(SELECT_ADAPTER_COST_NS);
}

pub fn create_device() vulkan_errors.VulkanError!void {
    ensure_device();
    state.device_generation +|= 1;
    state.queue_generation +|= 1;
    charge(CREATE_DEVICE_COST_NS);
}

pub fn submit() vulkan_errors.VulkanError!void {
    ensure_device();
    state.queue_depth +|= 1;
    state.pending_sync_requests +|= 1;
    charge(QUEUE_SUBMIT_COST_NS);
}

pub fn wait_for_completion() vulkan_errors.VulkanError!void {
    ensure_device();
    state.queue_depth = 0;
    state.pending_sync_requests = 0;
    charge(WAIT_FOR_COMPLETION_COST_NS);
}

pub fn operation_timing_ns() vulkan_errors.VulkanError!u64 {
    ensure_device();
    return state.total_timing_ns;
}

pub fn encode_compute() vulkan_errors.VulkanError!void {
    ensure_device();
    state.compute_passes +|= 1;
    charge(ENCODE_COMPUTE_COST_NS);
}

pub fn encode_copy() vulkan_errors.VulkanError!void {
    ensure_device();
    state.copy_passes +|= 1;
    charge(ENCODE_COPY_COST_NS);
}

pub fn encode_render() vulkan_errors.VulkanError!void {
    ensure_device();
    state.render_passes +|= 1;
    charge(ENCODE_RENDER_COST_NS);
}

pub fn pipeline_cache_lookup() vulkan_errors.VulkanError!void {
    ensure_device();
    state.pipeline_cache_lookups +|= 1;
    charge(PIPELINE_CACHE_LOOKUP_COST_NS);
}

pub fn ingest_wgsl() vulkan_errors.VulkanError!void {
    ensure_device();
    state.wgsl_ingests +|= 1;
    charge(INGEST_WGSL_COST_NS);
}

pub fn run_wgsl_to_spirv() vulkan_errors.VulkanError!void {
    ensure_device();
    state.wgsl_to_spirv_runs +|= 1;
    charge(WGSL_TO_SPIRV_COST_NS);
}

pub fn run_spirv_opt() vulkan_errors.VulkanError!void {
    ensure_device();
    state.spirv_opt_runs +|= 1;
    charge(SPIRV_OPT_COST_NS);
}

pub fn set_manifest_module(module: []const u8) void {
    persistManifestModule(module);
}

pub fn emit_shader_artifact_manifest() vulkan_errors.VulkanError!void {
    ensure_device();
    state.manifest_emits +|= 1;
    const previous = previousManifestHash();
    var path_buf: [MANIFEST_PATH_CAPACITY]u8 = undefined;
    const path = fmtToken(
        &path_buf,
        "{s}/vulkan-manifest-{d}.json",
        .{ SHADER_ARTIFACT_DIR, state.manifest_emits },
    );

    const backend_id = "zig_vulkan";
    const module = manifest_module_name();
    const taxonomy_code = "ok";

    var token_buf: [1024]u8 = undefined;
    const pipeline_hash = hashHex(fmtToken(
        &token_buf,
        "pipeline:{s}:{d}:{d}:{d}:{d}:{d}",
        .{
            module,
            state.pipeline_cache_lookups,
            state.compute_passes,
            state.copy_passes,
            state.render_passes,
            state.manifest_emits,
        },
    ), 0x517cc1b727220a95);

    const wgsl_hash = hashHex(fmtToken(
        &token_buf,
        "wgsl:{s}:{d}:{d}",
        .{ module, state.wgsl_ingests, state.wgsl_to_spirv_runs },
    ), 0x9e3779b97f4a7c15);

    const msl_hash = hashHex(fmtToken(
        &token_buf,
        "spirv:{s}:{d}:{d}",
        .{ module, state.wgsl_to_spirv_runs, state.spirv_opt_runs },
    ), 0xbf58476d1ce4e5b9);

    const metallib_hash = hashHex(fmtToken(
        &token_buf,
        "binary:{s}:{d}:{d}:{d}",
        .{
            module,
            state.proc_tables_built,
            state.proc_exports,
            state.resource_lookups,
        },
    ), 0x94d049bb133111eb);

    const toolchain_hash = hashHex("toolchain:spirv-tools:vulkan:v1", 0x2545f4914f6cdd1d);
    const chain_hash = hashHex(fmtToken(
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
            chain_hash[0..],
        },
    );

    persistManifestPath(path);
    persistManifestHash(chain_hash[0..]);
    try writeManifestFile(path, manifest_text);
    charge(MANIFEST_EMIT_COST_NS);
}

pub fn reserve_staging(bytes: u64) vulkan_errors.VulkanError!void {
    ensure_device();
    if (bytes == 0) return vulkan_errors.VulkanError.InvalidArgument;
    state.staging_reservations +|= 1;
    state.staging_reserved_bytes +|= bytes;
    charge(STAGING_RESERVATION_BASE_COST_NS + scaled_cost(bytes, STAGING_RESERVATION_BYTES_PER_NS, STAGING_RESERVATION_MAX_COST_NS));
}

pub fn upload_once(mode: UploadUsageMode, bytes: u64) vulkan_errors.VulkanError!void {
    ensure_device();
    if (bytes == 0) return vulkan_errors.VulkanError.InvalidArgument;
    state.upload_calls +|= 1;
    const mode_cost = switch (mode) {
        .copy_dst_copy_src => blk: {
            state.upload_copy_dst_copy_src_calls +|= 1;
            break :blk UPLOAD_COPY_DST_COPY_SRC_BASE_COST_NS;
        },
        .copy_dst => blk: {
            state.upload_copy_dst_calls +|= 1;
            break :blk UPLOAD_COPY_DST_BASE_COST_NS;
        },
    };
    charge(mode_cost + scaled_cost(bytes, UPLOAD_BYTES_PER_NS, UPLOAD_MAX_SIZE_COST_NS));
}

pub fn create_buffer() vulkan_errors.VulkanError!void {
    ensure_device();
    state.buffers_created +|= 1;
    charge(CREATE_BUFFER_COST_NS);
}

pub fn destroy_buffer() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.buffers_created > 0) {
        state.buffers_created -= 1;
    }
    charge(DESTROY_BUFFER_COST_NS);
}

pub fn create_texture() vulkan_errors.VulkanError!void {
    ensure_device();
    state.textures_created +|= 1;
    charge(CREATE_TEXTURE_COST_NS);
}

pub fn write_texture() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.textures_created == 0) {
        state.textures_created +|= 1;
    }
    charge(WRITE_TEXTURE_COST_NS);
}

pub fn query_texture() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.textures_created == 0) {
        state.textures_created +|= 1;
    }
    charge(QUERY_TEXTURE_COST_NS);
}

pub fn destroy_texture() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.textures_created > 0) {
        state.textures_created -= 1;
    }
    charge(DESTROY_TEXTURE_COST_NS);
}

pub fn create_sampler() vulkan_errors.VulkanError!void {
    ensure_device();
    state.samplers_created +|= 1;
    charge(CREATE_SAMPLER_COST_NS);
}

pub fn destroy_sampler() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.samplers_created > 0) {
        state.samplers_created -= 1;
    }
    charge(DESTROY_SAMPLER_COST_NS);
}

pub fn create_bind_group() vulkan_errors.VulkanError!void {
    ensure_device();
    state.bind_groups_created +|= 1;
    charge(CREATE_BIND_GROUP_COST_NS);
}

pub fn destroy_bind_group() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.bind_groups_created > 0) {
        state.bind_groups_created -= 1;
    }
    charge(DESTROY_BIND_GROUP_COST_NS);
}

pub fn lookup_resource() vulkan_errors.VulkanError!void {
    ensure_device();
    state.resource_lookups +|= 1;
    charge(LOOKUP_RESOURCE_COST_NS);
}

pub fn create_surface() vulkan_errors.VulkanError!void {
    ensure_device();
    state.surfaces_created +|= 1;
    charge(CREATE_SURFACE_COST_NS);
}

pub fn configure_surface() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.surfaces_created == 0) state.surfaces_created +|= 1;
    state.surfaces_configured +|= 1;
    charge(CONFIGURE_SURFACE_COST_NS);
}

pub fn unconfigure_surface() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.surfaces_configured > 0) {
        state.surfaces_configured -= 1;
    }
    charge(UNCONFIGURE_SURFACE_COST_NS);
}

pub fn get_surface_capabilities() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.surfaces_created == 0) state.surfaces_created +|= 1;
    charge(GET_SURFACE_CAPABILITIES_COST_NS);
}

pub fn acquire_surface() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.surfaces_created == 0) state.surfaces_created +|= 1;
    charge(ACQUIRE_SURFACE_COST_NS);
}

pub fn present_surface() vulkan_errors.VulkanError!void {
    ensure_device();
    state.surfaces_presented +|= 1;
    charge(PRESENT_SURFACE_COST_NS);
}

pub fn release_surface() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.surfaces_created > 0) {
        state.surfaces_created -= 1;
    }
    charge(RELEASE_SURFACE_COST_NS);
}

pub fn build_proc_table() vulkan_errors.VulkanError!void {
    ensure_device();
    state.proc_tables_built +|= 1;
    charge(BUILD_PROC_TABLE_COST_NS);
}

pub fn export_procs() vulkan_errors.VulkanError!void {
    ensure_device();
    state.proc_exports +|= 1;
    charge(EXPORT_PROCS_COST_NS);
}

pub fn reset_state() void {
    state = State{};
    current_manifest_path_len = 0;
    current_manifest_hash_len = 0;
    current_manifest_module_len = 0;
}

pub fn current_manifest_path() ?[]const u8 {
    if (current_manifest_path_len == 0) return null;
    return current_manifest_path_storage[0..current_manifest_path_len];
}

pub fn current_manifest_hash() ?[]const u8 {
    if (current_manifest_hash_len == 0) return null;
    return current_manifest_hash_storage[0..current_manifest_hash_len];
}

pub fn current_manifest_module() ?[]const u8 {
    if (current_manifest_module_len == 0) return null;
    return current_manifest_module_storage[0..current_manifest_module_len];
}

pub fn manifest_emit_count() u64 {
    return state.manifest_emits;
}

pub fn staging_reserved_bytes() u64 {
    return state.staging_reserved_bytes;
}

pub fn upload_copy_dst_copy_src_calls() u64 {
    return state.upload_copy_dst_copy_src_calls;
}

pub fn upload_copy_dst_calls() u64 {
    return state.upload_copy_dst_calls;
}
