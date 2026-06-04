const std = @import("std");
const builtin = @import("builtin");

const abi_callback = @import("../core/abi/wgpu_callback_descriptor_types.zig");
const abi_core = @import("../core/abi/wgpu_core_base_types.zig");
const abi_pipeline = @import("../core/abi/wgpu_pipeline_descriptor_types.zig");
const abi_texture = @import("../core/abi/wgpu_texture_base_types.zig");
const external_texture_ops = @import("../backend/dropin_external_texture.zig");
const native = @import("../doe_wgpu_native.zig");

pub const WGPUSharedBufferMemory = ?*anyopaque;
pub const WGPUSharedFence = ?*anyopaque;
pub const WGPUSharedTextureMemory = ?*anyopaque;
const WGPUStatus_Error: abi_core.WGPUStatus = 2;
const MAGIC_SHARED_TEXTURE_MEMORY: u32 = 0xD0E1_0020;
const STYPE_SHARED_TEXTURE_MEMORY_IOSURFACE_DESCRIPTOR: abi_core.WGPUSType = 0x0005_0023;

pub const WGPUSharedBufferMemoryDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: abi_core.WGPUStringView,
};

pub const WGPUSharedBufferMemoryBeginAccessDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    fenceCount: usize,
    fences: ?[*]const WGPUSharedFence,
    signaledValues: ?[*]const u64,
};

pub const WGPUSharedBufferMemoryEndAccessState = extern struct {
    nextInChain: ?*anyopaque,
    initialized: abi_core.WGPUBool,
    fenceCount: usize,
    fences: ?[*]const WGPUSharedFence,
    signaledValues: ?[*]const u64,
};

pub const WGPUSharedBufferMemoryProperties = extern struct {
    nextInChain: ?*anyopaque,
    size: u64,
    usage: u64,
};

pub const WGPUSharedFenceDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: abi_core.WGPUStringView,
};

pub const WGPUSharedFenceExportInfo = extern struct {
    nextInChain: ?*anyopaque,
    type: u32,
};

pub const WGPUSharedTextureMemoryDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    label: abi_core.WGPUStringView,
};

pub const WGPUSharedTextureMemoryBeginAccessDescriptor = extern struct {
    nextInChain: ?*anyopaque,
    concurrentRead: abi_core.WGPUBool,
    initialized: abi_core.WGPUBool,
    fenceCount: usize,
    fences: ?[*]const WGPUSharedFence,
    signaledValues: ?[*]const u64,
};

pub const WGPUSharedTextureMemoryEndAccessState = extern struct {
    nextInChain: ?*anyopaque,
    initialized: abi_core.WGPUBool,
    fenceCount: usize,
    fences: ?[*]const WGPUSharedFence,
    signaledValues: ?[*]const u64,
};

pub const WGPUExtent3D = extern struct {
    width: u32,
    height: u32,
    depthOrArrayLayers: u32,
};

pub const WGPUSharedTextureMemoryProperties = extern struct {
    nextInChain: ?*anyopaque,
    usage: u64,
    size: WGPUExtent3D,
    format: u32,
};

const WGPUSharedTextureMemoryIOSurfaceDescriptor = extern struct {
    chain: abi_callback.WGPUChainedStruct,
    ioSurface: ?*anyopaque,
    allowStorageBinding: abi_core.WGPUBool,
};

const DoeSharedTextureMemory = struct {
    pub const TYPE_MAGIC = MAGIC_SHARED_TEXTURE_MEMORY;
    magic: u32 = TYPE_MAGIC,
    ref_count: u32 = 1,
    backend: native.BackendKind = .metal,
    mtl_device: ?*anyopaque = null,
    iosurface: ?*anyopaque = null,
    width: u32 = 0,
    height: u32 = 0,
    usage: u64 = abi_texture.WGPUTextureUsage_TextureBinding |
        abi_texture.WGPUTextureUsage_RenderAttachment |
        abi_texture.WGPUTextureUsage_CopySrc |
        abi_texture.WGPUTextureUsage_CopyDst,
    format: u32 = abi_texture.WGPUTextureFormat_BGRA8Unorm,
    in_access: bool = false,
};

extern fn CFRetain(cf: ?*anyopaque) callconv(.c) ?*anyopaque;
extern fn CFRelease(cf: ?*anyopaque) callconv(.c) void;

fn logUnsupported(comptime symbol_name: []const u8) void {
    std.log.err("doe: {s} is unsupported until the Chromium shared-image bridge imports native handles through Doe", .{symbol_name});
}

