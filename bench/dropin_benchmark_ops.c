#define _POSIX_C_SOURCE 200809L

#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <time.h>

#include "dropin_benchmark_ops.h"

static const uint64_t ASYNC_TIMEOUT_MS = 5000;

typedef struct AdapterRequestState {
    volatile bool done;
    WGPURequestAdapterStatus status;
    WGPUAdapter adapter;
} AdapterRequestState;

typedef struct DeviceRequestState {
    volatile bool done;
    WGPURequestDeviceStatus status;
    WGPUDevice device;
} DeviceRequestState;

typedef struct QueueWorkDoneState {
    volatile bool done;
    WGPUQueueWorkDoneStatus status;
} QueueWorkDoneState;

static uint64_t monotonic_time_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ((uint64_t)ts.tv_sec * 1000000000ull) + (uint64_t)ts.tv_nsec;
}

static void sleep_one_millisecond(void) {
    struct timespec req;
    req.tv_sec = 0;
    req.tv_nsec = 1000000;
    nanosleep(&req, NULL);
}

static bool wait_for_flag(WGPUInstance instance, volatile bool* done, uint64_t timeout_ms) {
    const uint64_t timeout_ns = timeout_ms * 1000000ull;
    const uint64_t start_ns = monotonic_time_ns();
    while (!*done) {
        wgpuInstanceProcessEvents(instance);
        if ((monotonic_time_ns() - start_ns) > timeout_ns) {
            return false;
        }
        sleep_one_millisecond();
    }
    return true;
}

static void on_request_adapter(
    WGPURequestAdapterStatus status,
    WGPUAdapter adapter,
    WGPUStringView message,
    void* userdata1,
    void* userdata2
) {
    (void)message;
    (void)userdata2;
    AdapterRequestState* state = (AdapterRequestState*)userdata1;
    state->status = status;
    state->adapter = adapter;
    state->done = true;
}

static void on_request_device(
    WGPURequestDeviceStatus status,
    WGPUDevice device,
    WGPUStringView message,
    void* userdata1,
    void* userdata2
) {
    (void)message;
    (void)userdata2;
    DeviceRequestState* state = (DeviceRequestState*)userdata1;
    state->status = status;
    state->device = device;
    state->done = true;
}

static void on_queue_work_done(
    WGPUQueueWorkDoneStatus status,
    WGPUStringView message,
    void* userdata1,
    void* userdata2
) {
    (void)message;
    (void)userdata2;
    QueueWorkDoneState* state = (QueueWorkDoneState*)userdata1;
    state->status = status;
    state->done = true;
}

static bool request_adapter(WGPUInstance instance, WGPUAdapter* out_adapter, const char** failure) {
    AdapterRequestState adapter_state = {
        .done = false,
        .status = WGPURequestAdapterStatus_Error,
        .adapter = NULL,
    };

    WGPURequestAdapterCallbackInfo callback = WGPU_REQUEST_ADAPTER_CALLBACK_INFO_INIT;
    callback.mode = WGPUCallbackMode_AllowProcessEvents;
    callback.callback = on_request_adapter;
    callback.userdata1 = &adapter_state;

    WGPURequestAdapterOptions options = WGPU_REQUEST_ADAPTER_OPTIONS_INIT;
    wgpuInstanceRequestAdapter(instance, &options, callback);

    if (!wait_for_flag(instance, &adapter_state.done, ASYNC_TIMEOUT_MS)) {
        *failure = "adapter_request_timeout";
        return false;
    }
    if (adapter_state.status != WGPURequestAdapterStatus_Success || adapter_state.adapter == NULL) {
        *failure = "adapter_request_failed";
        return false;
    }

    *out_adapter = adapter_state.adapter;
    return true;
}

static bool request_device(
    WGPUInstance instance,
    WGPUAdapter adapter,
    WGPUDevice* out_device,
    const char** failure
) {
    DeviceRequestState device_state = {
        .done = false,
        .status = WGPURequestDeviceStatus_Error,
        .device = NULL,
    };

    WGPURequestDeviceCallbackInfo callback = WGPU_REQUEST_DEVICE_CALLBACK_INFO_INIT;
    callback.mode = WGPUCallbackMode_AllowProcessEvents;
    callback.callback = on_request_device;
    callback.userdata1 = &device_state;

    WGPUDeviceDescriptor descriptor = WGPU_DEVICE_DESCRIPTOR_INIT;
    wgpuAdapterRequestDevice(adapter, &descriptor, callback);

    if (!wait_for_flag(instance, &device_state.done, ASYNC_TIMEOUT_MS)) {
        *failure = "device_request_timeout";
        return false;
    }
    if (device_state.status != WGPURequestDeviceStatus_Success || device_state.device == NULL) {
        *failure = "device_request_failed";
        return false;
    }

    *out_device = device_state.device;
    return true;
}

