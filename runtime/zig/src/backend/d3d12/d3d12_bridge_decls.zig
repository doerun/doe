pub const c = @cImport({
    @cInclude("d3d12_bridge.h");
});

pub const D3D12DescriptorRangeDesc = c.D3D12DescriptorRangeDesc;
pub const D3D12InputElementDesc = c.D3D12InputElementDesc;
pub const D3D12GraphicsPipelineDesc = c.D3D12GraphicsPipelineDesc;

pub const SynchronizationError = error{ DeviceLost, QueueSignalFailed, FenceWaitFailed };

pub fn check_signal(result: c_int) SynchronizationError!void {
    switch (result) {
        c.D3D12_SYNC_OK => {},
        c.D3D12_SYNC_DEVICE_LOST => return error.DeviceLost,
        else => return error.QueueSignalFailed,
    }
}

pub fn check_wait(result: c_int) SynchronizationError!void {
    switch (result) {
        c.D3D12_SYNC_OK => {},
        c.D3D12_SYNC_DEVICE_LOST => return error.DeviceLost,
        else => return error.FenceWaitFailed,
    }
}
