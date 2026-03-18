/*
 * doe_napi_globals.c — Global variable definitions and library loading for doe_napi.
 *
 * Defines all function pointer globals, shared state globals, native-direct
 * method ref globals, and the doe_load_library N-API callback that resolves
 * symbols from the Doe shared library at runtime.
 */

#include "doe_napi_internal.h"

/* ================================================================
 * Function pointer definitions — DECL_PFN extern decls are in the header;
 * these are the actual storage definitions.
 * ================================================================ */

PFN_wgpuCreateInstance pfn_wgpuCreateInstance = NULL;
PFN_wgpuInstanceRelease pfn_wgpuInstanceRelease = NULL;
PFN_wgpuInstanceRequestAdapter pfn_wgpuInstanceRequestAdapter = NULL;
PFN_wgpuInstanceWaitAny pfn_wgpuInstanceWaitAny = NULL;
PFN_wgpuInstanceProcessEvents pfn_wgpuInstanceProcessEvents = NULL;
PFN_wgpuAdapterRelease pfn_wgpuAdapterRelease = NULL;
PFN_wgpuAdapterHasFeature pfn_wgpuAdapterHasFeature = NULL;
PFN_wgpuAdapterGetLimits pfn_wgpuAdapterGetLimits = NULL;
PFN_wgpuAdapterRequestDevice pfn_wgpuAdapterRequestDevice = NULL;
PFN_wgpuDeviceRelease pfn_wgpuDeviceRelease = NULL;
PFN_wgpuDeviceHasFeature pfn_wgpuDeviceHasFeature = NULL;
PFN_wgpuDeviceGetLimits pfn_wgpuDeviceGetLimits = NULL;
PFN_wgpuDeviceGetQueue pfn_wgpuDeviceGetQueue = NULL;
PFN_wgpuDeviceCreateBuffer pfn_wgpuDeviceCreateBuffer = NULL;
PFN_wgpuDeviceCreateShaderModule pfn_wgpuDeviceCreateShaderModule = NULL;
PFN_wgpuShaderModuleRelease pfn_wgpuShaderModuleRelease = NULL;
PFN_wgpuDeviceCreateComputePipeline pfn_wgpuDeviceCreateComputePipeline = NULL;
PFN_wgpuComputePipelineRelease pfn_wgpuComputePipelineRelease = NULL;
PFN_wgpuComputePipelineGetBindGroupLayout pfn_wgpuComputePipelineGetBindGroupLayout = NULL;
PFN_wgpuDeviceCreateBindGroupLayout pfn_wgpuDeviceCreateBindGroupLayout = NULL;
PFN_wgpuBindGroupLayoutRelease pfn_wgpuBindGroupLayoutRelease = NULL;
PFN_wgpuDeviceCreateBindGroup pfn_wgpuDeviceCreateBindGroup = NULL;
PFN_wgpuBindGroupRelease pfn_wgpuBindGroupRelease = NULL;
PFN_wgpuDeviceCreatePipelineLayout pfn_wgpuDeviceCreatePipelineLayout = NULL;
PFN_wgpuPipelineLayoutRelease pfn_wgpuPipelineLayoutRelease = NULL;
PFN_wgpuDeviceCreateCommandEncoder pfn_wgpuDeviceCreateCommandEncoder = NULL;
PFN_wgpuCommandEncoderRelease pfn_wgpuCommandEncoderRelease = NULL;
PFN_wgpuCommandEncoderBeginComputePass pfn_wgpuCommandEncoderBeginComputePass = NULL;
PFN_wgpuCommandEncoderCopyBufferToBuffer pfn_wgpuCommandEncoderCopyBufferToBuffer = NULL;
PFN_wgpuCommandEncoderCopyBufferToTexture pfn_wgpuCommandEncoderCopyBufferToTexture = NULL;
PFN_wgpuCommandEncoderCopyTextureToBuffer pfn_wgpuCommandEncoderCopyTextureToBuffer = NULL;
PFN_doeNativeCommandEncoderCopyBufferToTexture pfn_doeNativeCommandEncoderCopyBufferToTexture = NULL;
PFN_doeNativeCommandEncoderCopyTextureToBuffer pfn_doeNativeCommandEncoderCopyTextureToBuffer = NULL;
PFN_wgpuCommandEncoderFinish pfn_wgpuCommandEncoderFinish = NULL;
PFN_wgpuComputePassEncoderSetPipeline pfn_wgpuComputePassEncoderSetPipeline = NULL;
PFN_wgpuComputePassEncoderSetBindGroup pfn_wgpuComputePassEncoderSetBindGroup = NULL;
PFN_wgpuComputePassEncoderDispatchWorkgroups pfn_wgpuComputePassEncoderDispatchWorkgroups = NULL;
PFN_wgpuComputePassEncoderDispatchWorkgroupsIndirect pfn_wgpuComputePassEncoderDispatchWorkgroupsIndirect = NULL;
PFN_doeNativeComputePassDispatchIndirect pfn_doeNativeComputePassDispatchIndirect = NULL;
PFN_wgpuComputePassEncoderEnd pfn_wgpuComputePassEncoderEnd = NULL;
PFN_wgpuComputePassEncoderRelease pfn_wgpuComputePassEncoderRelease = NULL;
PFN_wgpuQueueSubmit pfn_wgpuQueueSubmit = NULL;
PFN_wgpuQueueWriteBuffer pfn_wgpuQueueWriteBuffer = NULL;
PFN_wgpuQueueOnSubmittedWorkDone pfn_wgpuQueueOnSubmittedWorkDone = NULL;
PFN_wgpuQueueRelease pfn_wgpuQueueRelease = NULL;
PFN_wgpuBufferRelease pfn_wgpuBufferRelease = NULL;
PFN_wgpuBufferUnmap pfn_wgpuBufferUnmap = NULL;
PFN_wgpuBufferGetConstMappedRange pfn_wgpuBufferGetConstMappedRange = NULL;
PFN_wgpuBufferGetMappedRange pfn_wgpuBufferGetMappedRange = NULL;
PFN_wgpuCommandBufferRelease pfn_wgpuCommandBufferRelease = NULL;
PFN_wgpuDeviceCreateTexture pfn_wgpuDeviceCreateTexture = NULL;
PFN_wgpuTextureCreateView pfn_wgpuTextureCreateView = NULL;
PFN_wgpuTextureRelease pfn_wgpuTextureRelease = NULL;
PFN_wgpuTextureViewRelease pfn_wgpuTextureViewRelease = NULL;
PFN_wgpuDeviceCreateSampler pfn_wgpuDeviceCreateSampler = NULL;
PFN_wgpuSamplerRelease pfn_wgpuSamplerRelease = NULL;
PFN_wgpuDeviceCreateRenderPipeline pfn_wgpuDeviceCreateRenderPipeline = NULL;
PFN_wgpuRenderPipelineRelease pfn_wgpuRenderPipelineRelease = NULL;
PFN_wgpuCommandEncoderBeginRenderPass pfn_wgpuCommandEncoderBeginRenderPass = NULL;
PFN_wgpuRenderPassEncoderSetPipeline pfn_wgpuRenderPassEncoderSetPipeline = NULL;
PFN_wgpuRenderPassEncoderSetBindGroup pfn_wgpuRenderPassEncoderSetBindGroup = NULL;
PFN_wgpuRenderPassEncoderSetVertexBuffer pfn_wgpuRenderPassEncoderSetVertexBuffer = NULL;
PFN_wgpuRenderPassEncoderSetIndexBuffer pfn_wgpuRenderPassEncoderSetIndexBuffer = NULL;
PFN_wgpuRenderPassEncoderDraw pfn_wgpuRenderPassEncoderDraw = NULL;
PFN_wgpuRenderPassEncoderDrawIndexed pfn_wgpuRenderPassEncoderDrawIndexed = NULL;
PFN_wgpuRenderPassEncoderEnd pfn_wgpuRenderPassEncoderEnd = NULL;
PFN_wgpuRenderPassEncoderRelease pfn_wgpuRenderPassEncoderRelease = NULL;
PFN_doeNativeAdapterGetLimits pfn_doeNativeAdapterGetLimits = NULL;
PFN_doeNativeDeviceGetLimits pfn_doeNativeDeviceGetLimits = NULL;
PFN_doeNativeAdapterHasFeature pfn_doeNativeAdapterHasFeature = NULL;
PFN_doeNativeDeviceHasFeature pfn_doeNativeDeviceHasFeature = NULL;
PFN_doeNativeCopyLastErrorMessage pfn_doeNativeCopyLastErrorMessage = NULL;
PFN_doeNativeCopyLastErrorStage pfn_doeNativeCopyLastErrorStage = NULL;
PFN_doeNativeCopyLastErrorKind pfn_doeNativeCopyLastErrorKind = NULL;
PFN_doeNativeGetLastErrorLine pfn_doeNativeGetLastErrorLine = NULL;
PFN_doeNativeGetLastErrorColumn pfn_doeNativeGetLastErrorColumn = NULL;
PFN_doeNativeCheckShaderSource pfn_doeNativeCheckShaderSource = NULL;
PFN_doeNativeShaderModuleGetBindings pfn_doeNativeShaderModuleGetBindings = NULL;
PFN_doeNativeAdapterRequestDevice pfn_doeNativeAdapterRequestDevice = NULL;
PFN_doeRequestAdapterFlat pfn_doeRequestAdapterFlat = NULL;
PFN_doeRequestDeviceFlat pfn_doeRequestDeviceFlat = NULL;
PFN_doeNativeQueueFlush pfn_doeNativeQueueFlush = NULL;
PFN_doeNativeComputeDispatchFlush pfn_doeNativeComputeDispatchFlush = NULL;
PFN_doeNativeDeviceCreateQuerySet pfn_doeNativeDeviceCreateQuerySet = NULL;
PFN_doeNativeCommandEncoderWriteTimestamp pfn_doeNativeCommandEncoderWriteTimestamp = NULL;
PFN_doeNativeCommandEncoderResolveQuerySet pfn_doeNativeCommandEncoderResolveQuerySet = NULL;
PFN_doeNativeQuerySetDestroy pfn_doeNativeQuerySetDestroy = NULL;
PFN_doeNativeBufferMapAsync pfn_doeNativeBufferMapAsync = NULL;