fn labelOwnedObject(raw: ?*anyopaque, label: abi_core.WGPUStringView) void {
    native.label_store.set(raw, label.data, label.length);
}

fn sharedTextureMemoryCast(raw: WGPUSharedTextureMemory) ?*DoeSharedTextureMemory {
    return native.cast(DoeSharedTextureMemory, raw);
}

fn findIOSurfaceDescriptor(
    descriptor: *const WGPUSharedTextureMemoryDescriptor,
) ?*const WGPUSharedTextureMemoryIOSurfaceDescriptor {
    var chain_raw = descriptor.nextInChain;
    while (chain_raw) |raw| {
        const chain: *const abi_callback.WGPUChainedStruct = @ptrCast(@alignCast(raw));
        if (chain.sType == STYPE_SHARED_TEXTURE_MEMORY_IOSURFACE_DESCRIPTOR) {
            return @ptrCast(@alignCast(raw));
        }
        chain_raw = chain.next;
    }
    return null;
}

fn retainCF(raw: ?*anyopaque) ?*anyopaque {
    if (comptime builtin.os.tag != .macos) return null;
    return CFRetain(raw);
}

fn releaseCF(raw: ?*anyopaque) void {
    if (comptime builtin.os.tag == .macos) {
        CFRelease(raw);
    }
}

pub fn wgpuDeviceCreateErrorBuffer(
    device: abi_core.WGPUDevice,
    descriptor: ?*const abi_pipeline.WGPUBufferDescriptor,
) callconv(.c) abi_core.WGPUBuffer {
    const dev = native.cast(native.DoeDevice, device) orelse return null;
    const buffer = native.make(native.DoeBuffer) orelse return null;
    const d = descriptor orelse &abi_pipeline.WGPUBufferDescriptor{
        .nextInChain = null,
        .label = .{ .data = null, .length = 0 },
        .usage = abi_core.WGPUBufferUsage_None,
        .size = 0,
        .mappedAtCreation = abi_core.WGPU_FALSE,
    };
    buffer.* = .{
        .error_object = true,
        .backend = dev.backend,
        .size = d.size,
        .usage = d.usage,
    };
    const raw = native.toOpaque(buffer);
    labelOwnedObject(raw, d.label);
    return raw;
}

pub fn wgpuDeviceCreateErrorTexture(
    device: abi_core.WGPUDevice,
    descriptor: ?*const abi_pipeline.WGPUTextureDescriptor,
) callconv(.c) abi_core.WGPUTexture {
    const dev = native.cast(native.DoeDevice, device) orelse return null;
    const texture = native.make(native.DoeTexture) orelse return null;
    const d = descriptor orelse &abi_pipeline.WGPUTextureDescriptor{
        .nextInChain = null,
        .label = .{ .data = null, .length = 0 },
        .usage = abi_texture.WGPUTextureUsage_None,
        .dimension = abi_texture.WGPUTextureDimension_2D,
        .size = .{ .width = 1, .height = 1, .depthOrArrayLayers = 1 },
        .format = abi_texture.WGPUTextureFormat_RGBA8Unorm,
        .mipLevelCount = 1,
        .sampleCount = 1,
        .viewFormatCount = 0,
        .viewFormats = null,
    };
    texture.* = .{
        .error_object = true,
        .backend = dev.backend,
        .format = d.format,
        .width = d.size.width,
        .height = d.size.height,
        .depth_or_array_layers = d.size.depthOrArrayLayers,
        .dimension = d.dimension,
        .mip_level_count = d.mipLevelCount,
        .sample_count = d.sampleCount,
        .usage = d.usage,
        .view_format_count = d.viewFormatCount,
    };
    const raw = native.toOpaque(texture);
    labelOwnedObject(raw, d.label);
    return raw;
}

pub fn wgpuDeviceImportSharedBufferMemory(
    device: abi_core.WGPUDevice,
    descriptor: ?*const WGPUSharedBufferMemoryDescriptor,
) callconv(.c) WGPUSharedBufferMemory {
    _ = device;
    _ = descriptor;
    logUnsupported("wgpuDeviceImportSharedBufferMemory");
    return null;
}

pub fn wgpuDeviceImportSharedFence(
    device: abi_core.WGPUDevice,
    descriptor: ?*const WGPUSharedFenceDescriptor,
) callconv(.c) WGPUSharedFence {
    _ = device;
    _ = descriptor;
    logUnsupported("wgpuDeviceImportSharedFence");
    return null;
}

