// Compute pipeline, shader module, and descriptor set management.
//
// Handles SPIR-V loading, WGSL-to-SPIR-V compilation, pipeline/layout
// creation, descriptor set allocation, and binding.

const std = @import("std");
const c = @import("vk_constants.zig");
const vk_device = @import("vk_device.zig");
const vk_upload = @import("vk_upload.zig");
const vk_resources = @import("vk_resources.zig");
const model = @import("../../model.zig");
const doe_wgsl = @import("../../doe_wgsl/mod.zig");
const common_errors = @import("../common/errors.zig");

const VkBuffer = c.VkBuffer;
const VkDeviceMemory = c.VkDeviceMemory;
const VK_NULL_U64 = c.VK_NULL_U64;

const MAX_KERNEL_SOURCE_BYTES: usize = 2 * 1024 * 1024;
const SPIRV_MAGIC: u32 = 0x07230203;
const DEFAULT_KERNEL_ROOT = "bench/kernels";
const MAIN_ENTRY: [*:0]const u8 = "main";

pub const DescriptorInfoKind = enum {
    buffer,
    image,
};

pub const PendingDescriptorWrite = struct {
    set_index: u32,
    binding: u32,
    descriptor_type: u32,
    kind: DescriptorInfoKind,
    info_index: usize,
};

const Runtime = @import("native_runtime.zig").NativeVulkanRuntime;

