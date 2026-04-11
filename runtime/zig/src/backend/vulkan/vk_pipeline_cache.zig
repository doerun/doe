const std = @import("std");
const c = @import("vk_constants.zig");

const VK_NULL_U64 = c.VK_NULL_U64;

pub const CachedDescriptorState = struct {
    descriptor_pool: c.VkDescriptorPool = VK_NULL_U64,
    descriptor_sets: [c.MAX_DESCRIPTOR_SETS]c.VkDescriptorSet = [_]c.VkDescriptorSet{VK_NULL_U64} ** c.MAX_DESCRIPTOR_SETS,
    descriptor_set_count: u32 = 0,
    current_descriptor_bindings_hash: u64 = 0,
    has_current_descriptor_bindings_hash: bool = false,
};

pub const CachedComputeState = struct {
    shader_module: c.VkShaderModule = VK_NULL_U64,
    pipeline_layout: c.VkPipelineLayout = VK_NULL_U64,
    pipeline: c.VkPipeline = VK_NULL_U64,
    descriptor_pool: c.VkDescriptorPool = VK_NULL_U64,
    descriptor_set_layouts: [c.MAX_DESCRIPTOR_SETS]c.VkDescriptorSetLayout = [_]c.VkDescriptorSetLayout{VK_NULL_U64} ** c.MAX_DESCRIPTOR_SETS,
    descriptor_sets: [c.MAX_DESCRIPTOR_SETS]c.VkDescriptorSet = [_]c.VkDescriptorSet{VK_NULL_U64} ** c.MAX_DESCRIPTOR_SETS,
    descriptor_set_count: u32 = 0,
    current_pipeline_hash: u64 = 0,
    current_layout_hash: u64 = 0,
    current_descriptor_bindings_hash: u64 = 0,
    current_entry_point_owned: ?[:0]u8 = null,
    descriptor_state_cache: std.AutoHashMapUnmanaged(u64, CachedDescriptorState) = .{},
    has_shader_module: bool = false,
    has_pipeline_layout: bool = false,
    has_pipeline: bool = false,
    has_descriptor_pool: bool = false,
    has_current_descriptor_bindings_hash: bool = false,
};

pub fn has_active_compute_state(self: anytype) bool {
    return self.has_shader_module or
        self.has_pipeline_layout or
        self.has_pipeline or
        self.has_descriptor_pool or
        self.current_pipeline_hash != 0 or
        self.current_layout_hash != 0 or
        self.current_entry_point_owned != null;
}

pub fn clear_active_compute_state(self: anytype) void {
    self.shader_module = VK_NULL_U64;
    self.pipeline_layout = VK_NULL_U64;
    self.pipeline = VK_NULL_U64;
    self.descriptor_pool = VK_NULL_U64;
    self.descriptor_set_layouts = [_]c.VkDescriptorSetLayout{VK_NULL_U64} ** c.MAX_DESCRIPTOR_SETS;
    self.descriptor_sets = [_]c.VkDescriptorSet{VK_NULL_U64} ** c.MAX_DESCRIPTOR_SETS;
    self.descriptor_set_count = 0;
    self.current_pipeline_hash = 0;
    self.current_layout_hash = 0;
    self.current_descriptor_bindings_hash = 0;
    self.current_entry_point_owned = null;
    self.current_descriptor_state_cache = .{};
    self.has_shader_module = false;
    self.has_pipeline_layout = false;
    self.has_pipeline = false;
    self.has_descriptor_pool = false;
    self.has_current_descriptor_bindings_hash = false;
}

pub fn capture_active_compute_state(self: anytype) CachedComputeState {
    return .{
        .shader_module = self.shader_module,
        .pipeline_layout = self.pipeline_layout,
        .pipeline = self.pipeline,
        .descriptor_pool = self.descriptor_pool,
        .descriptor_set_layouts = self.descriptor_set_layouts,
        .descriptor_sets = self.descriptor_sets,
        .descriptor_set_count = self.descriptor_set_count,
        .current_pipeline_hash = self.current_pipeline_hash,
        .current_layout_hash = self.current_layout_hash,
        .current_descriptor_bindings_hash = self.current_descriptor_bindings_hash,
        .current_entry_point_owned = self.current_entry_point_owned,
        .descriptor_state_cache = self.current_descriptor_state_cache,
        .has_shader_module = self.has_shader_module,
        .has_pipeline_layout = self.has_pipeline_layout,
        .has_pipeline = self.has_pipeline,
        .has_descriptor_pool = self.has_descriptor_pool,
        .has_current_descriptor_bindings_hash = self.has_current_descriptor_bindings_hash,
    };
}

pub fn restore_active_compute_state(self: anytype, cached: CachedComputeState) void {
    self.shader_module = cached.shader_module;
    self.pipeline_layout = cached.pipeline_layout;
    self.pipeline = cached.pipeline;
    self.descriptor_pool = cached.descriptor_pool;
    self.descriptor_set_layouts = cached.descriptor_set_layouts;
    self.descriptor_sets = cached.descriptor_sets;
    self.descriptor_set_count = cached.descriptor_set_count;
    self.current_pipeline_hash = cached.current_pipeline_hash;
    self.current_layout_hash = cached.current_layout_hash;
    self.current_descriptor_bindings_hash = cached.current_descriptor_bindings_hash;
    self.current_entry_point_owned = cached.current_entry_point_owned;
    self.current_descriptor_state_cache = cached.descriptor_state_cache;
    self.has_shader_module = cached.has_shader_module;
    self.has_pipeline_layout = cached.has_pipeline_layout;
    self.has_pipeline = cached.has_pipeline;
    self.has_descriptor_pool = cached.has_descriptor_pool;
    self.has_current_descriptor_bindings_hash = cached.has_current_descriptor_bindings_hash;
}

