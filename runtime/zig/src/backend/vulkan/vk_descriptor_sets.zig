const std = @import("std");
const c = @import("vk_constants.zig");
const vk_binding_hash = @import("vk_binding_hash.zig");
const vk_compute_sync = @import("vk_compute_sync.zig");
const vk_formats = @import("vk_formats.zig");
const vk_resources = @import("vk_resources.zig");
const vk_upload = @import("vk_upload.zig");
const model_binding_types = @import("../../model_binding_value_types.zig");
const model_compute_types = @import("../../model_compute_types.zig");
const model_texture_types = @import("../../model_texture_value_types.zig");

const VK_NULL_U64 = c.VK_NULL_U64;
const STACK_DESCRIPTOR_BINDING_CAPACITY: usize = vk_compute_sync.MAX_TRACKED_COMPUTE_BINDINGS;

const DescriptorInfoKind = enum {
    buffer,
    image,
};

const PendingDescriptorWrite = struct {
    set_index: u32,
    binding: u32,
    descriptor_type: u32,
    kind: DescriptorInfoKind,
    info_index: usize,
};

pub fn prepare_descriptor_sets(
    self: anytype,
    bindings: ?[]const model_compute_types.KernelBinding,
    initialize_buffers_on_create: bool,
    stash_active_descriptor_state: anytype,
    activate_cached_descriptor_state: anytype,
) !void {
    if (self.descriptor_set_count == 0) return;
    const bs = bindings orelse return error.InvalidArgument;
    const descriptor_bindings_hash = compute_descriptor_bindings_hash(bs);
    try prepare_descriptor_sets_with_hash(
        self,
        bs,
        descriptor_bindings_hash,
        initialize_buffers_on_create,
        stash_active_descriptor_state,
        activate_cached_descriptor_state,
    );
}

pub fn prepare_descriptor_sets_prehashed(
    self: anytype,
    bindings: ?[]const model_compute_types.KernelBinding,
    descriptor_bindings_hash: u64,
    initialize_buffers_on_create: bool,
    stash_active_descriptor_state: anytype,
    activate_cached_descriptor_state: anytype,
) !void {
    if (self.descriptor_set_count == 0) return;
    const bs = bindings orelse return error.InvalidArgument;
    try prepare_descriptor_sets_with_hash(
        self,
        bs,
        descriptor_bindings_hash,
        initialize_buffers_on_create,
        stash_active_descriptor_state,
        activate_cached_descriptor_state,
    );
}

fn prepare_descriptor_sets_with_hash(
    self: anytype,
    bs: []const model_compute_types.KernelBinding,
    descriptor_bindings_hash: u64,
    initialize_buffers_on_create: bool,
    stash_active_descriptor_state: anytype,
    activate_cached_descriptor_state: anytype,
) !void {
    if (self.has_descriptor_pool and self.has_current_descriptor_bindings_hash and descriptor_bindings_hash == self.current_descriptor_bindings_hash) {
        return;
    }
    if (self.has_descriptor_pool and self.has_current_descriptor_bindings_hash) {
        try stash_active_descriptor_state(self);
        if (activate_cached_descriptor_state(self, descriptor_bindings_hash)) {
            return;
        }
    }
    if (!self.recorded_submit_replay_active and (self.has_deferred_submissions or self.pending_uploads.items.len > 0)) {
        _ = try vk_upload.flush_queue(self);
    }
    try ensure_descriptor_pool(self, bs);
    if (can_prepare_stack_buffer_descriptors(bs)) {
        try prepare_stack_buffer_descriptors(
            self,
            bs,
            descriptor_bindings_hash,
            initialize_buffers_on_create,
        );
        return;
    }
    try prepare_general_descriptors(
        self,
        bs,
        descriptor_bindings_hash,
        initialize_buffers_on_create,
    );
}

fn can_prepare_stack_buffer_descriptors(bindings: []const model_compute_types.KernelBinding) bool {
    if (bindings.len > STACK_DESCRIPTOR_BINDING_CAPACITY) return false;
    for (bindings) |binding| {
        if (binding.resource_kind != .buffer) return false;
    }
    return true;
}

