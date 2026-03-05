const std = @import("std");
const model = @import("model.zig");
const types = @import("wgpu_types.zig");
const loader = @import("wgpu_loader.zig");
const p0_procs_mod = @import("wgpu_p0_procs.zig");
const resources = @import("wgpu_resources.zig");
const render_commands = @import("wgpu_render_commands.zig");
const extended_commands = @import("wgpu_extended_commands.zig");
const async_diagnostics_command = @import("wgpu_async_diagnostics_command.zig");
const ffi = @import("webgpu_ffi.zig");
const sandbox = @import("wgpu_sandbox_guard.zig");
const copy_commands = @import("wgpu_commands_copy.zig");
const compute_commands = @import("wgpu_commands_compute.zig");
const Backend = ffi.WebGPUBackend;

pub fn executeCommand(self: *Backend, command: model.Command) !types.NativeExecutionResult {
    if (!self.backendAvailable()) {
        return .{
            .status = .@"error",
            .status_message = "backend-not-initialized",
        };
    }

    sandbox.validateCommand(command) catch |err| {
        return .{
            .status = .@"error",
            .status_message = switch (err) {
                error.UploadExceedsAddressSpace => "upload bytes exceed address space",
                error.UploadZeroBytes => "upload command has zero bytes",
                error.CopyZeroBytes => "copy bytes must be > 0",
                error.CopyInvalidDirection => "invalid copy direction dimensions or format mismatch",
                error.CopyInvalidDimensions => "copy command missing valid dimensions",
                error.DispatchZeroDimensions => "dispatch dimensions must be non-zero",
                error.DispatchIndirectZeroDimensions => "dispatch_indirect dimensions must be non-zero",
                error.KernelDispatchZeroDimensions => "kernel_dispatch dimensions must be non-zero",
                error.KernelDispatchMissingMarker => "kernel_dispatch requires a non-empty kernel marker",
                error.KernelDispatchZeroRepeat => "kernel_dispatch repeat must be > 0",
            },
        };
    };

    self.clearUncapturedError();
    const result = try switch (command) {
        .upload => |upload| copy_commands.executeUpload(self, upload),
        .copy_buffer_to_texture => |copy| blk: {
            try flushPendingUploads(self);
            break :blk copy_commands.executeCopy(self, copy);
        },
        .barrier => |barrier| blk: {
            try flushPendingUploads(self);
            break :blk compute_commands.executeBarrier(self, barrier);
        },
        .dispatch => |dispatch| blk: {
            try flushPendingUploads(self);
            break :blk compute_commands.executeDispatch(self, dispatch);
        },
        .dispatch_indirect => |dispatch| blk: {
            try flushPendingUploads(self);
            break :blk compute_commands.executeDispatchIndirect(self, dispatch);
        },
        .kernel_dispatch => |kernel| blk: {
            try flushPendingUploads(self);
            break :blk compute_commands.executeKernelDispatch(self, kernel);
        },
        .render_draw => |render| blk: {
            try flushPendingUploads(self);
            break :blk render_commands.executeRenderDraw(self, render);
        },
        .draw_indirect => |render| blk: {
            try flushPendingUploads(self);
            break :blk render_commands.executeRenderDraw(self, render);
        },
        .draw_indexed_indirect => |render| blk: {
            try flushPendingUploads(self);
            break :blk render_commands.executeRenderDraw(self, render);
        },
        .render_pass => |render| blk: {
            try flushPendingUploads(self);
            break :blk render_commands.executeRenderDraw(self, render);
        },
        .sampler_create => |sampler_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSamplerCreate(self, sampler_cmd);
        },
        .sampler_destroy => |sampler_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSamplerDestroy(self, sampler_cmd);
        },
        .texture_write => |texture_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeTextureWrite(self, texture_cmd);
        },
        .texture_query => |texture_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeTextureQuery(self, texture_cmd);
        },
        .texture_destroy => |texture_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeTextureDestroy(self, texture_cmd);
        },
        .surface_create => |surface_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSurfaceCreate(self, surface_cmd);
        },
        .surface_capabilities => |surface_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSurfaceCapabilities(self, surface_cmd);
        },
        .surface_configure => |surface_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSurfaceConfigure(self, surface_cmd);
        },
        .surface_acquire => |surface_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSurfaceAcquire(self, surface_cmd);
        },
        .surface_present => |surface_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSurfacePresent(self, surface_cmd);
        },
        .surface_unconfigure => |surface_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSurfaceUnconfigure(self, surface_cmd);
        },
        .surface_release => |surface_cmd| blk: {
            try flushPendingUploads(self);
            break :blk extended_commands.executeSurfaceRelease(self, surface_cmd);
        },
        .async_diagnostics => |diagnostics| blk: {
            try flushPendingUploads(self);
            break :blk async_diagnostics_command.executeAsyncDiagnostics(self, diagnostics);
        },
        .map_async => |map_command| blk: {
            try flushPendingUploads(self);
            break :blk copy_commands.executeMapAsync(self, map_command);
        },
    };

    if (self.takeUncapturedError()) |error_type| {
        return .{
            .status = .@"error",
            .status_message = Backend.uncapturedErrorStatusMessage(error_type),
            .setup_ns = result.setup_ns,
            .encode_ns = result.encode_ns,
            .submit_wait_ns = result.submit_wait_ns,
            .dispatch_count = result.dispatch_count,
            .gpu_timestamp_ns = result.gpu_timestamp_ns,
            .gpu_timestamp_attempted = result.gpu_timestamp_attempted,
            .gpu_timestamp_valid = result.gpu_timestamp_valid,
        };
    }

    return result;
}

fn flushPendingUploads(self: *Backend) !void {
    if (self.upload_submit_pending == 0) return;
    _ = try self.submitEmpty();
    self.upload_submit_pending = 0;
}
