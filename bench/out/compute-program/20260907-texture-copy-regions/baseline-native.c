#include "webgpu.h"
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

extern WGPUCommandBuffer doeNativeCreateComputeDispatchCopyCommandBuffer(
    WGPUDevice, WGPUComputePipeline, WGPUBindGroup*, uint32_t, uint32_t, uint32_t, uint32_t,
    WGPUBuffer, uint64_t, WGPUBuffer, uint64_t, uint64_t);
extern WGPUCommandBuffer doeNativeCreateComputeDispatchBatchCopyCommandBuffer(
    WGPUDevice, size_t, WGPUComputePipeline*, WGPUBindGroup*, const uint32_t*, const uint32_t*,
    WGPUBuffer, uint64_t, WGPUBuffer, uint64_t, uint64_t);

enum { ELEMENT_COUNT = 4, NATIVE_BIND_GROUP_STRIDE = 4, AMD_PCI_VENDOR_ID = 0x1002,
       TEXTURE_ROW_BYTES = 256, TEXTURE_LAYER_COUNT = 2, RESIDENT_STORAGE_BYTES = 65536 };
static const uint32_t PADDING_SENTINEL = 0xaabbccddu;

static void adapter_ready(WGPURequestAdapterStatus status, WGPUAdapter adapter,
                          WGPUStringView message, void* result, void* unused) {
    (void)message; (void)unused;
    if (status == WGPURequestAdapterStatus_Success) *(WGPUAdapter*)result = adapter;
}

static void device_ready(WGPURequestDeviceStatus status, WGPUDevice device,
                         WGPUStringView message, void* result, void* unused) {
    (void)message; (void)unused;
    if (status == WGPURequestDeviceStatus_Success) *(WGPUDevice*)result = device;
}

static void map_ready(WGPUMapAsyncStatus status, WGPUStringView message, void* result, void* unused) {
    (void)message; (void)unused;
    *(bool*)result = status == WGPUMapAsyncStatus_Success;
}

static void scope_ready(WGPUPopErrorScopeStatus status, WGPUErrorType type, WGPUStringView message,
                        void* result, void* unused) {
    (void)message; (void)unused;
    *(bool*)result = status == WGPUPopErrorScopeStatus_Success && type == WGPUErrorType_Validation;
}

static bool pop_validation(WGPUInstance instance, WGPUDevice device) {
    bool validation = false;
    WGPUPopErrorScopeCallbackInfo callback = WGPU_POP_ERROR_SCOPE_CALLBACK_INFO_INIT;
    callback.mode = WGPUCallbackMode_AllowSpontaneous;
    callback.callback = scope_ready;
    callback.userdata1 = &validation;
    wgpuDevicePopErrorScope(device, callback);
    wgpuInstanceProcessEvents(instance);
    return validation;
}

static bool invalid_pass_lifetimes(WGPUInstance instance, WGPUDevice device, WGPUQueue queue) {
    enum { FINISH_OPEN, END_TWICE, STALE_PASS, NESTED_PASS, IMMEDIATE_PAYLOAD, PASS_CASE_COUNT };
    for (unsigned scenario = 0; scenario < PASS_CASE_COUNT; ++scenario) {
        WGPUCommandEncoder encoder = wgpuDeviceCreateCommandEncoder(device, NULL);
        if (!encoder) return false;
        WGPUComputePassEncoder pass = wgpuCommandEncoderBeginComputePass(encoder, NULL);
        if (!pass) { wgpuCommandEncoderRelease(encoder); return false; }
        WGPUComputePassEncoder next = NULL;
        wgpuDevicePushErrorScope(device, WGPUErrorFilter_Validation);
        if (scenario == END_TWICE) {
            wgpuComputePassEncoderEnd(pass);
            wgpuComputePassEncoderEnd(pass);
        } else if (scenario == STALE_PASS) {
            wgpuComputePassEncoderEnd(pass);
            next = wgpuCommandEncoderBeginComputePass(encoder, NULL);
            wgpuComputePassEncoderInsertDebugMarker(pass, (WGPUStringView){"stale", 5});
        } else if (scenario == NESTED_PASS) {
            next = wgpuCommandEncoderBeginComputePass(encoder, NULL);
        } else if (scenario == IMMEDIATE_PAYLOAD) {
            const uint32_t value = 7;
            wgpuComputePassEncoderSetImmediates(pass, 0, &value, sizeof(value));
            wgpuComputePassEncoderEnd(pass);
        }
        WGPUCommandBuffer commands = wgpuCommandEncoderFinish(encoder, NULL);
        const bool rejected_recording = pop_validation(instance, device);
        if (next) wgpuComputePassEncoderRelease(next);
        wgpuComputePassEncoderRelease(pass);
        wgpuCommandEncoderRelease(encoder);
        bool rejected_submit = false;
        if (commands) {
            wgpuDevicePushErrorScope(device, WGPUErrorFilter_Validation);
            wgpuQueueSubmit(queue, 1, &commands);
            rejected_submit = pop_validation(instance, device);
            wgpuCommandBufferRelease(commands);
        }
        if (!rejected_recording || !rejected_submit) {
            fprintf(stderr, "native pass lifecycle failed: case=%u recording=%u submission=%u\n",
                scenario, rejected_recording, rejected_submit);
            return false;
        }
    }
    WGPUPipelineLayoutDescriptor layout_desc = WGPU_PIPELINE_LAYOUT_DESCRIPTOR_INIT;
    layout_desc.immediateSize = sizeof(uint32_t);
    wgpuDevicePushErrorScope(device, WGPUErrorFilter_Validation);
    WGPUPipelineLayout layout = wgpuDeviceCreatePipelineLayout(device, &layout_desc);
    const bool rejected_layout = pop_validation(instance, device);
    if (layout) wgpuPipelineLayoutRelease(layout);
    if (layout || !rejected_layout) return false;
    printf("passed: invalid pass lifetimes and unsupported immediate payloads/layouts reject before execution\n");
    return true;
}

