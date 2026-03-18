#include "doe_napi_internal.h"

/* Helper: extract a uint32 from a named property of a JS object.
 * Returns 0 if the property is absent or not a number. */
static uint32_t get_u32_prop(napi_env env, napi_value obj, const char* key) {
    napi_value val;
    napi_get_named_property(env, obj, key, &val);
    uint32_t out = 0;
    napi_get_value_uint32(env, val, &out);
    return out;
}

/* Helper: extract a GPUOrigin3D {x,y,z} from a JS object into three uint32 output args. */
static void get_origin_3d(napi_env env, napi_value obj, uint32_t* x, uint32_t* y, uint32_t* z) {
    *x = get_u32_prop(env, obj, "x");
    *y = get_u32_prop(env, obj, "y");
    *z = get_u32_prop(env, obj, "z");
}

/* Helper: extract a GPUExtent3D {width,height,depthOrArrayLayers} from a JS object. */
static void get_extent_3d(napi_env env, napi_value obj, uint32_t* w, uint32_t* h, uint32_t* d) {
    *w = get_u32_prop(env, obj, "width");
    *h = get_u32_prop(env, obj, "height");
    *d = get_u32_prop(env, obj, "depthOrArrayLayers");
    if (*d == 0) *d = 1; /* default per WebGPU spec */
}

napi_value native_direct_queue_write_buffer(napi_env env, napi_callback_info info) {
    size_t argc = 5;
    napi_value argv[5];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 3) NAPI_THROW(env, "queue.writeBuffer requires buffer, offset, and data");
    NativeDirectQueueCache* queue_cache = native_direct_get_queue_cache(env, this_arg);
    NativeDirectBufferCache* buffer_cache = native_direct_get_buffer_cache(env, argv[0]);
    WGPUQueue queue = queue_cache ? queue_cache->queue : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    WGPUBuffer buffer = buffer_cache ? buffer_cache->buffer : native_direct_unwrap_external_prop(env, argv[0], DOE_DIRECT_NATIVE);
    if (!queue || !buffer) NAPI_THROW(env, "queue.writeBuffer requires queue and buffer");
    int64_t offset = 0;
    napi_get_value_int64(env, argv[1], &offset);

    void* data = NULL;
    size_t byte_length = 0;
    bool is_typedarray = false;
    napi_is_typedarray(env, argv[2], &is_typedarray);
    if (is_typedarray) {
        napi_typedarray_type ta_type;
        size_t ta_length;
        napi_value ab;
        size_t byte_offset;
        napi_get_typedarray_info(env, argv[2], &ta_type, &ta_length, &data, &ab, &byte_offset);
        size_t elem_size = 1;
        switch (ta_type) {
            case napi_int16_array: case napi_uint16_array: elem_size = 2; break;
            case napi_int32_array: case napi_uint32_array: case napi_float32_array: elem_size = 4; break;
            case napi_float64_array: case napi_bigint64_array: case napi_biguint64_array: elem_size = 8; break;
            default: elem_size = 1; break;
        }
        byte_length = ta_length * elem_size;
    } else {
        bool is_ab = false;
        napi_is_arraybuffer(env, argv[2], &is_ab);
        if (is_ab) {
            napi_get_arraybuffer_info(env, argv[2], &data, &byte_length);
        } else {
            bool is_buffer = false;
            napi_is_buffer(env, argv[2], &is_buffer);
            if (is_buffer) {
                napi_get_buffer_info(env, argv[2], &data, &byte_length);
            } else {
                NAPI_THROW(env, "queue.writeBuffer data must be TypedArray, ArrayBuffer, or Buffer");
            }
        }
    }

    if (argc >= 4 && argv[3]) {
        uint32_t data_offset = 0;
        napi_get_value_uint32(env, argv[3], &data_offset);
        data = ((uint8_t*)data) + data_offset;
        byte_length = byte_length > data_offset ? byte_length - data_offset : 0;
    }
    if (argc >= 5 && argv[4]) {
        uint32_t size = 0;
        napi_get_value_uint32(env, argv[4], &size);
        if (size < byte_length) byte_length = size;
    }

    pfn_wgpuQueueWriteBuffer(queue, buffer, (uint64_t)offset, data, byte_length);
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

