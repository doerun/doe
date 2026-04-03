// doe_bind_group_native.zig — Bind group, bind group layout, and pipeline layout
// C ABI exports for the Doe native Metal/Vulkan backend. Sharded from doe_wgpu_native.zig.

const native = @import("doe_native_base.zig");
const abi_base = @import("core/abi/wgpu_base_types.zig");
const abi_descriptor = @import("core/abi/wgpu_descriptor_types.zig");

const alloc = native.alloc;
const make = native.make;
const cast = native.cast;
const toOpaque = native.toOpaque;
const MAX_BIND = native.MAX_BIND;
const MAX_COMPUTE_BIND_GROUPS = native.MAX_COMPUTE_BIND_GROUPS;
const label_store = native.label_store;

const DoeDevice = native.DoeDevice;
const DoeBuffer = native.DoeBuffer;
const DoeTexture = native.DoeTexture;
const DoeSampler = native.DoeSampler;
const DoeBindGroupLayoutEntry = native.DoeBindGroupLayoutEntry;
const DoeBindGroupLayout = native.DoeBindGroupLayout;
const DoeBindGroup = native.DoeBindGroup;
const DoePipelineLayout = native.DoePipelineLayout;
const DoeTextureView = native.DoeTextureView;
const DoeExternalTexture = @import("doe_external_texture_native.zig").DoeExternalTexture;

const RESOURCE_KIND_NONE: u32 = 0;
const RESOURCE_KIND_BUFFER: u32 = 1;
const RESOURCE_KIND_SAMPLER: u32 = 2;
const RESOURCE_KIND_TEXTURE: u32 = 3;
const RESOURCE_KIND_STORAGE_TEXTURE: u32 = 4;
const RESOURCE_KIND_EXTERNAL_TEXTURE: u32 = 5;

fn chained_struct(raw: ?*anyopaque) ?*const abi_descriptor.WGPUChainedStruct {
    const ptr = raw orelse return null;
    return @ptrCast(@alignCast(ptr));
}

fn has_chain_type(raw: ?*anyopaque, s_type: abi_base.WGPUSType) bool {
    const chain = chained_struct(raw) orelse return false;
    return chain.sType == s_type;
}

fn external_texture_layout_chain(raw: ?*anyopaque) ?*const abi_descriptor.WGPUExternalTextureBindingLayout {
    if (!has_chain_type(raw, abi_base.WGPUSType_ExternalTextureBindingLayout)) return null;
    const ptr = raw orelse return null;
    return @ptrCast(@alignCast(ptr));
}

fn external_texture_entry_chain(raw: ?*anyopaque) ?*const abi_descriptor.WGPUExternalTextureBindingEntry {
    if (!has_chain_type(raw, abi_base.WGPUSType_ExternalTextureBindingEntry)) return null;
    const ptr = raw orelse return null;
    return @ptrCast(@alignCast(ptr));
}

fn classify_layout_entry(entry: abi_descriptor.WGPUBindGroupLayoutEntry) DoeBindGroupLayoutEntry {
    var out = DoeBindGroupLayoutEntry{
        .binding = entry.binding,
        .resource_kind = RESOURCE_KIND_NONE,
        .binding_array_size = entry.bindingArraySize,
    };
    if (external_texture_layout_chain(entry.nextInChain) != null) {
        out.resource_kind = RESOURCE_KIND_EXTERNAL_TEXTURE;
        return out;
    }
    if (entry.storageTexture.access != 0 or entry.storageTexture.format != 0 or entry.storageTexture.viewDimension != 0) {
        out.resource_kind = RESOURCE_KIND_STORAGE_TEXTURE;
        out.texture_sample_type = entry.storageTexture.access;
        out.texture_view_dimension = entry.storageTexture.viewDimension;
        return out;
    }
    if (entry.texture.sampleType != 0 or entry.texture.viewDimension != 0 or entry.texture.multisampled != 0) {
        out.resource_kind = RESOURCE_KIND_TEXTURE;
        out.texture_sample_type = entry.texture.sampleType;
        out.texture_view_dimension = entry.texture.viewDimension;
        out.texture_multisampled = entry.texture.multisampled != 0;
        return out;
    }
    if (entry.sampler.type != 0) {
        out.resource_kind = RESOURCE_KIND_SAMPLER;
        return out;
    }
    if (entry.buffer.type != 0 or entry.buffer.minBindingSize != 0 or entry.buffer.hasDynamicOffset != 0) {
        out.resource_kind = RESOURCE_KIND_BUFFER;
    }
    return out;
}