static bool texture_is_zero(WGPUInstance instance, WGPUDevice device, WGPUQueue queue,
                            WGPUTexture texture, WGPUBuffer readback) {
    WGPUCommandEncoder encoder = wgpuDeviceCreateCommandEncoder(device, NULL);
    if (!encoder) return false;
    WGPUTexelCopyTextureInfo source = WGPU_TEXEL_COPY_TEXTURE_INFO_INIT;
    source.texture = texture;
    WGPUTexelCopyBufferInfo target = WGPU_TEXEL_COPY_BUFFER_INFO_INIT;
    target.buffer = readback;
    target.layout.bytesPerRow = TEXTURE_ROW_BYTES;
    target.layout.rowsPerImage = 1;
    WGPUExtent3D extent = {ELEMENT_COUNT, 1, 1};
    wgpuCommandEncoderCopyTextureToBuffer(encoder, &source, &target, &extent);
    WGPUCommandBuffer commands = wgpuCommandEncoderFinish(encoder, NULL);
    wgpuCommandEncoderRelease(encoder);
    if (!commands) return false;
    wgpuQueueSubmit(queue, 1, &commands);
    wgpuCommandBufferRelease(commands);
    bool mapped = false;
    WGPUBufferMapCallbackInfo mapping = WGPU_BUFFER_MAP_CALLBACK_INFO_INIT;
    mapping.mode = WGPUCallbackMode_AllowSpontaneous;
    mapping.callback = map_ready;
    mapping.userdata1 = &mapped;
    wgpuBufferMapAsync(readback, WGPUMapMode_Read, 0, ELEMENT_COUNT * sizeof(uint32_t), mapping);
    wgpuInstanceProcessEvents(instance);
    if (!mapped) return false;
    const uint32_t* output = wgpuBufferGetConstMappedRange(readback, 0, ELEMENT_COUNT * sizeof(uint32_t));
    bool zero = output != NULL;
    for (size_t index = 0; output && index < ELEMENT_COUNT; ++index) zero &= output[index] == 0;
    wgpuBufferUnmap(readback);
    return zero;
}

static bool invalid_buffer_copies(WGPUInstance instance, WGPUDevice device, WGPUQueue queue) {
    enum { SOURCE_ALIGNMENT, DESTINATION_ALIGNMENT, SIZE_ALIGNMENT, SOURCE_RANGE,
           DESTINATION_RANGE, SAME_BUFFER, SOURCE_USAGE, DESTINATION_USAGE,
           ZERO_SIZE_USAGE, COPY_CASE_COUNT };
    WGPUBufferDescriptor desc = WGPU_BUFFER_DESCRIPTOR_INIT;
    desc.size = ELEMENT_COUNT * sizeof(uint32_t);
    desc.usage = WGPUBufferUsage_CopySrc | WGPUBufferUsage_CopyDst;
    WGPUBuffer source = wgpuDeviceCreateBuffer(device, &desc);
    WGPUBuffer destination = wgpuDeviceCreateBuffer(device, &desc);
    desc.usage = WGPUBufferUsage_Storage;
    WGPUBuffer wrong_usage = wgpuDeviceCreateBuffer(device, &desc);
    bool success = source && destination && wrong_usage;
    for (unsigned scenario = 0; success && scenario < COPY_CASE_COUNT; ++scenario) {
        WGPUCommandEncoder encoder = wgpuDeviceCreateCommandEncoder(device, NULL);
        if (!encoder) { success = false; break; }
        const uint64_t source_offset = scenario == SOURCE_ALIGNMENT ? 1 :
            scenario == SOURCE_RANGE ? desc.size : 0;
        const uint64_t destination_offset = scenario == DESTINATION_ALIGNMENT ? 1 :
            scenario == DESTINATION_RANGE ? desc.size : 0;
        const uint64_t size = scenario == SIZE_ALIGNMENT ? 1 :
            scenario == ZERO_SIZE_USAGE ? 0 : sizeof(uint32_t);
        WGPUBuffer src = scenario == SOURCE_USAGE || scenario == ZERO_SIZE_USAGE ? wrong_usage : source;
        WGPUBuffer dst = scenario == SAME_BUFFER ? source :
            scenario == DESTINATION_USAGE ? wrong_usage : destination;
        wgpuDevicePushErrorScope(device, WGPUErrorFilter_Validation);
        wgpuCommandEncoderCopyBufferToBuffer(encoder, src, source_offset, dst, destination_offset, size);
        WGPUCommandBuffer commands = wgpuCommandEncoderFinish(encoder, NULL);
        const bool recording_rejected = pop_validation(instance, device);
        wgpuCommandEncoderRelease(encoder);
        bool submit_rejected = false;
        if (commands && recording_rejected) {
            wgpuDevicePushErrorScope(device, WGPUErrorFilter_Validation);
            wgpuQueueSubmit(queue, 1, &commands);
            submit_rejected = pop_validation(instance, device);
        }
        if (commands) wgpuCommandBufferRelease(commands);
        success = recording_rejected && submit_rejected;
        if (!success) fprintf(stderr, "invalid buffer copy admitted: case=%u recording=%u submission=%u\n",
                              scenario, recording_rejected, submit_rejected);
    }
    if (source) wgpuBufferRelease(source);
    if (destination) wgpuBufferRelease(destination);
    if (wrong_usage) wgpuBufferRelease(wrong_usage);
    if (success) printf("passed: buffer copy alignment, range, identity, usage and empty-copy validation\n");
    return success;
}

