#include "doe_napi_internal.h"

/* ================================================================
 * Buffer
 * ================================================================ */

napi_value doe_create_buffer(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");

    WGPUBufferDescriptor desc;
    memset(&desc, 0, sizeof(desc));
    desc.usage = (uint64_t)get_int64_prop(env, _args[1], "usage");
    desc.size = (uint64_t)get_int64_prop(env, _args[1], "size");
    desc.mappedAtCreation = get_bool_prop(env, _args[1], "mappedAtCreation") ? 1 : 0;

    char* label_str = NULL;
    size_t label_len = 0;
    if (has_prop(env, _args[1], "label")) {
        label_str = dup_string_value(env, get_prop(env, _args[1], "label"), &label_len);
    }
    desc.label.data = label_str;
    desc.label.length = label_str ? label_len : 0;

    WGPUBuffer buf = pfn_wgpuDeviceCreateBuffer(device, &desc);
    free(label_str);
    if (!buf) NAPI_THROW(env, "createBuffer failed");
    return wrap_ptr(env, buf);
}

napi_value doe_buffer_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* buf = unwrap_ptr(env, _args[0]);
    if (buf) pfn_wgpuBufferRelease(buf);
    return NULL;
}

napi_value doe_buffer_unmap(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    WGPUBuffer buf = unwrap_ptr(env, _args[0]);
    if (buf) pfn_wgpuBufferUnmap(buf);
    return NULL;
}

/* bufferMapSync(instance, buffer, mode, offset, size) */
napi_value doe_buffer_map_sync(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    CHECK_LIB_LOADED(env);
    WGPUInstance inst = unwrap_ptr(env, _args[0]);
    WGPUBuffer buf = unwrap_ptr(env, _args[1]);
    if (!inst || !buf) NAPI_THROW(env, "bufferMapSync requires instance and buffer");
    uint32_t mode;
    napi_get_value_uint32(env, _args[2], &mode);
    int64_t offset_i, size_i;
    napi_get_value_int64(env, _args[3], &offset_i);
    napi_get_value_int64(env, _args[4], &size_i);

    BufferMapResult result = {0};
    WGPUBufferMapCallbackInfo cb_info = {
        .nextInChain = NULL,
        .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
        .callback = buffer_map_callback,
        .userdata1 = &result,
        .userdata2 = NULL,
    };

    if (pfn_doeNativeBufferMapAsync && pfn_doeNativeQueueFlush) {
        WGPUFuture future = pfn_doeNativeBufferMapAsync(
            buf,
            (uint64_t)mode,
            (size_t)offset_i,
            (size_t)size_i,
            cb_info
        );
        if (future.id == 0 || !result.done) NAPI_THROW(env, "doeNativeBufferMapAsync unavailable");
        if (result.status != WGPU_MAP_ASYNC_STATUS_SUCCESS)
            return throw_status_error(env, "DOE_BUFFER_MAP_ERROR", "doeNativeBufferMapAsync failed", result.status, result.message);
    } else {
        WGPUFuture future = pfn_wgpuBufferMapAsync2(buf, (uint64_t)mode,
            (size_t)offset_i, (size_t)size_i, cb_info);
        if (future.id == 0) NAPI_THROW(env, "bufferMapAsync future unavailable");
        if (!process_events_until(inst, &result.done, current_timeout_ns()))
            return throw_status_error(env, "DOE_BUFFER_MAP_TIMEOUT", "bufferMapAsync timed out", result.status, result.message);
        if (result.status != WGPU_MAP_ASYNC_STATUS_SUCCESS)
            return throw_status_error(env, "DOE_BUFFER_MAP_ERROR", "bufferMapAsync failed", result.status, result.message);
    }

    napi_value ok;
    napi_get_boolean(env, true, &ok);
    return ok;
}

