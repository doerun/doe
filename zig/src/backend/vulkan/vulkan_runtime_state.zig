const vulkan_errors = @import("vulkan_errors.zig");

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
    upload_calls: u64 = 0,
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
        state.total_timing_ns = 4_000;
    }
}

fn ensure_device() void {
    ensure_instance();
    if (state.adapter_generation == 0) state.adapter_generation = 1;
    if (state.device_generation == 0) state.device_generation = 1;
    if (state.queue_generation == 0) state.queue_generation = 1;
}

pub fn create_instance() vulkan_errors.VulkanError!void {
    state.instance_generation +|= 1;
    charge(14_000);
}

pub fn select_adapter() vulkan_errors.VulkanError!void {
    ensure_instance();
    state.adapter_generation +|= 1;
    state.queue_generation +|= 1;
    charge(11_000);
}

pub fn create_device() vulkan_errors.VulkanError!void {
    ensure_device();
    state.device_generation +|= 1;
    state.queue_generation +|= 1;
    charge(13_000);
}

pub fn submit() vulkan_errors.VulkanError!void {
    ensure_device();
    state.queue_depth +|= 1;
    state.pending_sync_requests +|= 1;
    charge(7_000);
}

pub fn wait_for_completion() vulkan_errors.VulkanError!void {
    ensure_device();
    state.queue_depth = 0;
    state.pending_sync_requests = 0;
    charge(9_000);
}

pub fn operation_timing_ns() vulkan_errors.VulkanError!u64 {
    ensure_device();
    return state.total_timing_ns;
}

pub fn encode_compute() vulkan_errors.VulkanError!void {
    ensure_device();
    state.compute_passes +|= 1;
    charge(8_500);
}

pub fn encode_copy() vulkan_errors.VulkanError!void {
    ensure_device();
    state.copy_passes +|= 1;
    charge(7_000);
}

pub fn encode_render() vulkan_errors.VulkanError!void {
    ensure_device();
    state.render_passes +|= 1;
    charge(10_000);
}

pub fn pipeline_cache_lookup() vulkan_errors.VulkanError!void {
    ensure_device();
    state.pipeline_cache_lookups +|= 1;
    charge(4_000);
}

pub fn ingest_wgsl() vulkan_errors.VulkanError!void {
    ensure_device();
    state.wgsl_ingests +|= 1;
    charge(16_000);
}

pub fn run_wgsl_to_spirv() vulkan_errors.VulkanError!void {
    ensure_device();
    state.wgsl_to_spirv_runs +|= 1;
    charge(21_000);
}

pub fn run_spirv_opt() vulkan_errors.VulkanError!void {
    ensure_device();
    state.spirv_opt_runs +|= 1;
    charge(18_500);
}

pub fn emit_shader_artifact_manifest() vulkan_errors.VulkanError!void {
    ensure_device();
    state.manifest_emits +|= 1;
    charge(5_200);
}

pub fn reserve_staging() vulkan_errors.VulkanError!void {
    ensure_device();
    state.staging_reservations +|= 1;
    charge(3_100);
}

pub fn upload_once() vulkan_errors.VulkanError!void {
    ensure_device();
    state.upload_calls +|= 1;
    charge(6_000);
}

pub fn create_buffer() vulkan_errors.VulkanError!void {
    ensure_device();
    state.buffers_created +|= 1;
    charge(2_300);
}

pub fn destroy_buffer() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.buffers_created > 0) {
        state.buffers_created -= 1;
    }
    charge(1_200);
}

pub fn create_texture() vulkan_errors.VulkanError!void {
    ensure_device();
    state.textures_created +|= 1;
    charge(2_400);
}

pub fn write_texture() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.textures_created == 0) {
        state.textures_created +|= 1;
    }
    charge(1_900);
}

pub fn query_texture() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.textures_created == 0) {
        state.textures_created +|= 1;
    }
    charge(1_100);
}

pub fn destroy_texture() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.textures_created > 0) {
        state.textures_created -= 1;
    }
    charge(1_700);
}

pub fn create_sampler() vulkan_errors.VulkanError!void {
    ensure_device();
    state.samplers_created +|= 1;
    charge(1_500);
}

pub fn destroy_sampler() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.samplers_created > 0) {
        state.samplers_created -= 1;
    }
    charge(1_100);
}

pub fn create_bind_group() vulkan_errors.VulkanError!void {
    ensure_device();
    state.bind_groups_created +|= 1;
    charge(2_600);
}

pub fn destroy_bind_group() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.bind_groups_created > 0) {
        state.bind_groups_created -= 1;
    }
    charge(1_600);
}

pub fn lookup_resource() vulkan_errors.VulkanError!void {
    ensure_device();
    state.resource_lookups +|= 1;
    charge(900);
}

pub fn create_surface() vulkan_errors.VulkanError!void {
    ensure_device();
    state.surfaces_created +|= 1;
    charge(4_800);
}

pub fn configure_surface() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.surfaces_created == 0) state.surfaces_created +|= 1;
    state.surfaces_configured +|= 1;
    charge(2_400);
}

pub fn unconfigure_surface() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.surfaces_configured > 0) {
        state.surfaces_configured -= 1;
    }
    charge(1_200);
}

pub fn get_surface_capabilities() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.surfaces_created == 0) state.surfaces_created +|= 1;
    charge(1_100);
}

pub fn acquire_surface() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.surfaces_created == 0) state.surfaces_created +|= 1;
    charge(1_700);
}

pub fn present_surface() vulkan_errors.VulkanError!void {
    ensure_device();
    state.surfaces_presented +|= 1;
    charge(5_600);
}

pub fn release_surface() vulkan_errors.VulkanError!void {
    ensure_device();
    if (state.surfaces_created > 0) {
        state.surfaces_created -= 1;
    }
    charge(2_000);
}

pub fn build_proc_table() vulkan_errors.VulkanError!void {
    ensure_device();
    state.proc_tables_built +|= 1;
    charge(1_300);
}

pub fn export_procs() vulkan_errors.VulkanError!void {
    ensure_device();
    state.proc_exports +|= 1;
    charge(900);
}