static bool buffer_matches_u32(WGPUInstance instance, WGPUBuffer buffer, uint32_t expected) {
    bool mapped = false;
    WGPUBufferMapCallbackInfo callback = WGPU_BUFFER_MAP_CALLBACK_INFO_INIT;
    callback.mode = WGPUCallbackMode_AllowSpontaneous;
    callback.callback = map_ready;
    callback.userdata1 = &mapped;
    wgpuBufferMapAsync(buffer, WGPUMapMode_Read, 0, sizeof(expected), callback);
    wgpuInstanceProcessEvents(instance);
    const uint32_t* output = mapped ? wgpuBufferGetConstMappedRange(buffer, 0, sizeof(expected)) : NULL;
    const bool matches = output && *output == expected;
    if (mapped) wgpuBufferUnmap(buffer);
    return matches;
}

static bool unavailable_copy_resources(WGPUInstance instance, WGPUDevice device, WGPUQueue queue) {
    enum { MAPPED_SOURCE, MAPPED_DESTINATION, DESTROYED_SOURCE, DESTROYED_DESTINATION,
           UNMAPPED_BEFORE_SUBMIT, RELEASED_SOURCE, AVAILABILITY_CASE_COUNT };
    const uint32_t expected = 0x12345678u;
    for (unsigned scenario = 0; scenario < AVAILABILITY_CASE_COUNT; ++scenario) {
        WGPUBufferDescriptor desc = WGPU_BUFFER_DESCRIPTOR_INIT;
        desc.size = sizeof(expected);
        desc.usage = WGPUBufferUsage_CopySrc;
        desc.mappedAtCreation = WGPU_TRUE;
        WGPUBuffer source = wgpuDeviceCreateBuffer(device, &desc);
        desc.usage = WGPUBufferUsage_CopyDst | WGPUBufferUsage_MapRead;
        desc.mappedAtCreation = scenario == MAPPED_DESTINATION ? WGPU_TRUE : WGPU_FALSE;
        WGPUBuffer destination = wgpuDeviceCreateBuffer(device, &desc);
        if (!source || !destination) return false;
        uint32_t* input = wgpuBufferGetMappedRange(source, 0, sizeof(expected));
        if (!input) return false;
        *input = expected;
        if (scenario != MAPPED_SOURCE && scenario != UNMAPPED_BEFORE_SUBMIT) wgpuBufferUnmap(source);
        WGPUCommandEncoder encoder = wgpuDeviceCreateCommandEncoder(device, NULL);
        if (!encoder) return false;
        wgpuDevicePushErrorScope(device, WGPUErrorFilter_Validation);
        wgpuCommandEncoderCopyBufferToBuffer(encoder, source, 0, destination, 0, sizeof(expected));
        WGPUCommandBuffer commands = wgpuCommandEncoderFinish(encoder, NULL);
        wgpuCommandEncoderRelease(encoder);
        const bool recording_rejected = pop_validation(instance, device);
        if (!commands || recording_rejected) return false;
        if (scenario == DESTROYED_SOURCE) wgpuBufferDestroy(source);
        if (scenario == DESTROYED_DESTINATION) wgpuBufferDestroy(destination);
        if (scenario == UNMAPPED_BEFORE_SUBMIT) wgpuBufferUnmap(source);
        if (scenario == RELEASED_SOURCE) { wgpuBufferRelease(source); source = NULL; }
        desc.mappedAtCreation = WGPU_FALSE;
        WGPUBuffer witness = wgpuDeviceCreateBuffer(device, &desc);
        if (!witness) return false;
        wgpuQueueWriteBuffer(queue, witness, 0, &expected, sizeof(expected));
        encoder = wgpuDeviceCreateCommandEncoder(device, NULL);
        if (!encoder) return false;
        wgpuCommandEncoderClearBuffer(encoder, witness, 0, sizeof(expected));
        WGPUCommandBuffer first = wgpuCommandEncoderFinish(encoder, NULL);
        wgpuCommandEncoderRelease(encoder);
        if (!first) return false;
        WGPUCommandBuffer batch[] = {first, commands};
        wgpuDevicePushErrorScope(device, WGPUErrorFilter_Validation);
        wgpuQueueSubmit(queue, 2, batch);
        const bool rejected = pop_validation(instance, device);
        const bool should_reject = scenario <= DESTROYED_DESTINATION;
        bool success = rejected == should_reject;
        if (success) success = buffer_matches_u32(instance, witness, should_reject ? expected : 0);
        if (!should_reject && success) success = buffer_matches_u32(instance, destination, expected);
        wgpuCommandBufferRelease(first);
        wgpuBufferRelease(witness);
        wgpuCommandBufferRelease(commands);
        if (source) wgpuBufferRelease(source);
        wgpuBufferRelease(destination);
        if (!success) {
            fprintf(stderr, "queue availability failed: case=%u rejected=%u expected=%u\n",
                    scenario, rejected, should_reject);
            return false;
        }
    }
    printf("passed: submission rejects mapped/destroyed buffers; unmap and caller release preserve valid copies\n");
    return true;
}