pub fn load_kernel_source(self: *const Runtime, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u8 {
    if (kernel_name.len == 0) return error.InvalidArgument;
    const path = try resolve_kernel_path(self, allocator, kernel_name);
    defer allocator.free(path);
    return std.fs.cwd().readFileAlloc(allocator, path, MAX_KERNEL_SOURCE_BYTES) catch error.ShaderCompileFailed;
}

pub fn load_kernel_spirv(self: *const Runtime, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u32 {
    if (kernel_name.len == 0) return error.InvalidArgument;
    const path = resolve_kernel_spirv_path(self, allocator, kernel_name) catch |err| switch (err) {
        error.UnsupportedFeature => return try compile_kernel_wgsl_to_spirv(self, allocator, kernel_name),
        else => return err,
    };
    defer allocator.free(path);

    const bytes = std.fs.cwd().readFileAlloc(allocator, path, MAX_KERNEL_SOURCE_BYTES) catch return error.ShaderCompileFailed;
    defer allocator.free(bytes);
    return try words_from_spirv_bytes(allocator, bytes);
}

fn compile_kernel_wgsl_to_spirv(self: *const Runtime, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u32 {
    const source_path = try resolve_kernel_path(self, allocator, kernel_name);
    defer allocator.free(source_path);
    if (!std.mem.endsWith(u8, source_path, ".wgsl")) return error.UnsupportedFeature;

    const wgsl = std.fs.cwd().readFileAlloc(allocator, source_path, MAX_KERNEL_SOURCE_BYTES) catch return error.ShaderCompileFailed;
    defer allocator.free(wgsl);

    var spirv_buf = try allocator.alloc(u8, doe_wgsl.MAX_SPIRV_OUTPUT);
    defer allocator.free(spirv_buf);
    const spirv_len = doe_wgsl.translateToSpirv(allocator, wgsl, spirv_buf) catch return error.ShaderCompileFailed;
    return try words_from_spirv_bytes(allocator, spirv_buf[0..spirv_len]);
}

pub fn set_compute_shader_spirv(
    self: *Runtime,
    words: []const u32,
    entry_point: ?[]const u8,
    bindings: ?[]const model.KernelBinding,
    initialize_buffers_on_create: bool,
) !void {
    if (words.len == 0 or words[0] != SPIRV_MAGIC) return error.ShaderCompileFailed;
    const pipeline_hash = compute_pipeline_hash(words, entry_point, bindings);
    if (!self.has_pipeline or pipeline_hash != self.current_pipeline_hash) {
        try build_pipeline_for_words(self, words, pipeline_hash, entry_point, bindings);
    }
    try prepare_descriptor_sets(self, bindings, initialize_buffers_on_create);
}

pub fn rebuild_compute_shader_spirv(self: *Runtime, words: []const u32) !void {
    if (words.len == 0 or words[0] != SPIRV_MAGIC) return error.ShaderCompileFailed;
    const hash = std.hash.Wyhash.hash(0, std.mem.sliceAsBytes(words));
    try build_pipeline_for_words(self, words, hash +% 1, null, null);
}

pub fn build_pipeline_for_words(
    self: *Runtime,
    words: []const u32,
    pipeline_hash: u64,
    entry_point: ?[]const u8,
    bindings: ?[]const model.KernelBinding,
) !void {
    if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
        _ = try vk_upload.flush_queue(self);
    }
    try ensure_pipeline_layout(self, bindings);
    destroy_pipeline_objects(self);
    errdefer destroy_pipeline_objects(self);

    const entry_name = entry_point orelse "main";
    const owned_entry = try self.allocator.dupeZ(u8, entry_name);
    errdefer self.allocator.free(owned_entry);

    var shader_info = c.VkShaderModuleCreateInfo{ .sType = c.VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO, .pNext = null, .flags = 0, .codeSize = words.len * @sizeOf(u32), .pCode = words.ptr };
    try c.check_vk(c.vkCreateShaderModule(self.device, &shader_info, null, &self.shader_module));
    self.has_shader_module = true;

    const stage_info = c.VkPipelineShaderStageCreateInfo{ .sType = c.VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, .pNext = null, .flags = 0, .stage = c.VK_SHADER_STAGE_COMPUTE_BIT, .module = self.shader_module, .pName = owned_entry.ptr, .pSpecializationInfo = null };
    var pipeline_info = c.VkComputePipelineCreateInfo{ .sType = c.VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO, .pNext = null, .flags = 0, .stage = stage_info, .layout = self.pipeline_layout, .basePipelineHandle = VK_NULL_U64, .basePipelineIndex = -1 };
    try c.check_vk(c.vkCreateComputePipelines(self.device, VK_NULL_U64, 1, @ptrCast(&pipeline_info), null, @ptrCast(&self.pipeline)));
    self.has_pipeline = true;
    self.current_entry_point_owned = owned_entry;
    self.current_pipeline_hash = pipeline_hash;
}

pub fn destroy_pipeline_objects(self: *Runtime) void {
    if (self.has_pipeline) {
        c.vkDestroyPipeline(self.device, self.pipeline, null);
        self.has_pipeline = false;
        self.pipeline = VK_NULL_U64;
    }
    if (self.has_shader_module) {
        c.vkDestroyShaderModule(self.device, self.shader_module, null);
        self.has_shader_module = false;
        self.shader_module = VK_NULL_U64;
    }
    if (self.current_entry_point_owned) |entry_name| {
        self.allocator.free(entry_name);
        self.current_entry_point_owned = null;
    }
    self.current_pipeline_hash = 0;
}

pub fn destroy_descriptor_state(self: *Runtime) void {
    if (self.has_descriptor_pool) {
        c.vkDestroyDescriptorPool(self.device, self.descriptor_pool, null);
        self.has_descriptor_pool = false;
        self.descriptor_pool = VK_NULL_U64;
    }
    var set_index: usize = 0;
    while (set_index < c.MAX_DESCRIPTOR_SETS) : (set_index += 1) {
        if (self.descriptor_set_layouts[set_index] != VK_NULL_U64) {
            c.vkDestroyDescriptorSetLayout(self.device, self.descriptor_set_layouts[set_index], null);
            self.descriptor_set_layouts[set_index] = VK_NULL_U64;
        }
        self.descriptor_sets[set_index] = VK_NULL_U64;
    }
    self.descriptor_set_count = 0;
    if (self.has_pipeline_layout) {
        c.vkDestroyPipelineLayout(self.device, self.pipeline_layout, null);
        self.has_pipeline_layout = false;
        self.pipeline_layout = VK_NULL_U64;
    }
    self.current_layout_hash = 0;
}

pub fn bind_descriptor_sets(self: *Runtime, command_buffer: c.VkCommandBuffer) void {
    if (!self.has_descriptor_pool or self.descriptor_set_count == 0) return;
    c.vkCmdBindDescriptorSets(
        command_buffer,
        c.VK_PIPELINE_BIND_POINT_COMPUTE,
        self.pipeline_layout,
        0,
        self.descriptor_set_count,
        self.descriptor_sets[0..@intCast(self.descriptor_set_count)].ptr,
        0,
        null,
    );
}

fn ensure_pipeline_layout(self: *Runtime, bindings: ?[]const model.KernelBinding) !void {
    const layout_hash = compute_layout_hash(bindings);
    if (self.has_pipeline_layout and layout_hash == self.current_layout_hash) return;

    destroy_descriptor_state(self);
    errdefer destroy_descriptor_state(self);

    var set_count: u32 = 0;
    if (bindings) |bs| {
        for (bs) |binding| {
            if (binding.group >= c.MAX_DESCRIPTOR_SETS_U32) return error.UnsupportedFeature;
            set_count = @max(set_count, binding.group + 1);
        }
    }

    const set_count_usize: usize = @intCast(set_count);
    var per_set_bindings = try self.allocator.alloc(std.ArrayListUnmanaged(c.VkDescriptorSetLayoutBinding), set_count_usize);
    defer {
        for (per_set_bindings) |*list| list.deinit(self.allocator);
        self.allocator.free(per_set_bindings);
    }
    for (per_set_bindings) |*list| list.* = .{};

    if (bindings) |bs| {
        for (bs) |binding| {
            try per_set_bindings[@intCast(binding.group)].append(self.allocator, .{
                .binding = binding.binding,
                .descriptorType = try descriptor_type_for_binding(binding),
                .descriptorCount = 1,
                .stageFlags = c.VK_SHADER_STAGE_COMPUTE_BIT,
                .pImmutableSamplers = null,
            });
        }
    }

    self.descriptor_set_count = set_count;
    var set_index: usize = 0;
    while (set_index < set_count_usize) : (set_index += 1) {
        const set_bindings = per_set_bindings[set_index].items;
        var layout_info = c.VkDescriptorSetLayoutCreateInfo{
            .sType = c.VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO,
            .pNext = null,
            .flags = 0,
            .bindingCount = @intCast(set_bindings.len),
            .pBindings = if (set_bindings.len > 0) set_bindings.ptr else null,
        };
        try c.check_vk(c.vkCreateDescriptorSetLayout(self.device, &layout_info, null, &self.descriptor_set_layouts[set_index]));
    }

    var layout_info = c.VkPipelineLayoutCreateInfo{
        .sType = c.VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
        .pNext = null,
        .flags = 0,
        .setLayoutCount = self.descriptor_set_count,
        .pSetLayouts = if (self.descriptor_set_count > 0) @ptrCast(self.descriptor_set_layouts[0..@intCast(self.descriptor_set_count)].ptr) else null,
        .pushConstantRangeCount = 0,
        .pPushConstantRanges = null,
    };
    try c.check_vk(c.vkCreatePipelineLayout(self.device, &layout_info, null, &self.pipeline_layout));
    self.has_pipeline_layout = true;
    self.current_layout_hash = layout_hash;
}

fn prepare_descriptor_sets(
    self: *Runtime,
    bindings: ?[]const model.KernelBinding,
    initialize_buffers_on_create: bool,
) !void {
    if (self.descriptor_set_count == 0) return;
    if (self.has_deferred_submissions or self.pending_uploads.items.len > 0) {
        _ = try vk_upload.flush_queue(self);
    }
    try ensure_descriptor_pool(self, bindings);

    const bs = bindings orelse return error.InvalidArgument;
    var buffer_infos = std.ArrayListUnmanaged(c.VkDescriptorBufferInfo){};
    defer buffer_infos.deinit(self.allocator);
    var image_infos = std.ArrayListUnmanaged(c.VkDescriptorImageInfo){};
    defer image_infos.deinit(self.allocator);
    var pending_writes = std.ArrayListUnmanaged(PendingDescriptorWrite){};
    defer pending_writes.deinit(self.allocator);
    var writes = std.ArrayListUnmanaged(c.VkWriteDescriptorSet){};
    defer writes.deinit(self.allocator);

    for (bs) |binding| {
        const descriptor_type = try descriptor_type_for_binding(binding);
        switch (binding.resource_kind) {
            .buffer => {
                const required_size = try vk_resources.required_compute_buffer_size(self, binding);
                const compute_buffer = try vk_resources.ensure_compute_buffer(
                    self,
                    binding.resource_handle,
                    required_size,
                    initialize_buffers_on_create,
                );
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
}

fn ensure_descriptor_pool(self: *Runtime, bindings: ?[]const model.KernelBinding) !void {
    if (self.has_descriptor_pool) return;
    if (self.descriptor_set_count == 0) return;

    var uniform_count: u32 = 0;
    var storage_count: u32 = 0;
    var sampled_image_count: u32 = 0;
    var storage_image_count: u32 = 0;
    if (bindings) |bs| {
        for (bs) |binding| {
            switch (try descriptor_type_for_binding(binding)) {
                c.VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER => uniform_count += 1,
                c.VK_DESCRIPTOR_TYPE_STORAGE_BUFFER => storage_count += 1,
                c.VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE => sampled_image_count += 1,
                c.VK_DESCRIPTOR_TYPE_STORAGE_IMAGE => storage_image_count += 1,
                else => return error.UnsupportedFeature,
            }
        }
    }

    var pool_sizes: [4]c.VkDescriptorPoolSize = undefined;
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

// --- Pure helpers ---

pub fn descriptor_type_for_binding(binding: model.KernelBinding) !u32 {
    return switch (binding.resource_kind) {
        .buffer => switch (binding.buffer_type) {
            model.WGPUBufferBindingType_Uniform => c.VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,
            model.WGPUBufferBindingType_Storage,
            model.WGPUBufferBindingType_ReadOnlyStorage,
            => c.VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,
            else => error.UnsupportedFeature,
        },
        .texture => c.VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE,
        .storage_texture => c.VK_DESCRIPTOR_TYPE_STORAGE_IMAGE,
    };
}

pub fn validate_texture_binding(binding: model.KernelBinding, texture: vk_resources.TextureResource) !void {
    if (binding.texture_view_dimension != model.WGPUTextureViewDimension_Undefined and
        binding.texture_view_dimension != model.WGPUTextureViewDimension_2D) return error.UnsupportedFeature;
    if (binding.texture_multisampled) return error.UnsupportedFeature;
    if (binding.texture_aspect != model.WGPUTextureAspect_Undefined and
        binding.texture_aspect != model.WGPUTextureAspect_All) return error.UnsupportedFeature;
    if (binding.texture_format != model.WGPUTextureFormat_Undefined and
        binding.texture_format != texture.format) return error.InvalidState;

    switch (binding.resource_kind) {
        .buffer => return error.InvalidArgument,
        .texture => {
            if ((texture.usage & model.WGPUTextureUsage_TextureBinding) == 0) return error.InvalidState;
            switch (binding.texture_sample_type) {
                model.WGPUTextureSampleType_Undefined,
                model.WGPUTextureSampleType_Float,
                model.WGPUTextureSampleType_UnfilterableFloat,
                => {},
                else => return error.UnsupportedFeature,
            }
        },
        .storage_texture => {
            if ((texture.usage & model.WGPUTextureUsage_StorageBinding) == 0) return error.InvalidState;
            switch (binding.storage_texture_access) {
                model.WGPUStorageTextureAccess_Undefined,
                model.WGPUStorageTextureAccess_WriteOnly,
                => {},
                else => return error.UnsupportedFeature,
            }
        },
    }
}

pub fn descriptor_range(binding: model.KernelBinding, buffer_size: u64) !u64 {
    if (binding.resource_kind != .buffer) return error.UnsupportedFeature;
    if (binding.buffer_size == model.WGPUWholeSize) {
        if (binding.buffer_offset > buffer_size) return error.InvalidArgument;
        return c.VK_WHOLE_SIZE;
    }
    if (binding.buffer_size == 0) return error.InvalidArgument;
    const end = std.math.add(u64, binding.buffer_offset, binding.buffer_size) catch return error.InvalidArgument;
    if (end > buffer_size) return error.InvalidArgument;
    return binding.buffer_size;
}

pub fn compute_layout_hash(bindings: ?[]const model.KernelBinding) u64 {
    var hasher = std.hash.Wyhash.init(0);
    if (bindings) |bs| {
        for (bs) |binding| {
            hasher.update(std.mem.asBytes(&binding.group));
            hasher.update(std.mem.asBytes(&binding.binding));
            hasher.update(std.mem.asBytes(&binding.resource_kind));
            hasher.update(std.mem.asBytes(&binding.buffer_type));
            hasher.update(std.mem.asBytes(&binding.texture_sample_type));
            hasher.update(std.mem.asBytes(&binding.texture_view_dimension));
            hasher.update(std.mem.asBytes(&binding.storage_texture_access));
            hasher.update(std.mem.asBytes(&binding.texture_format));
            hasher.update(std.mem.asBytes(&binding.texture_multisampled));
        }
    }
    return hasher.final();
}

pub fn compute_pipeline_hash(
    words: []const u32,
    entry_point: ?[]const u8,
    bindings: ?[]const model.KernelBinding,
) u64 {
    var hasher = std.hash.Wyhash.init(0);
    const layout_hash = compute_layout_hash(bindings);
    hasher.update(std.mem.sliceAsBytes(words));
    hasher.update(entry_point orelse "main");
    hasher.update(std.mem.asBytes(&layout_hash));
    return hasher.final();
}

pub fn words_from_spirv_bytes(allocator: std.mem.Allocator, bytes: []const u8) ![]u32 {
    if (bytes.len == 0 or (bytes.len % 4) != 0) return error.ShaderCompileFailed;

    const words = try allocator.alloc(u32, bytes.len / 4);
    errdefer allocator.free(words);
    for (words, 0..) |*word, i| {
        const start = i * 4;
        const chunk: *const [4]u8 = @ptrCast(bytes[start .. start + 4].ptr);
        word.* = std.mem.readInt(u32, chunk, .little);
    }
    if (words[0] != SPIRV_MAGIC) return error.ShaderCompileFailed;
    return words;
}

fn file_exists(path: []const u8) bool {
    std.fs.cwd().access(path, .{}) catch return false;
    return true;
}

fn resolve_kernel_path(self: *const Runtime, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u8 {
    const direct = try allocator.dupe(u8, kernel_name);
    if (file_exists(direct)) return direct;
    allocator.free(direct);

    const root = self.kernel_root orelse DEFAULT_KERNEL_ROOT;
    const rooted = try std.fmt.allocPrint(allocator, "{s}/{s}", .{ root, kernel_name });
    if (file_exists(rooted)) return rooted;
    allocator.free(rooted);

    if (!std.mem.endsWith(u8, kernel_name, ".wgsl")) {
        const with_suffix = try std.fmt.allocPrint(allocator, "{s}/{s}.wgsl", .{ root, kernel_name });
        if (file_exists(with_suffix)) return with_suffix;
        allocator.free(with_suffix);
    }
    return error.ShaderCompileFailed;
}

fn resolve_kernel_spirv_path(self: *const Runtime, allocator: std.mem.Allocator, kernel_name: []const u8) ![]u8 {
    const source_path = try resolve_kernel_path(self, allocator, kernel_name);
    defer allocator.free(source_path);

    if (std.mem.endsWith(u8, source_path, ".spv") or std.mem.endsWith(u8, source_path, ".spirv")) {
        return try allocator.dupe(u8, source_path);
    }

    const sibling_spv = try std.fmt.allocPrint(allocator, "{s}.spv", .{source_path});
    if (file_exists(sibling_spv)) return sibling_spv;
    allocator.free(sibling_spv);

    if (std.mem.lastIndexOfScalar(u8, source_path, '.')) |idx| {
        const replaced = try std.fmt.allocPrint(allocator, "{s}.spv", .{source_path[0..idx]});
        if (file_exists(replaced)) return replaced;
        allocator.free(replaced);
    }

    return error.UnsupportedFeature;
}