PFN_wgpuBufferMapAsync2 pfn_wgpuBufferMapAsync2 = NULL;

/* Manual Fn* function pointers */
FnAdapterGetPreferredCanvasFormat pfn_doeNativeAdapterGetPreferredCanvasFormat = NULL;
FnDeviceAddEventListener pfn_doeNativeDeviceAddEventListener = NULL;
FnDeviceRemoveEventListener pfn_doeNativeDeviceRemoveEventListener = NULL;
FnDeviceImportExternalTexture pfn_doeNativeDeviceImportExternalTexture = NULL;
FnBindingCommandsSetImmediates pfn_doeNativeBindingCommandsSetImmediates = NULL;
FnComputePassSetImmediates pfn_doeNativeComputePassSetImmediates = NULL;
FnRenderPassSetImmediates pfn_doeNativeRenderPassSetImmediates = NULL;
FnRenderBundleEncoderSetImmediates pfn_doeNativeRenderBundleEncoderSetImmediates = NULL;
FnRenderPassSetViewport pfn_doeNativeRenderPassSetViewport = NULL;
FnRenderPassSetScissorRect pfn_doeNativeRenderPassSetScissorRect = NULL;
FnRenderPassSetBlendConstant pfn_doeNativeRenderPassSetBlendConstant = NULL;
FnRenderPassSetStencilReference pfn_doeNativeRenderPassSetStencilReference = NULL;
FnRenderPassPushDebugGroup pfn_doeNativeRenderPassPushDebugGroup = NULL;
FnRenderPassPopDebugGroup pfn_doeNativeRenderPassPopDebugGroup = NULL;
FnRenderPassInsertDebugMarker pfn_doeNativeRenderPassInsertDebugMarker = NULL;
FnRenderBundleEncoderPushDebugGroup pfn_doeNativeRenderBundleEncoderPushDebugGroup = NULL;
FnRenderBundleEncoderPopDebugGroup pfn_doeNativeRenderBundleEncoderPopDebugGroup = NULL;
FnRenderBundleEncoderInsertDebugMarker pfn_doeNativeRenderBundleEncoderInsertDebugMarker = NULL;
FnAdapterGetInfo pfn_doeNativeAdapterGetInfo = NULL;
FnAdapterFreeInfo pfn_doeNativeAdapterFreeInfo = NULL;
FnShaderModuleGetCompilationInfo pfn_doeNativeShaderModuleGetCompilationInfo = NULL;
FnDevicePushErrorScope pfn_doeNativeDevicePushErrorScope = NULL;
FnDevicePopErrorScope pfn_doeNativeDevicePopErrorScope = NULL;
FnDevicePushErrorScope pfn_wgpuDevicePushErrorScope = NULL;
FnDevicePopErrorScope pfn_wgpuDevicePopErrorScope = NULL;
FnDeviceSetUncapturedErrorCallback pfn_doeNativeDeviceSetUncapturedErrorCallback = NULL;
FnDeviceRegisterLostCallback pfn_doeNativeDeviceRegisterLostCallback = NULL;
FnRenderPipelineGetBindGroupLayout pfn_doeNativeRenderPipelineGetBindGroupLayout = NULL;
FnCommandEncoderClearBuffer pfn_doeNativeCommandEncoderClearBuffer = NULL;
FnCommandEncoderCopyTextureToTexture pfn_doeNativeCommandEncoderCopyTextureToTexture = NULL;
FnWgpuCommandEncoderCopyTextureToTexture pfn_wgpuCommandEncoderCopyTextureToTexture = NULL;
FnQueueWriteTexture pfn_doeNativeQueueWriteTexture = NULL;
FnDeviceCreateRenderBundleEncoder pfn_doeNativeDeviceCreateRenderBundleEncoder = NULL;
FnRenderBundleEncoderRelease pfn_doeNativeRenderBundleEncoderRelease = NULL;
FnRenderBundleEncoderSetPipeline pfn_doeNativeRenderBundleEncoderSetPipeline = NULL;
FnRenderBundleEncoderSetBindGroup pfn_doeNativeRenderBundleEncoderSetBindGroup = NULL;
FnRenderBundleEncoderSetVertexBuffer pfn_doeNativeRenderBundleEncoderSetVertexBuffer = NULL;
FnRenderBundleEncoderSetIndexBuffer pfn_doeNativeRenderBundleEncoderSetIndexBuffer = NULL;
FnRenderBundleEncoderDraw pfn_doeNativeRenderBundleEncoderDraw = NULL;
FnRenderBundleEncoderDrawIndexed pfn_doeNativeRenderBundleEncoderDrawIndexed = NULL;
FnRenderBundleEncoderFinish pfn_doeNativeRenderBundleEncoderFinish = NULL;
FnRenderBundleRelease pfn_doeNativeRenderBundleRelease = NULL;

