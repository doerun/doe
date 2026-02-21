const std = @import("std");
const model = @import("model.zig");
const types = @import("wgpu_types.zig");
const loader = @import("wgpu_loader.zig");
const resources = @import("wgpu_resources.zig");
const async_procs_mod = @import("wgpu_async_procs.zig");
const render_api_mod = @import("wgpu_render_api.zig");
const render_types_mod = @import("wgpu_render_types.zig");
const ffi = @import("webgpu_ffi.zig");
const Backend = ffi.WebGPUBackend;

const RENDER_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST: u32 = 0x00000004;
const RENDER_FRONT_FACE_CCW: u32 = 0x00000001;
const RENDER_CULL_MODE_NONE: u32 = 0x00000001;
const RENDER_COLOR_WRITE_MASK_ALL: u64 = 0x000000000000000F;
const RENDER_MULTISAMPLE_MASK_ALL: u32 = 0xFFFF_FFFF;

const DIAGNOSTIC_SHADER_SOURCE =
    \\@vertex
    \\fn vs_main(@builtin(vertex_index) idx: u32) -> @builtin(position) vec4f {
    \\  var p = array<vec2f, 3>(
    \\    vec2f(0.0, 0.5),
    \\    vec2f(-0.5, -0.5),
    \\    vec2f(0.5, -0.5),
    \\  );
    \\  let pos = p[idx];
    \\  return vec4f(pos, 0.0, 1.0);
    \\}
    \\@fragment
    \\fn fs_main() -> @location(0) vec4f {
    \\  return vec4f(0.0, 0.0, 0.0, 1.0);
    \\}
;