/* GPUQueue.writeTexture(destination, data, dataLayout, size)
 * argv[0]: {texture, mipLevel, origin: {x,y,z}, aspect?}
 * argv[1]: ArrayBuffer | TypedArray — pixel data
 * argv[2]: {offset?, bytesPerRow, rowsPerImage?}
 * argv[3]: {width, height, depthOrArrayLayers} */
napi_value native_direct_queue_write_texture(napi_env env, napi_callback_info info) {
    size_t argc = 4;
    napi_value argv[4];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 4) NAPI_THROW(env, "writeTexture requires destination, data, dataLayout, and size");
    NativeDirectQueueCache* queue_cache = native_direct_get_queue_cache(env, this_arg);
    void* queue = queue_cache ? queue_cache->queue : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!queue) NAPI_THROW(env, "writeTexture: invalid queue");
    napi_value tex_obj = get_prop(env, argv[0], "texture");
    void* texture = native_direct_unwrap_external_prop(env, tex_obj, DOE_DIRECT_NATIVE);
    if (!texture) NAPI_THROW(env, "writeTexture: invalid destination texture");
    uint32_t dst_mip = get_u32_prop(env, argv[0], "mipLevel");
    uint32_t dst_x = 0, dst_y = 0, dst_z = 0;
    napi_value dst_origin = get_prop(env, argv[0], "origin");
    napi_valuetype dst_origin_type;
    napi_typeof(env, dst_origin, &dst_origin_type);
    if (dst_origin_type == napi_object) get_origin_3d(env, dst_origin, &dst_x, &dst_y, &dst_z);
    /* Extract pixel data pointer and byte length */
    void* data = NULL;
    size_t data_len = 0;
    bool is_typedarray = false;
    napi_is_typedarray(env, argv[1], &is_typedarray);
    if (is_typedarray) {
        napi_typedarray_type ta_type;
        size_t ta_length;
        napi_value ab;
        size_t byte_offset;
        napi_get_typedarray_info(env, argv[1], &ta_type, &ta_length, &data, &ab, &byte_offset);
        size_t elem_size = 1;
        switch (ta_type) {
            case napi_int16_array: case napi_uint16_array: elem_size = 2; break;
            case napi_int32_array: case napi_uint32_array: case napi_float32_array: elem_size = 4; break;
            case napi_float64_array: case napi_bigint64_array: case napi_biguint64_array: elem_size = 8; break;
            default: elem_size = 1; break;
        }
        data_len = ta_length * elem_size;
    } else {
        bool is_ab = false;
        napi_is_arraybuffer(env, argv[1], &is_ab);
        if (is_ab) {
            napi_get_arraybuffer_info(env, argv[1], &data, &data_len);
        } else {
            NAPI_THROW(env, "writeTexture: data must be TypedArray or ArrayBuffer");
        }
    }
    /* dataLayout: {offset?, bytesPerRow, rowsPerImage?} */
    uint32_t layout_offset = get_u32_prop(env, argv[2], "offset");
    uint32_t bytes_per_row = get_u32_prop(env, argv[2], "bytesPerRow");
    uint32_t rows_per_image = get_u32_prop(env, argv[2], "rowsPerImage");
    if (layout_offset > 0 && layout_offset < data_len) {
        data = ((uint8_t*)data) + layout_offset;
        data_len -= layout_offset;
    }
    /* copySize */
    uint32_t width = 1, height = 1, depth_or_layers = 1;
    napi_valuetype size_type;
    napi_typeof(env, argv[3], &size_type);
    if (size_type == napi_object) get_extent_3d(env, argv[3], &width, &height, &depth_or_layers);
    if (pfn_doeNativeQueueWriteTexture) {
        pfn_doeNativeQueueWriteTexture(
            queue, texture,
            data, data_len,
            bytes_per_row, rows_per_image,
            dst_x, dst_y, dst_z, dst_mip, 0,
            width, height, depth_or_layers);
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

napi_value native_direct_queue_submit(napi_env env, napi_callback_info info) {
    size_t argc = 1;
    napi_value argv[1];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "queue.submit requires command buffers");
    NativeDirectQueueCache* queue_cache = native_direct_get_queue_cache(env, this_arg);
    WGPUQueue queue = queue_cache ? queue_cache->queue : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!queue) NAPI_THROW(env, "Invalid queue");
    uint32_t cmd_count = 0;
    napi_get_array_length(env, argv[0], &cmd_count);
    if (cmd_count == 1) {
        napi_value elem;
        WGPUCommandBuffer cmd = NULL;
        napi_get_element(env, argv[0], 0, &elem);
        {
            NativeDirectHandleCache* command_buffer_cache = native_direct_get_handle_cache(env, elem);
            cmd = command_buffer_cache ? (WGPUCommandBuffer)command_buffer_cache->native : native_direct_unwrap_external_prop(env, elem, DOE_DIRECT_NATIVE);
        }
        pfn_wgpuQueueSubmit(queue, 1, &cmd);
    } else {
        WGPUCommandBuffer* cmds = (WGPUCommandBuffer*)calloc(cmd_count, sizeof(WGPUCommandBuffer));
        if (!cmds && cmd_count > 0) NAPI_THROW(env, "queue.submit: out of memory");
        for (uint32_t i = 0; i < cmd_count; i++) {
            napi_value elem;
            napi_get_element(env, argv[0], i, &elem);
            {
                NativeDirectHandleCache* command_buffer_cache = native_direct_get_handle_cache(env, elem);
                cmds[i] = command_buffer_cache ? (WGPUCommandBuffer)command_buffer_cache->native : native_direct_unwrap_external_prop(env, elem, DOE_DIRECT_NATIVE);
            }
        }
        pfn_wgpuQueueSubmit(queue, cmd_count, cmds);
        free(cmds);
    }
    native_direct_queue_mark_submitted(env, this_arg);
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