fn prepare_stack_buffer_descriptors(
    self: anytype,
    bindings: []const model_compute_types.KernelBinding,
    descriptor_bindings_hash: u64,
    initialize_buffers_on_create: bool,
) !void {
    var buffer_infos: [STACK_DESCRIPTOR_BINDING_CAPACITY]c.VkDescriptorBufferInfo = undefined;
    var writes: [STACK_DESCRIPTOR_BINDING_CAPACITY]c.VkWriteDescriptorSet = undefined;
    var retired_promoted_buffers: [STACK_DESCRIPTOR_BINDING_CAPACITY]vk_resources.ComputeBuffer = undefined;
    var retired_count: usize = 0;
    defer {
        for (retired_promoted_buffers[0..retired_count]) |buffer| {
            vk_resources.release_compute_buffer(self, buffer);
        }
    }

    var write_count: usize = 0;
    for (bindings) |binding| {
        const descriptor_type = try descriptor_type_for_binding(binding);
        const promotion = try vk_resources.ensure_compute_buffer_for_binding(
            self,
            binding,
            initialize_buffers_on_create,
        );
        if (promotion.retired_source) |retired_source| {
            retired_promoted_buffers[retired_count] = retired_source;
            retired_count += 1;
        }
        const compute_buffer = promotion.buffer;
        buffer_infos[write_count] = .{
            .buffer = compute_buffer.buffer,
            .offset = binding.buffer_offset,
            .range = try descriptor_range(binding, compute_buffer.size),
        };
        writes[write_count] = .{
            .sType = c.VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
            .pNext = null,
            .dstSet = self.descriptor_sets[@intCast(binding.group)],
            .dstBinding = binding.binding,
            .dstArrayElement = 0,
            .descriptorCount = 1,
            .descriptorType = descriptor_type,
            .pImageInfo = null,
            .pBufferInfo = @ptrCast(&buffer_infos[write_count]),
            .pTexelBufferView = null,
        };
        write_count += 1;
    }

    if (write_count > 0) {
        c.vkUpdateDescriptorSets(self.device, @intCast(write_count), writes[0..write_count].ptr, 0, null);
    }
    self.current_descriptor_bindings_hash = descriptor_bindings_hash;
    self.has_current_descriptor_bindings_hash = true;
}

fn prepare_general_descriptors(
    self: anytype,
    bindings: []const model_compute_types.KernelBinding,
    descriptor_bindings_hash: u64,
    initialize_buffers_on_create: bool,
) !void {
    var buffer_infos = std.ArrayListUnmanaged(c.VkDescriptorBufferInfo){};
    defer buffer_infos.deinit(self.allocator);
    var image_infos = std.ArrayListUnmanaged(c.VkDescriptorImageInfo){};
    defer image_infos.deinit(self.allocator);
    var retired_promoted_buffers = std.ArrayListUnmanaged(vk_resources.ComputeBuffer){};
    defer {
        for (retired_promoted_buffers.items) |buffer| {
            vk_resources.release_compute_buffer(self, buffer);
        }
        retired_promoted_buffers.deinit(self.allocator);
    }
    var pending_writes = std.ArrayListUnmanaged(PendingDescriptorWrite){};
    defer pending_writes.deinit(self.allocator);
    var writes = std.ArrayListUnmanaged(c.VkWriteDescriptorSet){};
    defer writes.deinit(self.allocator);

    for (bindings) |binding| {
        const descriptor_type = try descriptor_type_for_binding(binding);
        switch (binding.resource_kind) {
            .buffer => {
                const promotion = try vk_resources.ensure_compute_buffer_for_binding(
                    self,
                    binding,
                    initialize_buffers_on_create,
                );
                if (promotion.retired_source) |retired_source| {
                    try retired_promoted_buffers.append(self.allocator, retired_source);
                }
                const compute_buffer = promotion.buffer;
                try buffer_infos.append(self.allocator, .{
                    .buffer = compute_buffer.buffer,
                    .offset = binding.buffer_offset,
                    .range = try descriptor_range(binding, compute_buffer.size),
                });
                try pending_writes.append(self.allocator, .{
                    .set_index = binding.group,
                    .binding = binding.binding,
                    .descriptor_type = descriptor_type,
                    .kind = .buffer,
                    .info_index = buffer_infos.items.len - 1,
                });
            },
            .texture, .storage_texture => {
                const texture = self.textures.getPtr(binding.resource_handle) orelse return error.InvalidState;
                try validate_texture_binding(binding, texture.*);
                try vk_resources.ensure_texture_shader_layout(self, texture);
                try image_infos.append(self.allocator, .{
                    .sampler = 0,
                    .imageView = texture.view,
                    .imageLayout = texture.layout,
                });
                try pending_writes.append(self.allocator, .{
                    .set_index = binding.group,
                    .binding = binding.binding,
                    .descriptor_type = descriptor_type,
                    .kind = .image,
                    .info_index = image_infos.items.len - 1,
                });
            },
            .sampler => {
                const vk_sampler = self.samplers.get(binding.resource_handle) orelse return error.InvalidState;
                try image_infos.append(self.allocator, .{
                    .sampler = vk_sampler,
                    .imageView = VK_NULL_U64,
                    .imageLayout = 0,
                });
                try pending_writes.append(self.allocator, .{
                    .set_index = binding.group,
                    .binding = binding.binding,
                    .descriptor_type = descriptor_type,
                    .kind = .image,
                    .info_index = image_infos.items.len - 1,
                });
            },
        }
    }

    for (pending_writes.items) |pending| {
        try writes.append(self.allocator, .{
            .sType = c.VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET,
            .pNext = null,
            .dstSet = self.descriptor_sets[@intCast(pending.set_index)],
            .dstBinding = pending.binding,
            .dstArrayElement = 0,
            .descriptorCount = 1,
            .descriptorType = pending.descriptor_type,
            .pImageInfo = if (pending.kind == .image) @ptrCast(&image_infos.items[pending.info_index]) else null,
            .pBufferInfo = if (pending.kind == .buffer) @ptrCast(&buffer_infos.items[pending.info_index]) else null,
            .pTexelBufferView = null,
        });
    }

    if (writes.items.len > 0) {
        c.vkUpdateDescriptorSets(self.device, @intCast(writes.items.len), writes.items.ptr, 0, null);
    }
    self.current_descriptor_bindings_hash = descriptor_bindings_hash;
    self.has_current_descriptor_bindings_hash = true;
}