pub fn executeAsyncDiagnostics(self: *Backend, diagnostics: model.AsyncDiagnosticsCommand) !types.NativeExecutionResult {
    const procs = self.procs orelse return error.ProceduralNotReady;
    const render_api = render_api_mod.loadRenderApi(procs, self.dyn_lib) orelse {
        return .{ .status = .unsupported, .status_message = "async diagnostics requires render api surface" };
    };
    const async_procs = async_procs_mod.loadAsyncProcs(self.dyn_lib) orelse {
        return .{ .status = .unsupported, .status_message = "async diagnostics requires async api surface" };
    };

    const setup_start_ns = std.time.nanoTimestamp();
    const shader_module = resources.createShaderModule(self, DIAGNOSTIC_SHADER_SOURCE) catch |err| {
        return .{
            .status = .@"error",
            .status_message = switch (err) {
                error.KernelModuleCreationFailed => "async diagnostics shader module creation failed",
                else => "async diagnostics shader setup failed",
            },
        };
    };
    defer procs.wgpuShaderModuleRelease(shader_module);

    const compilation_state = async_procs_mod.requestShaderCompilationInfoAndWait(
        async_procs,
        self.instance.?,
        procs,
        shader_module,
    ) catch {
        return .{ .status = .@"error", .status_message = "async diagnostics compilation info request failed" };
    };
    if (compilation_state.status != async_procs_mod.COMPILATION_INFO_STATUS_SUCCESS) {
        return .{ .status = .@"error", .status_message = "async diagnostics compilation info status not successful" };
    }

    async_procs_mod.pushErrorScope(async_procs, self.device.?, async_procs_mod.ERROR_FILTER_VALIDATION);
    async_procs_mod.pushErrorScope(async_procs, self.device.?, async_procs_mod.ERROR_FILTER_INTERNAL);
    async_procs_mod.pushErrorScope(async_procs, self.device.?, async_procs_mod.ERROR_FILTER_OUT_OF_MEMORY);

    var color_target = render_types_mod.RenderColorTargetState{
        .nextInChain = null,
        .format = resources.normalizeTextureFormat(diagnostics.target_format),
        .blend = null,
        .writeMask = RENDER_COLOR_WRITE_MASK_ALL,
    };
    if (color_target.format == types.WGPUTextureFormat_Undefined) {
        color_target.format = model.WGPUTextureFormat_RGBA8Unorm;
    }
    var fragment_state = render_types_mod.RenderFragmentState{
        .nextInChain = null,
        .module = shader_module,
        .entryPoint = loader.stringView("fs_main"),
        .constantCount = 0,
        .constants = null,
        .targetCount = 1,
        .targets = @ptrCast(&color_target),
    };
    const pipeline_desc = render_types_mod.RenderPipelineDescriptor{
        .nextInChain = null,
        .label = loader.stringView("fawn.async_diagnostics"),
        .layout = null,
        .vertex = .{
            .nextInChain = null,
            .module = shader_module,
            .entryPoint = loader.stringView("vs_main"),
            .constantCount = 0,
            .constants = null,
            .bufferCount = 0,
            .buffers = null,
        },
        .primitive = .{
            .nextInChain = null,
            .topology = RENDER_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,
            .stripIndexFormat = 0,
            .frontFace = RENDER_FRONT_FACE_CCW,
            .cullMode = RENDER_CULL_MODE_NONE,
            .unclippedDepth = types.WGPU_FALSE,
        },
        .depthStencil = null,
        .multisample = .{
            .nextInChain = null,
            .count = 1,
            .mask = RENDER_MULTISAMPLE_MASK_ALL,
            .alphaToCoverageEnabled = types.WGPU_FALSE,
        },
        .fragment = &fragment_state,
    };
    const pipeline = async_procs_mod.createRenderPipelineAsyncAndWait(
        async_procs,
        self.instance.?,
        procs,
        self.device.?,
        @ptrCast(&pipeline_desc),
    ) catch {
        _ = async_procs_mod.popErrorScopeAndWait(async_procs, self.instance.?, procs, self.device.?) catch {};
        _ = async_procs_mod.popErrorScopeAndWait(async_procs, self.instance.?, procs, self.device.?) catch {};
        _ = async_procs_mod.popErrorScopeAndWait(async_procs, self.instance.?, procs, self.device.?) catch {};
        return .{ .status = .@"error", .status_message = "async diagnostics async pipeline creation failed" };
    };
    render_api.render_pipeline_release(pipeline);

    const out_of_memory_scope = async_procs_mod.popErrorScopeAndWait(async_procs, self.instance.?, procs, self.device.?) catch {
        return .{ .status = .@"error", .status_message = "async diagnostics out-of-memory scope pop failed" };
    };
    const internal_scope = async_procs_mod.popErrorScopeAndWait(async_procs, self.instance.?, procs, self.device.?) catch {
        return .{ .status = .@"error", .status_message = "async diagnostics internal scope pop failed" };
    };
    const validation_scope = async_procs_mod.popErrorScopeAndWait(async_procs, self.instance.?, procs, self.device.?) catch {
        return .{ .status = .@"error", .status_message = "async diagnostics validation scope pop failed" };
    };
    const no_error = @as(u32, @intFromEnum(types.WGPUErrorType.noError));
    if (out_of_memory_scope.status != async_procs_mod.POP_ERROR_SCOPE_STATUS_SUCCESS or
        internal_scope.status != async_procs_mod.POP_ERROR_SCOPE_STATUS_SUCCESS or
        validation_scope.status != async_procs_mod.POP_ERROR_SCOPE_STATUS_SUCCESS or
        out_of_memory_scope.error_type != no_error or
        internal_scope.error_type != no_error or
        validation_scope.error_type != no_error)
    {
        return .{ .status = .@"error", .status_message = "async diagnostics error-scope validation failed" };
    }

    const setup_end_ns = std.time.nanoTimestamp();
    const setup_ns = if (setup_end_ns > setup_start_ns)
        @as(u64, @intCast(setup_end_ns - setup_start_ns))
    else
        0;
    return .{
        .status = .ok,
        .status_message = "async diagnostics completed",
        .setup_ns = setup_ns,
    };
}