pub fn wgpuDeviceImportSharedTextureMemory(
    device: abi_core.WGPUDevice,
    descriptor: ?*const WGPUSharedTextureMemoryDescriptor,
) callconv(.c) WGPUSharedTextureMemory {
    if (comptime builtin.os.tag != .macos) {
        logUnsupported("wgpuDeviceImportSharedTextureMemory(non_macos)");
        return null;
    }
    const dev = native.cast(native.DoeDevice, device) orelse return null;
    const desc = descriptor orelse return null;
    const ios_desc = findIOSurfaceDescriptor(desc) orelse {
        logUnsupported("wgpuDeviceImportSharedTextureMemory(non_iosurface)");
        return null;
    };
    const iosurface = retainCF(ios_desc.ioSurface) orelse return null;
    const imported = external_texture_ops.importIOSurface(dev.mtl_device, iosurface) orelse {
        releaseCF(iosurface);
        return null;
    };
    defer external_texture_ops.releasePlanes(imported);
    if (!imported.is_single_plane) {
        releaseCF(iosurface);
        return null;
    }

    const shared_memory = native.make(DoeSharedTextureMemory) orelse {
        releaseCF(iosurface);
        return null;
    };
    shared_memory.* = .{
        .backend = dev.backend,
        .mtl_device = dev.mtl_device,
        .iosurface = iosurface,
        .width = imported.width,
        .height = imported.height,
    };
    const raw = native.toOpaque(shared_memory);
    labelOwnedObject(raw, desc.label);
    return raw;
}

pub fn wgpuSharedBufferMemoryBeginAccess(
    shared_buffer_memory: WGPUSharedBufferMemory,
    buffer: abi_core.WGPUBuffer,
    descriptor: ?*const WGPUSharedBufferMemoryBeginAccessDescriptor,
) callconv(.c) abi_core.WGPUStatus {
    _ = shared_buffer_memory;
    _ = buffer;
    _ = descriptor;
    return WGPUStatus_Error;
}

pub fn wgpuSharedBufferMemoryCreateBuffer(
    shared_buffer_memory: WGPUSharedBufferMemory,
    descriptor: ?*const abi_pipeline.WGPUBufferDescriptor,
) callconv(.c) abi_core.WGPUBuffer {
    _ = shared_buffer_memory;
    _ = descriptor;
    return null;
}

pub fn wgpuSharedBufferMemoryEndAccess(
    shared_buffer_memory: WGPUSharedBufferMemory,
    buffer: abi_core.WGPUBuffer,
    descriptor: ?*WGPUSharedBufferMemoryEndAccessState,
) callconv(.c) abi_core.WGPUStatus {
    _ = shared_buffer_memory;
    _ = buffer;
    if (descriptor) |state| {
        state.initialized = abi_core.WGPU_FALSE;
        state.fenceCount = 0;
        state.fences = null;
        state.signaledValues = null;
    }
    return WGPUStatus_Error;
}

pub fn wgpuSharedBufferMemoryGetProperties(
    shared_buffer_memory: WGPUSharedBufferMemory,
    properties: ?*WGPUSharedBufferMemoryProperties,
) callconv(.c) abi_core.WGPUStatus {
    _ = shared_buffer_memory;
    if (properties) |out| {
        out.size = 0;
        out.usage = 0;
    }
    return WGPUStatus_Error;
}

pub fn wgpuSharedBufferMemoryIsDeviceLost(shared_buffer_memory: WGPUSharedBufferMemory) callconv(.c) abi_core.WGPUBool {
    _ = shared_buffer_memory;
    return abi_core.WGPU_TRUE;
}

pub fn wgpuSharedBufferMemorySetLabel(shared_buffer_memory: WGPUSharedBufferMemory, label: abi_core.WGPUStringView) callconv(.c) void {
    _ = shared_buffer_memory;
    _ = label;
}

pub fn wgpuSharedBufferMemoryAddRef(shared_buffer_memory: WGPUSharedBufferMemory) callconv(.c) void {
    _ = shared_buffer_memory;
}

pub fn wgpuSharedBufferMemoryRelease(shared_buffer_memory: WGPUSharedBufferMemory) callconv(.c) void {
    _ = shared_buffer_memory;
}

pub fn wgpuSharedBufferMemoryEndAccessStateFreeMembers(state: WGPUSharedBufferMemoryEndAccessState) callconv(.c) void {
    _ = state;
}

pub fn wgpuSharedFenceExportInfo(shared_fence: WGPUSharedFence, info: ?*WGPUSharedFenceExportInfo) callconv(.c) void {
    _ = shared_fence;
    if (info) |out| {
        out.type = 0;
    }
}

