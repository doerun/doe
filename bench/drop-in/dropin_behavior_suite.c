#define _POSIX_C_SOURCE 200809L

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include <webgpu.h>

static const uint64_t ASYNC_TIMEOUT_MS = 5000;

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

typedef struct AdapterRequestState {
    volatile bool done;
    WGPURequestAdapterStatus status;
    WGPUAdapter adapter;
    char message[256];
} AdapterRequestState;

typedef struct DeviceRequestState {
    volatile bool done;
    WGPURequestDeviceStatus status;
    WGPUDevice device;
    char message[256];
} DeviceRequestState;

typedef struct QueueWorkDoneState {
    volatile bool done;
    WGPUQueueWorkDoneStatus status;
    char message[256];
} QueueWorkDoneState;

typedef struct ErrorScopeState {
    volatile bool done;
    WGPUPopErrorScopeStatus status;
    WGPUErrorType error_type;
    char message[256];
} ErrorScopeState;

typedef struct SuiteResult {
    bool pass;
    bool instance_create;
    bool adapter_request;
    bool device_request;
    bool queue_ops;
    bool error_capture;
    bool lifecycle;
    uint32_t adapter_status;
    uint32_t device_status;
    uint32_t queue_work_done_status;
    uint32_t pop_error_scope_status;
    uint32_t pop_error_type;
    const char* failure;
} SuiteResult;

static void copy_message(char* out, size_t out_cap, WGPUStringView message) {
    if (out == NULL || out_cap == 0) {
        return;
    }
    out[0] = '\0';
    if (message.data == NULL || message.length == 0) {
        return;
    }
    size_t copy_len = message.length;
    if (copy_len >= out_cap) {
        copy_len = out_cap - 1;
    }
    memcpy(out, message.data, copy_len);
    out[copy_len] = '\0';
}

static void on_request_adapter(
    WGPURequestAdapterStatus status,
    WGPUAdapter adapter,
    WGPUStringView message,
    void* userdata1,
    void* userdata2
) {
    (void)userdata2;
    AdapterRequestState* state = (AdapterRequestState*)userdata1;
    state->status = status;
    state->adapter = adapter;
    copy_message(state->message, sizeof(state->message), message);
    state->done = true;
}

static void on_request_device(
    WGPURequestDeviceStatus status,
    WGPUDevice device,
    WGPUStringView message,
    void* userdata1,
    void* userdata2
) {
    (void)userdata2;
    DeviceRequestState* state = (DeviceRequestState*)userdata1;
    state->status = status;
    state->device = device;
    copy_message(state->message, sizeof(state->message), message);
    state->done = true;
}

static void on_queue_work_done(
    WGPUQueueWorkDoneStatus status,
    WGPUStringView message,
    void* userdata1,
    void* userdata2
) {
    (void)userdata2;
    QueueWorkDoneState* state = (QueueWorkDoneState*)userdata1;
    state->status = status;
    copy_message(state->message, sizeof(state->message), message);
    state->done = true;
}

static void on_pop_error_scope(
    WGPUPopErrorScopeStatus status,
    WGPUErrorType type,
    WGPUStringView message,
    void* userdata1,
    void* userdata2
) {
    (void)userdata2;
    ErrorScopeState* state = (ErrorScopeState*)userdata1;
    state->status = status;
    state->error_type = type;
    copy_message(state->message, sizeof(state->message), message);
    state->done = true;
}

static bool request_adapter_with_power_preference(
    WGPUInstance instance,
    WGPUPowerPreference power_preference,
    AdapterRequestState* out_state)
{
    out_state->done = false;
    out_state->status = WGPURequestAdapterStatus_Error;
    out_state->adapter = NULL;
    out_state->message[0] = '\0';

    WGPURequestAdapterCallbackInfo adapter_callback = WGPU_REQUEST_ADAPTER_CALLBACK_INFO_INIT;
    adapter_callback.mode = WGPUCallbackMode_AllowProcessEvents;
    adapter_callback.callback = on_request_adapter;
    adapter_callback.userdata1 = out_state;

    WGPURequestAdapterOptions adapter_options = WGPU_REQUEST_ADAPTER_OPTIONS_INIT;
    adapter_options.powerPreference = power_preference;
    wgpuInstanceRequestAdapter(instance, &adapter_options, adapter_callback);
    return wait_for_flag(instance, &out_state->done, ASYNC_TIMEOUT_MS);
}

static const char* bool_to_json(bool value) {
    return value ? "true" : "false";
}