napi_value native_direct_queue_on_submitted_work_done(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);
    NativeDirectQueueCache* queue_cache = native_direct_get_queue_cache(env, this_arg);
    WGPUInstance inst = queue_cache ? queue_cache->instance : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_INSTANCE);
    WGPUQueue queue = queue_cache ? queue_cache->queue : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!queue) NAPI_THROW(env, "Invalid queue");
    double queue_flush_ms = 0.0;
    const uint64_t submit_wait_started_ns = monotonic_now_ns();
    if (native_direct_queue_has_pending(env, this_arg)) {
        if (pfn_doeNativeQueueFlush) {
            const uint64_t flush_started_ns = monotonic_now_ns();
            pfn_doeNativeQueueFlush(queue);
            queue_flush_ms = native_direct_elapsed_ms(flush_started_ns);
        } else {
            QueueWorkDoneResult result = {0};
            WGPUQueueWorkDoneCallbackInfo cb_info = {
                .nextInChain = NULL,
                .mode = WGPU_CALLBACK_MODE_WAIT_ANY_ONLY,
                .callback = queue_work_done_callback,
                .userdata1 = &result,
                .userdata2 = NULL,
            };
            WGPUFuture future = pfn_wgpuQueueOnSubmittedWorkDone(queue, cb_info);
            if (future.id == 0) NAPI_THROW(env, "queue work-done future unavailable");
            const uint64_t flush_started_ns = monotonic_now_ns();
            uint64_t start_ns = monotonic_now_ns();
            while (!result.done) {
                WGPUFutureWaitInfo wait_info = {
                    .future = future,
                    .completed = 0,
                };
                uint32_t wait_status = pfn_wgpuInstanceWaitAny(inst, 1, &wait_info, 0);
                if (wait_status == WGPU_WAIT_STATUS_SUCCESS) {
                    if (!result.done) pfn_wgpuInstanceProcessEvents(inst);
                } else if (wait_status == WGPU_WAIT_STATUS_TIMED_OUT) {
                    pfn_wgpuInstanceProcessEvents(inst);
                    if (monotonic_now_ns() - start_ns >= current_timeout_ns()) {
                        napi_throw_error(env, "DOE_QUEUE_TIMEOUT", "queue wait timed out");
                        return NULL;
                    }
                    wait_slice();
                } else if (wait_status == WGPU_WAIT_STATUS_ERROR) {
                    napi_throw_error(env, "DOE_QUEUE_UNAVAILABLE", "queue wait failed");
                    return NULL;
                } else {
                    NAPI_THROW(env, "queue wait returned unsupported status");
                }
            }
            if (result.status != WGPU_QUEUE_WORK_DONE_STATUS_SUCCESS) {
                return throw_status_error(env, "DOE_QUEUE_FLUSH_ERROR", "queue work did not complete", result.status, result.message);
            }
            queue_flush_ms = native_direct_elapsed_ms(flush_started_ns);
        }
        native_direct_queue_mark_done(env, this_arg);
    }
    native_direct_set_double_prop(env, this_arg, DOE_DIRECT_DIAG_QUEUE_FLUSH_MS, queue_flush_ms);
    native_direct_set_double_prop(env, this_arg, DOE_DIRECT_DIAG_SUBMIT_WAIT_MS, native_direct_elapsed_ms(submit_wait_started_ns));
    return native_direct_resolved_undefined_promise(env);
}