/* bufferGetMappedRange(buffer, offset, size) → ArrayBuffer */
napi_value doe_buffer_get_mapped_range(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    CHECK_LIB_LOADED(env);
    WGPUBuffer buf = unwrap_ptr(env, _args[0]);
    int64_t offset_i, size_i;
    napi_get_value_int64(env, _args[1], &offset_i);
    napi_get_value_int64(env, _args[2], &size_i);

    /* pfn_wgpuBufferGetMappedRange resolves to Dawn for Doe-native buffers (~50us, returns NULL).
     * Go directly to pfn_wgpuBufferGetConstMappedRange (routes to doeNativeBufferGetConstMappedRange, fast). */
    void* data = (void*)pfn_wgpuBufferGetConstMappedRange(buf, (size_t)offset_i, (size_t)size_i);
    if (!data) NAPI_THROW(env, "getMappedRange returned NULL");

    napi_value ab;
    napi_create_external_arraybuffer(env, data, (size_t)size_i, NULL, NULL, &ab);
    return ab;
}

napi_value doe_buffer_read_copy(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    CHECK_LIB_LOADED(env);
    WGPUBuffer buf = unwrap_ptr(env, _args[0]);
    int64_t offset_i, size_i;
    napi_get_value_int64(env, _args[1], &offset_i);
    napi_get_value_int64(env, _args[2], &size_i);

    void* data = (void*)pfn_wgpuBufferGetConstMappedRange(buf, (size_t)offset_i, (size_t)size_i);
    if (!data) NAPI_THROW(env, "bufferReadCopy getMappedRange returned NULL");

    void* copy = NULL;
    napi_value ab;
    napi_create_arraybuffer(env, (size_t)size_i, &copy, &ab);
    if (copy && size_i > 0) {
        memcpy(copy, data, (size_t)size_i);
    }
    return ab;
}

/* bufferGetStagedRange(buf, offset, size) → V8-heap ArrayBuffer for WRITE-mode maps.
 * Allocates a V8-managed buffer so TypedArray ops (fill, set, etc.) use V8's fast SIMD
 * paths rather than the slow external-memory path. Call bufferFlushStagedRange on unmap. */
napi_value doe_buffer_get_staged_range(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    CHECK_LIB_LOADED(env);
    int64_t size_i = 0;
    napi_get_value_int64(env, _args[2], &size_i);
    void* copy = NULL;
    napi_value ab;
    napi_create_arraybuffer(env, (size_t)size_i, &copy, &ab);
    return ab;
}

/* bufferFlushStagedRange(buf, arraybuffer, offset, size) → memcpy staged V8 buffer → Metal. */
napi_value doe_buffer_flush_staged_range(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 4);
    CHECK_LIB_LOADED(env);
    WGPUBuffer buf = unwrap_ptr(env, _args[0]);
    void* staged = NULL;
    size_t staged_len = 0;
    napi_get_arraybuffer_info(env, _args[1], &staged, &staged_len);
    int64_t offset_i = 0, size_i = 0;
    napi_get_value_int64(env, _args[2], &offset_i);
    napi_get_value_int64(env, _args[3], &size_i);
    if (!staged || size_i <= 0) return NULL;
    /* For Doe-native buffers pfn_wgpuBufferGetMappedRange resolves to Dawn (returns NULL, ~50us).
     * pfn_wgpuBufferGetConstMappedRange routes to doeNativeBufferGetConstMappedRange (fast, writable). */
    void* mapped = (void*)pfn_wgpuBufferGetConstMappedRange(buf, (size_t)offset_i, (size_t)size_i);
    if (!mapped) NAPI_THROW(env, "bufferFlushStagedRange: mapped range unavailable");
    memcpy(mapped, staged, (size_t)size_i);
    return NULL;
}

