#include "doe_napi_internal.h"

/* Forward declarations for methods defined in other nd files */
napi_value native_direct_queue_submit(napi_env env, napi_callback_info info);
napi_value native_direct_queue_write_buffer(napi_env env, napi_callback_info info);
napi_value native_direct_queue_write_texture(napi_env env, napi_callback_info info);
napi_value native_direct_queue_on_submitted_work_done(napi_env env, napi_callback_info info);
napi_value native_direct_buffer_map_async(napi_env env, napi_callback_info info);
napi_value native_direct_buffer_get_mapped_range(napi_env env, napi_callback_info info);
napi_value native_direct_buffer_read_copy(napi_env env, napi_callback_info info);
napi_value native_direct_buffer_map_read_copy_unmap(napi_env env, napi_callback_info info);
napi_value native_direct_buffer_unmap(napi_env env, napi_callback_info info);
napi_value native_direct_buffer_destroy(napi_env env, napi_callback_info info);
napi_value native_direct_device_create_buffer(napi_env env, napi_callback_info info);
napi_value native_direct_device_create_shader_module(napi_env env, napi_callback_info info);
napi_value native_direct_device_create_compute_pipeline(napi_env env, napi_callback_info info);
napi_value native_direct_device_create_compute_pipeline_async(napi_env env, napi_callback_info info);
napi_value native_direct_device_create_bind_group_layout(napi_env env, napi_callback_info info);
napi_value native_direct_device_create_bind_group(napi_env env, napi_callback_info info);
napi_value native_direct_device_create_pipeline_layout(napi_env env, napi_callback_info info);
napi_value native_direct_device_create_command_encoder(napi_env env, napi_callback_info info);
napi_value native_direct_device_destroy(napi_env env, napi_callback_info info);
napi_value native_direct_device_add_event_listener(napi_env env, napi_callback_info info);
napi_value native_direct_device_remove_event_listener(napi_env env, napi_callback_info info);
napi_value native_direct_device_import_external_texture(napi_env env, napi_callback_info info);
napi_value native_direct_command_encoder_begin_compute_pass(napi_env env, napi_callback_info info);
napi_value native_direct_command_encoder_copy_buffer_to_buffer(napi_env env, napi_callback_info info);
napi_value native_direct_command_encoder_clear_buffer(napi_env env, napi_callback_info info);
napi_value native_direct_command_encoder_copy_texture_to_texture(napi_env env, napi_callback_info info);
napi_value native_direct_command_encoder_finish(napi_env env, napi_callback_info info);
napi_value native_direct_compute_pass_set_pipeline(napi_env env, napi_callback_info info);
napi_value native_direct_compute_pass_set_bind_group(napi_env env, napi_callback_info info);
napi_value native_direct_compute_pass_dispatch_workgroups(napi_env env, napi_callback_info info);
napi_value native_direct_compute_pass_dispatch_workgroups_indirect(napi_env env, napi_callback_info info);
napi_value native_direct_compute_pass_end(napi_env env, napi_callback_info info);
napi_value native_direct_compute_pass_set_immediates(napi_env env, napi_callback_info info);
napi_value native_direct_render_pass_set_immediates(napi_env env, napi_callback_info info);
napi_value native_direct_render_pass_set_viewport(napi_env env, napi_callback_info info);
napi_value native_direct_render_pass_set_scissor_rect(napi_env env, napi_callback_info info);
napi_value native_direct_render_pass_set_blend_constant(napi_env env, napi_callback_info info);
napi_value native_direct_render_pass_set_stencil_reference(napi_env env, napi_callback_info info);
napi_value native_direct_render_pass_push_debug_group(napi_env env, napi_callback_info info);
napi_value native_direct_render_pass_pop_debug_group(napi_env env, napi_callback_info info);
napi_value native_direct_render_pass_insert_debug_marker(napi_env env, napi_callback_info info);
napi_value native_direct_render_bundle_encoder_set_immediates(napi_env env, napi_callback_info info);

/* ================================================================
 * Adapter — getPreferredCanvasFormat
 * ================================================================ */