static bool texture_submission_lifetime(WGPUInstance instance, WGPUDevice device, WGPUQueue queue) {
    const uint32_t expected = 0x76543210u;
    for (unsigned destroy = 0; destroy < 2; ++destroy) {
        WGPUTextureDescriptor desc = WGPU_TEXTURE_DESCRIPTOR_INIT;
        desc.usage = WGPUTextureUsage_CopySrc | WGPUTextureUsage_CopyDst;
        desc.dimension = WGPUTextureDimension_2D;
        desc.size = (WGPUExtent3D){1, 1, 1};
        desc.format = WGPUTextureFormat_R32Uint;
        WGPUTexture texture = wgpuDeviceCreateTexture(device, &desc);
        WGPUBufferDescriptor buffer_desc = WGPU_BUFFER_DESCRIPTOR_INIT;
        buffer_desc.size = sizeof(expected);
        buffer_desc.usage = WGPUBufferUsage_CopySrc;
        buffer_desc.mappedAtCreation = WGPU_TRUE;
        WGPUBuffer input = wgpuDeviceCreateBuffer(device, &buffer_desc);
        buffer_desc.usage = WGPUBufferUsage_CopyDst | WGPUBufferUsage_MapRead;
        buffer_desc.mappedAtCreation = WGPU_FALSE;
        WGPUBuffer output = wgpuDeviceCreateBuffer(device, &buffer_desc);
        if (!texture || !input || !output) return false;
        uint32_t* mapped = wgpuBufferGetMappedRange(input, 0, sizeof(expected));
        if (!mapped) return false;
        *mapped = expected;
        wgpuBufferUnmap(input);
        WGPUTexelCopyTextureInfo texture_copy = WGPU_TEXEL_COPY_TEXTURE_INFO_INIT;
        texture_copy.texture = texture;
        WGPUTexelCopyBufferInfo buffer_copy = WGPU_TEXEL_COPY_BUFFER_INFO_INIT;
        buffer_copy.buffer = input;
        buffer_copy.layout.bytesPerRow = TEXTURE_ROW_BYTES;
        buffer_copy.layout.rowsPerImage = 1;
        WGPUCommandEncoder encoder = wgpuDeviceCreateCommandEncoder(device, NULL);
        if (!encoder) return false;
        wgpuCommandEncoderCopyBufferToTexture(encoder, &buffer_copy, &texture_copy, &desc.size);
        buffer_copy.buffer = output;
        wgpuCommandEncoderCopyTextureToBuffer(encoder, &texture_copy, &buffer_copy, &desc.size);
        WGPUCommandBuffer commands = wgpuCommandEncoderFinish(encoder, NULL);
        wgpuCommandEncoderRelease(encoder);
        if (!commands) return false;
        if (destroy) {
            wgpuTextureDestroy(texture);
            wgpuTextureDestroy(texture);
            wgpuDevicePushErrorScope(device, WGPUErrorFilter_Validation);
            WGPUTextureView view = wgpuTextureCreateView(texture, NULL);
            bool view_rejected = pop_validation(instance, device);
            if (view) wgpuTextureViewRelease(view);
            if (!view || view_rejected) return false;
            wgpuDevicePushErrorScope(device, WGPUErrorFilter_Validation);
            wgpuQueueWriteTexture(queue, &texture_copy, &expected, sizeof(expected), &buffer_copy.layout, &desc.size);
            if (!pop_validation(instance, device)) return false;
        }
        wgpuTextureRelease(texture);
        wgpuBufferRelease(input);
        wgpuDevicePushErrorScope(device, WGPUErrorFilter_Validation);
        wgpuQueueSubmit(queue, 1, &commands);
        const bool rejected = pop_validation(instance, device);
        bool success = rejected == (destroy != 0);
        if (!destroy && success) success = buffer_matches_u32(instance, output, expected);
        wgpuCommandBufferRelease(commands);
        wgpuBufferRelease(output);
        if (!success) return false;
    }
    printf("passed: texture caller release preserves copies; explicit destruction rejects submission and writes\n");
    return true;
}

