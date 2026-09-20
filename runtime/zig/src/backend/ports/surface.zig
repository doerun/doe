//! Outbound port for surface lifecycle and presentation operations.
//!
//! Provider context and vtable outlive calls; operation inputs are borrowed.
//! The provider owns acquired drawables and their retirement. A successful
//! presentation report does not establish display visibility or presentation
//! timing. Backend capability/admission failures pass through unchanged.

const prepared = @import("../../contracts/prepared_operation.zig");
const report = @import("../../contracts/execution_report.zig");

pub const SurfacePortVTable = struct {
    execute_surface: *const fn (ctx: *anyopaque, op: prepared.PreparedSurfaceOperation) anyerror!report.ExecutionReport,
};

pub const SurfacePort = struct {
    context: *anyopaque,
    vtable: *const SurfacePortVTable,

    pub fn execute(self: SurfacePort, op: prepared.PreparedSurfaceOperation) !report.ExecutionReport {
        return self.vtable.execute_surface(self.context, op);
    }
};
