pub const formats = @import("d3d12_formats.zig");

pub const HEAP_TYPE_UPLOAD: c_int = 2;
pub const HEAP_TYPE_READBACK: c_int = 3;

pub const RESOURCE_STATE_PRESENT: c_int = 0x00000000;
pub const RESOURCE_STATE_RENDER_TARGET: c_int = 0x00000004;
pub const RESOURCE_STATE_DEPTH_WRITE: c_int = 0x00000010;
pub const RESOURCE_STATE_DEPTH_READ: c_int = 0x00000020;
pub const RESOURCE_STATE_UNORDERED_ACCESS: c_int = 0x00000008;
// Canonical D3D12 values per d3d12.h: COPY_DEST=0x400, COPY_SOURCE=0x800.
// Previously swapped. Latent for the compute-only cohort; any texture
// transitioning into or out of a copy state from the Zig backend would have
// passed the wrong state constant, triggering D3D12 validation errors on
// debug devices.
pub const RESOURCE_STATE_COPY_DEST: c_int = 0x00000400;
pub const RESOURCE_STATE_COPY_SOURCE: c_int = 0x00000800;
pub const RESOURCE_STATE_RESOLVE_DEST: c_int = 0x00001000;
pub const RESOURCE_STATE_RESOLVE_SOURCE: c_int = 0x00002000;
pub const RESOURCE_STATE_PIXEL_SHADER_RESOURCE: c_int = 0x00000080;
pub const RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE: c_int = 0x00000040;
pub const RESOURCE_STATE_GENERIC_READ: c_int = 0x00000001 | 0x00000002 | 0x00000040 | 0x00000080 | 0x00000200 | 0x00000800;

pub const D3D_PRIMITIVE_TOPOLOGY_TRIANGLELIST: c_int = 4;
pub const D3D_PRIMITIVE_TOPOLOGY_TRIANGLESTRIP: c_int = 5;
pub const D3D_PRIMITIVE_TOPOLOGY_LINELIST: c_int = 2;
pub const D3D_PRIMITIVE_TOPOLOGY_LINESTRIP: c_int = 3;
pub const D3D_PRIMITIVE_TOPOLOGY_POINTLIST: c_int = 1;

// D3D12_SRV_DIMENSION values per d3d12.h. Previously transcribed locally
// in resources/d3d12_texture_view.zig with four wrong values: TEXTURE1D=3
// (should be 2, was encoding TEXTURE1DARRAY), TEXTURE3D=7 (should be 8,
// was encoding TEXTURE2DMSARRAY), TEXTURECUBE=8 (should be 9, was
// encoding TEXTURE3D), TEXTURECUBEARRAY=9 (should be 10, was encoding
// TEXTURECUBE). Any SRV descriptor written for a 1D, 3D, cube, or cube
// array texture carried the wrong ViewDimension.
pub const SRV_DIMENSION_UNKNOWN: u32 = 0;
pub const SRV_DIMENSION_BUFFER: u32 = 1;
pub const SRV_DIMENSION_TEXTURE1D: u32 = 2;
pub const SRV_DIMENSION_TEXTURE1DARRAY: u32 = 3;
pub const SRV_DIMENSION_TEXTURE2D: u32 = 4;
pub const SRV_DIMENSION_TEXTURE2DARRAY: u32 = 5;
pub const SRV_DIMENSION_TEXTURE2DMS: u32 = 6;
pub const SRV_DIMENSION_TEXTURE2DMSARRAY: u32 = 7;
pub const SRV_DIMENSION_TEXTURE3D: u32 = 8;
pub const SRV_DIMENSION_TEXTURECUBE: u32 = 9;
pub const SRV_DIMENSION_TEXTURECUBEARRAY: u32 = 10;

// D3D12_DESCRIPTOR_HEAP_TYPE values per d3d12.h. Centralized here so
// spec_diff_gate.py can audit future drift; previously transcribed
// locally in d3d12_descriptors.zig (values correct but ungoverned).
pub const DESCRIPTOR_HEAP_TYPE_CBV_SRV_UAV: c_int = 0;
pub const DESCRIPTOR_HEAP_TYPE_SAMPLER: c_int = 1;
pub const DESCRIPTOR_HEAP_TYPE_RTV: c_int = 2;
pub const DESCRIPTOR_HEAP_TYPE_DSV: c_int = 3;

// D3D12_DESCRIPTOR_RANGE_TYPE values per d3d12.h. Centralized here so
// spec_diff_gate.py can audit future drift; previously transcribed
// locally in d3d12_descriptors.zig and d3d12_runtime_compute.zig
// (values correct but ungoverned and duplicated).
pub const DESCRIPTOR_RANGE_TYPE_SRV: u32 = 0;
pub const DESCRIPTOR_RANGE_TYPE_UAV: u32 = 1;
pub const DESCRIPTOR_RANGE_TYPE_CBV: u32 = 2;
pub const DESCRIPTOR_RANGE_TYPE_SAMPLER: u32 = 3;

// D3D12_RESOURCE_DIMENSION values per d3d12.h. Not currently used in
// Zig — bridge.c consumes the canonical C symbols directly — but
// centralized here pre-emptively in case a Zig path needs to encode a
// dimension before a create-resource bridge call lands.
pub const RESOURCE_DIMENSION_UNKNOWN: u32 = 0;
pub const RESOURCE_DIMENSION_BUFFER: u32 = 1;
pub const RESOURCE_DIMENSION_TEXTURE1D: u32 = 2;
pub const RESOURCE_DIMENSION_TEXTURE2D: u32 = 3;
pub const RESOURCE_DIMENSION_TEXTURE3D: u32 = 4;

// D3D12_INPUT_CLASSIFICATION values per d3d12.h. Centralized here so the
// values used by commands/d3d12_render.zig for vertex-input slot classification
// are spec-diff governed.
pub const INPUT_CLASSIFICATION_PER_VERTEX_DATA: u32 = 0;
pub const INPUT_CLASSIFICATION_PER_INSTANCE_DATA: u32 = 1;

// D3D12_COMMAND_LIST_TYPE values per d3d12.h. Not currently referenced from
// Zig — bridge.c uses the canonical C symbols directly — but centralized so
// any future Zig path that encodes a command-list type is spec-diff
// governed from day one.
pub const COMMAND_LIST_TYPE_DIRECT: u32 = 0;
pub const COMMAND_LIST_TYPE_BUNDLE: u32 = 1;
pub const COMMAND_LIST_TYPE_COMPUTE: u32 = 2;
pub const COMMAND_LIST_TYPE_COPY: u32 = 3;

// WebGPU depth format IDs
pub const WGPU_DEPTH16_UNORM: u32 = 0x0000002D;
pub const WGPU_DEPTH24_PLUS: u32 = 0x0000002E;
pub const WGPU_DEPTH24_PLUS_STENCIL8: u32 = 0x0000002F;
pub const WGPU_DEPTH32_FLOAT: u32 = 0x00000030;
pub const WGPU_DEPTH32_FLOAT_STENCIL8: u32 = 0x00000031;