napi_value native_direct_buffer_map_async(napi_env env, napi_callback_info info) {
    size_t argc = 3;
    napi_value argv[3];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    if (argc < 1) NAPI_THROW(env, "buffer.mapAsync requires a mode");
    NativeDirectBufferCache* buffer_cache = native_direct_get_buffer_cache(env, this_arg);
    WGPUInstance inst = buffer_cache ? buffer_cache->instance : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_INSTANCE);
    WGPUBuffer buffer = buffer_cache ? buffer_cache->buffer : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    napi_value queue_obj = NULL;
    if (buffer_cache && buffer_cache->queue_ref) {
        napi_get_reference_value(env, buffer_cache->queue_ref, &queue_obj);
    } else {
        queue_obj = get_prop(env, this_arg, DOE_DIRECT_QUEUE);
    }
    if (!buffer) NAPI_THROW(env, "Invalid buffer");
    uint32_t mode = 0;
    int64_t offset = 0;
    int64_t size = buffer_cache ? (int64_t)buffer_cache->size : (int64_t)get_double_prop(env, this_arg, "size");
    napi_get_value_uint32(env, argv[0], &mode);
    if (argc >= 2 && argv[1]) napi_get_value_int64(env, argv[1], &offset);
    if (argc >= 3 && argv[2]) napi_get_value_int64(env, argv[2], &size);
    double map_queue_flush_ms = 0.0;
    if (native_direct_queue_has_pending(env, queue_obj)) {
        NativeDirectQueueCache* queue_cache = native_direct_get_queue_cache(env, queue_obj);
        WGPUQueue queue = queue_cache ? queue_cache->queue : native_direct_unwrap_external_prop(env, queue_obj, DOE_DIRECT_NATIVE);
        if (pfn_doeNativeQueueFlush) {
            const uint64_t flush_started_ns = monotonic_now_ns();
            pfn_doeNativeQueueFlush(queue);
            map_queue_flush_ms = native_direct_elapsed_ms(flush_started_ns);
        } else {
            QueueWorkDoneResult result = {0};
            WGPUQueueWorkDoneCallbackInfo cb_info = {
                .nextInChain = NULL,
                .mode = WGPU_CALLBACK_MODE_WAIT_ANY_ONLY,
                .callback = queue_work_done_callback,
                .userdata1 = &result,
                .userdata2 = NULL,
            };
            WGPUFuture future = pfn_wgpuQueueOnSubmittedWorkDone(queue, cb_info);
            if (future.id == 0) NAPI_THROW(env, "queue work-done future unavailable");
            const uint64_t flush_started_ns = monotonic_now_ns();
            if (!process_events_until(inst, &result.done, current_timeout_ns())) {
                return throw_status_error(env, "DOE_QUEUE_TIMEOUT", "queue wait timed out", result.status, result.message);
            }
            if (result.status != WGPU_QUEUE_WORK_DONE_STATUS_SUCCESS) {
                return throw_status_error(env, "DOE_QUEUE_FLUSH_ERROR", "queue work did not complete", result.status, result.message);
            }
            map_queue_flush_ms = native_direct_elapsed_ms(flush_started_ns);
        }
        native_direct_queue_mark_done(env, queue_obj);
    }

    BufferMapResult result = {0};
    WGPUBufferMapCallbackInfo cb_info = {
        .nextInChain = NULL,
        .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
        .callback = buffer_map_callback,
        .userdata1 = &result,
        .userdata2 = NULL,
    };
    const uint64_t map_started_ns = monotonic_now_ns();
    if (pfn_doeNativeBufferMapAsync && pfn_doeNativeQueueFlush) {
        WGPUFuture future = pfn_doeNativeBufferMapAsync(buffer, (uint64_t)mode, (size_t)offset, (size_t)size, cb_info);
        if (future.id == 0 || !result.done) NAPI_THROW(env, "doeNativeBufferMapAsync unavailable");
        if (result.status != WGPU_MAP_ASYNC_STATUS_SUCCESS) {
            return throw_status_error(env, "DOE_BUFFER_MAP_ERROR", "doeNativeBufferMapAsync failed", result.status, result.message);
        }
    } else {
        WGPUFuture future = pfn_wgpuBufferMapAsync2(buffer, (uint64_t)mode, (size_t)offset, (size_t)size, cb_info);
        if (future.id == 0) NAPI_THROW(env, "bufferMapAsync future unavailable");
        if (!process_events_until(inst, &result.done, current_timeout_ns())) {
            return throw_status_error(env, "DOE_BUFFER_MAP_TIMEOUT", "bufferMapAsync timed out", result.status, result.message);
        }
        if (result.status != WGPU_MAP_ASYNC_STATUS_SUCCESS) {
            return throw_status_error(env, "DOE_BUFFER_MAP_ERROR", "bufferMapAsync failed", result.status, result.message);
        }
    }
    native_direct_set_double_prop(env, this_arg, DOE_DIRECT_DIAG_MAP_QUEUE_FLUSH_MS, map_queue_flush_ms);
    native_direct_set_double_prop(env, this_arg, DOE_DIRECT_DIAG_MAP_ASYNC_MS, native_direct_elapsed_ms(map_started_ns));
    return native_direct_resolved_undefined_promise(env);
}