fn infer_texture_sample_type(tex: *DoeTexture) u32 {
    return switch (tex.format) {
        abi_base.WGPUTextureFormat_Depth16Unorm,
        abi_base.WGPUTextureFormat_Depth24Plus,
        abi_base.WGPUTextureFormat_Depth24PlusStencil8,
        abi_base.WGPUTextureFormat_Depth32Float,
        abi_base.WGPUTextureFormat_Depth32FloatStencil8,
        => abi_base.WGPUTextureSampleType_Depth,
        abi_base.WGPUTextureFormat_R8Uint,
        abi_base.WGPUTextureFormat_R16Uint,
        abi_base.WGPUTextureFormat_RG8Uint,
        abi_base.WGPUTextureFormat_R32Uint,
        abi_base.WGPUTextureFormat_RG16Uint,
        abi_base.WGPUTextureFormat_RGBA8Uint,
        abi_base.WGPUTextureFormat_RGB10A2Uint,
        abi_base.WGPUTextureFormat_RG32Uint,
        abi_base.WGPUTextureFormat_RGBA16Uint,
        abi_base.WGPUTextureFormat_RGBA32Uint,
        => abi_base.WGPUTextureSampleType_Uint,
        abi_base.WGPUTextureFormat_R8Sint,
        abi_base.WGPUTextureFormat_R16Sint,
        abi_base.WGPUTextureFormat_RG8Sint,
        abi_base.WGPUTextureFormat_R32Sint,
        abi_base.WGPUTextureFormat_RG16Sint,
        abi_base.WGPUTextureFormat_RGBA8Sint,
        abi_base.WGPUTextureFormat_RG32Sint,
        abi_base.WGPUTextureFormat_RGBA16Sint,
        abi_base.WGPUTextureFormat_RGBA32Sint,
        => abi_base.WGPUTextureSampleType_Sint,
        else => abi_base.WGPUTextureSampleType_Float,
    };
}

fn resolve_view_dimension(view: *DoeTextureView) u32 {
    if (view.dimension != 0) return view.dimension;
    if (view.tex.texture_binding_view_dimension != 0) return view.tex.texture_binding_view_dimension;
    return switch (view.tex.dimension) {
        abi_base.WGPUTextureDimension_1D => abi_base.WGPUTextureViewDimension_1D,
        abi_base.WGPUTextureDimension_3D => abi_base.WGPUTextureViewDimension_3D,
        else => abi_base.WGPUTextureViewDimension_2D,
    };
}

fn texture_aspect_matches(tex: *DoeTexture, view: *DoeTextureView) bool {
    const aspect = if (view.aspect != 0) view.aspect else abi_base.WGPUTextureAspect_All;
    return switch (aspect) {
        abi_base.WGPUTextureAspect_All => true,
        abi_base.WGPUTextureAspect_DepthOnly => switch (tex.format) {
            abi_base.WGPUTextureFormat_Stencil8 => false,
            abi_base.WGPUTextureFormat_Depth16Unorm, abi_base.WGPUTextureFormat_Depth24Plus, abi_base.WGPUTextureFormat_Depth24PlusStencil8, abi_base.WGPUTextureFormat_Depth32Float, abi_base.WGPUTextureFormat_Depth32FloatStencil8 => true,
            else => false,
        },
        abi_base.WGPUTextureAspect_StencilOnly => switch (tex.format) {
            abi_base.WGPUTextureFormat_Stencil8, abi_base.WGPUTextureFormat_Depth24PlusStencil8, abi_base.WGPUTextureFormat_Depth32FloatStencil8 => true,
            else => false,
        },
        else => false,
    };
}