static bool wait_for_queue_done(
    WGPUInstance instance,
    WGPUQueue queue,
    const char** failure
) {
    QueueWorkDoneState state = {
        .done = false,
        .status = WGPUQueueWorkDoneStatus_Error,
    };

    WGPUQueueWorkDoneCallbackInfo callback = WGPU_QUEUE_WORK_DONE_CALLBACK_INFO_INIT;
    callback.mode = WGPUCallbackMode_AllowProcessEvents;
    callback.callback = on_queue_work_done;
    callback.userdata1 = &state;

    wgpuQueueOnSubmittedWorkDone(queue, callback);

    if (!wait_for_flag(instance, &state.done, ASYNC_TIMEOUT_MS)) {
        *failure = "queue_work_done_timeout";
        return false;
    }
    if (state.status != WGPUQueueWorkDoneStatus_Success) {
        *failure = "queue_work_done_failed";
        return false;
    }
    return true;
}

bool dropin_bench_create_context(DropinContext* ctx, const char** failure) {
    memset(ctx, 0, sizeof(*ctx));

    WGPUInstanceDescriptor instance_desc = WGPU_INSTANCE_DESCRIPTOR_INIT;
    ctx->instance = wgpuCreateInstance(&instance_desc);
    if (ctx->instance == NULL) {
        *failure = "instance_create_failed";
        return false;
    }

    if (!request_adapter(ctx->instance, &ctx->adapter, failure)) {
        return false;
    }

    if (!request_device(ctx->instance, ctx->adapter, &ctx->device, failure)) {
        return false;
    }

    ctx->queue = wgpuDeviceGetQueue(ctx->device);
    if (ctx->queue == NULL) {
        *failure = "device_get_queue_failed";
        return false;
    }

    WGPUBufferDescriptor buffer_desc = WGPU_BUFFER_DESCRIPTOR_INIT;
    buffer_desc.size = BENCH_BUFFER_SIZE;
    buffer_desc.usage = WGPUBufferUsage_CopyDst | WGPUBufferUsage_CopySrc;
    buffer_desc.mappedAtCreation = WGPU_FALSE;
    ctx->buffer = wgpuDeviceCreateBuffer(ctx->device, &buffer_desc);
    if (ctx->buffer == NULL) {
        *failure = "buffer_create_failed";
        return false;
    }

    return true;
}

void dropin_bench_destroy_context(DropinContext* ctx) {
    if (ctx->buffer != NULL) {
        wgpuBufferRelease(ctx->buffer);
        ctx->buffer = NULL;
    }
    if (ctx->queue != NULL) {
        wgpuQueueRelease(ctx->queue);
        ctx->queue = NULL;
    }
    if (ctx->device != NULL) {
        wgpuDeviceDestroy(ctx->device);
        wgpuDeviceRelease(ctx->device);
        ctx->device = NULL;
    }
    if (ctx->adapter != NULL) {
        wgpuAdapterRelease(ctx->adapter);
        ctx->adapter = NULL;
    }
    if (ctx->instance != NULL) {
        wgpuInstanceRelease(ctx->instance);
        ctx->instance = NULL;
    }
}

bool dropin_bench_instance_create_destroy_once(const char** failure) {
    WGPUInstanceDescriptor instance_desc = WGPU_INSTANCE_DESCRIPTOR_INIT;
    WGPUInstance instance = wgpuCreateInstance(&instance_desc);
    if (instance == NULL) {
        *failure = "instance_create_failed";
        return false;
    }
    wgpuInstanceRelease(instance);
    return true;
}

bool dropin_bench_queue_submit_empty_once(DropinContext* ctx, const char** failure) {
    WGPUCommandEncoder encoder = NULL;
    WGPUCommandBuffer command_buffer = NULL;
    bool ok = false;

    WGPUCommandEncoderDescriptor encoder_desc = WGPU_COMMAND_ENCODER_DESCRIPTOR_INIT;
    encoder = wgpuDeviceCreateCommandEncoder(ctx->device, &encoder_desc);
    if (encoder == NULL) {
        *failure = "create_command_encoder_failed";
        goto done;
    }

    WGPUCommandBufferDescriptor command_desc = WGPU_COMMAND_BUFFER_DESCRIPTOR_INIT;
    command_buffer = wgpuCommandEncoderFinish(encoder, &command_desc);
    if (command_buffer == NULL) {
        *failure = "command_encoder_finish_failed";
        goto done;
    }

    wgpuQueueSubmit(ctx->queue, 1, &command_buffer);
    if (!wait_for_queue_done(ctx->instance, ctx->queue, failure)) {
        goto done;
    }

    ok = true;

done:
    if (command_buffer != NULL) {
        wgpuCommandBufferRelease(command_buffer);
    }
    if (encoder != NULL) {
        wgpuCommandEncoderRelease(encoder);
    }
    return ok;
}

