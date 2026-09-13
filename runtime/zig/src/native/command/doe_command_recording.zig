const objects = @import("../support/doe_native_object_types.zig");
const commands = @import("../support/doe_native_command_types.zig");
const errors = @import("../../runtime/diagnostics/error_scope.zig");
const contract = @import("../../contracts/command_recording.zig");

pub fn fail(encoder: *objects.DoeCommandEncoder, cause: contract.Failure) void {
    if (encoder.state.fail(cause))
        encoder.dev.error_scopes.deliver(errors.zig_error_to_type(cause), contract.message(cause));
}

pub fn requireOpen(encoder: *objects.DoeCommandEncoder) bool {
    if (encoder.state == .open) return true;
    fail(encoder, error.InvalidState);
    return false;
}

pub fn requireRecording(encoder: *objects.DoeCommandEncoder) bool {
    if (encoder.state == .open or encoder.state == .pass) return true;
    fail(encoder, error.InvalidState);
    return false;
}

pub fn requirePass(encoder: *objects.DoeCommandEncoder, identity: usize) bool {
    if (encoder.state == .pass and encoder.state.pass == identity) return true;
    fail(encoder, error.InvalidState);
    return false;
}

pub fn endPass(encoder: *objects.DoeCommandEncoder, identity: usize) void {
    if (encoder.state == .pass and encoder.state.pass == identity) encoder.state = .open;
}

pub fn reserve(encoder: *objects.DoeCommandEncoder, command_count: usize, reference_count: usize) bool {
    if (!requireRecording(encoder)) return false;
    const before = encoder.cmds.capacity;
    encoder.cmds.ensureUnusedCapacity(encoder.allocator, command_count) catch |err| {
        observeGrowth(encoder, before, true);
        fail(encoder, err);
        return false;
    };
    observeGrowth(encoder, before, false);
    encoder.references.ensureUnusedCapacity(encoder.allocator, reference_count) catch |err| {
        fail(encoder, err);
        return false;
    };
    return true;
}

fn observeGrowth(encoder: *objects.DoeCommandEncoder, before: usize, failed: bool) void {
    if (comptime @import("doe_command_storage.zig").OBSERVATION_MODE == .ordinary) return;
    if (encoder.dev.command_storage) |*pool| pool.observeGrowth(before, encoder.cmds.capacity, failed);
}

pub fn append(encoder: *objects.DoeCommandEncoder, command: commands.RecordedCmd) bool {
    if (!reserve(encoder, 1, 0)) return false;
    encoder.cmds.appendAssumeCapacity(command);
    return true;
}