static bool texture_region_copies(WGPUInstance instance, WGPUDevice device, WGPUQueue queue) {
    enum { MIP_WIDTH = 4, MIP_HEIGHT = 4, LAYERS = 4, STORAGE_BYTES = TEXTURE_ROW_BYTES * MIP_HEIGHT * LAYERS,
           PATCH_OFFSET = 16, PATCH_ROWS = 3, PATCH_WIDTH = 2, PATCH_HEIGHT = 2 };
    const uint32_t initial = 0x24681357u;
    for (unsigned volume = 0; volume < 2; ++volume) {
        WGPUTextureDescriptor desc = WGPU_TEXTURE_DESCRIPTOR_INIT;
        desc.usage = WGPUTextureUsage_CopySrc | WGPUTextureUsage_CopyDst;
        desc.dimension = volume ? WGPUTextureDimension_3D : WGPUTextureDimension_2D;
        desc.size = (WGPUExtent3D){MIP_WIDTH * 2, MIP_HEIGHT * 2, LAYERS};
        desc.mipLevelCount = 2;
        desc.format = WGPUTextureFormat_R32Uint;
        WGPUTexture texture = wgpuDeviceCreateTexture(device, &desc);
        WGPUBufferDescriptor bd = WGPU_BUFFER_DESCRIPTOR_INIT;
        bd.size = STORAGE_BYTES;
        bd.usage = WGPUBufferUsage_CopySrc;
        bd.mappedAtCreation = WGPU_TRUE;
        WGPUBuffer input = wgpuDeviceCreateBuffer(device, &bd);
        WGPUBuffer patch = wgpuDeviceCreateBuffer(device, &bd);
        bd.usage = WGPUBufferUsage_CopyDst | WGPUBufferUsage_MapRead;
        bd.mappedAtCreation = WGPU_FALSE;
        WGPUBuffer output = wgpuDeviceCreateBuffer(device, &bd);
        if (!texture || !input || !patch || !output) return false;
        uint32_t* initial_data = wgpuBufferGetMappedRange(input, 0, STORAGE_BYTES);
        uint32_t* patch_data = wgpuBufferGetMappedRange(patch, 0, STORAGE_BYTES);
        if (!initial_data || !patch_data) return false;
        for (size_t i = 0; i < STORAGE_BYTES / sizeof(uint32_t); ++i) {
            initial_data[i] = initial;
            patch_data[i] = PADDING_SENTINEL;
        }
        const unsigned patch_layers = volume ? 1 : 2;
        for (unsigned z = 0; z < patch_layers; ++z)
            for (unsigned y = 0; y < PATCH_HEIGHT; ++y)
                for (unsigned x = 0; x < PATCH_WIDTH; ++x)
                    patch_data[(PATCH_OFFSET + (z * PATCH_ROWS + y) * TEXTURE_ROW_BYTES) / sizeof(uint32_t) + x] =
                        0x10100000u + z * 100 + y * 10 + x;
        wgpuBufferUnmap(input);
        wgpuBufferUnmap(patch);
        WGPUCommandEncoder encoder = wgpuDeviceCreateCommandEncoder(device, NULL);
        if (!encoder) return false;
        WGPUTexelCopyTextureInfo tc = WGPU_TEXEL_COPY_TEXTURE_INFO_INIT;
        tc.texture = texture;
        tc.mipLevel = 1;
        WGPUTexelCopyBufferInfo bc = WGPU_TEXEL_COPY_BUFFER_INFO_INIT;
        bc.buffer = input;
        bc.layout.bytesPerRow = TEXTURE_ROW_BYTES;
        bc.layout.rowsPerImage = MIP_HEIGHT;
        WGPUExtent3D full = {MIP_WIDTH, MIP_HEIGHT, volume ? LAYERS / 2 : LAYERS};
        wgpuCommandEncoderCopyBufferToTexture(encoder, &bc, &tc, &full);
        bc.buffer = patch;
        bc.layout.offset = PATCH_OFFSET;
        bc.layout.rowsPerImage = PATCH_ROWS;
        tc.origin = (WGPUOrigin3D){1, 2, 1};
        WGPUExtent3D patch_size = {PATCH_WIDTH, PATCH_HEIGHT, patch_layers};
        wgpuCommandEncoderCopyBufferToTexture(encoder, &bc, &tc, &patch_size);
        tc.origin = (WGPUOrigin3D){0, 0, 0};
        bc.buffer = output;
        bc.layout.offset = 0;
        bc.layout.rowsPerImage = MIP_HEIGHT;
        wgpuCommandEncoderCopyTextureToBuffer(encoder, &tc, &bc, &full);
        WGPUCommandBuffer commands = wgpuCommandEncoderFinish(encoder, NULL);
        wgpuCommandEncoderRelease(encoder);
        if (!commands) return false;
        wgpuTextureRelease(texture);
        wgpuBufferRelease(input);
        wgpuBufferRelease(patch);
        wgpuDevicePushErrorScope(device, WGPUErrorFilter_Validation);
        wgpuQueueSubmit(queue, 1, &commands);
        const bool rejected = pop_validation(instance, device);
        bool mapped = false;
        WGPUBufferMapCallbackInfo callback = WGPU_BUFFER_MAP_CALLBACK_INFO_INIT;
        callback.mode = WGPUCallbackMode_AllowSpontaneous;
        callback.callback = map_ready;
        callback.userdata1 = &mapped;
        wgpuBufferMapAsync(output, WGPUMapMode_Read, 0, STORAGE_BYTES, callback);
        wgpuInstanceProcessEvents(instance);
        const uint32_t* actual = mapped ? wgpuBufferGetConstMappedRange(output, 0, STORAGE_BYTES) : NULL;
        bool success = !rejected && actual;
        for (unsigned z = 0; success && z < full.depthOrArrayLayers; ++z)
            for (unsigned y = 0; success && y < MIP_HEIGHT; ++y)
                for (unsigned x = 0; success && x < MIP_WIDTH; ++x) {
                    const bool inside = z >= 1 && z < 1 + patch_layers && y >= 2 && x >= 1 && x < 3;
                    const uint32_t expected = inside ? 0x10100000u + (z - 1) * 100 + (y - 2) * 10 + x - 1 : initial;
                    const uint32_t value = actual[(z * MIP_HEIGHT + y) * TEXTURE_ROW_BYTES / sizeof(uint32_t) + x];
                    if (value != expected) {
                        fprintf(stderr, "texture origin mismatch: volume=%u xyz=%u,%u,%u got=%u expected=%u\n", volume, x, y, z, value, expected);
                        success = false;
                    }
                }
        if (mapped) wgpuBufferUnmap(output);
        wgpuCommandBufferRelease(commands);
        wgpuBufferRelease(output);
        if (!success) return false;
    }
    printf("passed: texture copies preserve mip-relative array and volume origins, patch strides and untouched pixels\n");
    return true;
}

