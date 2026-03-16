#ifndef FAWN_DROPIN_BENCHMARK_OPS_H
#define FAWN_DROPIN_BENCHMARK_OPS_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <webgpu.h>

#define BENCH_BUFFER_SIZE 65536u
#define BENCH_WRITE_SMALL 1024u
#define BENCH_WRITE_MEDIUM 4096u
#define BENCH_WRITE_LARGE 65536u

typedef struct DropinContext {
    WGPUInstance instance;
    WGPUAdapter adapter;
    WGPUDevice device;
    WGPUQueue queue;
    WGPUBuffer buffer;
} DropinContext;

bool dropin_bench_create_context(DropinContext* ctx, const char** failure);
void dropin_bench_destroy_context(DropinContext* ctx);

bool dropin_bench_instance_create_destroy_once(const char** failure);
bool dropin_bench_queue_submit_empty_once(DropinContext* ctx, const char** failure);
bool dropin_bench_command_encoder_finish_empty_once(DropinContext* ctx, const char** failure);
bool dropin_bench_queue_write_buffer_size_once(
    DropinContext* ctx,
    size_t write_size,
    const char** failure
);
bool dropin_bench_buffer_create_destroy_once(
    DropinContext* ctx,
    uint64_t size_bytes,
    const char** failure
);
bool dropin_bench_full_lifecycle_device_only_once(const char** failure);
bool dropin_bench_full_lifecycle_queue_submit_once(const char** failure);
bool dropin_bench_full_lifecycle_write_size_once(size_t write_size, const char** failure);
bool dropin_bench_full_lifecycle_queue_ops_once(const char** failure);

#endif