fn ensure_descriptor_pool(self: anytype, bindings: ?[]const model_compute_types.KernelBinding) !void {
    if (self.has_descriptor_pool) return;
    if (self.descriptor_set_count == 0) return;
    const bs = bindings orelse return error.InvalidArgument;
    var uniform_count: u32 = 0;
    var storage_count: u32 = 0;
    var sampled_image_count: u32 = 0;
    var storage_image_count: u32 = 0;
    var sampler_count: u32 = 0;
    for (bs) |binding| {
        switch (try descriptor_type_for_binding(binding)) {
            c.VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER => uniform_count += 1,
            c.VK_DESCRIPTOR_TYPE_STORAGE_BUFFER => storage_count += 1,
            c.VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE => sampled_image_count += 1,
            c.VK_DESCRIPTOR_TYPE_STORAGE_IMAGE => storage_image_count += 1,
            c.VK_DESCRIPTOR_TYPE_SAMPLER => sampler_count += 1,
            else => return error.UnsupportedFeature,
        }
    }

    var pool_sizes: [5]c.VkDescriptorPoolSize = undefined;
    var pool_size_count: usize = 0;
    if (uniform_count > 0) {
        pool_sizes[pool_size_count] = .{ .type = c.VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, .descriptorCount = uniform_count };
        pool_size_count += 1;
    }
    if (storage_count > 0) {
        pool_sizes[pool_size_count] = .{ .type = c.VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, .descriptorCount = storage_count };
        pool_size_count += 1;
    }
    if (sampled_image_count > 0) {
        pool_sizes[pool_size_count] = .{ .type = c.VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE, .descriptorCount = sampled_image_count };
        pool_size_count += 1;
    }
    if (storage_image_count > 0) {
        pool_sizes[pool_size_count] = .{ .type = c.VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, .descriptorCount = storage_image_count };
        pool_size_count += 1;
    }
    if (sampler_count > 0) {
        pool_sizes[pool_size_count] = .{ .type = c.VK_DESCRIPTOR_TYPE_SAMPLER, .descriptorCount = sampler_count };
        pool_size_count += 1;
    }

    var pool_info = c.VkDescriptorPoolCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .maxSets = self.descriptor_set_count,
        .poolSizeCount = @intCast(pool_size_count),
        .pPoolSizes = if (pool_size_count > 0) pool_sizes[0..pool_size_count].ptr else null,
    };
    try c.check_vk(c.vkCreateDescriptorPool(self.device, &pool_info, null, &self.descriptor_pool));
    errdefer {
        c.vkDestroyDescriptorPool(self.device, self.descriptor_pool, null);
        self.descriptor_pool = VK_NULL_U64;
    }

    var alloc_info = c.VkDescriptorSetAllocateInfo{
        .sType = c.VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO,
        .pNext = null,
        .descriptorPool = self.descriptor_pool,
        .descriptorSetCount = self.descriptor_set_count,
        .pSetLayouts = self.descriptor_set_layouts[0..@intCast(self.descriptor_set_count)].ptr,
    };
    try c.check_vk(c.vkAllocateDescriptorSets(self.device, &alloc_info, self.descriptor_sets[0..@intCast(self.descriptor_set_count)].ptr));
    self.has_descriptor_pool = true;
}