static napi_value native_direct_adapter_get_preferred_canvas_format(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);
    if (!pfn_doeNativeAdapterGetPreferredCanvasFormat) {
        /* Symbol not present yet — return the WebGPU preferred canvas format
         * for Apple Silicon (bgra8unorm is the Metal swapchain default). */
        napi_value result;
        napi_create_string_utf8(env, "bgra8unorm", NAPI_AUTO_LENGTH, &result);
        return result;
    }
    NativeDirectHandleCache* cache = native_direct_get_handle_cache(env, this_arg);
    void* adapter = cache ? cache->native : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    uint32_t fmt = pfn_doeNativeAdapterGetPreferredCanvasFormat(adapter);
    const char* name = texture_format_u32_to_string(fmt);
    if (name) {
        napi_value result;
        napi_create_string_utf8(env, name, NAPI_AUTO_LENGTH, &result);
        return result;
    }
    /* Unknown format — return the raw u32. */
    napi_value result;
    napi_create_uint32(env, fmt, &result);
    return result;
}

/* ================================================================
 * Adapter — getInfo
 * ================================================================ */

static napi_value native_direct_adapter_get_info(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);

    napi_value obj;
    napi_create_object(env, &obj);

    const char* vendor = "";
    const char* arch   = "";
    const char* device = "";
    const char* desc   = "";
    char* block = NULL;

    if (pfn_doeNativeAdapterGetInfo && pfn_doeNativeAdapterFreeInfo) {
        NativeDirectHandleCache* cache = native_direct_get_handle_cache(env, this_arg);
        void* adapter = cache ? cache->native
                              : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
        pfn_doeNativeAdapterGetInfo(adapter, &vendor, &arch, &device, &desc, &block);
        if (!vendor) vendor = "";
        if (!arch)   arch   = "";
        if (!device) device = "";
        if (!desc)   desc   = "";
    }

    napi_value v_vendor, v_arch, v_device, v_desc;
    napi_create_string_utf8(env, vendor, NAPI_AUTO_LENGTH, &v_vendor);
    napi_create_string_utf8(env, arch,   NAPI_AUTO_LENGTH, &v_arch);
    napi_create_string_utf8(env, device, NAPI_AUTO_LENGTH, &v_device);
    napi_create_string_utf8(env, desc,   NAPI_AUTO_LENGTH, &v_desc);
    napi_set_named_property(env, obj, "vendor",       v_vendor);
    napi_set_named_property(env, obj, "architecture", v_arch);
    napi_set_named_property(env, obj, "device",       v_device);
    napi_set_named_property(env, obj, "description",  v_desc);

    /* Apple Silicon SIMD-group size is fixed at 32 on all known variants. */
    napi_value v_sg_min, v_sg_max;
    napi_create_uint32(env, 32, &v_sg_min);
    napi_create_uint32(env, 32, &v_sg_max);
    napi_set_named_property(env, obj, "subgroupMinSize", v_sg_min);
    napi_set_named_property(env, obj, "subgroupMaxSize", v_sg_max);

    if (block && pfn_doeNativeAdapterFreeInfo) {
        pfn_doeNativeAdapterFreeInfo(block);
    }
    return obj;
}

/* ================================================================
 * ShaderModule — getCompilationInfo
 * ================================================================ */