fn storage_texture_access_supported(access: u32) bool {
    return switch (access) {
        abi_base.WGPUStorageTextureAccess_Undefined, abi_base.WGPUStorageTextureAccess_WriteOnly, abi_base.WGPUStorageTextureAccess_ReadOnly, abi_base.WGPUStorageTextureAccess_ReadWrite => true,
        else => false,
    };
}

fn texture_view_matches_layout(layout_entry: DoeBindGroupLayoutEntry, view: *DoeTextureView) bool {
    const tex = view.tex;
    if (layout_entry.texture_multisampled != (tex.sample_count > 1)) return false;
    if (layout_entry.texture_view_dimension != 0 and
        layout_entry.texture_view_dimension != abi_base.WGPUTextureViewDimension_Undefined and
        layout_entry.texture_view_dimension != resolve_view_dimension(view)) return false;
    if (layout_entry.texture_sample_type != 0 and
        layout_entry.texture_sample_type != abi_base.WGPUTextureSampleType_Undefined and
        layout_entry.texture_sample_type != infer_texture_sample_type(tex)) return false;
    if (!texture_aspect_matches(tex, view)) return false;
    return true;
}

fn storage_texture_matches_layout(layout_entry: DoeBindGroupLayoutEntry, view: *DoeTextureView) bool {
    switch (view.tex.format) {
        abi_base.WGPUTextureFormat_Stencil8, abi_base.WGPUTextureFormat_Depth16Unorm, abi_base.WGPUTextureFormat_Depth24Plus, abi_base.WGPUTextureFormat_Depth24PlusStencil8, abi_base.WGPUTextureFormat_Depth32Float, abi_base.WGPUTextureFormat_Depth32FloatStencil8 => return false,
        else => {},
    }
    const usage = view.usage | view.tex.usage;
    if ((usage & abi_base.WGPUTextureUsage_StorageBinding) == 0) return false;
    if (layout_entry.texture_view_dimension != 0 and
        layout_entry.texture_view_dimension != abi_base.WGPUTextureViewDimension_Undefined and
        layout_entry.texture_view_dimension != resolve_view_dimension(view)) return false;
    if (!texture_aspect_matches(view.tex, view)) return false;
    return storage_texture_access_supported(layout_entry.texture_sample_type);
}

fn find_layout_entry(layout: *DoeBindGroupLayout, binding: u32) ?DoeBindGroupLayoutEntry {
    const entries = layout.entries orelse return null;
    for (entries) |entry| {
        if (entry.binding == binding) return entry;
    }
    return null;
}

fn retain_buffer(bg: *DoeBindGroup, binding: usize, buffer: *DoeBuffer) void {
    native.object_add_ref(DoeBuffer, toOpaque(buffer));
    bg.retained_buffers[binding] = buffer;
}

fn retain_texture_view(bg: *DoeBindGroup, binding: usize, view: *DoeTextureView) void {
    native.object_add_ref(DoeTextureView, toOpaque(view));
    bg.retained_texture_views[binding] = view;
}

fn retain_sampler(bg: *DoeBindGroup, binding: usize, sampler: *DoeSampler) void {
    native.object_add_ref(DoeSampler, toOpaque(sampler));
    bg.retained_samplers[binding] = sampler;
}

fn retain_external_texture(bg: *DoeBindGroup, binding: usize, external_texture: abi_base.WGPUExternalTexture) void {
    native.object_add_ref(DoeExternalTexture, external_texture);
    bg.retained_external_textures[binding] = external_texture;
}

fn resolve_external_texture(entry: abi_descriptor.WGPUBindGroupEntry) ?abi_base.WGPUExternalTexture {
    if (external_texture_entry_chain(entry.nextInChain)) |chain| {
        return chain.externalTexture;
    }
    return null;
}

// ============================================================
// Bind Group Layout / Bind Group / Pipeline Layout
// ============================================================