static bool execute(WGPUInstance instance, WGPUDevice device, WGPUQueue queue,
                    bool batch, bool via_texture, bool resident_roundtrip) {
    bool success = false, mapped = false;
    WGPUShaderModule shader = NULL;
    WGPUComputePipeline pipeline = NULL;
    WGPUBindGroupLayout layout = NULL;
    WGPUBindGroup group = NULL;
    WGPUBuffer storage = NULL, readback = NULL;
    WGPUTexture texture = NULL;
    WGPUCommandBuffer commands = NULL;
    const uint32_t input[ELEMENT_COUNT] = {17, 29, 43, 71};
    static const char wgsl[] =
        "@group(0) @binding(0) var<storage, read_write> values: array<u32>;"
        "@compute @workgroup_size(1) fn main(@builtin(global_invocation_id) id: vec3<u32>) {"
        "values[id.x] = values[id.x] + 1u; }";
#define REQUIRE(condition) do { if (!(condition)) { \
    fprintf(stderr, "native recorded compute failed at line %d: %s\n", __LINE__, #condition); \
    goto cleanup; } } while (0)
    WGPUShaderSourceWGSL source = WGPU_SHADER_SOURCE_WGSL_INIT;
    source.code = (WGPUStringView){wgsl, sizeof(wgsl) - 1};
    WGPUShaderModuleDescriptor shader_desc = WGPU_SHADER_MODULE_DESCRIPTOR_INIT;
    shader_desc.nextInChain = &source.chain;
    shader = wgpuDeviceCreateShaderModule(device, &shader_desc);
    REQUIRE(shader);
    WGPUComputePipelineDescriptor pipeline_desc = WGPU_COMPUTE_PIPELINE_DESCRIPTOR_INIT;
    pipeline_desc.compute.module = shader;
    pipeline_desc.compute.entryPoint = (WGPUStringView){"main", 4};
    pipeline = wgpuDeviceCreateComputePipeline(device, &pipeline_desc);
    REQUIRE(pipeline);
    layout = wgpuComputePipelineGetBindGroupLayout(pipeline, 0);
    REQUIRE(layout);
    WGPUBufferDescriptor buffer_desc = WGPU_BUFFER_DESCRIPTOR_INIT;
    buffer_desc.size = via_texture ? TEXTURE_ROW_BYTES + sizeof(input) : sizeof(input);
    if (resident_roundtrip) buffer_desc.size = RESIDENT_STORAGE_BYTES;
    buffer_desc.usage = WGPUBufferUsage_Storage | WGPUBufferUsage_CopySrc | WGPUBufferUsage_CopyDst;
    storage = wgpuDeviceCreateBuffer(device, &buffer_desc);
    if (via_texture) buffer_desc.size = TEXTURE_ROW_BYTES * TEXTURE_LAYER_COUNT;
    buffer_desc.usage = WGPUBufferUsage_MapRead | WGPUBufferUsage_CopyDst;
    readback = wgpuDeviceCreateBuffer(device, &buffer_desc);
    REQUIRE(storage && readback);
    wgpuQueueWriteBuffer(queue, storage, 0, input, sizeof(input));
    if (via_texture) wgpuQueueWriteBuffer(queue, storage, TEXTURE_ROW_BYTES, input, sizeof(input));
    WGPUBindGroupEntry entry = WGPU_BIND_GROUP_ENTRY_INIT;
    entry.buffer = storage;
    entry.size = resident_roundtrip ? RESIDENT_STORAGE_BYTES : sizeof(input);
    WGPUBindGroupDescriptor group_desc = WGPU_BIND_GROUP_DESCRIPTOR_INIT;
    group_desc.layout = layout;
    group_desc.entryCount = 1;
    group_desc.entries = &entry;
    group = wgpuDeviceCreateBindGroup(device, &group_desc);
    REQUIRE(group);

    WGPUCommandBuffer invalid = doeNativeCreateComputeDispatchCopyCommandBuffer(
        device, pipeline, &group, 1, ELEMENT_COUNT, 1, 1, storage, 0, NULL, 0, sizeof(input));
    if (invalid) wgpuCommandBufferRelease(invalid);
    REQUIRE(!invalid);
    if (via_texture) {
        WGPUTextureDescriptor texture_desc = WGPU_TEXTURE_DESCRIPTOR_INIT;
        texture_desc.size = (WGPUExtent3D){ELEMENT_COUNT, 1, TEXTURE_LAYER_COUNT};
        texture_desc.dimension = WGPUTextureDimension_2D;
        texture_desc.format = WGPUTextureFormat_RGBA8Unorm;
        texture_desc.usage = WGPUTextureUsage_CopySrc | WGPUTextureUsage_CopyDst;
        texture = wgpuDeviceCreateTexture(device, &texture_desc);
        REQUIRE(texture);
        WGPUTextureView copy_view = wgpuTextureCreateView(texture, NULL);
        REQUIRE(copy_view);
        wgpuTextureViewRelease(copy_view);
        WGPUTexelCopyTextureInfo image = WGPU_TEXEL_COPY_TEXTURE_INFO_INIT;
        image.texture = texture;
        WGPUTexelCopyBufferInfo source_buffer = WGPU_TEXEL_COPY_BUFFER_INFO_INIT;
        source_buffer.buffer = storage;
        source_buffer.layout.bytesPerRow = TEXTURE_ROW_BYTES;
        source_buffer.layout.rowsPerImage = 1;
        WGPUTexelCopyBufferInfo target_buffer = source_buffer;
        target_buffer.buffer = readback;
        const uint32_t zeros[ELEMENT_COUNT] = {0};
        const WGPUExtent3D first_layer = {ELEMENT_COUNT, 1, 1};
        wgpuQueueWriteTexture(queue, &image, zeros, sizeof(zeros), &source_buffer.layout, &first_layer);
        WGPUCommandEncoder abandoned = wgpuDeviceCreateCommandEncoder(device, NULL);
        REQUIRE(abandoned);
        wgpuCommandEncoderCopyBufferToTexture(abandoned, &source_buffer, &image, &texture_desc.size);
        wgpuCommandEncoderRelease(abandoned);
        REQUIRE(texture_is_zero(instance, device, queue, texture, readback));
        uint32_t sentinel[TEXTURE_ROW_BYTES * TEXTURE_LAYER_COUNT / sizeof(uint32_t)];
        for (size_t index = 0; index < sizeof(sentinel) / sizeof(sentinel[0]); ++index)
            sentinel[index] = PADDING_SENTINEL;
        wgpuQueueWriteBuffer(queue, readback, 0, sentinel, sizeof(sentinel));
        WGPUCommandEncoder encoder = wgpuDeviceCreateCommandEncoder(device, NULL);
        REQUIRE(encoder);
        WGPUComputePassEncoder pass = wgpuCommandEncoderBeginComputePass(encoder, NULL);
        if (!pass) { wgpuCommandEncoderRelease(encoder); REQUIRE(pass); }
        wgpuComputePassEncoderSetPipeline(pass, pipeline);
        wgpuComputePassEncoderSetBindGroup(pass, 0, group, 0, NULL);
        wgpuComputePassEncoderDispatchWorkgroups(pass, ELEMENT_COUNT, 1, 1);
        wgpuComputePassEncoderEnd(pass);
        wgpuComputePassEncoderRelease(pass);
        wgpuCommandEncoderCopyBufferToTexture(encoder, &source_buffer, &image, &texture_desc.size);
        if (resident_roundtrip) {
            target_buffer.buffer = storage;
            wgpuCommandEncoderClearBuffer(encoder, storage, 0, TEXTURE_ROW_BYTES + sizeof(input));
        }
        wgpuCommandEncoderCopyTextureToBuffer(encoder, &image, &target_buffer, &texture_desc.size);
        if (resident_roundtrip) {
            pass = wgpuCommandEncoderBeginComputePass(encoder, NULL);
            if (!pass) { wgpuCommandEncoderRelease(encoder); REQUIRE(pass); }
            wgpuComputePassEncoderSetPipeline(pass, pipeline);
            wgpuComputePassEncoderSetBindGroup(pass, 0, group, 0, NULL);
            wgpuComputePassEncoderDispatchWorkgroups(pass, ELEMENT_COUNT, 1, 1);
            wgpuComputePassEncoderEnd(pass);
            wgpuComputePassEncoderRelease(pass);
            wgpuCommandEncoderCopyBufferToBuffer(encoder, storage, 0, readback, 0, TEXTURE_ROW_BYTES + sizeof(input));
        }
        commands = wgpuCommandEncoderFinish(encoder, NULL);
        wgpuCommandEncoderRelease(encoder);
        wgpuTextureRelease(texture); texture = NULL;
    } else if (batch) {
        WGPUComputePipeline pipelines[] = {pipeline, pipeline};
        WGPUBindGroup groups[2 * NATIVE_BIND_GROUP_STRIDE] = {0};
        groups[0] = group;
        groups[NATIVE_BIND_GROUP_STRIDE] = group;
        const uint32_t counts[] = {1, 1};
        const uint32_t dimensions[] = {ELEMENT_COUNT, 1, 1, ELEMENT_COUNT, 1, 1};
        commands = doeNativeCreateComputeDispatchBatchCopyCommandBuffer(
            device, 2, pipelines, groups, counts, dimensions, storage, 0, readback, 0, sizeof(input));
    } else {
        commands = doeNativeCreateComputeDispatchCopyCommandBuffer(
            device, pipeline, &group, 1, ELEMENT_COUNT, 1, 1, storage, 0, readback, 0, sizeof(input));
    }
    REQUIRE(commands);
    wgpuBindGroupRelease(group); group = NULL;
    wgpuComputePipelineRelease(pipeline); pipeline = NULL;
    wgpuShaderModuleRelease(shader); shader = NULL;
    wgpuBindGroupLayoutRelease(layout); layout = NULL;
    wgpuBufferRelease(storage); storage = NULL;
    wgpuQueueSubmit(queue, 1, &commands);
    wgpuCommandBufferRelease(commands); commands = NULL;
    WGPUBufferMapCallbackInfo mapping = WGPU_BUFFER_MAP_CALLBACK_INFO_INIT;
    mapping.mode = WGPUCallbackMode_AllowSpontaneous;
    mapping.callback = map_ready;
    mapping.userdata1 = &mapped;
    const size_t mapped_bytes = via_texture ? TEXTURE_ROW_BYTES * TEXTURE_LAYER_COUNT : sizeof(input);
    wgpuBufferMapAsync(readback, WGPUMapMode_Read, 0, mapped_bytes, mapping);
    wgpuInstanceProcessEvents(instance);
    REQUIRE(mapped);
    const uint32_t* output = wgpuBufferGetConstMappedRange(readback, 0, mapped_bytes);
    REQUIRE(output);
    for (size_t index = 0; index < ELEMENT_COUNT; ++index)
        REQUIRE(output[index] == input[index] + ((batch || resident_roundtrip) ? 2u : 1u));
    if (via_texture) {
        for (size_t index = 0; index < ELEMENT_COUNT; ++index)
            REQUIRE(output[TEXTURE_ROW_BYTES / sizeof(uint32_t) + index] == input[index]);
        for (size_t index = TEXTURE_ROW_BYTES / sizeof(uint32_t) + ELEMENT_COUNT;
             index < mapped_bytes / sizeof(uint32_t); ++index)
            REQUIRE(output[index] == PADDING_SENTINEL);
        if (!resident_roundtrip) {
            for (size_t index = ELEMENT_COUNT; index < TEXTURE_ROW_BYTES / sizeof(uint32_t); ++index)
                REQUIRE(output[index] == PADDING_SENTINEL);
        }
    }
    if (resident_roundtrip)
        printf("passed: layered texture restore into resident storage, dependent dispatch, caller release/readback\n");
    else if (via_texture)
        printf("passed: abandoned texture copy, caller release, ordered GPU dispatch/layered texture copy/readback\n");
    else
        printf("passed: %s native constructor, failed construction, caller release, dispatch/copy/readback\n", batch ? "batch" : "single");
    success = true;
