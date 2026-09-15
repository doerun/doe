//! Application request contracts for the Hexagonal core.
//!
//! Represents incoming application intent before normalization and preparation.

const compute_contract = @import("../contracts/compute.zig");
const prepared = @import("../contracts/prepared_operation.zig");

pub const WorkgroupCount = compute_contract.WorkgroupCount;

pub const ComputeRequest = compute_contract.DispatchRequest;
pub const TransferRequest = prepared.DirectBufferWrite;

pub const ApplicationRequest = union(enum) {
    compute: ComputeRequest,
    transfer: TransferRequest,
};