pub fn wgpuSharedFenceAddRef(shared_fence: WGPUSharedFence) callconv(.c) void {
    _ = shared_fence;
}

pub fn wgpuSharedFenceRelease(shared_fence: WGPUSharedFence) callconv(.c) void {
    _ = shared_fence;
}

pub fn wgpuSharedTextureMemoryBeginAccess(
    shared_texture_memory: WGPUSharedTextureMemory,
    texture: abi_core.WGPUTexture,
    descriptor: ?*const WGPUSharedTextureMemoryBeginAccessDescriptor,
) callconv(.c) abi_core.WGPUStatus {
    const shared_memory = sharedTextureMemoryCast(shared_texture_memory) orelse return WGPUStatus_Error;
    const tex = native.cast(native.DoeTexture, texture) orelse return WGPUStatus_Error;
    if (shared_memory.in_access or tex.error_object or tex.mtl == null) {
        return WGPUStatus_Error;
    }
    if (descriptor) |desc| {
        if (desc.fenceCount != 0) return WGPUStatus_Error;
    }
    shared_memory.in_access = true;
    return abi_core.WGPUStatus_Success;
}

pub fn wgpuSharedTextureMemoryCreateTexture(
    shared_texture_memory: WGPUSharedTextureMemory,
    descriptor: ?*const abi_pipeline.WGPUTextureDescriptor,
) callconv(.c) abi_core.WGPUTexture {
    const shared_memory = sharedTextureMemoryCast(shared_texture_memory) orelse return null;
    const default_desc = abi_pipeline.WGPUTextureDescriptor{
        .nextInChain = null,
        .label = .{ .data = null, .length = 0 },
        .usage = shared_memory.usage,
        .dimension = abi_texture.WGPUTextureDimension_2D,
        .size = .{
            .width = shared_memory.width,
            .height = shared_memory.height,
            .depthOrArrayLayers = 1,
        },
        .format = shared_memory.format,
        .mipLevelCount = 1,
        .sampleCount = 1,
        .viewFormatCount = 0,
        .viewFormats = null,
    };
    const desc = descriptor orelse &default_desc;
    if (desc.format != shared_memory.format or
        desc.dimension != abi_texture.WGPUTextureDimension_2D or
        desc.size.width != shared_memory.width or
        desc.size.height != shared_memory.height or
        desc.size.depthOrArrayLayers != 1 or
        desc.mipLevelCount != 1 or
        desc.sampleCount != 1)
    {
        return null;
    }
    const imported = external_texture_ops.importIOSurface(
        shared_memory.mtl_device,
        shared_memory.iosurface,
    ) orelse return null;
    if (!imported.is_single_plane) {
        external_texture_ops.releasePlanes(imported);
        return null;
    }

    const texture = native.make(native.DoeTexture) orelse {
        external_texture_ops.releasePlanes(imported);
        return null;
    };
    texture.* = .{
        .error_object = false,
        .backend = shared_memory.backend,
        .mtl = imported.plane0,
        .format = desc.format,
        .width = desc.size.width,
        .height = desc.size.height,
        .depth_or_array_layers = desc.size.depthOrArrayLayers,
        .dimension = desc.dimension,
        .mip_level_count = desc.mipLevelCount,
        .sample_count = desc.sampleCount,
        .usage = desc.usage,
        .view_format_count = desc.viewFormatCount,
    };
    const raw = native.toOpaque(texture);
    labelOwnedObject(raw, desc.label);
    return raw;
}

pub fn wgpuSharedTextureMemoryEndAccess(
    shared_texture_memory: WGPUSharedTextureMemory,
    texture: abi_core.WGPUTexture,
    descriptor: ?*WGPUSharedTextureMemoryEndAccessState,
) callconv(.c) abi_core.WGPUStatus {
    const shared_memory = sharedTextureMemoryCast(shared_texture_memory) orelse return WGPUStatus_Error;
    const tex = native.cast(native.DoeTexture, texture) orelse return WGPUStatus_Error;
    if (descriptor) |state| {
        state.initialized = abi_core.WGPU_TRUE;
        state.fenceCount = 0;
        state.fences = null;
        state.signaledValues = null;
    }
    if (!shared_memory.in_access or tex.error_object or tex.mtl == null) {
        return WGPUStatus_Error;
    }
    shared_memory.in_access = false;
    return abi_core.WGPUStatus_Success;
}

