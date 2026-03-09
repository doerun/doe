const model = @import("model.zig");
const types = @import("core/abi/wgpu_types.zig");
const ffi = @import("webgpu_ffi.zig");
const sandbox = @import("wgpu_sandbox_guard.zig");
const core_dispatch = @import("core/command_dispatch.zig");
const full_dispatch = @import("full/command_dispatch.zig");
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
    if (model.as_core_command(command)) |core_command| {
        switch (core_command) {
            .upload => {},
            else => try flushPendingUploads(self),
        }
    } else {
        try flushPendingUploads(self);
    }
    const result = if (try core_dispatch.execute(self, command)) |core_result|
        core_result
    else if (try full_dispatch.execute(self, command)) |full_result|
        full_result
    else
        unreachable;

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
    if (self.core.upload_submit_pending == 0) return;
    _ = try self.submitEmpty();
    self.core.upload_submit_pending = 0;
}