napi_value native_direct_buffer_get_mapped_range(napi_env env, napi_callback_info info) {
    size_t argc = 2;
    napi_value argv[2];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    NativeDirectBufferCache* buffer_cache = native_direct_get_buffer_cache(env, this_arg);
    WGPUBuffer buffer = buffer_cache ? buffer_cache->buffer : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!buffer) NAPI_THROW(env, "Invalid buffer");
    int64_t offset = 0;
    int64_t size = buffer_cache ? (int64_t)buffer_cache->size : (int64_t)get_double_prop(env, this_arg, "size");
    if (argc >= 1 && argv[0]) napi_get_value_int64(env, argv[0], &offset);
    if (argc >= 2 && argv[1]) napi_get_value_int64(env, argv[1], &size);
    const uint64_t get_mapped_range_started_ns = monotonic_now_ns();
    void* data = pfn_wgpuBufferGetMappedRange(buffer, (size_t)offset, (size_t)size);
    if (!data) data = (void*)pfn_wgpuBufferGetConstMappedRange(buffer, (size_t)offset, (size_t)size);
    if (!data) NAPI_THROW(env, "getMappedRange returned NULL");
    if (buffer_cache &&
        buffer_cache->mapped_range_ref &&
        buffer_cache->mapped_ptr == data &&
        buffer_cache->mapped_offset == (size_t)offset &&
        buffer_cache->mapped_size == (size_t)size) {
        napi_value cached;
        native_direct_set_double_prop(env, this_arg, DOE_DIRECT_DIAG_GET_MAPPED_RANGE_MS, native_direct_elapsed_ms(get_mapped_range_started_ns));
        napi_get_reference_value(env, buffer_cache->mapped_range_ref, &cached);
        return cached;
    }
    if (buffer_cache) native_direct_invalidate_buffer_mapped_range_cache(env, buffer_cache);
    napi_value array_buffer;
    napi_create_external_arraybuffer(env, data, (size_t)size, NULL, NULL, &array_buffer);
    if (buffer_cache) {
        napi_create_reference(env, array_buffer, 1, &buffer_cache->mapped_range_ref);
        buffer_cache->mapped_offset = (size_t)offset;
        buffer_cache->mapped_size = (size_t)size;
        buffer_cache->mapped_ptr = data;
    }
    native_direct_set_double_prop(env, this_arg, DOE_DIRECT_DIAG_GET_MAPPED_RANGE_MS, native_direct_elapsed_ms(get_mapped_range_started_ns));
    return array_buffer;
}