static napi_value native_direct_shader_module_get_compilation_info(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);

    NativeDirectHandleCache* cache = native_direct_get_handle_cache(env, this_arg);
    void* module_raw = cache ? cache->native
                             : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);

    const char* json_str = "[]";
    if (pfn_doeNativeShaderModuleGetCompilationInfo) {
        const char* native_json = pfn_doeNativeShaderModuleGetCompilationInfo(module_raw);
        if (native_json) json_str = native_json;
    }

    /* Parse via JS JSON.parse — the Zig layer emits strict JSON. */
    napi_value global, json_obj, json_parse_fn, json_str_val, parse_args[1], parsed;
    napi_get_global(env, &global);
    napi_get_named_property(env, global, "JSON", &json_obj);
    napi_get_named_property(env, json_obj, "parse", &json_parse_fn);
    napi_create_string_utf8(env, json_str, NAPI_AUTO_LENGTH, &json_str_val);
    parse_args[0] = json_str_val;

    napi_value messages;
    napi_status parse_status = napi_call_function(env, json_obj, json_parse_fn, 1, parse_args, &parsed);
    if (parse_status != napi_ok) {
        napi_create_array_with_length(env, 0, &messages);
    } else {
        messages = parsed;
    }

    /* Ensure each message has all 5 required fields */
    uint32_t msg_count = 0;
    napi_get_array_length(env, messages, &msg_count);
    for (uint32_t i = 0; i < msg_count; i++) {
        napi_value msg_obj;
        napi_get_element(env, messages, i, &msg_obj);
        ensure_compilation_message_fields(env, msg_obj);
    }

    napi_value compilation_info;
    napi_create_object(env, &compilation_info);
    napi_set_named_property(env, compilation_info, "messages", messages);
    return native_direct_resolved_promise(env, compilation_info);
}

/* ================================================================
 * Adapter lifecycle — requestAdapter, requestDevice, destroy
 * ================================================================ */

static napi_value native_direct_gpu_request_adapter(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    (void)argv;
    WGPUInstance inst = native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_INSTANCE);
    WGPUAdapter adapter = native_direct_request_adapter_sync(env, inst);
    if (!adapter) return NULL;
    return native_direct_resolved_promise(env, create_native_direct_adapter_object(env, inst, adapter));
}

static napi_value native_direct_adapter_request_device(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    (void)argv;
    WGPUInstance inst = native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_INSTANCE);
    WGPUAdapter adapter = native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    WGPUDevice device = native_direct_request_device_sync(env, inst, adapter);
    if (!device) return NULL;
    return native_direct_resolved_promise(env, create_native_direct_device_object(env, inst, device));
}

static napi_value native_direct_adapter_destroy(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);
    WGPUAdapter adapter = native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (adapter) {
        pfn_wgpuAdapterRelease(adapter);
        native_direct_set_external_prop(env, this_arg, DOE_DIRECT_NATIVE, NULL);
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

/* ================================================================
 * Object constructors
 * ================================================================ */

napi_value create_native_direct_gpu_object(napi_env env, WGPUInstance instance) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_INSTANCE, instance);
    native_direct_wrap_handle_cache(env, obj, instance, NULL);
    native_direct_add_cached_method(env, obj, "requestAdapter", native_direct_gpu_request_adapter, &native_direct_method_gpu_request_adapter_ref);
    return obj;
}

napi_value create_native_direct_adapter_object(napi_env env, WGPUInstance instance, WGPUAdapter adapter) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_INSTANCE, instance);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, adapter);
    native_direct_wrap_handle_cache(env, obj, instance, adapter);
    bool limits_ok = false;
    WGPULimits limits = native_direct_query_adapter_limits(adapter, &limits_ok);
    native_direct_set_object_prop(env, obj, "limits", limits_ok ? create_limits_object(env, &limits) : native_direct_create_empty_object(env));
    native_direct_set_object_prop(env, obj, "features", native_direct_create_empty_set(env));
    native_direct_add_cached_method(env, obj, "requestDevice", native_direct_adapter_request_device, &native_direct_method_adapter_request_device_ref);
    native_direct_add_cached_method(env, obj, "destroy", native_direct_adapter_destroy, &native_direct_method_adapter_destroy_ref);
    native_direct_add_cached_method(env, obj, "getPreferredCanvasFormat", native_direct_adapter_get_preferred_canvas_format, &native_direct_method_adapter_get_preferred_canvas_format_ref);
    /* GPUAdapter.info — method that returns the info object directly (not async). */
    native_direct_add_cached_method(env, obj, "getInfo", native_direct_adapter_get_info, &native_direct_method_adapter_get_info_ref);
    return obj;
}