int main(void) {
    SuiteResult result = {
        .pass = false,
        .instance_create = false,
        .adapter_request = false,
        .device_request = false,
        .queue_ops = false,
        .error_capture = false,
        .lifecycle = false,
        .adapter_status = 0,
        .device_status = 0,
        .queue_work_done_status = 0,
        .pop_error_scope_status = 0,
        .pop_error_type = 0,
        .failure = "unknown",
    };

    WGPUInstance instance = NULL;
    WGPUAdapter adapter = NULL;
    WGPUDevice device = NULL;
    WGPUQueue queue = NULL;
    WGPUCommandEncoder command_encoder = NULL;
    WGPUCommandBuffer command_buffer = NULL;
    WGPUBuffer work_buffer = NULL;

    WGPUInstanceDescriptor instance_desc = WGPU_INSTANCE_DESCRIPTOR_INIT;
    instance = wgpuCreateInstance(&instance_desc);
    if (instance == NULL) {
        result.failure = "instance_create_failed";
        goto cleanup;
    }
    result.instance_create = true;

    AdapterRequestState adapter_state = {
        .done = false,
        .status = WGPURequestAdapterStatus_Error,
        .adapter = NULL,
        .message = {0},
    };
    const WGPUPowerPreference requests[] = {
        WGPUPowerPreference_HighPerformance,
        WGPUPowerPreference_Undefined,
        WGPUPowerPreference_LowPower,
    };
    bool adapter_ready = false;
    for (size_t i = 0; i < sizeof(requests) / sizeof(requests[0]); ++i) {
        if (!request_adapter_with_power_preference(instance, requests[i], &adapter_state)) {
            result.failure = "adapter_request_timeout";
            goto cleanup;
        }
        result.adapter_status = (uint32_t)adapter_state.status;
        adapter = adapter_state.adapter;
        if (adapter_state.status == WGPURequestAdapterStatus_Success && adapter != NULL) {
            adapter_ready = true;
            break;
        }
    }
    if (!adapter_ready) {
        result.failure = "adapter_request_failed";
        goto cleanup;
    }
    result.adapter_request = true;

    DeviceRequestState device_state = {
        .done = false,
        .status = WGPURequestDeviceStatus_Error,
        .device = NULL,
        .message = {0},
    };
    WGPURequestDeviceCallbackInfo device_callback = WGPU_REQUEST_DEVICE_CALLBACK_INFO_INIT;
    device_callback.mode = WGPUCallbackMode_AllowProcessEvents;
    device_callback.callback = on_request_device;
    device_callback.userdata1 = &device_state;

    WGPUDeviceDescriptor device_desc = WGPU_DEVICE_DESCRIPTOR_INIT;
    wgpuAdapterRequestDevice(adapter, &device_desc, device_callback);
    if (!wait_for_flag(instance, &device_state.done, ASYNC_TIMEOUT_MS)) {
        result.failure = "device_request_timeout";
        goto cleanup;
    }

    result.device_status = (uint32_t)device_state.status;
    device = device_state.device;
    if (device_state.status != WGPURequestDeviceStatus_Success || device == NULL) {
        result.failure = "device_request_failed";
        goto cleanup;
    }
    result.device_request = true;

    queue = wgpuDeviceGetQueue(device);
    if (queue == NULL) {
        result.failure = "device_get_queue_failed";
        goto cleanup;
    }

    WGPUBufferDescriptor work_buffer_desc = WGPU_BUFFER_DESCRIPTOR_INIT;
    work_buffer_desc.size = 32;
    work_buffer_desc.usage = WGPUBufferUsage_CopyDst | WGPUBufferUsage_CopySrc;
    work_buffer_desc.mappedAtCreation = WGPU_FALSE;
    work_buffer = wgpuDeviceCreateBuffer(device, &work_buffer_desc);
    if (work_buffer == NULL) {
        result.failure = "queue_work_buffer_create_failed";
        goto cleanup;
    }

    const uint32_t payload = 0x12345678u;
    wgpuQueueWriteBuffer(queue, work_buffer, 0, &payload, sizeof(payload));

    WGPUCommandEncoderDescriptor encoder_desc = WGPU_COMMAND_ENCODER_DESCRIPTOR_INIT;
    command_encoder = wgpuDeviceCreateCommandEncoder(device, &encoder_desc);
    if (command_encoder == NULL) {
        result.failure = "create_command_encoder_failed";
        goto cleanup;
    }

    WGPUCommandBufferDescriptor command_buffer_desc = WGPU_COMMAND_BUFFER_DESCRIPTOR_INIT;
    command_buffer = wgpuCommandEncoderFinish(command_encoder, &command_buffer_desc);
    if (command_buffer == NULL) {
        result.failure = "command_encoder_finish_failed";
        goto cleanup;
    }

    wgpuQueueSubmit(queue, 1, &command_buffer);

    QueueWorkDoneState queue_state = {
        .done = false,
        .status = WGPUQueueWorkDoneStatus_Error,
        .message = {0},
    };
    WGPUQueueWorkDoneCallbackInfo queue_callback = WGPU_QUEUE_WORK_DONE_CALLBACK_INFO_INIT;
    queue_callback.mode = WGPUCallbackMode_AllowProcessEvents;
    queue_callback.callback = on_queue_work_done;
    queue_callback.userdata1 = &queue_state;

    wgpuQueueOnSubmittedWorkDone(queue, queue_callback);
    if (!wait_for_flag(instance, &queue_state.done, ASYNC_TIMEOUT_MS)) {
        result.failure = "queue_work_done_timeout";
        goto cleanup;
    }

    result.queue_work_done_status = (uint32_t)queue_state.status;
    if (queue_state.status != WGPUQueueWorkDoneStatus_Success) {
        result.failure = "queue_work_done_failed";
        goto cleanup;
    }
    result.queue_ops = true;

    wgpuDevicePushErrorScope(device, WGPUErrorFilter_Validation);
    wgpuQueueWriteBuffer(queue, work_buffer, 1024, &payload, sizeof(payload));

    ErrorScopeState error_state = {
        .done = false,
        .status = WGPUPopErrorScopeStatus_Error,
        .error_type = WGPUErrorType_NoError,
        .message = {0},
    };
    WGPUPopErrorScopeCallbackInfo error_callback = WGPU_POP_ERROR_SCOPE_CALLBACK_INFO_INIT;
    error_callback.mode = WGPUCallbackMode_AllowProcessEvents;
    error_callback.callback = on_pop_error_scope;
    error_callback.userdata1 = &error_state;

    wgpuDevicePopErrorScope(device, error_callback);
    if (!wait_for_flag(instance, &error_state.done, ASYNC_TIMEOUT_MS)) {
        result.failure = "pop_error_scope_timeout";
        goto cleanup;
    }

    result.pop_error_scope_status = (uint32_t)error_state.status;
    result.pop_error_type = (uint32_t)error_state.error_type;
    if (error_state.status != WGPUPopErrorScopeStatus_Success) {
        result.failure = "pop_error_scope_failed";
        goto cleanup;
    }
    if (error_state.error_type == WGPUErrorType_NoError) {
        result.failure = "validation_error_not_observed";
        goto cleanup;
    }
    result.error_capture = true;

    result.pass = true;
    result.failure = "none";

cleanup:
    if (command_buffer != NULL) {
        wgpuCommandBufferRelease(command_buffer);
        command_buffer = NULL;
    }
    if (command_encoder != NULL) {
        wgpuCommandEncoderRelease(command_encoder);
        command_encoder = NULL;
    }
    if (work_buffer != NULL) {
        wgpuBufferRelease(work_buffer);
        work_buffer = NULL;
    }
    if (queue != NULL) {
        wgpuQueueRelease(queue);
        queue = NULL;
    }
    if (device != NULL) {
        wgpuDeviceDestroy(device);
        wgpuDeviceRelease(device);
        device = NULL;
    }
    if (adapter != NULL) {
        wgpuAdapterRelease(adapter);
        adapter = NULL;
    }
    if (instance != NULL) {
        wgpuInstanceRelease(instance);
        instance = NULL;
    }

    if (result.instance_create) {
        result.lifecycle = true;
    }

    if (!result.pass) {
        if (!result.adapter_request && adapter_state.message[0] != '\0') {
            fprintf(stderr, "dropin_behavior_adapter_message: %s\n", adapter_state.message);
        }
        if (result.adapter_request && !result.device_request && device_state.message[0] != '\0') {
            fprintf(stderr, "dropin_behavior_device_message: %s\n", device_state.message);
        }
        if (result.device_request && !result.queue_ops && queue_state.message[0] != '\0') {
            fprintf(stderr, "dropin_behavior_queue_message: %s\n", queue_state.message);
        }
        if (result.queue_ops && !result.error_capture && error_state.message[0] != '\0') {
            fprintf(stderr, "dropin_behavior_error_scope_message: %s\n", error_state.message);
        }
    }

    printf(
        "{\"schemaVersion\":1,\"pass\":%s,\"instanceCreate\":%s,\"adapterRequest\":%s,"
        "\"deviceRequest\":%s,\"queueOps\":%s,\"errorCapture\":%s,\"lifecycle\":%s,"
        "\"adapterStatus\":%u,\"deviceStatus\":%u,\"queueWorkDoneStatus\":%u,"
        "\"popErrorScopeStatus\":%u,\"popErrorType\":%u,\"failure\":\"%s\"}\n",
        bool_to_json(result.pass),
        bool_to_json(result.instance_create),
        bool_to_json(result.adapter_request),
        bool_to_json(result.device_request),
        bool_to_json(result.queue_ops),
        bool_to_json(result.error_capture),
        bool_to_json(result.lifecycle),
        (unsigned)result.adapter_status,
        (unsigned)result.device_status,
        (unsigned)result.queue_work_done_status,
        (unsigned)result.pop_error_scope_status,
        (unsigned)result.pop_error_type,
        result.failure
    );

    return result.pass ? 0 : 1;
}
