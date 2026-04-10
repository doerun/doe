pub const c = @cImport({
    @cInclude("d3d12_bridge.h");
});

pub const D3D12DescriptorRangeDesc = c.D3D12DescriptorRangeDesc;
pub const D3D12InputElementDesc = c.D3D12InputElementDesc;
pub const D3D12GraphicsPipelineDesc = c.D3D12GraphicsPipelineDesc;