pub export fn doeNativeDeviceCreateBindGroupLayout(dev_raw: ?*anyopaque, desc: ?*const abi_descriptor.WGPUBindGroupLayoutDescriptor) callconv(.c) ?*anyopaque {
    _ = dev_raw;
    const d = desc orelse return null;
    if (d.entryCount > 0 and d.entries == null) {
        return null;
    }
    const bgl = make(DoeBindGroupLayout) orelse return null;
    var stored_entries: ?[]DoeBindGroupLayoutEntry = null;
    if (d.entryCount > 0) {
        stored_entries = alloc.alloc(DoeBindGroupLayoutEntry, d.entryCount) catch {
            alloc.destroy(bgl);
            return null;
        };
        for (d.entries.?[0..d.entryCount], 0..) |entry, i| {
            stored_entries.?[i] = classify_layout_entry(entry);
        }
    }
    bgl.* = .{
        .entry_count = @intCast(d.entryCount),
        .entries = stored_entries,
    };
    const result = toOpaque(bgl);
    label_store.set(result, d.label.data, d.label.length);
    return result;
}

pub export fn doeNativeBindGroupLayoutRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeBindGroupLayout, raw)) |l| {
        if (!native.object_should_destroy(l)) return;
        label_store.remove(raw);
        if (l.entries) |entries| alloc.free(entries);
        alloc.destroy(l);
    }
}

pub export fn doeNativeDeviceCreateBindGroup(dev_raw: ?*anyopaque, desc: ?*const abi_descriptor.WGPUBindGroupDescriptor) callconv(.c) ?*anyopaque {
    const d = desc orelse return null;
    const bg = make(DoeBindGroup) orelse return null;
    bg.* = .{};
    const layout = cast(DoeBindGroupLayout, d.layout);

    // For Vulkan devices, store the DoeBuffer* opaque pointer in buffers[] instead
    // of the MTL handle, so the compute dispatch can look up the vk_id at submit time.
    const is_vulkan = if (cast(DoeDevice, dev_raw)) |dev| dev.backend == .vulkan else false;

    for (d.entries[0..d.entryCount]) |e| {
        if (layout) |bgl| {
            if (find_layout_entry(bgl, e.binding)) |layout_entry| {
                if (layout_entry.resource_kind == RESOURCE_KIND_TEXTURE) {
                    const view = cast(DoeTextureView, e.textureView) orelse {
                        alloc.destroy(bg);
                        return null;
                    };
                    if (!texture_view_matches_layout(layout_entry, view)) {
                        alloc.destroy(bg);
                        return null;
                    }
                } else if (layout_entry.resource_kind == RESOURCE_KIND_STORAGE_TEXTURE) {
                    const view = cast(DoeTextureView, e.textureView) orelse {
                        alloc.destroy(bg);
                        return null;
                    };
                    if (!storage_texture_matches_layout(layout_entry, view)) {
                        alloc.destroy(bg);
                        return null;
                    }
                } else if (layout_entry.resource_kind == RESOURCE_KIND_EXTERNAL_TEXTURE) {
                    const external_texture = resolve_external_texture(e) orelse {
                        alloc.destroy(bg);
                        return null;
                    };
                    const ext = native.cast(DoeExternalTexture, external_texture) orelse {
                        alloc.destroy(bg);
                        return null;
                    };
                    if (ext.expired or ext.plane0 == null) {
                        alloc.destroy(bg);
                        return null;
                    }
                }
            }
        }
        if (e.binding < MAX_BIND) {
            if (cast(DoeBuffer, e.buffer)) |doe_buf| {
                if (is_vulkan) {
                    // Store the DoeBuffer handle — dispatch reads vk_id from it.
                    bg.buffers[e.binding] = toOpaque(doe_buf);
                } else {
                    bg.buffers[e.binding] = doe_buf.mtl;
                }
                bg.offsets[e.binding] = e.offset;
                bg.buffer_sizes[e.binding] = doe_buf.size;
                retain_buffer(bg, e.binding, doe_buf);
            } else if (cast(DoeTextureView, e.textureView)) |view| {
                bg.textures[e.binding] = if (view.handle) |handle| handle else view.tex.mtl;
                bg.texture_views[e.binding] = toOpaque(view);
                retain_texture_view(bg, e.binding, view);
            } else if (cast(DoeSampler, e.sampler)) |sampler| {
                bg.samplers[e.binding] = sampler.mtl;
                retain_sampler(bg, e.binding, sampler);
            } else if (resolve_external_texture(e)) |external_texture| {
                const ext_mod = @import("doe_external_texture_native.zig");
                const ext = native.cast(DoeExternalTexture, external_texture) orelse continue;
                // Resolve the MTL handle from plane0 (works for both DoeTextureView
                // and native-imported paths).
                const p0_mtl = ext_mod.resolvePlane0MtlHandle(ext);
                bg.textures[e.binding] = p0_mtl;
                bg.texture_views[e.binding] = ext.plane0;
                retain_external_texture(bg, e.binding, external_texture);
                if (ext_mod.isMultiPlane(ext)) {
                    const next_slot = e.binding + 1;
                    if (next_slot < MAX_BIND) {
                        bg.textures[next_slot] = ext_mod.resolvePlane1MtlHandle(ext);
                        bg.texture_views[next_slot] = ext.plane1;
                        if (next_slot + 1 > bg.count) bg.count = next_slot + 1;
                    }
                }
            } else continue;
            if (e.binding + 1 > bg.count) bg.count = e.binding + 1;
        }
    }
    const bg_result = toOpaque(bg);
    label_store.set(bg_result, d.label.data, d.label.length);
    return bg_result;
}