napi_value doe_buffer_write_mapped_range(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    CHECK_LIB_LOADED(env);
    WGPUBuffer buf = unwrap_ptr(env, _args[0]);
    int64_t offset_i = 0;
    napi_get_value_int64(env, _args[1], &offset_i);

    void* data = NULL;
    size_t byte_length = 0;
    bool is_typed_array = false;
    napi_is_typedarray(env, _args[2], &is_typed_array);
    if (is_typed_array) {
        napi_typedarray_type ta_type;
        size_t ta_length = 0;
        void* ta_data = NULL;
        napi_value ta_arraybuffer;
        size_t ta_byte_offset = 0;
        napi_get_typedarray_info(env, _args[2], &ta_type, &ta_length, &ta_data, &ta_arraybuffer, &ta_byte_offset);
        data = ta_data;
        switch (ta_type) {
            case napi_uint16_array: case napi_int16_array: byte_length = ta_length * 2; break;
            case napi_uint32_array: case napi_int32_array: case napi_float32_array: byte_length = ta_length * 4; break;
            case napi_float64_array: case napi_bigint64_array: case napi_biguint64_array: byte_length = ta_length * 8; break;
            default: byte_length = ta_length; break;
        }
    } else {
        bool is_ab = false;
        napi_is_arraybuffer(env, _args[2], &is_ab);
        if (is_ab) {
            napi_get_arraybuffer_info(env, _args[2], &data, &byte_length);
        } else {
            bool is_buffer = false;
            napi_is_buffer(env, _args[2], &is_buffer);
            if (is_buffer) {
                napi_get_buffer_info(env, _args[2], &data, &byte_length);
            } else {
                NAPI_THROW(env, "bufferWriteMappedRange: data must be TypedArray, ArrayBuffer, or Buffer");
            }
        }
    }

    void* mapped = pfn_wgpuBufferGetMappedRange(buf, (size_t)offset_i, byte_length);
    if (!mapped) NAPI_THROW(env, "bufferWriteMappedRange: mapped range unavailable");
    memcpy(mapped, data, byte_length);
    return NULL;
}

napi_value doe_buffer_read_indirect_counts(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUBuffer buf = unwrap_ptr(env, _args[0]);
    int64_t offset_i = 0;
    napi_get_value_int64(env, _args[1], &offset_i);
    if (!buf) NAPI_THROW(env, "bufferReadIndirectCounts requires buffer");
    if (offset_i < 0) NAPI_THROW(env, "bufferReadIndirectCounts offset must be non-negative");

    const uint32_t* counts = (const uint32_t*)pfn_wgpuBufferGetConstMappedRange(buf, (size_t)offset_i, 3 * sizeof(uint32_t));
    if (!counts) NAPI_THROW(env, "bufferReadIndirectCounts: unable to read indirect data");

    napi_value result;
    napi_create_object(env, &result);
    napi_value x;
    napi_value y;
    napi_value z;
    napi_create_uint32(env, counts[0], &x);
    napi_create_uint32(env, counts[1], &y);
    napi_create_uint32(env, counts[2], &z);
    napi_set_named_property(env, result, "x", x);
    napi_set_named_property(env, result, "y", y);
    napi_set_named_property(env, result, "z", z);
    return result;
}

/* bufferGetMapState(buffer) → "unmapped" | "pending" | "mapped"
 * Doe's bufferMapAsync is synchronous, so state is binary. Returns "unmapped"
 * as a stub; wire to native wgpuBufferGetMapState when exposed by the runtime. */
napi_value doe_buffer_get_map_state(napi_env env, napi_callback_info info) {
    (void)info;
    napi_value result;
    napi_create_string_utf8(env, "unmapped", NAPI_AUTO_LENGTH, &result);
    return result;
}

/* bufferAssertMappedPrefixF32(buffer, expected, count) */
napi_value doe_buffer_assert_mapped_prefix_f32(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    CHECK_LIB_LOADED(env);
    WGPUBuffer buf = unwrap_ptr(env, _args[0]);
    double expected = 0.0;
    uint32_t count = 0;
    napi_get_value_double(env, _args[1], &expected);
    napi_get_value_uint32(env, _args[2], &count);
    if (!buf) NAPI_THROW(env, "bufferAssertMappedPrefixF32 requires buffer");
    const float* mapped = (const float*)pfn_wgpuBufferGetConstMappedRange(buf, 0, count * sizeof(float));
    if (!mapped) NAPI_THROW(env, "bufferAssertMappedPrefixF32: mapped range unavailable");
    for (uint32_t i = 0; i < count; i++) {
        if ((double)mapped[i] != expected) {
            char msg[128];
            snprintf(msg, sizeof(msg), "expected readback[%u] === %.0f, got %.9g", i, expected, (double)mapped[i]);
            NAPI_THROW(env, msg);
        }
    }
    napi_value ok;
    napi_get_boolean(env, true, &ok);
    return ok;
}