napi_value native_direct_buffer_read_copy(napi_env env, napi_callback_info info) {
    size_t argc = 2;
    napi_value argv[2];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    NativeDirectBufferCache* buffer_cache = native_direct_get_buffer_cache(env, this_arg);
    WGPUBuffer buffer = buffer_cache ? buffer_cache->buffer : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!buffer) NAPI_THROW(env, "Invalid buffer");
    int64_t offset = 0;
    int64_t size = buffer_cache ? (int64_t)buffer_cache->size : (int64_t)get_double_prop(env, this_arg, "size");
    if (argc >= 1 && argv[0]) napi_get_value_int64(env, argv[0], &offset);
    if (argc >= 2 && argv[1]) napi_get_value_int64(env, argv[1], &size);
    void* data = pfn_wgpuBufferGetMappedRange(buffer, (size_t)offset, (size_t)size);
    if (!data) data = (void*)pfn_wgpuBufferGetConstMappedRange(buffer, (size_t)offset, (size_t)size);
    if (!data) NAPI_THROW(env, "bufferReadCopy getMappedRange returned NULL");
    void* copy = NULL;
    napi_value array_buffer;
    napi_create_arraybuffer(env, (size_t)size, &copy, &array_buffer);
    if (copy && size > 0) memcpy(copy, data, (size_t)size);
    return array_buffer;
}

/* Combined map+copy+unmap in a single N-API call.
   Eliminates: mapAsync promise overhead, external arraybuffer from getMappedRange,
   .slice() copy in JS, and separate unmap call. Returns a V8-owned ArrayBuffer. */
