const std = @import("std");

pub fn adapterAllocator() std.mem.Allocator {
    return std.heap.c_allocator;
}

pub fn callbackJobAllocator() std.mem.Allocator {
    return std.heap.c_allocator;
}

pub fn dropinAsyncPipelineAllocator() std.mem.Allocator {
    return std.heap.c_allocator;
}

pub fn metalPipelineCacheAllocator() std.mem.Allocator {
    return std.heap.c_allocator;
}

pub fn multiQueueAllocator() std.mem.Allocator {
    return std.heap.c_allocator;
}