napi_value create_native_direct_queue_object(napi_env env, WGPUInstance instance, WGPUQueue queue) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_INSTANCE, instance);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, queue);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_QUEUE_NATIVE, queue);
    native_direct_set_uint32_prop(env, obj, DOE_DIRECT_SUBMITTED_SERIAL, 0);
    native_direct_set_uint32_prop(env, obj, DOE_DIRECT_COMPLETED_SERIAL, 0);
    native_direct_set_double_prop(env, obj, DOE_DIRECT_DIAG_SUBMIT_WAIT_MS, 0.0);
    native_direct_set_double_prop(env, obj, DOE_DIRECT_DIAG_QUEUE_FLUSH_MS, 0.0);
    native_direct_wrap_queue_cache(env, obj, instance, queue);
    native_direct_add_cached_method(env, obj, "submit", native_direct_queue_submit, &native_direct_method_queue_submit_ref);
    native_direct_add_cached_method(env, obj, "writeBuffer", native_direct_queue_write_buffer, &native_direct_method_queue_write_buffer_ref);
    native_direct_add_cached_method(env, obj, "writeTexture", native_direct_queue_write_texture, &native_direct_method_queue_write_texture_ref);
    native_direct_add_cached_method(env, obj, "onSubmittedWorkDone", native_direct_queue_on_submitted_work_done, &native_direct_method_queue_on_submitted_work_done_ref);
    return obj;
}

napi_value create_native_direct_device_object(napi_env env, WGPUInstance instance, WGPUDevice device) {
    napi_value obj;
    WGPUQueue queue = pfn_wgpuDeviceGetQueue(device);
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_INSTANCE, instance);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, device);
    native_direct_wrap_handle_cache(env, obj, instance, device);
    bool limits_ok = false;
    WGPULimits limits = native_direct_query_device_limits(device, &limits_ok);
    native_direct_set_object_prop(env, obj, "limits", limits_ok ? create_limits_object(env, &limits) : native_direct_create_empty_object(env));
    native_direct_set_object_prop(env, obj, "features", native_direct_create_empty_set(env));
    native_direct_set_object_prop(env, obj, "queue", create_native_direct_queue_object(env, instance, queue));
    native_direct_add_cached_method(env, obj, "createBuffer", native_direct_device_create_buffer, &native_direct_method_device_create_buffer_ref);
    native_direct_add_cached_method(env, obj, "createShaderModule", native_direct_device_create_shader_module, &native_direct_method_device_create_shader_module_ref);
    native_direct_add_cached_method(env, obj, "createComputePipeline", native_direct_device_create_compute_pipeline, &native_direct_method_device_create_compute_pipeline_ref);
    native_direct_add_cached_method(env, obj, "createComputePipelineAsync", native_direct_device_create_compute_pipeline_async, &native_direct_method_device_create_compute_pipeline_async_ref);
    native_direct_add_cached_method(env, obj, "createBindGroupLayout", native_direct_device_create_bind_group_layout, &native_direct_method_device_create_bind_group_layout_ref);
    native_direct_add_cached_method(env, obj, "createBindGroup", native_direct_device_create_bind_group, &native_direct_method_device_create_bind_group_ref);
    native_direct_add_cached_method(env, obj, "createPipelineLayout", native_direct_device_create_pipeline_layout, &native_direct_method_device_create_pipeline_layout_ref);
    native_direct_add_cached_method(env, obj, "createCommandEncoder", native_direct_device_create_command_encoder, &native_direct_method_device_create_command_encoder_ref);
    native_direct_add_cached_method(env, obj, "destroy", native_direct_device_destroy, &native_direct_method_device_destroy_ref);
    native_direct_add_cached_method(env, obj, "addEventListener", native_direct_device_add_event_listener, &native_direct_method_device_add_event_listener_ref);
    native_direct_add_cached_method(env, obj, "removeEventListener", native_direct_device_remove_event_listener, &native_direct_method_device_remove_event_listener_ref);
    native_direct_add_cached_method(env, obj, "importExternalTexture", native_direct_device_import_external_texture, &native_direct_method_device_import_external_texture_ref);
    return obj;
}