pub export fn doeNativeBindGroupRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoeBindGroup, raw)) |g| {
        if (!native.object_should_destroy(g)) return;
        label_store.remove(raw);
        for (g.retained_buffers) |maybe_buffer| {
            if (maybe_buffer) |buffer| native.doeNativeBufferRelease(toOpaque(buffer));
        }
        for (g.retained_texture_views) |maybe_view| {
            if (maybe_view) |view| native.doeNativeTextureViewRelease(toOpaque(view));
        }
        for (g.retained_samplers) |maybe_sampler| {
            if (maybe_sampler) |sampler| native.doeNativeSamplerRelease(toOpaque(sampler));
        }
        for (g.retained_external_textures) |external_texture| {
            if (external_texture != null) native.doeNativeExternalTextureRelease(external_texture);
        }
        alloc.destroy(g);
    }
}

pub export fn doeNativeDeviceCreatePipelineLayout(dev_raw: ?*anyopaque, desc: ?*const abi_descriptor.WGPUPipelineLayoutDescriptor) callconv(.c) ?*anyopaque {
    _ = dev_raw;
    const pl = make(DoePipelineLayout) orelse return null;
    pl.* = .{};
    const pl_result = toOpaque(pl);
    if (desc) |pd| {
        if (pd.bindGroupLayoutCount > MAX_COMPUTE_BIND_GROUPS) {
            doeNativePipelineLayoutRelease(pl_result);
            return null;
        }
        pl.immediate_size = pd.immediateSize;
        pl.bind_group_layout_count = @intCast(pd.bindGroupLayoutCount);
        for (0..pd.bindGroupLayoutCount) |index| {
            const layout = cast(DoeBindGroupLayout, pd.bindGroupLayouts[index]) orelse {
                doeNativePipelineLayoutRelease(pl_result);
                return null;
            };
            native.object_add_ref(DoeBindGroupLayout, toOpaque(layout));
            pl.bind_group_layouts[index] = layout;
        }
        label_store.set(pl_result, pd.label.data, pd.label.length);
    }
    return pl_result;
}

pub export fn doeNativePipelineLayoutRelease(raw: ?*anyopaque) callconv(.c) void {
    if (cast(DoePipelineLayout, raw)) |l| {
        if (!native.object_should_destroy(l)) return;
        label_store.remove(raw);
        for (l.bind_group_layouts[0..l.bind_group_layout_count]) |layout| {
            if (layout) |bgl| doeNativeBindGroupLayoutRelease(toOpaque(bgl));
        }
        alloc.destroy(l);
    }
}