/* ================================================================
 * Shared state globals
 * ================================================================ */

void* g_lib = NULL;
uint64_t g_timeout_ns = DOE_DEFAULT_TIMEOUT_NS;
DeviceCallbackBinding* g_uncaptured_bindings = NULL;
DeviceCallbackBinding* g_lost_bindings = NULL;

/* ================================================================
 * Native-direct method refs
 * ================================================================ */

napi_ref native_direct_method_gpu_request_adapter_ref = NULL;
napi_ref native_direct_method_adapter_request_device_ref = NULL;
napi_ref native_direct_method_adapter_destroy_ref = NULL;
napi_ref native_direct_method_queue_submit_ref = NULL;
napi_ref native_direct_method_queue_write_buffer_ref = NULL;
napi_ref native_direct_method_queue_on_submitted_work_done_ref = NULL;
napi_ref native_direct_method_device_create_buffer_ref = NULL;
napi_ref native_direct_method_device_create_shader_module_ref = NULL;
napi_ref native_direct_method_device_create_compute_pipeline_ref = NULL;
napi_ref native_direct_method_device_create_compute_pipeline_async_ref = NULL;
napi_ref native_direct_method_device_create_bind_group_layout_ref = NULL;
napi_ref native_direct_method_device_create_bind_group_ref = NULL;
napi_ref native_direct_method_device_create_pipeline_layout_ref = NULL;
napi_ref native_direct_method_device_create_command_encoder_ref = NULL;
napi_ref native_direct_method_device_destroy_ref = NULL;
napi_ref native_direct_method_buffer_map_async_ref = NULL;
napi_ref native_direct_method_buffer_get_mapped_range_ref = NULL;
napi_ref native_direct_method_buffer_read_copy_ref = NULL;
napi_ref native_direct_method_buffer_map_read_copy_unmap_ref = NULL;
napi_ref native_direct_method_buffer_unmap_ref = NULL;
napi_ref native_direct_method_buffer_destroy_ref = NULL;
napi_ref native_direct_method_command_encoder_begin_compute_pass_ref = NULL;
napi_ref native_direct_method_command_encoder_copy_buffer_to_buffer_ref = NULL;
napi_ref native_direct_method_command_encoder_finish_ref = NULL;
napi_ref native_direct_method_compute_pass_set_pipeline_ref = NULL;
napi_ref native_direct_method_compute_pass_set_bind_group_ref = NULL;
napi_ref native_direct_method_compute_pass_dispatch_workgroups_ref = NULL;
napi_ref native_direct_method_compute_pass_dispatch_workgroups_indirect_ref = NULL;
napi_ref native_direct_method_compute_pass_end_ref = NULL;
napi_ref native_direct_method_compute_pass_set_immediates_ref = NULL;
napi_ref native_direct_method_render_pass_set_immediates_ref = NULL;
napi_ref native_direct_method_render_pass_set_viewport_ref = NULL;
napi_ref native_direct_method_render_pass_set_scissor_rect_ref = NULL;
napi_ref native_direct_method_render_pass_set_blend_constant_ref = NULL;
napi_ref native_direct_method_render_pass_set_stencil_reference_ref = NULL;
napi_ref native_direct_method_render_pass_push_debug_group_ref = NULL;
napi_ref native_direct_method_render_pass_pop_debug_group_ref = NULL;
napi_ref native_direct_method_render_pass_insert_debug_marker_ref = NULL;
napi_ref native_direct_method_render_bundle_encoder_set_immediates_ref = NULL;
napi_ref native_direct_method_adapter_get_preferred_canvas_format_ref = NULL;
napi_ref native_direct_method_device_add_event_listener_ref = NULL;
napi_ref native_direct_method_device_remove_event_listener_ref = NULL;
napi_ref native_direct_method_device_import_external_texture_ref = NULL;
napi_ref native_direct_method_command_encoder_clear_buffer_ref = NULL;
napi_ref native_direct_method_command_encoder_copy_texture_to_texture_ref = NULL;
napi_ref native_direct_method_queue_write_texture_ref = NULL;
napi_ref native_direct_method_adapter_get_info_ref = NULL;
napi_ref native_direct_method_shader_module_get_compilation_info_ref = NULL;
napi_ref native_direct_resolved_undefined_promise_ref = NULL;