napi_value create_native_direct_buffer_object(napi_env env, WGPUInstance instance, napi_value queue_obj, WGPUBuffer buffer, uint64_t size, uint64_t usage) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_INSTANCE, instance);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, buffer);
    native_direct_set_object_prop(env, obj, DOE_DIRECT_QUEUE, queue_obj);
    native_direct_set_double_prop(env, obj, "size", (double)size);
    native_direct_set_double_prop(env, obj, "usage", (double)usage);
    native_direct_set_double_prop(env, obj, DOE_DIRECT_DIAG_MAP_ASYNC_MS, 0.0);
    native_direct_set_double_prop(env, obj, DOE_DIRECT_DIAG_MAP_QUEUE_FLUSH_MS, 0.0);
    native_direct_set_double_prop(env, obj, DOE_DIRECT_DIAG_GET_MAPPED_RANGE_MS, 0.0);
    native_direct_wrap_buffer_cache(env, obj, instance, buffer, size, usage, queue_obj);
    native_direct_add_cached_method(env, obj, "mapAsync", native_direct_buffer_map_async, &native_direct_method_buffer_map_async_ref);
    native_direct_add_cached_method(env, obj, "getMappedRange", native_direct_buffer_get_mapped_range, &native_direct_method_buffer_get_mapped_range_ref);
    native_direct_add_cached_method(env, obj, "_readCopy", native_direct_buffer_read_copy, &native_direct_method_buffer_read_copy_ref);
    native_direct_add_cached_method(env, obj, "_mapReadCopyUnmap", native_direct_buffer_map_read_copy_unmap, &native_direct_method_buffer_map_read_copy_unmap_ref);
    native_direct_add_cached_method(env, obj, "unmap", native_direct_buffer_unmap, &native_direct_method_buffer_unmap_ref);
    native_direct_add_cached_method(env, obj, "destroy", native_direct_buffer_destroy, &native_direct_method_buffer_destroy_ref);
    return obj;
}

napi_value create_native_direct_bind_group_layout_object(napi_env env, WGPUBindGroupLayout layout) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, layout);
    native_direct_wrap_handle_cache(env, obj, NULL, layout);
    return obj;
}

napi_value create_native_direct_bind_group_object(napi_env env, WGPUBindGroup group) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, group);
    native_direct_wrap_handle_cache(env, obj, NULL, group);
    return obj;
}

napi_value create_native_direct_pipeline_layout_object(napi_env env, WGPUPipelineLayout layout) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, layout);
    native_direct_wrap_handle_cache(env, obj, NULL, layout);
    return obj;
}

napi_value create_native_direct_shader_module_object(napi_env env, WGPUShaderModule shader_module) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, shader_module);
    native_direct_wrap_handle_cache(env, obj, NULL, shader_module);
    /* GPUShaderModule.getCompilationInfo() — returns a Promise<GPUCompilationInfo>. */
    native_direct_add_cached_method(env, obj, "getCompilationInfo", native_direct_shader_module_get_compilation_info, &native_direct_method_shader_module_get_compilation_info_ref);
    return obj;
}

napi_value create_native_direct_compute_pipeline_object(napi_env env, WGPUComputePipeline pipeline) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, pipeline);
    native_direct_wrap_handle_cache(env, obj, NULL, pipeline);
    return obj;
}

napi_value create_native_direct_command_buffer_object(napi_env env, WGPUCommandBuffer command_buffer) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, command_buffer);
    native_direct_wrap_handle_cache(env, obj, NULL, command_buffer);
    return obj;
}

napi_value create_native_direct_command_encoder_object(napi_env env, WGPUCommandEncoder encoder) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, encoder);
    native_direct_wrap_handle_cache(env, obj, NULL, encoder);
    native_direct_add_cached_method(env, obj, "beginComputePass", native_direct_command_encoder_begin_compute_pass, &native_direct_method_command_encoder_begin_compute_pass_ref);
    native_direct_add_cached_method(env, obj, "copyBufferToBuffer", native_direct_command_encoder_copy_buffer_to_buffer, &native_direct_method_command_encoder_copy_buffer_to_buffer_ref);
    native_direct_add_cached_method(env, obj, "clearBuffer", native_direct_command_encoder_clear_buffer, &native_direct_method_command_encoder_clear_buffer_ref);
    native_direct_add_cached_method(env, obj, "copyTextureToTexture", native_direct_command_encoder_copy_texture_to_texture, &native_direct_method_command_encoder_copy_texture_to_texture_ref);
    native_direct_add_cached_method(env, obj, "finish", native_direct_command_encoder_finish, &native_direct_method_command_encoder_finish_ref);
    return obj;
}