pub fn wgpuSharedTextureMemoryGetProperties(
    shared_texture_memory: WGPUSharedTextureMemory,
    properties: ?*WGPUSharedTextureMemoryProperties,
) callconv(.c) abi_core.WGPUStatus {
    const shared_memory = sharedTextureMemoryCast(shared_texture_memory) orelse return WGPUStatus_Error;
    if (properties) |out| {
        out.usage = shared_memory.usage;
        out.size = .{
            .width = shared_memory.width,
            .height = shared_memory.height,
            .depthOrArrayLayers = 1,
        };
        out.format = shared_memory.format;
    }
    return abi_core.WGPUStatus_Success;
}

pub fn wgpuSharedTextureMemoryIsDeviceLost(shared_texture_memory: WGPUSharedTextureMemory) callconv(.c) abi_core.WGPUBool {
    if (sharedTextureMemoryCast(shared_texture_memory) == null) {
        return abi_core.WGPU_TRUE;
    }
    return abi_core.WGPU_FALSE;
}

pub fn wgpuSharedTextureMemorySetLabel(shared_texture_memory: WGPUSharedTextureMemory, label: abi_core.WGPUStringView) callconv(.c) void {
    if (sharedTextureMemoryCast(shared_texture_memory) != null) {
        labelOwnedObject(shared_texture_memory, label);
    }
}

pub fn wgpuSharedTextureMemoryAddRef(shared_texture_memory: WGPUSharedTextureMemory) callconv(.c) void {
    const shared_memory = sharedTextureMemoryCast(shared_texture_memory) orelse return;
    shared_memory.ref_count +|= 1;
}

pub fn wgpuSharedTextureMemoryRelease(shared_texture_memory: WGPUSharedTextureMemory) callconv(.c) void {
    const shared_memory = sharedTextureMemoryCast(shared_texture_memory) orelse return;
    if (!native.object_should_destroy(shared_memory)) return;
    native.label_store.remove(shared_texture_memory);
    if (shared_memory.iosurface) |iosurface| {
        releaseCF(iosurface);
    }
    native.alloc.destroy(shared_memory);
}

pub fn wgpuSharedTextureMemoryEndAccessStateFreeMembers(state: WGPUSharedTextureMemoryEndAccessState) callconv(.c) void {
    _ = state;
}

test "browser error object procs return Doe-owned releasable handles" {
    var device = native.DoeDevice{};
    const device_raw = native.toOpaque(&device);

    const buffer_desc = abi_pipeline.WGPUBufferDescriptor{
        .nextInChain = null,
        .label = .{ .data = "error-buffer".ptr, .length = "error-buffer".len },
        .usage = abi_core.WGPUBufferUsage_CopyDst,
        .size = 64,
        .mappedAtCreation = abi_core.WGPU_FALSE,
    };
    const buffer_raw = wgpuDeviceCreateErrorBuffer(device_raw, &buffer_desc);
    const buffer = native.cast(native.DoeBuffer, buffer_raw) orelse return error.TestExpectedEqual;
    try std.testing.expect(buffer.error_object);
    try std.testing.expectEqual(device.backend, buffer.backend);
    try std.testing.expectEqual(buffer_desc.size, buffer.size);
    try std.testing.expectEqual(buffer_desc.usage, buffer.usage);
    native.doeNativeBufferRelease(buffer_raw);

    const texture_desc = abi_pipeline.WGPUTextureDescriptor{
        .nextInChain = null,
        .label = .{ .data = "error-texture".ptr, .length = "error-texture".len },
        .usage = abi_texture.WGPUTextureUsage_TextureBinding,
        .dimension = abi_texture.WGPUTextureDimension_2D,
        .size = .{ .width = 4, .height = 2, .depthOrArrayLayers = 1 },
        .format = abi_texture.WGPUTextureFormat_RGBA8Unorm,
        .mipLevelCount = 1,
        .sampleCount = 1,
        .viewFormatCount = 0,
        .viewFormats = null,
    };
    const texture_raw = wgpuDeviceCreateErrorTexture(device_raw, &texture_desc);
    const texture = native.cast(native.DoeTexture, texture_raw) orelse return error.TestExpectedEqual;
    try std.testing.expect(texture.error_object);
    try std.testing.expectEqual(device.backend, texture.backend);
    try std.testing.expectEqual(texture_desc.format, texture.format);
    try std.testing.expectEqual(texture_desc.size.width, texture.width);
    try std.testing.expectEqual(texture_desc.size.height, texture.height);
    try std.testing.expectEqual(texture_desc.usage, texture.usage);
    try std.testing.expectEqual(@as(abi_core.WGPUTextureView, null), native.doeNativeTextureCreateView(texture_raw, null));
    native.doeNativeTextureRelease(texture_raw);
}