cleanup:
    if (mapped && readback) wgpuBufferUnmap(readback);
    if (commands) wgpuCommandBufferRelease(commands);
    if (group) wgpuBindGroupRelease(group);
    if (layout) wgpuBindGroupLayoutRelease(layout);
    if (pipeline) wgpuComputePipelineRelease(pipeline);
    if (shader) wgpuShaderModuleRelease(shader);
    if (storage) wgpuBufferRelease(storage);
    if (readback) wgpuBufferRelease(readback);
    if (texture) wgpuTextureRelease(texture);
    return success;
#undef REQUIRE
}

int main(void) {
    int result = 1;
    WGPUInstance instance = wgpuCreateInstance(NULL);
    WGPUAdapter adapter = NULL;
    WGPUDevice device = NULL;
    WGPUQueue queue = NULL;
    if (!instance) goto cleanup;
    WGPURequestAdapterOptions options = WGPU_REQUEST_ADAPTER_OPTIONS_INIT;
    options.backendType = WGPUBackendType_Vulkan;
    WGPURequestAdapterCallbackInfo adapter_callback = WGPU_REQUEST_ADAPTER_CALLBACK_INFO_INIT;
    adapter_callback.mode = WGPUCallbackMode_AllowSpontaneous;
    adapter_callback.callback = adapter_ready;
    adapter_callback.userdata1 = &adapter;
    wgpuInstanceRequestAdapter(instance, &options, adapter_callback);
    wgpuInstanceProcessEvents(instance);
    if (!adapter) goto cleanup;
    WGPUAdapterInfo info = WGPU_ADAPTER_INFO_INIT;
    if (wgpuAdapterGetInfo(adapter, &info) != WGPUStatus_Success) goto cleanup;
    const bool hardware_vulkan = info.backendType == WGPUBackendType_Vulkan &&
        info.adapterType != WGPUAdapterType_CPU && info.vendorID == AMD_PCI_VENDOR_ID;
    printf("backend=%u adapter=%u vendor=%u device=%u GPU=%.*s description=%.*s\n",
        info.backendType, info.adapterType, info.vendorID, info.deviceID,
        (int)info.device.length, info.device.data, (int)info.description.length, info.description.data);
    wgpuAdapterInfoFreeMembers(info);
    if (!hardware_vulkan) goto cleanup;
    WGPURequestDeviceCallbackInfo device_callback = WGPU_REQUEST_DEVICE_CALLBACK_INFO_INIT;
    device_callback.mode = WGPUCallbackMode_AllowSpontaneous;
    device_callback.callback = device_ready;
    device_callback.userdata1 = &device;
    wgpuAdapterRequestDevice(adapter, NULL, device_callback);
    wgpuInstanceProcessEvents(instance);
    if (!device) goto cleanup;
    queue = wgpuDeviceGetQueue(device);
    if (queue && invalid_pass_lifetimes(instance, device, queue) && invalid_buffer_copies(instance, device, queue) &&
        unavailable_copy_resources(instance, device, queue) &&
        texture_submission_lifetime(instance, device, queue) &&
        texture_region_copies(instance, device, queue) &&
        execute(instance, device, queue, false, false, false) &&
        execute(instance, device, queue, true, false, false)) {
        const bool layered_readback = execute(instance, device, queue, false, true, false);
        const bool resident_roundtrip = execute(instance, device, queue, false, true, true);
        if (layered_readback && resident_roundtrip) result = 0;
    }
cleanup:
    if (queue) wgpuQueueRelease(queue);
    if (device) { wgpuDeviceDestroy(device); wgpuDeviceRelease(device); }
    if (adapter) wgpuAdapterRelease(adapter);
    if (instance) wgpuInstanceRelease(instance);
    return result;
}