napi_value create_native_direct_compute_pass_object(napi_env env, WGPUComputePassEncoder pass) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, pass);
    native_direct_wrap_handle_cache(env, obj, NULL, pass);
    native_direct_add_cached_method(env, obj, "setPipeline", native_direct_compute_pass_set_pipeline, &native_direct_method_compute_pass_set_pipeline_ref);
    native_direct_add_cached_method(env, obj, "setBindGroup", native_direct_compute_pass_set_bind_group, &native_direct_method_compute_pass_set_bind_group_ref);
    native_direct_add_cached_method(env, obj, "dispatchWorkgroups", native_direct_compute_pass_dispatch_workgroups, &native_direct_method_compute_pass_dispatch_workgroups_ref);
    native_direct_add_cached_method(env, obj, "dispatchWorkgroupsIndirect", native_direct_compute_pass_dispatch_workgroups_indirect, &native_direct_method_compute_pass_dispatch_workgroups_indirect_ref);
    native_direct_add_cached_method(env, obj, "end", native_direct_compute_pass_end, &native_direct_method_compute_pass_end_ref);
    /* GPUBindingCommandsMixin#setImmediates — covers both mixin and compute-pass-specific contract */
    native_direct_add_cached_method(env, obj, "setImmediates", native_direct_compute_pass_set_immediates, &native_direct_method_compute_pass_set_immediates_ref);
    return obj;
}

/* create_native_direct_render_pass_object: wraps a WGPURenderPassEncoder as a JS
 * object with all GPURenderPassEncoder control methods registered. */
napi_value create_native_direct_render_pass_object(napi_env env, WGPURenderPassEncoder pass) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, pass);
    native_direct_wrap_handle_cache(env, obj, NULL, pass);
    /* GPURenderPassEncoder#setImmediates (GPUBindingCommandsMixin) */
    native_direct_add_cached_method(env, obj, "setImmediates", native_direct_render_pass_set_immediates, &native_direct_method_render_pass_set_immediates_ref);
    /* GPURenderPassEncoder dynamic state */
    native_direct_add_cached_method(env, obj, "setViewport", native_direct_render_pass_set_viewport, &native_direct_method_render_pass_set_viewport_ref);
    native_direct_add_cached_method(env, obj, "setScissorRect", native_direct_render_pass_set_scissor_rect, &native_direct_method_render_pass_set_scissor_rect_ref);
    native_direct_add_cached_method(env, obj, "setBlendConstant", native_direct_render_pass_set_blend_constant, &native_direct_method_render_pass_set_blend_constant_ref);
    native_direct_add_cached_method(env, obj, "setStencilReference", native_direct_render_pass_set_stencil_reference, &native_direct_method_render_pass_set_stencil_reference_ref);
    /* GPURenderPassEncoder debug markers */
    native_direct_add_cached_method(env, obj, "pushDebugGroup", native_direct_render_pass_push_debug_group, &native_direct_method_render_pass_push_debug_group_ref);
    native_direct_add_cached_method(env, obj, "popDebugGroup", native_direct_render_pass_pop_debug_group, &native_direct_method_render_pass_pop_debug_group_ref);
    native_direct_add_cached_method(env, obj, "insertDebugMarker", native_direct_render_pass_insert_debug_marker, &native_direct_method_render_pass_insert_debug_marker_ref);
    return obj;
}

/* native_direct_create_instance — exported as "nativeDirectCreate".
 * Creates a WGPUInstance and returns a JS GPU object bound to it. */
napi_value doe_native_direct_create(napi_env env, napi_callback_info info) {
    (void)info;
    CHECK_LIB_LOADED(env);
    WGPUInstance inst = pfn_wgpuCreateInstance(NULL);
    if (!inst) NAPI_THROW(env, "wgpuCreateInstance returned NULL");
    return create_native_direct_gpu_object(env, inst);
}
