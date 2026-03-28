#define _POSIX_C_SOURCE 200809L

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#include <webgpu.h>

static const uint64_t ASYNC_TIMEOUT_MS = 5000;
static const uint32_t EXPECTED_VALUES[4] = {2, 4, 6, 8};
static const uint32_t INPUT_VALUES[4] = {1, 2, 3, 4};
static const size_t BUFFER_SIZE = sizeof(INPUT_VALUES);

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

typedef struct MapState {
    volatile bool done;
    WGPUMapAsyncStatus status;
    char message[256];
} MapState;

typedef struct ErrorScopeState {
    volatile bool done;
    WGPUPopErrorScopeStatus status;
    WGPUErrorType error_type;
    char message[256];
} ErrorScopeState;

typedef struct ConsumerResult {
    bool pass;
    bool instance_create;
    bool adapter_request;
    bool device_request;
    bool dispatch_submit;
    bool queue_callback;
    bool readback_callback;
    bool dispatch_result;
    bool validation_error;
    bool lifecycle;
    uint32_t adapter_status;
    uint32_t device_status;
    uint32_t queue_work_done_status;
    uint32_t map_status;
    uint32_t pop_error_scope_status;
    uint32_t pop_error_type;
    const char* failure;
} ConsumerResult;

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

static WGPUStringView str_view(const char* text) {
    WGPUStringView view = {0};
    if (text == NULL) {
        return view;
    }
    view.data = text;
    view.length = strlen(text);
    return view;
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

static void on_buffer_map(
    WGPUMapAsyncStatus status,
    WGPUStringView message,
    void* userdata1,
    void* userdata2
) {
    (void)userdata2;
    MapState* state = (MapState*)userdata1;
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

static bool request_adapter(WGPUInstance instance, AdapterRequestState* state) {
    const WGPUPowerPreference requests[] = {
        WGPUPowerPreference_HighPerformance,
        WGPUPowerPreference_Undefined,
        WGPUPowerPreference_LowPower,
    };
    for (size_t i = 0; i < sizeof(requests) / sizeof(requests[0]); ++i) {
        memset(state, 0, sizeof(*state));
        state->status = WGPURequestAdapterStatus_Error;
        WGPURequestAdapterCallbackInfo callback = WGPU_REQUEST_ADAPTER_CALLBACK_INFO_INIT;
        callback.mode = WGPUCallbackMode_AllowProcessEvents;
        callback.callback = on_request_adapter;
        callback.userdata1 = state;
        WGPURequestAdapterOptions options = WGPU_REQUEST_ADAPTER_OPTIONS_INIT;
        options.powerPreference = requests[i];
        wgpuInstanceRequestAdapter(instance, &options, callback);
        if (!wait_for_flag(instance, &state->done, ASYNC_TIMEOUT_MS)) {
            return false;
        }
        if (state->status == WGPURequestAdapterStatus_Success && state->adapter != NULL) {
            return true;
        }
    }
    return false;
}

static bool request_device(WGPUInstance instance, WGPUAdapter adapter, DeviceRequestState* state) {
    memset(state, 0, sizeof(*state));
    state->status = WGPURequestDeviceStatus_Error;
    WGPURequestDeviceCallbackInfo callback = WGPU_REQUEST_DEVICE_CALLBACK_INFO_INIT;
    callback.mode = WGPUCallbackMode_AllowProcessEvents;
    callback.callback = on_request_device;
    callback.userdata1 = state;
    WGPUDeviceDescriptor descriptor = WGPU_DEVICE_DESCRIPTOR_INIT;
    wgpuAdapterRequestDevice(adapter, &descriptor, callback);
    if (!wait_for_flag(instance, &state->done, ASYNC_TIMEOUT_MS)) {
        return false;
    }
    return state->status == WGPURequestDeviceStatus_Success && state->device != NULL;
}

int main(void) {
    static const char* shader_code =
        "@group(0) @binding(0) var<storage, read> input_data: array<u32>;\n"
        "@group(0) @binding(1) var<storage, read_write> output_data: array<u32>;\n"
        "@compute @workgroup_size(1)\n"
        "fn main(@builtin(global_invocation_id) gid: vec3u) {\n"
        "  let i = gid.x;\n"
        "  if (i < 4u) {\n"
        "    output_data[i] = input_data[i] * 2u;\n"
        "  }\n"
        "}\n";

    ConsumerResult result = {
        .pass = false,
        .instance_create = false,
        .adapter_request = false,
        .device_request = false,
        .dispatch_submit = false,
        .queue_callback = false,
        .readback_callback = false,
        .dispatch_result = false,
        .validation_error = false,
        .lifecycle = false,
        .adapter_status = 0,
        .device_status = 0,
        .queue_work_done_status = 0,
        .map_status = 0,
        .pop_error_scope_status = 0,
        .pop_error_type = 0,
        .failure = "unknown",
    };

    WGPUInstance instance = NULL;
    WGPUAdapter adapter = NULL;
    WGPUDevice device = NULL;
    WGPUQueue queue = NULL;
    WGPUShaderModule shader = NULL;
    WGPUComputePipeline pipeline = NULL;
    WGPUBindGroupLayout bind_group_layout = NULL;
    WGPUBindGroup bind_group = NULL;
    WGPUBuffer input_buffer = NULL;
    WGPUBuffer output_buffer = NULL;
    WGPUBuffer readback_buffer = NULL;
    WGPUCommandEncoder encoder = NULL;
    WGPUComputePassEncoder pass = NULL;
    WGPUCommandBuffer command_buffer = NULL;

    WGPUInstanceDescriptor instance_desc = WGPU_INSTANCE_DESCRIPTOR_INIT;
    instance = wgpuCreateInstance(&instance_desc);
    if (instance == NULL) {
        result.failure = "instance_create_failed";
        goto cleanup;
    }
    result.instance_create = true;

    AdapterRequestState adapter_state = {0};
    if (!request_adapter(instance, &adapter_state)) {
        result.failure = "adapter_request_timeout";
        goto cleanup;
    }
    result.adapter_status = (uint32_t)adapter_state.status;
    adapter = adapter_state.adapter;
    if (adapter_state.status != WGPURequestAdapterStatus_Success || adapter == NULL) {
        result.failure = "adapter_request_failed";
        goto cleanup;
    }
    result.adapter_request = true;

    DeviceRequestState device_state = {0};
    if (!request_device(instance, adapter, &device_state)) {
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

    WGPUBufferDescriptor input_desc = WGPU_BUFFER_DESCRIPTOR_INIT;
    input_desc.size = BUFFER_SIZE;
    input_desc.usage = WGPUBufferUsage_CopyDst | WGPUBufferUsage_Storage;
    input_buffer = wgpuDeviceCreateBuffer(device, &input_desc);
    if (input_buffer == NULL) {
        result.failure = "input_buffer_create_failed";
        goto cleanup;
    }

    WGPUBufferDescriptor output_desc = WGPU_BUFFER_DESCRIPTOR_INIT;
    output_desc.size = BUFFER_SIZE;
    output_desc.usage = WGPUBufferUsage_Storage | WGPUBufferUsage_CopySrc;
    output_buffer = wgpuDeviceCreateBuffer(device, &output_desc);
    if (output_buffer == NULL) {
        result.failure = "output_buffer_create_failed";
        goto cleanup;
    }

    WGPUBufferDescriptor readback_desc = WGPU_BUFFER_DESCRIPTOR_INIT;
    readback_desc.size = BUFFER_SIZE;
    readback_desc.usage = WGPUBufferUsage_CopyDst | WGPUBufferUsage_MapRead;
    readback_buffer = wgpuDeviceCreateBuffer(device, &readback_desc);
    if (readback_buffer == NULL) {
        result.failure = "readback_buffer_create_failed";
        goto cleanup;
    }

    WGPUShaderSourceWGSL wgsl = WGPU_SHADER_SOURCE_WGSL_INIT;
    wgsl.code = str_view(shader_code);
    WGPUShaderModuleDescriptor shader_desc = WGPU_SHADER_MODULE_DESCRIPTOR_INIT;
    shader_desc.nextInChain = &wgsl.chain;
    shader = wgpuDeviceCreateShaderModule(device, &shader_desc);
    if (shader == NULL) {
        result.failure = "shader_module_create_failed";
        goto cleanup;
    }

    WGPUComputePipelineDescriptor pipeline_desc = WGPU_COMPUTE_PIPELINE_DESCRIPTOR_INIT;
    pipeline_desc.layout = NULL;
    pipeline_desc.compute.module = shader;
    pipeline_desc.compute.entryPoint = str_view("main");
    pipeline = wgpuDeviceCreateComputePipeline(device, &pipeline_desc);
    if (pipeline == NULL) {
        result.failure = "compute_pipeline_create_failed";
        goto cleanup;
    }

    bind_group_layout = wgpuComputePipelineGetBindGroupLayout(pipeline, 0);
    if (bind_group_layout == NULL) {
        result.failure = "bind_group_layout_failed";
        goto cleanup;
    }

    WGPUBindGroupEntry entries[2];
    memset(entries, 0, sizeof(entries));
    entries[0].binding = 0;
    entries[0].buffer = input_buffer;
    entries[0].offset = 0;
    entries[0].size = BUFFER_SIZE;
    entries[1].binding = 1;
    entries[1].buffer = output_buffer;
    entries[1].offset = 0;
    entries[1].size = BUFFER_SIZE;

    WGPUBindGroupDescriptor bind_group_desc = WGPU_BIND_GROUP_DESCRIPTOR_INIT;
    bind_group_desc.layout = bind_group_layout;
    bind_group_desc.entryCount = 2;
    bind_group_desc.entries = entries;
    bind_group = wgpuDeviceCreateBindGroup(device, &bind_group_desc);
    if (bind_group == NULL) {
        result.failure = "bind_group_create_failed";
        goto cleanup;
    }

    wgpuQueueWriteBuffer(queue, input_buffer, 0, INPUT_VALUES, BUFFER_SIZE);

    WGPUCommandEncoderDescriptor encoder_desc = WGPU_COMMAND_ENCODER_DESCRIPTOR_INIT;
    encoder = wgpuDeviceCreateCommandEncoder(device, &encoder_desc);
    if (encoder == NULL) {
        result.failure = "command_encoder_create_failed";
        goto cleanup;
    }

    WGPUComputePassDescriptor pass_desc = WGPU_COMPUTE_PASS_DESCRIPTOR_INIT;
    pass = wgpuCommandEncoderBeginComputePass(encoder, &pass_desc);
    if (pass == NULL) {
        result.failure = "compute_pass_create_failed";
        goto cleanup;
    }

    wgpuComputePassEncoderSetPipeline(pass, pipeline);
    wgpuComputePassEncoderSetBindGroup(pass, 0, bind_group, 0, NULL);
    wgpuComputePassEncoderDispatchWorkgroups(pass, 4, 1, 1);
    wgpuComputePassEncoderEnd(pass);
    wgpuComputePassEncoderRelease(pass);
    pass = NULL;

    wgpuCommandEncoderCopyBufferToBuffer(encoder, output_buffer, 0, readback_buffer, 0, BUFFER_SIZE);

    WGPUCommandBufferDescriptor command_desc = WGPU_COMMAND_BUFFER_DESCRIPTOR_INIT;
    command_buffer = wgpuCommandEncoderFinish(encoder, &command_desc);
    if (command_buffer == NULL) {
        result.failure = "command_buffer_finish_failed";
        goto cleanup;
    }

    wgpuQueueSubmit(queue, 1, &command_buffer);
    result.dispatch_submit = true;

    QueueWorkDoneState queue_state = {0};
    queue_state.status = WGPUQueueWorkDoneStatus_Error;
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
    result.queue_callback = true;

    MapState map_state = {0};
    map_state.status = WGPUMapAsyncStatus_Error;
    WGPUBufferMapCallbackInfo map_callback = WGPU_BUFFER_MAP_CALLBACK_INFO_INIT;
    map_callback.mode = WGPUCallbackMode_AllowProcessEvents;
    map_callback.callback = on_buffer_map;
    map_callback.userdata1 = &map_state;
    wgpuBufferMapAsync(readback_buffer, WGPUMapMode_Read, 0, BUFFER_SIZE, map_callback);
    if (!wait_for_flag(instance, &map_state.done, ASYNC_TIMEOUT_MS)) {
        result.failure = "buffer_map_timeout";
        goto cleanup;
    }
    result.map_status = (uint32_t)map_state.status;
    if (map_state.status != WGPUMapAsyncStatus_Success) {
        result.failure = "buffer_map_failed";
        goto cleanup;
    }
    result.readback_callback = true;

    const uint32_t* mapped = (const uint32_t*)wgpuBufferGetConstMappedRange(readback_buffer, 0, BUFFER_SIZE);
    if (mapped == NULL) {
        result.failure = "mapped_range_null";
        goto cleanup;
    }
    if (memcmp(mapped, EXPECTED_VALUES, BUFFER_SIZE) != 0) {
        result.failure = "dispatch_result_mismatch";
        goto cleanup;
    }
    result.dispatch_result = true;
    wgpuBufferUnmap(readback_buffer);

    wgpuDevicePushErrorScope(device, WGPUErrorFilter_Validation);
    wgpuQueueWriteBuffer(queue, output_buffer, BUFFER_SIZE + sizeof(uint32_t), INPUT_VALUES, sizeof(uint32_t));
    ErrorScopeState error_state = {0};
    error_state.status = WGPUPopErrorScopeStatus_Error;
    error_state.error_type = WGPUErrorType_NoError;
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
    result.validation_error = true;

    result.pass = true;
    result.failure = "none";

cleanup:
    if (pass != NULL) {
        wgpuComputePassEncoderRelease(pass);
        pass = NULL;
    }
    if (command_buffer != NULL) {
        wgpuCommandBufferRelease(command_buffer);
        command_buffer = NULL;
    }
    if (encoder != NULL) {
        wgpuCommandEncoderRelease(encoder);
        encoder = NULL;
    }
    if (bind_group != NULL) {
        wgpuBindGroupRelease(bind_group);
        bind_group = NULL;
    }
    if (bind_group_layout != NULL) {
        wgpuBindGroupLayoutRelease(bind_group_layout);
        bind_group_layout = NULL;
    }
    if (pipeline != NULL) {
        wgpuComputePipelineRelease(pipeline);
        pipeline = NULL;
    }
    if (shader != NULL) {
        wgpuShaderModuleRelease(shader);
        shader = NULL;
    }
    if (readback_buffer != NULL) {
        wgpuBufferRelease(readback_buffer);
        readback_buffer = NULL;
    }
    if (output_buffer != NULL) {
        wgpuBufferRelease(output_buffer);
        output_buffer = NULL;
    }
    if (input_buffer != NULL) {
        wgpuBufferRelease(input_buffer);
        input_buffer = NULL;
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

    printf(
        "{\"schemaVersion\":1,\"pass\":%s,\"instanceCreate\":%s,\"adapterRequest\":%s,"
        "\"deviceRequest\":%s,\"dispatchSubmit\":%s,\"queueCallback\":%s,"
        "\"readbackCallback\":%s,\"dispatchResult\":%s,\"validationError\":%s,"
        "\"lifecycle\":%s,\"adapterStatus\":%u,\"deviceStatus\":%u,"
        "\"queueWorkDoneStatus\":%u,\"mapStatus\":%u,\"popErrorScopeStatus\":%u,"
        "\"popErrorType\":%u,\"failure\":\"%s\"}\n",
        result.pass ? "true" : "false",
        result.instance_create ? "true" : "false",
        result.adapter_request ? "true" : "false",
        result.device_request ? "true" : "false",
        result.dispatch_submit ? "true" : "false",
        result.queue_callback ? "true" : "false",
        result.readback_callback ? "true" : "false",
        result.dispatch_result ? "true" : "false",
        result.validation_error ? "true" : "false",
        result.lifecycle ? "true" : "false",
        (unsigned)result.adapter_status,
        (unsigned)result.device_status,
        (unsigned)result.queue_work_done_status,
        (unsigned)result.map_status,
        (unsigned)result.pop_error_scope_status,
        (unsigned)result.pop_error_type,
        result.failure
    );

    return result.pass ? 0 : 1;
}
