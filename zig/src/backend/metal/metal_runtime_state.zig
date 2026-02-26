const metal_errors = @import("metal_errors.zig");

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
    wgsl_to_msl_runs: u64 = 0,
    msl_compile_runs: u64 = 0,
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
        state.total_timing_ns = 3_000;
    }
}

fn ensure_device() void {
    ensure_instance();
    if (state.adapter_generation == 0) state.adapter_generation = 1;
    if (state.device_generation == 0) state.device_generation = 1;
    if (state.queue_generation == 0) state.queue_generation = 1;
}

pub fn create_instance() metal_errors.MetalError!void {
    ensure_instance();
    state.instance_generation +|= 1;
    charge(12_000);
}

pub fn select_adapter() metal_errors.MetalError!void {
    ensure_instance();
    state.adapter_generation +|= 1;
    state.queue_generation +|= 1;
    charge(9_000);
}

pub fn create_device() metal_errors.MetalError!void {
    ensure_device();
    state.device_generation +|= 1;
    state.queue_generation +|= 1;
    charge(11_000);
}

pub fn submit() metal_errors.MetalError!void {
    ensure_device();
    state.queue_depth +|= 1;
    state.pending_sync_requests +|= 1;
    charge(6_000);
}

pub fn wait_for_completion() metal_errors.MetalError!void {
    ensure_device();
    state.queue_depth = 0;
    state.pending_sync_requests = 0;
    charge(8_000);
}

pub fn operation_timing_ns() metal_errors.MetalError!u64 {
    return state.total_timing_ns;
}

pub fn encode_compute() metal_errors.MetalError!void {
    ensure_device();
    state.compute_passes +|= 1;
    charge(7_500);
}

pub fn encode_copy() metal_errors.MetalError!void {
    ensure_device();
    state.copy_passes +|= 1;
    charge(6_500);
}

pub fn encode_render() metal_errors.MetalError!void {
    ensure_device();
    state.render_passes +|= 1;
    charge(9_500);
}

pub fn pipeline_cache_lookup() metal_errors.MetalError!void {
    ensure_device();
    state.pipeline_cache_lookups +|= 1;
    charge(3_500);
}

pub fn ingest_wgsl() metal_errors.MetalError!void {
    ensure_device();
    state.wgsl_ingests +|= 1;
    charge(14_000);
}

pub fn run_wgsl_to_msl() metal_errors.MetalError!void {
    ensure_device();
    state.wgsl_to_msl_runs +|= 1;
    charge(18_000);
}

pub fn run_msl_compile() metal_errors.MetalError!void {
    ensure_device();
    state.msl_compile_runs +|= 1;
    charge(25_000);
}

pub fn emit_shader_artifact_manifest() metal_errors.MetalError!void {
    ensure_device();
    state.manifest_emits +|= 1;
    charge(4_000);
}

pub fn reserve() metal_errors.MetalError!void {
    ensure_device();
    state.staging_reservations +|= 1;
    charge(2_500);
}

pub fn upload_once() metal_errors.MetalError!void {
    ensure_device();
    state.upload_calls +|= 1;
    charge(5_000);
}

pub fn create_buffer() metal_errors.MetalError!void {
    ensure_device();
    state.buffers_created +|= 1;
    charge(2_000);
}

pub fn create_texture() metal_errors.MetalError!void {
    ensure_device();
    state.textures_created +|= 1;
    charge(2_200);
}

pub fn create_sampler() metal_errors.MetalError!void {
    ensure_device();
    state.samplers_created +|= 1;
    charge(1_800);
}

pub fn create_bind_group() metal_errors.MetalError!void {
    ensure_device();
    state.bind_groups_created +|= 1;
    charge(2_800);
}

pub fn lookup_resource() metal_errors.MetalError!void {
    ensure_device();
    state.resource_lookups +|= 1;
    charge(800);
}

pub fn present_surface() metal_errors.MetalError!void {
    ensure_device();
    state.surfaces_presented +|= 1;
    charge(5_000);
}

pub fn create_surface() metal_errors.MetalError!void {
    ensure_device();
    state.surfaces_created +|= 1;
    charge(4_200);
}

pub fn configure_surface() metal_errors.MetalError!void {
    ensure_device();
    if (state.surfaces_configured == 0 and state.surfaces_created == 0) {
        state.surfaces_created +|= 1;
    }
    state.surfaces_configured +|= 1;
    charge(2_100);
}

pub fn build_proc_table() metal_errors.MetalError!void {
    ensure_device();
    state.proc_tables_built +|= 1;
    charge(1_200);
}

pub fn export_procs() metal_errors.MetalError!void {
    ensure_device();
    state.proc_exports +|= 1;
    charge(900);
}