napi_value native_direct_buffer_map_read_copy_unmap(napi_env env, napi_callback_info info) {
    size_t argc = 3;
    napi_value argv[3];
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, argv, &this_arg, NULL);
    NativeDirectBufferCache* buffer_cache = native_direct_get_buffer_cache(env, this_arg);
    WGPUBuffer buffer = buffer_cache ? buffer_cache->buffer : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    if (!buffer) NAPI_THROW(env, "Invalid buffer");
    uint32_t mode = 0x0001; /* MAP_READ */
    int64_t offset = 0;
    int64_t size = buffer_cache ? (int64_t)buffer_cache->size : (int64_t)get_double_prop(env, this_arg, "size");
    if (argc >= 1 && argv[0]) napi_get_value_uint32(env, argv[0], &mode);
    if (argc >= 2 && argv[1]) napi_get_value_int64(env, argv[1], &offset);
    if (argc >= 3 && argv[2]) napi_get_value_int64(env, argv[2], &size);

    /* flush queue if pending */
    napi_value queue_obj = NULL;
    if (buffer_cache && buffer_cache->queue_ref) {
        napi_get_reference_value(env, buffer_cache->queue_ref, &queue_obj);
    } else {
        queue_obj = get_prop(env, this_arg, DOE_DIRECT_QUEUE);
    }
    if (queue_obj && native_direct_queue_has_pending(env, queue_obj)) {
        NativeDirectQueueCache* queue_cache = native_direct_get_queue_cache(env, queue_obj);
        WGPUQueue queue = queue_cache ? queue_cache->queue : native_direct_unwrap_external_prop(env, queue_obj, DOE_DIRECT_NATIVE);
        if (pfn_doeNativeQueueFlush) {
            pfn_doeNativeQueueFlush(queue);
        } else {
            WGPUInstance inst = buffer_cache ? buffer_cache->instance : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_INSTANCE);
            QueueWorkDoneResult qresult = {0};
            WGPUQueueWorkDoneCallbackInfo cb_info = {
                .nextInChain = NULL,
                .mode = WGPU_CALLBACK_MODE_WAIT_ANY_ONLY,
                .callback = queue_work_done_callback,
                .userdata1 = &qresult,
                .userdata2 = NULL,
            };
            WGPUFuture future = pfn_wgpuQueueOnSubmittedWorkDone(queue, cb_info);
            if (future.id == 0) NAPI_THROW(env, "queue work-done future unavailable");
            if (!process_events_until(inst, &qresult.done, current_timeout_ns())) {
                NAPI_THROW(env, "queue wait timed out in mapReadCopyUnmap");
            }
        }
        native_direct_queue_mark_done(env, queue_obj);
    }

    /* map */
    WGPUInstance inst = buffer_cache ? buffer_cache->instance : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_INSTANCE);
    BufferMapResult result = {0};
    WGPUBufferMapCallbackInfo cb_info = {
        .nextInChain = NULL,
        .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
        .callback = buffer_map_callback,
        .userdata1 = &result,
        .userdata2 = NULL,
    };
    if (pfn_doeNativeBufferMapAsync && pfn_doeNativeQueueFlush) {
        WGPUFuture future = pfn_doeNativeBufferMapAsync(buffer, (uint64_t)mode, (size_t)offset, (size_t)size, cb_info);
        if (future.id == 0 || !result.done) NAPI_THROW(env, "mapReadCopyUnmap: map failed");
    } else {
        WGPUFuture future = pfn_wgpuBufferMapAsync2(buffer, (uint64_t)mode, (size_t)offset, (size_t)size, cb_info);
        if (future.id == 0) NAPI_THROW(env, "mapReadCopyUnmap: map future unavailable");
        if (!process_events_until(inst, &result.done, current_timeout_ns())) {
            NAPI_THROW(env, "mapReadCopyUnmap: map timed out");
        }
    }
    if (result.status != WGPU_MAP_ASYNC_STATUS_SUCCESS) {
        NAPI_THROW(env, "mapReadCopyUnmap: map failed");
    }

    /* copy mapped data into a V8-owned ArrayBuffer */
    void* data = pfn_wgpuBufferGetMappedRange(buffer, (size_t)offset, (size_t)size);
    if (!data) data = (void*)pfn_wgpuBufferGetConstMappedRange(buffer, (size_t)offset, (size_t)size);
    if (!data) {
        pfn_wgpuBufferUnmap(buffer);
        NAPI_THROW(env, "mapReadCopyUnmap: getMappedRange returned NULL");
    }
    void* copy = NULL;
    napi_value array_buffer;
    napi_create_arraybuffer(env, (size_t)size, &copy, &array_buffer);
    if (copy && size > 0) memcpy(copy, data, (size_t)size);

    /* unmap and invalidate cache */
    native_direct_invalidate_buffer_mapped_range_cache(env, buffer_cache);
    pfn_wgpuBufferUnmap(buffer);

    return array_buffer;
}

napi_value native_direct_buffer_unmap(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);
    NativeDirectBufferCache* buffer_cache = native_direct_get_buffer_cache(env, this_arg);
    WGPUBuffer buffer = buffer_cache ? buffer_cache->buffer : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    native_direct_invalidate_buffer_mapped_range_cache(env, buffer_cache);
    if (buffer) pfn_wgpuBufferUnmap(buffer);
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

napi_value native_direct_buffer_destroy(napi_env env, napi_callback_info info) {
    size_t argc = 0;
    napi_value this_arg;
    napi_get_cb_info(env, info, &argc, NULL, &this_arg, NULL);
    NativeDirectBufferCache* buffer_cache = native_direct_get_buffer_cache(env, this_arg);
    WGPUBuffer buffer = buffer_cache ? buffer_cache->buffer : native_direct_unwrap_external_prop(env, this_arg, DOE_DIRECT_NATIVE);
    native_direct_invalidate_buffer_mapped_range_cache(env, buffer_cache);
    if (buffer) {
        pfn_wgpuBufferRelease(buffer);
        native_direct_set_external_prop(env, this_arg, DOE_DIRECT_NATIVE, NULL);
        if (buffer_cache) buffer_cache->buffer = NULL;
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}
