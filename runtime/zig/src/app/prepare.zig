//! Prepares requests into read-only PreparedOperations for synchronous execution.

const request = @import("request.zig");
const command_contract = @import("../contracts/command.zig");
const prepared = @import("../contracts/prepared_operation.zig");
const model_compute = @import("../contracts/model/model_compute_types.zig");

pub fn prepareCompute(req: request.ComputeRequest, operation_id: u64) prepared.PreparedComputeOperation {
    return prepareComputeFromCommand(req.toCommand(), operation_id);
}

pub fn prepareComputeFromCommand(cmd: model_compute.KernelDispatchCommand, operation_id: u64) prepared.PreparedComputeOperation {
    return prepareCommand(.{ .kernel_dispatch = cmd }, operation_id).compute;
}

pub fn prepareTransfer(req: request.TransferRequest, operation_id: u64) prepared.PreparedTransferOperation {
    return prepared.directBufferWrite(req, operation_id).transfer;
}

pub fn prepareCommand(command: command_contract.Command, operation_id: u64) prepared.PreparedOperation {
    return prepared.fromCommand(command, operation_id);
}