pub fn destroy_cached_descriptor_state(self: anytype, cached: CachedDescriptorState) void {
    if (cached.descriptor_pool != VK_NULL_U64) {
        c.vkDestroyDescriptorPool(self.device, cached.descriptor_pool, null);
    }
}

pub fn release_descriptor_state_cache(self: anytype) void {
    var it = self.current_descriptor_state_cache.valueIterator();
    while (it.next()) |cached| destroy_cached_descriptor_state(self, cached.*);
    self.current_descriptor_state_cache.deinit(self.allocator);
    self.current_descriptor_state_cache = .{};
}

pub fn destroy_cached_compute_state(self: anytype, cached: CachedComputeState) void {
    if (cached.pipeline != VK_NULL_U64) c.vkDestroyPipeline(self.device, cached.pipeline, null);
    if (cached.shader_module != VK_NULL_U64) c.vkDestroyShaderModule(self.device, cached.shader_module, null);
    if (cached.descriptor_pool != VK_NULL_U64) c.vkDestroyDescriptorPool(self.device, cached.descriptor_pool, null);
    var descriptor_state_cache = cached.descriptor_state_cache;
    var descriptor_it = descriptor_state_cache.valueIterator();
    while (descriptor_it.next()) |descriptor_cached| {
        destroy_cached_descriptor_state(self, descriptor_cached.*);
    }
    descriptor_state_cache.deinit(self.allocator);
    for (cached.descriptor_set_layouts) |layout| {
        if (layout != VK_NULL_U64) c.vkDestroyDescriptorSetLayout(self.device, layout, null);
    }
    if (cached.pipeline_layout != VK_NULL_U64) c.vkDestroyPipelineLayout(self.device, cached.pipeline_layout, null);
    if (cached.current_entry_point_owned) |entry_name| self.allocator.free(entry_name);
}

pub fn release_cached_compute_states(self: anytype) void {
    var it = self.cached_compute_states.valueIterator();
    while (it.next()) |cached| destroy_cached_compute_state(self, cached.*);
    self.cached_compute_states.deinit(self.allocator);
}

pub fn stash_active_compute_state(self: anytype) !void {
    if (!has_active_compute_state(self)) return;
    const cache_key = self.current_pipeline_hash;
    if (cache_key == 0) return;
    const cached = capture_active_compute_state(self);
    clear_active_compute_state(self);
    if (self.cached_compute_states.fetchRemove(cache_key)) |removed| {
        destroy_cached_compute_state(self, removed.value);
    }
    try self.cached_compute_states.put(self.allocator, cache_key, cached);
}

pub fn activate_cached_compute_state(self: anytype, pipeline_hash: u64) bool {
    const removed = self.cached_compute_states.fetchRemove(pipeline_hash) orelse return false;
    restore_active_compute_state(self, removed.value);
    return true;
}

pub fn capture_active_descriptor_state(self: anytype) CachedDescriptorState {
    return .{
        .descriptor_pool = self.descriptor_pool,
        .descriptor_sets = self.descriptor_sets,
        .descriptor_set_count = self.descriptor_set_count,
        .current_descriptor_bindings_hash = self.current_descriptor_bindings_hash,
        .has_current_descriptor_bindings_hash = self.has_current_descriptor_bindings_hash,
    };
}

pub fn clear_active_descriptor_state(self: anytype) void {
    self.descriptor_pool = VK_NULL_U64;
    self.descriptor_sets = [_]c.VkDescriptorSet{VK_NULL_U64} ** c.MAX_DESCRIPTOR_SETS;
    self.current_descriptor_bindings_hash = 0;
    self.has_descriptor_pool = false;
    self.has_current_descriptor_bindings_hash = false;
}

pub fn restore_active_descriptor_state(self: anytype, cached: CachedDescriptorState) void {
    self.descriptor_pool = cached.descriptor_pool;
    self.descriptor_sets = cached.descriptor_sets;
    self.descriptor_set_count = cached.descriptor_set_count;
    self.current_descriptor_bindings_hash = cached.current_descriptor_bindings_hash;
    self.has_descriptor_pool = cached.descriptor_pool != VK_NULL_U64;
    self.has_current_descriptor_bindings_hash = cached.has_current_descriptor_bindings_hash;
}

pub fn stash_active_descriptor_state(self: anytype) !void {
    if (!self.has_descriptor_pool or !self.has_current_descriptor_bindings_hash) return;
    const cache_key = self.current_descriptor_bindings_hash;
    if (cache_key == 0) return;
    const cached = capture_active_descriptor_state(self);
    clear_active_descriptor_state(self);
    if (self.current_descriptor_state_cache.fetchRemove(cache_key)) |removed| {
        destroy_cached_descriptor_state(self, removed.value);
    }
    try self.current_descriptor_state_cache.put(self.allocator, cache_key, cached);
}

pub fn activate_cached_descriptor_state(self: anytype, descriptor_bindings_hash: u64) bool {
    const removed = self.current_descriptor_state_cache.fetchRemove(descriptor_bindings_hash) orelse return false;
    restore_active_descriptor_state(self, removed.value);
    return true;
}
