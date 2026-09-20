//! Outbound port for sampler, texture, and mapping resource operations.
//!
//! Context and vtable are borrowed from the provider and outlive every call.
//! Input slices are borrowed only for execute; deferred work must own a snapshot
//! and retain referenced resources separately. Numeric handles transfer no ownership.
//! Success reports the operation under the provider's queue policy, not a promise
//! of GPU completion. Completion belongs to the queue contract. Report messages
//! remain provider-owned; copy them before retaining a result beyond that lifetime.

const prepared = @import("../../contracts/prepared_operation.zig");
const report = @import("../../contracts/execution_report.zig");

pub const ResourcePortVTable = struct {
    execute_resource: *const fn (ctx: *anyopaque, op: prepared.PreparedResourceOperation) anyerror!report.ExecutionReport,
};

pub const ResourcePort = struct {
    context: *anyopaque,
    vtable: *const ResourcePortVTable,

    pub fn execute(self: ResourcePort, op: prepared.PreparedResourceOperation) !report.ExecutionReport {
        return self.vtable.execute_resource(self.context, op);
    }
};
