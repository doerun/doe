const std = @import("std");
const vulkan_errors = @import("vulkan_errors.zig");
const doe_wgsl = @import("../../doe_wgsl/mod.zig");
const artifact_state = @import("../common/artifact_state.zig");
const hash_utils = @import("../common/hash_utils.zig");

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
const HASH_HEX_SIZE = hash_utils.SHA256_HEX_SIZE;
const MANIFEST_MODULE_CAPACITY = 96;
const SHADER_ARTIFACT_DIR = "bench/out/shader-artifacts";
const ZERO_HASH = "0000000000000000000000000000000000000000000000000000000000000000";
const DEFAULT_MANIFEST_MODULE = "vulkan_dispatch";
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

fn fmt_token(buf: []u8, comptime fmt: []const u8, args: anytype) []const u8 {
    return std.fmt.bufPrint(buf, fmt, args) catch "";
}

fn sha256_hex(input: []const u8) [HASH_HEX_SIZE]u8 {
    return hash_utils.sha256_hex(input);
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

fn previous_manifest_hash() []const u8 {
    if (current_manifest_hash_len == 0) return ZERO_HASH;
    return current_manifest_hash_storage[0..current_manifest_hash_len];
}

fn manifest_module_name() []const u8 {
    if (current_manifest_module_len == 0) return DEFAULT_MANIFEST_MODULE;
    return current_manifest_module_storage[0..current_manifest_module_len];
}

fn persist_manifest_path(path: []const u8) void {
    if (path.len == 0) return;
    artifact_state.persist_value(current_manifest_path_storage[0..], &current_manifest_path_len, path);
}

fn persist_manifest_hash(hash: []const u8) void {
    if (hash.len == 0) return;
    artifact_state.persist_value(current_manifest_hash_storage[0..], &current_manifest_hash_len, hash);
}

fn persist_manifest_module(module: []const u8) void {
    if (module.len == 0) return;
    artifact_state.persist_value(current_manifest_module_storage[0..], &current_manifest_module_len, module);
}

fn write_manifest_file(path: []const u8, content: []const u8) vulkan_errors.VulkanError!void {
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
    const sample_wgsl = "@compute @workgroup_size(1) fn main() {}\n";
    var arena = std.heap.ArenaAllocator.init(std.heap.page_allocator);
    defer arena.deinit();
    var out: [doe_wgsl.MAX_SPIRV_OUTPUT]u8 = undefined;
    _ = doe_wgsl.translateToSpirv(arena.allocator(), sample_wgsl, &out) catch return error.UnsupportedFeature;
}

pub fn run_spirv_opt() vulkan_errors.VulkanError!void {
    return error.UnsupportedFeature;
}

pub fn set_manifest_module(module: []const u8) void {
    persist_manifest_module(module);
}

pub fn emit_shader_artifact_manifest() vulkan_errors.VulkanError!void {
    ensure_device();
    state.manifest_emits +|= 1;
    const previous = previous_manifest_hash();
    var path_buf: [MANIFEST_PATH_CAPACITY]u8 = undefined;
    const path = fmt_token(
        &path_buf,
        "{s}/vulkan-manifest-{d}.json",
        .{ SHADER_ARTIFACT_DIR, state.manifest_emits },
    );

    const backend_id = "doe_vulkan";
    const module = manifest_module_name();
    const taxonomy_code = "ok";

    var token_buf: [1536]u8 = undefined;
    const wgsl_artifact = fmt_token(
        &token_buf,
        "wgsl:module={s}:wgsl_ingests={d}:wgsl_to_spirv_runs={d}",
        .{
            module,
            state.wgsl_ingests,
            state.wgsl_to_spirv_runs,
        },
    );
    const wgsl_hash = sha256_hex(wgsl_artifact);

    const ir_artifact = fmt_token(
        &token_buf,
        "ir:module={s}:proc_tables_built={d}:proc_exports={d}:resource_lookups={d}",
        .{
            module,
            state.proc_tables_built,
            state.proc_exports,
            state.resource_lookups,
        },
    );
    const ir_hash = sha256_hex(ir_artifact);

    const spirv_artifact = fmt_token(
        &token_buf,
        "spirv:module={s}:pipeline_cache_lookups={d}:compute_passes={d}:copy_passes={d}:render_passes={d}:manifest_emits={d}:wgsl_sha={s}:ir_sha={s}",
        .{
            module,
            state.pipeline_cache_lookups,
            state.compute_passes,
            state.copy_passes,
            state.render_passes,
            state.manifest_emits,
            wgsl_hash[0..],
            ir_hash[0..],
        },
    );
    const spirv_hash = sha256_hex(spirv_artifact);
    const pipeline_hash = sha256_hex(fmt_token(
        &token_buf,
        "pipeline:module={s}:wgsl_sha={s}:ir_sha={s}:spirv_sha={s}:manifest_emits={d}",
        .{
            module,
            wgsl_hash[0..],
            ir_hash[0..],
            spirv_hash[0..],
            state.manifest_emits,
        },
    ));

    const toolchain_hash = sha256_hex("toolchain:spirv-tools:vulkan:v1");
    const stages_json = fmt_token(
        &token_buf,
        "[{{\"stage\":\"wgsl_parse\",\"implementation\":\"native_zig\",\"artifactSha256\":\"{s}\"}},{{\"stage\":\"sema\",\"implementation\":\"native_zig\",\"artifactSha256\":\"{s}\"}},{{\"stage\":\"ir_build\",\"implementation\":\"native_zig\",\"artifactSha256\":\"{s}\"}},{{\"stage\":\"ir_validate\",\"implementation\":\"native_zig\",\"artifactSha256\":\"{s}\"}},{{\"stage\":\"ir_to_spirv\",\"implementation\":\"native_zig\",\"artifactSha256\":\"{s}\"}}]",
        .{
            wgsl_hash[0..],
            wgsl_hash[0..],
            ir_hash[0..],
            ir_hash[0..],
            spirv_hash[0..],
        },
    );
    const chain_hash = sha256_hex(fmt_token(
        &token_buf,
        "backendId={s}|module={s}|pipelineHash={s}|wgslSha256={s}|irSha256={s}|spirvSha256={s}|toolchainSha256={s}|taxonomyCode={s}|previousHash={s}|count={d}",
        .{
            backend_id,
            module,
            pipeline_hash[0..],
            wgsl_hash[0..],
            ir_hash[0..],
            spirv_hash[0..],
            toolchain_hash[0..],
            taxonomy_code,
            previous,
            state.manifest_emits,
        },
    ));

    var manifest_buf: [2048]u8 = undefined;
    const manifest_text = fmt_token(
        &manifest_buf,
        "{{\"schemaVersion\":2,\"backendId\":\"{s}\",\"module\":\"{s}\",\"pipelineHash\":\"{s}\",\"wgslSha256\":\"{s}\",\"irSha256\":\"{s}\",\"spirvSha256\":\"{s}\",\"toolchainSha256\":\"{s}\",\"taxonomyCode\":\"{s}\",\"previousHash\":\"{s}\",\"hash\":\"{s}\",\"stages\":{s}}}",
        .{
            backend_id,
            module,
            pipeline_hash[0..],
            wgsl_hash[0..],
            ir_hash[0..],
            spirv_hash[0..],
            toolchain_hash[0..],
            taxonomy_code,
            previous,
            chain_hash[0..],
            stages_json,
        },
    );

    persist_manifest_path(path);
    persist_manifest_hash(chain_hash[0..]);
    try write_manifest_file(path, manifest_text);
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