pub fn descriptor_type_for_binding(binding: model_compute_types.KernelBinding) !u32 {
    return switch (binding.resource_kind) {
        .buffer => switch (binding.buffer_type) {
            model_binding_types.WGPUBufferBindingType_Uniform => c.VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,
            model_binding_types.WGPUBufferBindingType_Storage,
            model_binding_types.WGPUBufferBindingType_ReadOnlyStorage,
            => c.VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
            else => error.UnsupportedFeature,
        },
        .texture => c.VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE,
        .storage_texture => c.VK_DESCRIPTOR_TYPE_STORAGE_IMAGE,
        .sampler => c.VK_DESCRIPTOR_TYPE_SAMPLER,
    };
}

pub fn validate_texture_binding(binding: model_compute_types.KernelBinding, texture: vk_resources.TextureResource) !void {
    if (binding.texture_view_dimension != model_texture_types.WGPUTextureViewDimension_Undefined and
        binding.texture_view_dimension != texture.view_dimension) return error.InvalidState;
    if (binding.texture_multisampled != (texture.sample_count > 1)) return error.InvalidState;
    try validate_texture_binding_aspect(binding.texture_aspect, texture);
    if (binding.texture_format != model_texture_types.WGPUTextureFormat_Undefined and
        binding.texture_format != texture.format) return error.InvalidState;

    switch (binding.resource_kind) {
        .buffer, .sampler => return error.InvalidArgument,
        .texture => {
            if ((texture.usage & model_texture_types.WGPUTextureUsage_TextureBinding) == 0) return error.InvalidState;
            switch (binding.texture_sample_type) {
                model_binding_types.WGPUTextureSampleType_Undefined,
                model_binding_types.WGPUTextureSampleType_Float,
                model_binding_types.WGPUTextureSampleType_UnfilterableFloat,
                model_binding_types.WGPUTextureSampleType_Depth,
                model_binding_types.WGPUTextureSampleType_Sint,
                model_binding_types.WGPUTextureSampleType_Uint,
                => {},
                else => return error.UnsupportedFeature,
            }
        },
        .storage_texture => {
            if ((texture.usage & model_texture_types.WGPUTextureUsage_StorageBinding) == 0) return error.InvalidState;
            switch (binding.storage_texture_access) {
                model_binding_types.WGPUStorageTextureAccess_Undefined,
                model_binding_types.WGPUStorageTextureAccess_WriteOnly,
                model_binding_types.WGPUStorageTextureAccess_ReadOnly,
                model_binding_types.WGPUStorageTextureAccess_ReadWrite,
                => {},
                else => return error.UnsupportedFeature,
            }
        },
    }
}

fn validate_texture_binding_aspect(binding_aspect: u32, texture: vk_resources.TextureResource) !void {
    if (binding_aspect == model_texture_types.WGPUTextureAspect_Undefined or
        binding_aspect == model_texture_types.WGPUTextureAspect_All) return;

    const full_mask = vk_formats.aspect_mask_for_format(texture.format);
    const requested_mask = switch (binding_aspect) {
        model_texture_types.WGPUTextureAspect_DepthOnly => vk_formats.VK_IMAGE_ASPECT_DEPTH_BIT,
        model_texture_types.WGPUTextureAspect_StencilOnly => vk_formats.VK_IMAGE_ASPECT_STENCIL_BIT,
        else => return error.UnsupportedFeature,
    };
    if (requested_mask != full_mask) return error.UnsupportedFeature;
}

pub fn descriptor_range(binding: model_compute_types.KernelBinding, buffer_size: u64) !u64 {
    if (binding.resource_kind != .buffer) return error.UnsupportedFeature;
    if (binding.buffer_size == model_texture_types.WGPUWholeSize) {
        if (binding.buffer_offset > buffer_size) return error.InvalidArgument;
        return c.VK_WHOLE_SIZE;
    }
    if (binding.buffer_size == 0) return error.InvalidArgument;
    const end = std.math.add(u64, binding.buffer_offset, binding.buffer_size) catch return error.InvalidArgument;
    if (end > buffer_size) return error.InvalidArgument;
    return binding.buffer_size;
}

pub fn compute_descriptor_bindings_hash(bindings: []const model_compute_types.KernelBinding) u64 {
    return vk_binding_hash.compute_descriptor_bindings_hash(bindings);
}