bool dropin_bench_command_encoder_finish_empty_once(DropinContext* ctx, const char** failure) {
    WGPUCommandEncoder encoder = NULL;
    WGPUCommandBuffer command_buffer = NULL;
    bool ok = false;

    WGPUCommandEncoderDescriptor encoder_desc = WGPU_COMMAND_ENCODER_DESCRIPTOR_INIT;
    encoder = wgpuDeviceCreateCommandEncoder(ctx->device, &encoder_desc);
    if (encoder == NULL) {
        *failure = "create_command_encoder_failed";
        goto done;
    }

    WGPUCommandBufferDescriptor command_desc = WGPU_COMMAND_BUFFER_DESCRIPTOR_INIT;
    command_buffer = wgpuCommandEncoderFinish(encoder, &command_desc);
    if (command_buffer == NULL) {
        *failure = "command_encoder_finish_failed";
        goto done;
    }

    ok = true;

done:
    if (command_buffer != NULL) {
        wgpuCommandBufferRelease(command_buffer);
    }
    if (encoder != NULL) {
        wgpuCommandEncoderRelease(encoder);
    }
    return ok;
}

bool dropin_bench_queue_write_buffer_size_once(
    DropinContext* ctx,
    size_t write_size,
    const char** failure
) {
    static uint8_t data[BENCH_BUFFER_SIZE];
    static bool initialized = false;

    if (write_size == 0 || write_size > BENCH_BUFFER_SIZE) {
        *failure = "invalid_write_size";
        return false;
    }

    if (!initialized) {
        for (size_t i = 0; i < BENCH_BUFFER_SIZE; ++i) {
            data[i] = (uint8_t)(i & 0xFFu);
        }
        initialized = true;
    }

    wgpuQueueWriteBuffer(ctx->queue, ctx->buffer, 0, data, write_size);
    if (!wait_for_queue_done(ctx->instance, ctx->queue, failure)) {
        return false;
    }
    return true;
}

bool dropin_bench_buffer_create_destroy_once(
    DropinContext* ctx,
    uint64_t size_bytes,
    const char** failure
) {
    WGPUBufferDescriptor buffer_desc = WGPU_BUFFER_DESCRIPTOR_INIT;
    buffer_desc.size = size_bytes;
    buffer_desc.usage = WGPUBufferUsage_CopyDst | WGPUBufferUsage_CopySrc;
    buffer_desc.mappedAtCreation = WGPU_FALSE;
    WGPUBuffer buffer = wgpuDeviceCreateBuffer(ctx->device, &buffer_desc);
    if (buffer == NULL) {
        *failure = "buffer_create_failed";
        return false;
    }
    wgpuBufferRelease(buffer);
    return true;
}

bool dropin_bench_full_lifecycle_device_only_once(const char** failure) {
    DropinContext ctx;
    if (!dropin_bench_create_context(&ctx, failure)) {
        dropin_bench_destroy_context(&ctx);
        return false;
    }
    dropin_bench_destroy_context(&ctx);
    return true;
}

bool dropin_bench_full_lifecycle_queue_submit_once(const char** failure) {
    DropinContext ctx;
    bool ok = false;

    if (!dropin_bench_create_context(&ctx, failure)) {
        dropin_bench_destroy_context(&ctx);
        return false;
    }
    if (!dropin_bench_queue_submit_empty_once(&ctx, failure)) {
        goto done;
    }
    ok = true;

done:
    dropin_bench_destroy_context(&ctx);
    return ok;
}

bool dropin_bench_full_lifecycle_write_size_once(size_t write_size, const char** failure) {
    DropinContext ctx;
    bool ok = false;

    if (!dropin_bench_create_context(&ctx, failure)) {
        dropin_bench_destroy_context(&ctx);
        return false;
    }
    if (!dropin_bench_queue_write_buffer_size_once(&ctx, write_size, failure)) {
        goto done;
    }
    ok = true;

done:
    dropin_bench_destroy_context(&ctx);
    return ok;
}

bool dropin_bench_full_lifecycle_queue_ops_once(const char** failure) {
    DropinContext ctx;
    bool ok = false;

    if (!dropin_bench_create_context(&ctx, failure)) {
        dropin_bench_destroy_context(&ctx);
        return false;
    }

    if (!dropin_bench_queue_write_buffer_size_once(&ctx, BENCH_WRITE_MEDIUM, failure)) {
        goto done;
    }
    if (!dropin_bench_queue_submit_empty_once(&ctx, failure)) {
        goto done;
    }

    ok = true;

done:
    dropin_bench_destroy_context(&ctx);
    return ok;
}