/* ================================================================
 * Library loading
 * ================================================================ */

napi_value doe_load_library(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    size_t path_len = 0;
    napi_get_value_string_utf8(env, _args[0], NULL, 0, &path_len);
    char* path = (char*)malloc(path_len + 1);
    napi_get_value_string_utf8(env, _args[0], path, path_len + 1, &path_len);

    if (g_lib) { LIB_CLOSE(g_lib); g_lib = NULL; }
    g_lib = LIB_OPEN(path);
    free(path);
    if (!g_lib) NAPI_THROW(env, "Failed to load libwebgpu_doe");

    const char* timeout_env = getenv("DOE_TIMEOUT_MS");
    if (timeout_env && timeout_env[0] != '\0') {
        char* end = NULL;
        unsigned long parsed = strtoul(timeout_env, &end, 10);
        if (end && *end == '\0') {
            g_timeout_ns = (uint64_t)parsed * 1000000ULL;
        }
    }

    LOAD_SYM(wgpuCreateInstance);
    LOAD_SYM(wgpuInstanceRelease);
    LOAD_SYM(wgpuInstanceRequestAdapter);
    LOAD_SYM(wgpuInstanceWaitAny);
    LOAD_SYM(wgpuInstanceProcessEvents);
    LOAD_SYM(wgpuAdapterRelease);
    LOAD_SYM(wgpuAdapterHasFeature);
    LOAD_SYM(wgpuAdapterGetLimits);
    LOAD_SYM(wgpuAdapterRequestDevice);
    LOAD_SYM(wgpuDeviceRelease);
    LOAD_SYM(wgpuDeviceHasFeature);
    LOAD_SYM(wgpuDeviceGetQueue);
    LOAD_SYM(wgpuDeviceCreateBuffer);
    LOAD_SYM(wgpuDeviceCreateShaderModule);
    LOAD_SYM(wgpuShaderModuleRelease);
    LOAD_SYM(wgpuDeviceCreateComputePipeline);
    LOAD_SYM(wgpuComputePipelineRelease);
    LOAD_SYM(wgpuComputePipelineGetBindGroupLayout);
    LOAD_SYM(wgpuDeviceCreateBindGroupLayout);
    LOAD_SYM(wgpuBindGroupLayoutRelease);
    LOAD_SYM(wgpuDeviceCreateBindGroup);
    LOAD_SYM(wgpuBindGroupRelease);
    LOAD_SYM(wgpuDeviceCreatePipelineLayout);
    LOAD_SYM(wgpuPipelineLayoutRelease);
    LOAD_SYM(wgpuDeviceCreateCommandEncoder);
    LOAD_SYM(wgpuCommandEncoderRelease);
    LOAD_SYM(wgpuCommandEncoderBeginComputePass);
    LOAD_SYM(wgpuCommandEncoderCopyBufferToBuffer);
    LOAD_SYM(wgpuCommandEncoderCopyBufferToTexture);
    LOAD_SYM(wgpuCommandEncoderCopyTextureToBuffer);
    LOAD_SYM(doeNativeCommandEncoderCopyBufferToTexture);
    LOAD_SYM(doeNativeCommandEncoderCopyTextureToBuffer);
    LOAD_SYM(wgpuCommandEncoderFinish);
    LOAD_SYM(wgpuComputePassEncoderSetPipeline);
    LOAD_SYM(wgpuComputePassEncoderSetBindGroup);
    LOAD_SYM(wgpuComputePassEncoderDispatchWorkgroups);
    LOAD_SYM(wgpuComputePassEncoderDispatchWorkgroupsIndirect);
    LOAD_SYM(doeNativeComputePassDispatchIndirect);
    LOAD_SYM(wgpuComputePassEncoderEnd);
    LOAD_SYM(wgpuComputePassEncoderRelease);
    LOAD_SYM(wgpuQueueSubmit);
    LOAD_SYM(wgpuQueueWriteBuffer);
    LOAD_SYM(wgpuQueueOnSubmittedWorkDone);
    LOAD_SYM(wgpuQueueRelease);
    LOAD_SYM(wgpuBufferRelease);
    LOAD_SYM(wgpuBufferUnmap);
    LOAD_SYM(wgpuBufferGetConstMappedRange);
    LOAD_SYM(wgpuBufferGetMappedRange);
    LOAD_SYM(wgpuCommandBufferRelease);
    LOAD_SYM(wgpuDeviceCreateTexture);
    LOAD_SYM(wgpuTextureCreateView);
    LOAD_SYM(wgpuTextureRelease);
    LOAD_SYM(wgpuTextureViewRelease);
    LOAD_SYM(wgpuDeviceCreateSampler);
    LOAD_SYM(wgpuSamplerRelease);
    LOAD_SYM(wgpuDeviceCreateRenderPipeline);
    LOAD_SYM(wgpuRenderPipelineRelease);
    LOAD_SYM(wgpuCommandEncoderBeginRenderPass);
    LOAD_SYM(wgpuRenderPassEncoderSetPipeline);
    LOAD_SYM(wgpuRenderPassEncoderSetBindGroup);
    LOAD_SYM(wgpuRenderPassEncoderSetVertexBuffer);
    LOAD_SYM(wgpuRenderPassEncoderSetIndexBuffer);
    LOAD_SYM(wgpuRenderPassEncoderDraw);
    LOAD_SYM(wgpuRenderPassEncoderDrawIndexed);
    LOAD_SYM(wgpuRenderPassEncoderEnd);
    LOAD_SYM(wgpuRenderPassEncoderRelease);
    LOAD_SYM(wgpuAdapterGetLimits);
    LOAD_SYM(wgpuAdapterHasFeature);
    LOAD_SYM(wgpuDeviceHasFeature);
    LOAD_SYM(wgpuDeviceGetLimits);
    pfn_doeNativeAdapterGetLimits = (PFN_doeNativeAdapterGetLimits)LIB_SYM(g_lib, "doeNativeAdapterGetLimits");
    pfn_doeNativeDeviceGetLimits = (PFN_doeNativeDeviceGetLimits)LIB_SYM(g_lib, "doeNativeDeviceGetLimits");
    pfn_doeNativeAdapterHasFeature = (PFN_doeNativeAdapterHasFeature)LIB_SYM(g_lib, "doeNativeAdapterHasFeature");
    pfn_doeNativeDeviceHasFeature = (PFN_doeNativeDeviceHasFeature)LIB_SYM(g_lib, "doeNativeDeviceHasFeature");
    pfn_doeNativeCopyLastErrorMessage = (PFN_doeNativeCopyLastErrorMessage)LIB_SYM(g_lib, "doeNativeCopyLastErrorMessage");
    pfn_doeNativeCopyLastErrorStage = (PFN_doeNativeCopyLastErrorStage)LIB_SYM(g_lib, "doeNativeCopyLastErrorStage");
    pfn_doeNativeCopyLastErrorKind = (PFN_doeNativeCopyLastErrorKind)LIB_SYM(g_lib, "doeNativeCopyLastErrorKind");
    pfn_doeNativeGetLastErrorLine = (PFN_doeNativeGetLastErrorLine)LIB_SYM(g_lib, "doeNativeGetLastErrorLine");
    pfn_doeNativeGetLastErrorColumn = (PFN_doeNativeGetLastErrorColumn)LIB_SYM(g_lib, "doeNativeGetLastErrorColumn");
    pfn_doeNativeCheckShaderSource = (PFN_doeNativeCheckShaderSource)LIB_SYM(g_lib, "doeNativeCheckShaderSource");
    pfn_doeNativeShaderModuleGetBindings = (PFN_doeNativeShaderModuleGetBindings)LIB_SYM(g_lib, "doeNativeShaderModuleGetBindings");
    pfn_doeNativeAdapterRequestDevice = (PFN_doeNativeAdapterRequestDevice)LIB_SYM(g_lib, "doeNativeAdapterRequestDevice");
    pfn_doeNativeBufferMapAsync = (PFN_doeNativeBufferMapAsync)LIB_SYM(g_lib, "doeNativeBufferMapAsync");
    pfn_doeRequestAdapterFlat = (PFN_doeRequestAdapterFlat)LIB_SYM(g_lib, "doeRequestAdapterFlat");
    pfn_doeRequestDeviceFlat = (PFN_doeRequestDeviceFlat)LIB_SYM(g_lib, "doeRequestDeviceFlat");
    pfn_wgpuBufferMapAsync2 = (PFN_wgpuBufferMapAsync2)LIB_SYM(g_lib, "wgpuBufferMapAsync");
    pfn_doeNativeQueueFlush = (PFN_doeNativeQueueFlush)LIB_SYM(g_lib, "doeNativeQueueFlush");
    pfn_doeNativeComputeDispatchFlush = (PFN_doeNativeComputeDispatchFlush)LIB_SYM(g_lib, "doeNativeComputeDispatchFlush");
    pfn_doeNativeDeviceCreateQuerySet = (PFN_doeNativeDeviceCreateQuerySet)LIB_SYM(g_lib, "doeNativeDeviceCreateQuerySet");
    pfn_doeNativeCommandEncoderWriteTimestamp = (PFN_doeNativeCommandEncoderWriteTimestamp)LIB_SYM(g_lib, "doeNativeCommandEncoderWriteTimestamp");
    pfn_doeNativeCommandEncoderResolveQuerySet = (PFN_doeNativeCommandEncoderResolveQuerySet)LIB_SYM(g_lib, "doeNativeCommandEncoderResolveQuerySet");
    pfn_doeNativeQuerySetDestroy = (PFN_doeNativeQuerySetDestroy)LIB_SYM(g_lib, "doeNativeQuerySetDestroy");

    /* Optional symbols for 14-binding expansion — absent until delivered. */
    pfn_doeNativeAdapterGetPreferredCanvasFormat = (FnAdapterGetPreferredCanvasFormat)LIB_SYM(g_lib, "doeNativeAdapterGetPreferredCanvasFormat");
    pfn_doeNativeDeviceAddEventListener = (FnDeviceAddEventListener)LIB_SYM(g_lib, "doeNativeDeviceAddEventListener");
    pfn_doeNativeDeviceRemoveEventListener = (FnDeviceRemoveEventListener)LIB_SYM(g_lib, "doeNativeDeviceRemoveEventListener");
    pfn_doeNativeDeviceImportExternalTexture = (FnDeviceImportExternalTexture)LIB_SYM(g_lib, "doeNativeDeviceImportExternalTexture");
    pfn_doeNativeBindingCommandsSetImmediates = (FnBindingCommandsSetImmediates)LIB_SYM(g_lib, "doeNativeBindingCommandsSetImmediates");
    pfn_doeNativeComputePassSetImmediates = (FnComputePassSetImmediates)LIB_SYM(g_lib, "doeNativeComputePassSetImmediates");
    pfn_doeNativeRenderPassSetImmediates = (FnRenderPassSetImmediates)LIB_SYM(g_lib, "doeNativeRenderPassSetImmediates");
    pfn_doeNativeRenderBundleEncoderSetImmediates = (FnRenderBundleEncoderSetImmediates)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderSetImmediates");

    /* GPUAdapter.info and GPUShaderModule.getCompilationInfo — optional; absent on older builds. */
    pfn_doeNativeAdapterGetInfo = (FnAdapterGetInfo)LIB_SYM(g_lib, "doeNativeAdapterGetInfo");
    pfn_doeNativeAdapterFreeInfo = (FnAdapterFreeInfo)LIB_SYM(g_lib, "doeNativeAdapterFreeInfo");
    pfn_doeNativeShaderModuleGetCompilationInfo = (FnShaderModuleGetCompilationInfo)LIB_SYM(g_lib, "doeNativeShaderModuleGetCompilationInfo");
    pfn_doeNativeDevicePushErrorScope = (FnDevicePushErrorScope)LIB_SYM(g_lib, "doeNativeDevicePushErrorScope");
    pfn_doeNativeDevicePopErrorScope = (FnDevicePopErrorScope)LIB_SYM(g_lib, "doeNativeDevicePopErrorScope");
    pfn_wgpuDevicePushErrorScope = (FnDevicePushErrorScope)LIB_SYM(g_lib, "wgpuDevicePushErrorScope");
    pfn_wgpuDevicePopErrorScope = (FnDevicePopErrorScope)LIB_SYM(g_lib, "wgpuDevicePopErrorScope");
    pfn_doeNativeDeviceSetUncapturedErrorCallback = (FnDeviceSetUncapturedErrorCallback)LIB_SYM(g_lib, "doeNativeDeviceSetUncapturedErrorCallback");
    pfn_doeNativeDeviceRegisterLostCallback = (FnDeviceRegisterLostCallback)LIB_SYM(g_lib, "doeNativeDeviceRegisterLostCallback");

    /* GPURenderPassEncoder control methods — optional; absent on older builds. */
    pfn_doeNativeRenderPassSetViewport = (FnRenderPassSetViewport)LIB_SYM(g_lib, "doeNativeRenderPassSetViewport");
    pfn_doeNativeRenderPassSetScissorRect = (FnRenderPassSetScissorRect)LIB_SYM(g_lib, "doeNativeRenderPassSetScissorRect");
    pfn_doeNativeRenderPassSetBlendConstant = (FnRenderPassSetBlendConstant)LIB_SYM(g_lib, "doeNativeRenderPassSetBlendConstant");
    pfn_doeNativeRenderPassSetStencilReference = (FnRenderPassSetStencilReference)LIB_SYM(g_lib, "doeNativeRenderPassSetStencilReference");
    pfn_doeNativeRenderPassPushDebugGroup = (FnRenderPassPushDebugGroup)LIB_SYM(g_lib, "doeNativeRenderPassPushDebugGroup");
    pfn_doeNativeRenderPassPopDebugGroup = (FnRenderPassPopDebugGroup)LIB_SYM(g_lib, "doeNativeRenderPassPopDebugGroup");
    pfn_doeNativeRenderPassInsertDebugMarker = (FnRenderPassInsertDebugMarker)LIB_SYM(g_lib, "doeNativeRenderPassInsertDebugMarker");

    /* clearBuffer / copyTextureToTexture / writeTexture — optional; absent on older builds. */
    pfn_doeNativeCommandEncoderClearBuffer = (FnCommandEncoderClearBuffer)LIB_SYM(g_lib, "doeNativeCommandEncoderClearBuffer");
    pfn_doeNativeCommandEncoderCopyTextureToTexture = (FnCommandEncoderCopyTextureToTexture)LIB_SYM(g_lib, "doeNativeCommandEncoderCopyTextureToTexture");
    pfn_wgpuCommandEncoderCopyTextureToTexture = (FnWgpuCommandEncoderCopyTextureToTexture)LIB_SYM(g_lib, "wgpuCommandEncoderCopyTextureToTexture");
    pfn_doeNativeQueueWriteTexture = (FnQueueWriteTexture)LIB_SYM(g_lib, "doeNativeQueueWriteTexture");

    /* renderPipelineGetBindGroupLayout — optional; absent on older builds. */
    pfn_doeNativeRenderPipelineGetBindGroupLayout = (FnRenderPipelineGetBindGroupLayout)LIB_SYM(g_lib, "doeNativeRenderPipelineGetBindGroupLayout");

    /* GPURenderBundleEncoder / GPURenderBundle — optional; absent on older builds. */
    pfn_doeNativeDeviceCreateRenderBundleEncoder   = (FnDeviceCreateRenderBundleEncoder)LIB_SYM(g_lib, "doeNativeDeviceCreateRenderBundleEncoder");
    pfn_doeNativeRenderBundleEncoderRelease        = (FnRenderBundleEncoderRelease)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderRelease");
    pfn_doeNativeRenderBundleEncoderSetPipeline    = (FnRenderBundleEncoderSetPipeline)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderSetPipeline");
    pfn_doeNativeRenderBundleEncoderSetBindGroup   = (FnRenderBundleEncoderSetBindGroup)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderSetBindGroup");
    pfn_doeNativeRenderBundleEncoderSetVertexBuffer = (FnRenderBundleEncoderSetVertexBuffer)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderSetVertexBuffer");
    pfn_doeNativeRenderBundleEncoderSetIndexBuffer  = (FnRenderBundleEncoderSetIndexBuffer)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderSetIndexBuffer");
    pfn_doeNativeRenderBundleEncoderDraw           = (FnRenderBundleEncoderDraw)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderDraw");
    pfn_doeNativeRenderBundleEncoderDrawIndexed    = (FnRenderBundleEncoderDrawIndexed)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderDrawIndexed");
    pfn_doeNativeRenderBundleEncoderPushDebugGroup = (FnRenderBundleEncoderPushDebugGroup)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderPushDebugGroup");
    pfn_doeNativeRenderBundleEncoderPopDebugGroup = (FnRenderBundleEncoderPopDebugGroup)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderPopDebugGroup");
    pfn_doeNativeRenderBundleEncoderInsertDebugMarker = (FnRenderBundleEncoderInsertDebugMarker)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderInsertDebugMarker");
    pfn_doeNativeRenderBundleEncoderFinish         = (FnRenderBundleEncoderFinish)LIB_SYM(g_lib, "doeNativeRenderBundleEncoderFinish");
    pfn_doeNativeRenderBundleRelease               = (FnRenderBundleRelease)LIB_SYM(g_lib, "doeNativeRenderBundleRelease");

    /* Validate all critical function pointers were resolved. */
    if (!pfn_wgpuCreateInstance || !pfn_wgpuInstanceRelease || !pfn_wgpuInstanceRequestAdapter ||
        !pfn_wgpuInstanceWaitAny || !pfn_wgpuInstanceProcessEvents ||
        !pfn_wgpuAdapterRequestDevice ||
        !pfn_wgpuDeviceGetQueue || !pfn_wgpuDeviceCreateBuffer ||
        !pfn_wgpuDeviceCreateShaderModule || !pfn_wgpuDeviceCreateComputePipeline ||
        !pfn_wgpuDeviceCreateCommandEncoder || !pfn_wgpuCommandEncoderBeginComputePass ||
        !pfn_wgpuCommandEncoderFinish || !pfn_wgpuQueueSubmit ||
        !pfn_wgpuQueueOnSubmittedWorkDone ||
        !pfn_wgpuBufferMapAsync2) {
        LIB_CLOSE(g_lib);
        g_lib = NULL;
        NAPI_THROW(env, "Failed to resolve required symbols from libwebgpu_doe");
    }

    napi_value result;
    napi_get_boolean(env, true, &result);
    return result;
}
