/*
 * doe_napi_queue.c — Command encoder, compute pass, and queue N-API bindings.
 *
 * Covers: createCommandEncoder, command encoder copy/clear ops, compute pass
 * encode/dispatch, queue submit/write/flush paths, and batched fast paths.
 */
#include "doe_napi_internal.h"

/* ================================================================
 * Command Encoder
 * ================================================================ */

napi_value doe_create_command_encoder(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");
    WGPUCommandEncoderDescriptor desc = {
        .nextInChain = NULL, .label = { .data = NULL, .length = 0 },
    };
    WGPUCommandEncoder enc = pfn_wgpuDeviceCreateCommandEncoder(device, &desc);
    if (!enc) NAPI_THROW(env, "createCommandEncoder failed");
    return wrap_ptr(env, enc);
}

napi_value doe_command_encoder_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuCommandEncoderRelease(p);
    return NULL;
}

napi_value doe_command_encoder_copy_buffer_to_buffer(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 6);
    CHECK_LIB_LOADED(env);
    WGPUCommandEncoder enc = unwrap_ptr(env, _args[0]);
    WGPUBuffer src = unwrap_ptr(env, _args[1]);
    int64_t src_offset; napi_get_value_int64(env, _args[2], &src_offset);
    WGPUBuffer dst = unwrap_ptr(env, _args[3]);
    int64_t dst_offset; napi_get_value_int64(env, _args[4], &dst_offset);
    int64_t size; napi_get_value_int64(env, _args[5], &size);
    pfn_wgpuCommandEncoderCopyBufferToBuffer(enc, src, (uint64_t)src_offset,
        dst, (uint64_t)dst_offset, (uint64_t)size);
    return NULL;
}

napi_value doe_command_encoder_copy_buffer_to_texture(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 14);
    CHECK_LIB_LOADED(env);
    WGPUCommandEncoder enc = unwrap_ptr(env, _args[0]);
    WGPUBuffer src_buffer = unwrap_ptr(env, _args[1]);
    if (!enc || !src_buffer) NAPI_THROW(env, "commandEncoderCopyBufferToTexture requires encoder and buffer");
    WGPUTexelCopyBufferInfo src; memset(&src, 0, sizeof(src));
    src.buffer = src_buffer;
    int64_t src_offset = 0; napi_get_value_int64(env, _args[2], &src_offset);
    src.layout.offset = (uint64_t)src_offset;
    napi_get_value_uint32(env, _args[3], &src.layout.bytesPerRow);
    napi_get_value_uint32(env, _args[4], &src.layout.rowsPerImage);
    WGPUTexelCopyTextureInfo dst; memset(&dst, 0, sizeof(dst));
    dst.texture = unwrap_ptr(env, _args[5]);
    if (!dst.texture) NAPI_THROW(env, "commandEncoderCopyBufferToTexture requires destination texture");
    napi_get_value_uint32(env, _args[6], &dst.mipLevel);
    napi_get_value_uint32(env, _args[7], &dst.origin.x);
    napi_get_value_uint32(env, _args[8], &dst.origin.y);
    napi_get_value_uint32(env, _args[9], &dst.origin.z);
    napi_get_value_uint32(env, _args[10], &dst.aspect);
    WGPUExtent3D size;
    napi_get_value_uint32(env, _args[11], &size.width);
    napi_get_value_uint32(env, _args[12], &size.height);
    napi_get_value_uint32(env, _args[13], &size.depthOrArrayLayers);
    if (pfn_doeNativeCommandEncoderCopyBufferToTexture) {
        pfn_doeNativeCommandEncoderCopyBufferToTexture(enc, src.buffer,
            src.layout.offset, src.layout.bytesPerRow, src.layout.rowsPerImage,
            dst.texture, dst.mipLevel, size.width, size.height, size.depthOrArrayLayers);
    } else if (pfn_wgpuCommandEncoderCopyBufferToTexture) {
        pfn_wgpuCommandEncoderCopyBufferToTexture(enc, &src, &dst, &size);
    } else {
        NAPI_THROW(env, "commandEncoderCopyBufferToTexture: no implementation available in loaded library");
    }
    return NULL;
}

napi_value doe_command_encoder_copy_texture_to_buffer(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 14);
    CHECK_LIB_LOADED(env);
    WGPUCommandEncoder enc = unwrap_ptr(env, _args[0]);
    WGPUTexture src_texture = unwrap_ptr(env, _args[1]);
    if (!enc || !src_texture) NAPI_THROW(env, "commandEncoderCopyTextureToBuffer requires encoder and texture");
    WGPUTexelCopyTextureInfo src; memset(&src, 0, sizeof(src));
    src.texture = src_texture;
    napi_get_value_uint32(env, _args[2], &src.mipLevel);
    napi_get_value_uint32(env, _args[3], &src.origin.x);
    napi_get_value_uint32(env, _args[4], &src.origin.y);
    napi_get_value_uint32(env, _args[5], &src.origin.z);
    napi_get_value_uint32(env, _args[6], &src.aspect);
    WGPUTexelCopyBufferInfo dst; memset(&dst, 0, sizeof(dst));
    dst.buffer = unwrap_ptr(env, _args[7]);
    if (!dst.buffer) NAPI_THROW(env, "commandEncoderCopyTextureToBuffer requires destination buffer");
    int64_t dst_offset = 0; napi_get_value_int64(env, _args[8], &dst_offset);
    dst.layout.offset = (uint64_t)dst_offset;
    napi_get_value_uint32(env, _args[9], &dst.layout.bytesPerRow);
    napi_get_value_uint32(env, _args[10], &dst.layout.rowsPerImage);
    WGPUExtent3D size;
    napi_get_value_uint32(env, _args[11], &size.width);
    napi_get_value_uint32(env, _args[12], &size.height);
    napi_get_value_uint32(env, _args[13], &size.depthOrArrayLayers);
    if (pfn_doeNativeCommandEncoderCopyTextureToBuffer) {
        pfn_doeNativeCommandEncoderCopyTextureToBuffer(enc, src.texture, src.mipLevel,
            dst.buffer, dst.layout.offset, dst.layout.bytesPerRow, dst.layout.rowsPerImage,
            size.width, size.height, size.depthOrArrayLayers);
    } else {
        pfn_wgpuCommandEncoderCopyTextureToBuffer(enc, &src, &dst, &size);
    }
    return NULL;
}

napi_value doe_command_encoder_clear_buffer(napi_env env, napi_callback_info info) {
    size_t argc = 4;
    napi_value argv[4];
    napi_get_cb_info(env, info, &argc, argv, NULL, NULL);
    CHECK_LIB_LOADED(env);
    if (argc < 2) NAPI_THROW(env, "commandEncoderClearBuffer requires encoder and buffer");
    if (!pfn_doeNativeCommandEncoderClearBuffer)
        NAPI_THROW(env, "commandEncoderClearBuffer: no implementation available in loaded library");
    WGPUCommandEncoder enc = unwrap_ptr(env, argv[0]);
    WGPUBuffer buffer = unwrap_ptr(env, argv[1]);
    if (!enc || !buffer) NAPI_THROW(env, "commandEncoderClearBuffer requires encoder and buffer");
    uint64_t offset = 0;
    uint64_t size = WGPU_WHOLE_SIZE;
    if (argc >= 3) {
        napi_valuetype vt; napi_typeof(env, argv[2], &vt);
        if (vt == napi_number || vt == napi_bigint) {
            int64_t v = 0; napi_get_value_int64(env, argv[2], &v);
            if (v > 0) offset = (uint64_t)v;
        }
    }
    if (argc >= 4) {
        napi_valuetype vt; napi_typeof(env, argv[3], &vt);
        if (vt == napi_number || vt == napi_bigint) {
            int64_t v = 0; napi_get_value_int64(env, argv[3], &v);
            if (v > 0) size = (uint64_t)v;
            else if (v == 0) size = 0;
        }
    }
    pfn_doeNativeCommandEncoderClearBuffer(enc, buffer, offset, size);
    return NULL;
}

napi_value doe_command_encoder_copy_texture_to_texture(napi_env env, napi_callback_info info) {
    size_t argc = 15;
    napi_value argv[15];
    napi_get_cb_info(env, info, &argc, argv, NULL, NULL);
    CHECK_LIB_LOADED(env);
    if (argc != 14 && argc != 15)
        NAPI_THROW(env, "commandEncoderCopyTextureToTexture requires 14 or 15 arguments");
    if (!pfn_doeNativeCommandEncoderCopyTextureToTexture && !pfn_wgpuCommandEncoderCopyTextureToTexture)
        NAPI_THROW(env, "commandEncoderCopyTextureToTexture: no implementation available in loaded library");
    const size_t di = argc == 15 ? 7 : 6;
    WGPUCommandEncoder enc    = unwrap_ptr(env, argv[0]);
    WGPUTexture src_texture   = unwrap_ptr(env, argv[1]);
    WGPUTexture dst_texture   = unwrap_ptr(env, argv[di]);
    if (!enc || !src_texture || !dst_texture)
        NAPI_THROW(env, "commandEncoderCopyTextureToTexture requires encoder and textures");
    uint32_t src_mip = 0, src_x = 0, src_y = 0, src_z = 0;
    uint32_t dst_mip = 0, dst_x = 0, dst_y = 0, dst_z = 0;
    uint32_t width = 1, height = 1, depth_or_layers = 1;
    napi_get_value_uint32(env, argv[2], &src_mip);
    napi_get_value_uint32(env, argv[3], &src_x);
    napi_get_value_uint32(env, argv[4], &src_y);
    napi_get_value_uint32(env, argv[5], &src_z);
    napi_get_value_uint32(env, argv[di + 1], &dst_mip);
    napi_get_value_uint32(env, argv[di + 2], &dst_x);
    napi_get_value_uint32(env, argv[di + 3], &dst_y);
    napi_get_value_uint32(env, argv[di + 4], &dst_z);
    napi_get_value_uint32(env, argv[di + 5], &width);
    napi_get_value_uint32(env, argv[di + 6], &height);
    napi_get_value_uint32(env, argv[di + 7], &depth_or_layers);
    if (pfn_doeNativeCommandEncoderCopyTextureToTexture) {
        pfn_doeNativeCommandEncoderCopyTextureToTexture(enc,
            src_texture, src_mip, 0, src_x, src_y, src_z,
            dst_texture, dst_mip, 0, dst_x, dst_y, dst_z,
            width, height, depth_or_layers);
    } else {
        WGPUTexelCopyTextureInfo s, d; WGPUExtent3D sz;
        memset(&s, 0, sizeof(s)); memset(&d, 0, sizeof(d));
        s.texture = src_texture; s.mipLevel = src_mip;
        s.origin.x = src_x; s.origin.y = src_y; s.origin.z = src_z;
        d.texture = dst_texture; d.mipLevel = dst_mip;
        d.origin.x = dst_x; d.origin.y = dst_y; d.origin.z = dst_z;
        sz.width = width; sz.height = height; sz.depthOrArrayLayers = depth_or_layers;
        pfn_wgpuCommandEncoderCopyTextureToTexture(enc, &s, &d, &sz);
    }
    return NULL;
}

/* ================================================================
 * Compute Pass
 * ================================================================ */

napi_value doe_begin_compute_pass(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    WGPUCommandEncoder enc = unwrap_ptr(env, _args[0]);
    if (!enc) NAPI_THROW(env, "Invalid encoder");
    WGPUComputePassDescriptor desc = {
        .nextInChain = NULL, .label = { .data = NULL, .length = 0 }, .timestampWrites = NULL,
    };
    WGPUComputePassEncoder pass = pfn_wgpuCommandEncoderBeginComputePass(enc, &desc);
    if (!pass) NAPI_THROW(env, "beginComputePass failed");
    return wrap_ptr(env, pass);
}

napi_value doe_compute_pass_set_pipeline(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    pfn_wgpuComputePassEncoderSetPipeline(unwrap_ptr(env, _args[0]), unwrap_ptr(env, _args[1]));
    return NULL;
}

napi_value doe_compute_pass_set_bind_group(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    WGPUComputePassEncoder pass = unwrap_ptr(env, _args[0]);
    uint32_t index; napi_get_value_uint32(env, _args[1], &index);
    WGPUBindGroup group = unwrap_ptr(env, _args[2]);
    pfn_wgpuComputePassEncoderSetBindGroup(pass, index, group, 0, NULL);
    return NULL;
}

napi_value doe_compute_pass_dispatch(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 4);
    WGPUComputePassEncoder pass = unwrap_ptr(env, _args[0]);
    uint32_t x, y, z;
    napi_get_value_uint32(env, _args[1], &x);
    napi_get_value_uint32(env, _args[2], &y);
    napi_get_value_uint32(env, _args[3], &z);
    pfn_wgpuComputePassEncoderDispatchWorkgroups(pass, x, y, z);
    return NULL;
}

/* computePassDispatchWorkgroupsIndirect(pass, buffer, offset) */
napi_value doe_compute_pass_dispatch_indirect(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    WGPUComputePassEncoder pass = unwrap_ptr(env, _args[0]);
    WGPUBuffer buffer = unwrap_ptr(env, _args[1]);
    int64_t offset; napi_get_value_int64(env, _args[2], &offset);
    if (pfn_doeNativeComputePassDispatchIndirect)
        pfn_doeNativeComputePassDispatchIndirect(pass, buffer, (uint64_t)offset);
    else
        pfn_wgpuComputePassEncoderDispatchWorkgroupsIndirect(pass, buffer, (uint64_t)offset);
    return NULL;
}

napi_value doe_compute_pass_end(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    pfn_wgpuComputePassEncoderEnd(unwrap_ptr(env, _args[0]));
    return NULL;
}

napi_value doe_compute_pass_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuComputePassEncoderRelease(p);
    return NULL;
}

napi_value doe_command_encoder_finish(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    WGPUCommandEncoder enc = unwrap_ptr(env, _args[0]);
    if (!enc) NAPI_THROW(env, "Invalid encoder");
    WGPUCommandBufferDescriptor desc = {
        .nextInChain = NULL, .label = { .data = NULL, .length = 0 },
    };
    WGPUCommandBuffer cmd = pfn_wgpuCommandEncoderFinish(enc, &desc);
    if (!cmd) NAPI_THROW(env, "commandEncoderFinish failed");
    return wrap_ptr(env, cmd);
}

napi_value doe_command_buffer_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuCommandBufferRelease(p);
    return NULL;
}

/* ================================================================
 * Queue
 * ================================================================ */

napi_value doe_queue_submit(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUQueue queue = unwrap_ptr(env, _args[0]);
    if (!queue) NAPI_THROW(env, "Invalid queue");
    uint32_t cmd_count = 0;
    napi_get_array_length(env, _args[1], &cmd_count);
    WGPUCommandBuffer* cmds = (WGPUCommandBuffer*)calloc(cmd_count, sizeof(WGPUCommandBuffer));
    for (uint32_t i = 0; i < cmd_count; i++) {
        napi_value elem;
        napi_get_element(env, _args[1], i, &elem);
        cmds[i] = unwrap_ptr(env, elem);
    }
    pfn_wgpuQueueSubmit(queue, cmd_count, cmds);
    free(cmds);
    return NULL;
}

/* queueWriteBuffer(queue, buffer, offset, typedArray) */
napi_value doe_queue_write_buffer(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 4);
    CHECK_LIB_LOADED(env);
    WGPUQueue queue = unwrap_ptr(env, _args[0]);
    WGPUBuffer buf = unwrap_ptr(env, _args[1]);
    if (!queue || !buf) NAPI_THROW(env, "queueWriteBuffer requires queue and buffer");
    int64_t offset; napi_get_value_int64(env, _args[2], &offset);
    void* data = NULL;
    size_t byte_length = 0;
    bool is_typedarray = false;
    napi_is_typedarray(env, _args[3], &is_typedarray);
    if (is_typedarray) {
        napi_typedarray_type ta_type; size_t ta_length; napi_value ab; size_t byte_offset;
        napi_get_typedarray_info(env, _args[3], &ta_type, &ta_length, &data, &ab, &byte_offset);
        size_t elem_size = 1;
        switch (ta_type) {
            case napi_int8_array: case napi_uint8_array: case napi_uint8_clamped_array: elem_size = 1; break;
            case napi_int16_array: case napi_uint16_array: elem_size = 2; break;
            case napi_int32_array: case napi_uint32_array: case napi_float32_array: elem_size = 4; break;
            case napi_float64_array: case napi_bigint64_array: case napi_biguint64_array: elem_size = 8; break;
            default: elem_size = 1; break;
        }
        byte_length = ta_length * elem_size;
    } else {
        bool is_ab = false;
        napi_is_arraybuffer(env, _args[3], &is_ab);
        if (is_ab) {
            napi_get_arraybuffer_info(env, _args[3], &data, &byte_length);
        } else {
            bool is_buffer = false;
            napi_is_buffer(env, _args[3], &is_buffer);
            if (is_buffer) napi_get_buffer_info(env, _args[3], &data, &byte_length);
            else NAPI_THROW(env, "queueWriteBuffer: data must be TypedArray, ArrayBuffer, or Buffer");
        }
    }
    pfn_wgpuQueueWriteBuffer(queue, buf, (uint64_t)offset, data, byte_length);
    return NULL;
}

/* queueFlush(instance, queue) — wait for all pending GPU work to complete. */
napi_value doe_queue_flush(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUInstance inst = unwrap_ptr(env, _args[0]);
    WGPUQueue queue = unwrap_ptr(env, _args[1]);
    if (!queue) NAPI_THROW(env, "queueFlush requires queue");
    if (pfn_doeNativeQueueFlush) { pfn_doeNativeQueueFlush(queue); return NULL; }
    if (!inst) {
        napi_throw_error(env, "DOE_QUEUE_UNAVAILABLE", "queueFlush requires instance when doeNativeQueueFlush is unavailable");
        return NULL;
    }
    QueueWorkDoneResult result = {0};
    WGPUQueueWorkDoneCallbackInfo cb_info = {
        .nextInChain = NULL, .mode = WGPU_CALLBACK_MODE_WAIT_ANY_ONLY,
        .callback = queue_work_done_callback, .userdata1 = &result, .userdata2 = NULL,
    };
    WGPUFuture future = pfn_wgpuQueueOnSubmittedWorkDone(queue, cb_info);
    if (future.id == 0) NAPI_THROW(env, "queueFlush: queue work-done future unavailable");
    uint64_t start_ns = monotonic_now_ns();
    while (!result.done) {
        WGPUFutureWaitInfo wait_info = { .future = future, .completed = 0 };
        uint32_t wait_status = pfn_wgpuInstanceWaitAny(inst, 1, &wait_info, 0);
        if (wait_status == WGPU_WAIT_STATUS_SUCCESS) {
            if (!result.done) pfn_wgpuInstanceProcessEvents(inst);
        } else if (wait_status == WGPU_WAIT_STATUS_TIMED_OUT) {
            pfn_wgpuInstanceProcessEvents(inst);
            if (monotonic_now_ns() - start_ns >= current_timeout_ns()) {
                napi_throw_error(env, "DOE_QUEUE_TIMEOUT", "queueFlush: queue wait timed out");
                return NULL;
            }
            wait_slice();
        } else if (wait_status == WGPU_WAIT_STATUS_ERROR) {
            napi_throw_error(env, "DOE_QUEUE_UNAVAILABLE", "queueFlush: wgpuInstanceWaitAny failed");
            return NULL;
        } else {
            NAPI_THROW(env, "queueFlush: unsupported wait status");
        }
    }
    if (result.status != WGPU_QUEUE_WORK_DONE_STATUS_SUCCESS)
        return throw_status_error(env, "DOE_QUEUE_FLUSH_ERROR", "queueFlush: queue work did not complete", result.status, result.message);
    return NULL;
}

/* submitBatched(device, queue, commandsArray)
 * Fast path: single dispatch or dispatch+copy → doeNativeComputeDispatchFlush. */
napi_value doe_queue_submit_batched(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    WGPUQueue queue = unwrap_ptr(env, _args[1]);
    napi_value commands = _args[2];
    if (!device || !queue) NAPI_THROW(env, "submitBatched requires device and queue");
    uint32_t cmd_count = 0;
    napi_get_array_length(env, commands, &cmd_count);
    if (cmd_count == 0) return NULL;

    if (pfn_doeNativeComputeDispatchFlush && (cmd_count == 1 || cmd_count == 2)) {
        napi_value cmd0; napi_get_element(env, commands, 0, &cmd0);
        uint32_t t0 = get_uint32_prop(env, cmd0, "t");
        uint32_t t1 = UINT32_MAX;
        napi_value cmd1 = NULL;
        if (cmd_count == 2) { napi_get_element(env, commands, 1, &cmd1); t1 = get_uint32_prop(env, cmd1, "t"); }
        if (t0 == 0 && (cmd_count == 1 || t1 == 1)) {
            void* pipeline = unwrap_ptr(env, get_prop(env, cmd0, "p"));
            napi_value bgs = get_prop(env, cmd0, "bg");
            uint32_t bg_count = 0; napi_get_array_length(env, bgs, &bg_count);
            if (bg_count > BATCH_MAX_BIND_GROUPS) bg_count = BATCH_MAX_BIND_GROUPS;
            void* bg_ptrs[BATCH_MAX_BIND_GROUPS] = {NULL};
            for (uint32_t j = 0; j < bg_count; j++) {
                napi_value bg_val; napi_get_element(env, bgs, j, &bg_val);
                bg_ptrs[j] = unwrap_ptr(env, bg_val);
            }
            uint32_t dx = get_uint32_prop(env, cmd0, "x");
            uint32_t dy = get_uint32_prop(env, cmd0, "y");
            uint32_t dz = get_uint32_prop(env, cmd0, "z");
            void* copy_src = NULL; uint64_t copy_src_off = 0;
            void* copy_dst = NULL; uint64_t copy_dst_off = 0;
            uint64_t copy_size = 0;
            if (cmd_count == 2) {
                copy_src     = unwrap_ptr(env, get_prop(env, cmd1, "s"));
                copy_dst     = unwrap_ptr(env, get_prop(env, cmd1, "d"));
                copy_src_off = (uint64_t)get_int64_prop(env, cmd1, "so");
                copy_dst_off = (uint64_t)get_int64_prop(env, cmd1, "do");
                copy_size    = (uint64_t)get_int64_prop(env, cmd1, "sz");
            }
            pfn_doeNativeComputeDispatchFlush(queue, pipeline, (void**)bg_ptrs, bg_count,
                dx, dy, dz, copy_src, copy_src_off, copy_dst, copy_dst_off, copy_size);
            return NULL;
        }
    }

    int flush_after_submit = 0;
    if (cmd_count == 2) {
        napi_value cmd0, cmd1;
        napi_get_element(env, commands, 0, &cmd0);
        napi_get_element(env, commands, 1, &cmd1);
        if (get_uint32_prop(env, cmd0, "t") == 0 && get_uint32_prop(env, cmd1, "t") == 1)
            flush_after_submit = 1;
    }
    WGPUCommandEncoder encoder = pfn_wgpuDeviceCreateCommandEncoder(device, NULL);
    if (!encoder) NAPI_THROW(env, "submitBatched: createCommandEncoder failed");
    for (uint32_t i = 0; i < cmd_count; i++) {
        napi_value cmd; napi_get_element(env, commands, i, &cmd);
        uint32_t type = get_uint32_prop(env, cmd, "t");
        if (type == 0) {
            WGPUComputePassEncoder pass = pfn_wgpuCommandEncoderBeginComputePass(encoder, NULL);
            void* pipeline = unwrap_ptr(env, get_prop(env, cmd, "p"));
            pfn_wgpuComputePassEncoderSetPipeline(pass, pipeline);
            napi_value bgs = get_prop(env, cmd, "bg");
            uint32_t bg_count = 0; napi_get_array_length(env, bgs, &bg_count);
            if (bg_count > BATCH_MAX_BIND_GROUPS) bg_count = BATCH_MAX_BIND_GROUPS;
            for (uint32_t j = 0; j < bg_count; j++) {
                napi_value bg_val; napi_get_element(env, bgs, j, &bg_val);
                void* bg = unwrap_ptr(env, bg_val);
                if (bg) pfn_wgpuComputePassEncoderSetBindGroup(pass, j, bg, 0, NULL);
            }
            pfn_wgpuComputePassEncoderDispatchWorkgroups(pass,
                get_uint32_prop(env, cmd, "x"), get_uint32_prop(env, cmd, "y"), get_uint32_prop(env, cmd, "z"));
            pfn_wgpuComputePassEncoderEnd(pass);
            pfn_wgpuComputePassEncoderRelease(pass);
        } else if (type == 1) {
            void* src = unwrap_ptr(env, get_prop(env, cmd, "s"));
            void* dst = unwrap_ptr(env, get_prop(env, cmd, "d"));
            pfn_wgpuCommandEncoderCopyBufferToBuffer(encoder, src,
                (uint64_t)get_int64_prop(env, cmd, "so"), dst,
                (uint64_t)get_int64_prop(env, cmd, "do"),
                (uint64_t)get_int64_prop(env, cmd, "sz"));
        }
    }
    WGPUCommandBuffer cmd_buf = pfn_wgpuCommandEncoderFinish(encoder, NULL);
    pfn_wgpuQueueSubmit(queue, 1, &cmd_buf);
    if (flush_after_submit && pfn_doeNativeQueueFlush) pfn_doeNativeQueueFlush(queue);
    pfn_wgpuCommandBufferRelease(cmd_buf);
    pfn_wgpuCommandEncoderRelease(encoder);
    return NULL;
}

/* submitComputeDispatchCopy(device, queue, pipeline, bindGroups, x, y, z,
 *                           src, srcOff, dst, dstOff, size) */
napi_value doe_queue_submit_compute_dispatch_copy(napi_env env, napi_callback_info info) {
    size_t argc = 12;
    napi_value args[12];
    napi_status status = napi_get_cb_info(env, info, &argc, args, NULL, NULL);
    if (status != napi_ok || argc != 12) NAPI_THROW(env, "submitComputeDispatchCopy requires 12 arguments");
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, args[0]);
    WGPUQueue queue   = unwrap_ptr(env, args[1]);
    void* pipeline    = unwrap_ptr(env, args[2]);
    napi_value bgs    = args[3];
    uint32_t dx = 0, dy = 0, dz = 0;
    int64_t copy_src_off_i = 0, copy_dst_off_i = 0, copy_size_i = 0;
    napi_get_value_uint32(env, args[4], &dx);
    napi_get_value_uint32(env, args[5], &dy);
    napi_get_value_uint32(env, args[6], &dz);
    void* copy_src = unwrap_ptr(env, args[7]);
    napi_get_value_int64(env, args[8], &copy_src_off_i);
    void* copy_dst = unwrap_ptr(env, args[9]);
    napi_get_value_int64(env, args[10], &copy_dst_off_i);
    napi_get_value_int64(env, args[11], &copy_size_i);
    if (!device || !queue || !pipeline) NAPI_THROW(env, "submitComputeDispatchCopy requires device, queue, and pipeline");
    uint32_t bg_count = 0; napi_get_array_length(env, bgs, &bg_count);
    if (bg_count > BATCH_MAX_BIND_GROUPS) bg_count = BATCH_MAX_BIND_GROUPS;
    void* bg_ptrs[BATCH_MAX_BIND_GROUPS] = {NULL};
    for (uint32_t j = 0; j < bg_count; j++) {
        napi_value bg_val; napi_get_element(env, bgs, j, &bg_val);
        bg_ptrs[j] = unwrap_ptr(env, bg_val);
    }
    if (pfn_doeNativeComputeDispatchFlush) {
        pfn_doeNativeComputeDispatchFlush(queue, pipeline, (void**)bg_ptrs, bg_count, dx, dy, dz,
            copy_src, (uint64_t)copy_src_off_i, copy_dst, (uint64_t)copy_dst_off_i, (uint64_t)copy_size_i);
        return NULL;
    }
    WGPUCommandEncoder encoder = pfn_wgpuDeviceCreateCommandEncoder(device, NULL);
    if (!encoder) NAPI_THROW(env, "submitComputeDispatchCopy: createCommandEncoder failed");
    WGPUComputePassEncoder pass = pfn_wgpuCommandEncoderBeginComputePass(encoder, NULL);
    if (!pass) { pfn_wgpuCommandEncoderRelease(encoder); NAPI_THROW(env, "submitComputeDispatchCopy: beginComputePass failed"); }
    pfn_wgpuComputePassEncoderSetPipeline(pass, pipeline);
    for (uint32_t j = 0; j < bg_count; j++)
        if (bg_ptrs[j]) pfn_wgpuComputePassEncoderSetBindGroup(pass, j, bg_ptrs[j], 0, NULL);
    pfn_wgpuComputePassEncoderDispatchWorkgroups(pass, dx, dy, dz);
    pfn_wgpuComputePassEncoderEnd(pass);
    pfn_wgpuComputePassEncoderRelease(pass);
    pfn_wgpuCommandEncoderCopyBufferToBuffer(encoder,
        copy_src, (uint64_t)copy_src_off_i, copy_dst, (uint64_t)copy_dst_off_i, (uint64_t)copy_size_i);
    WGPUCommandBuffer cmd_buf = pfn_wgpuCommandEncoderFinish(encoder, NULL);
    if (!cmd_buf) { pfn_wgpuCommandEncoderRelease(encoder); NAPI_THROW(env, "submitComputeDispatchCopy: finish failed"); }
    pfn_wgpuQueueSubmit(queue, 1, &cmd_buf);
    pfn_wgpuCommandBufferRelease(cmd_buf);
    pfn_wgpuCommandEncoderRelease(encoder);
    return NULL;
}

/* flushAndMapSync(instance, queue, buffer, mode, offset, size) */
napi_value doe_compute_dispatch_flush_and_map_sync(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 6);
    CHECK_LIB_LOADED(env);
    WGPUInstance inst = unwrap_ptr(env, _args[0]);
    WGPUQueue queue   = unwrap_ptr(env, _args[1]);
    WGPUBuffer buf    = unwrap_ptr(env, _args[2]);
    uint32_t mode; napi_get_value_uint32(env, _args[3], &mode);
    int64_t offset_i, size_i;
    napi_get_value_int64(env, _args[4], &offset_i);
    napi_get_value_int64(env, _args[5], &size_i);
    if (!queue || !buf) NAPI_THROW(env, "flushAndMapSync requires queue and buffer");
    if (pfn_doeNativeQueueFlush) pfn_doeNativeQueueFlush(queue);
    BufferMapResult result = {0};
    WGPUBufferMapCallbackInfo cb_info = {
        .nextInChain = NULL, .mode = WGPU_CALLBACK_MODE_ALLOW_PROCESS_EVENTS,
        .callback = buffer_map_callback, .userdata1 = &result, .userdata2 = NULL,
    };
    if (pfn_doeNativeBufferMapAsync && pfn_doeNativeQueueFlush) {
        WGPUFuture future = pfn_doeNativeBufferMapAsync(buf, (uint64_t)mode, (size_t)offset_i, (size_t)size_i, cb_info);
        if (future.id == 0 || !result.done) NAPI_THROW(env, "flushAndMapSync: doeNativeBufferMapAsync unavailable");
        if (result.status != WGPU_MAP_ASYNC_STATUS_SUCCESS)
            return throw_status_error(env, "DOE_BUFFER_MAP_ERROR", "flushAndMapSync: doeNativeBufferMapAsync failed", result.status, result.message);
    } else {
        WGPUFuture future = pfn_wgpuBufferMapAsync2(buf, (uint64_t)mode, (size_t)offset_i, (size_t)size_i, cb_info);
        if (future.id == 0) NAPI_THROW(env, "flushAndMapSync: bufferMapAsync future unavailable");
        if (!process_events_until(inst, &result.done, current_timeout_ns()))
            return throw_status_error(env, "DOE_BUFFER_MAP_TIMEOUT", "flushAndMapSync: bufferMapAsync timed out", result.status, result.message);
        if (result.status != WGPU_MAP_ASYNC_STATUS_SUCCESS)
            return throw_status_error(env, "DOE_BUFFER_MAP_ERROR", "flushAndMapSync: bufferMapAsync failed", result.status, result.message);
    }
    napi_value ok; napi_get_boolean(env, true, &ok);
    return ok;
}

napi_value doe_queue_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuQueueRelease(p);
    return NULL;
}

/* queueWriteTexture(queueNative, textureNative, dataBuffer, dataOffset,
 *                  bytesPerRow, rowsPerImage, mipLevel,
 *                  originX, originY, originZ, width, height, depthOrArrayLayers) */
napi_value doe_queue_write_texture(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 13);
    CHECK_LIB_LOADED(env);
    void* queue   = unwrap_ptr(env, _args[0]);
    void* texture = unwrap_ptr(env, _args[1]);
    if (!queue || !texture) NAPI_THROW(env, "queueWriteTexture: invalid queue or texture");
    void* data = NULL; size_t data_len = 0;
    bool is_typedarray = false;
    napi_is_typedarray(env, _args[2], &is_typedarray);
    if (is_typedarray) {
        napi_typedarray_type ta_type; size_t ta_length; napi_value ab; size_t byte_offset;
        napi_get_typedarray_info(env, _args[2], &ta_type, &ta_length, &data, &ab, &byte_offset);
        size_t elem_size = 1;
        switch (ta_type) {
            case napi_int16_array: case napi_uint16_array: elem_size = 2; break;
            case napi_int32_array: case napi_uint32_array: case napi_float32_array: elem_size = 4; break;
            case napi_float64_array: case napi_bigint64_array: case napi_biguint64_array: elem_size = 8; break;
            default: elem_size = 1; break;
        }
        data_len = ta_length * elem_size;
    } else {
        bool is_ab = false; napi_is_arraybuffer(env, _args[2], &is_ab);
        if (is_ab) napi_get_arraybuffer_info(env, _args[2], &data, &data_len);
        else NAPI_THROW(env, "queueWriteTexture: data must be TypedArray or ArrayBuffer");
    }
    uint32_t data_offset = 0; napi_get_value_uint32(env, _args[3], &data_offset);
    uint32_t bytes_per_row = 0; napi_get_value_uint32(env, _args[4], &bytes_per_row);
    uint32_t rows_per_image = 0; napi_get_value_uint32(env, _args[5], &rows_per_image);
    uint32_t mip_level = 0; napi_get_value_uint32(env, _args[6], &mip_level);
    uint32_t origin_x = 0; napi_get_value_uint32(env, _args[7], &origin_x);
    uint32_t origin_y = 0; napi_get_value_uint32(env, _args[8], &origin_y);
    uint32_t origin_z = 0; napi_get_value_uint32(env, _args[9], &origin_z);
    uint32_t width = 1; napi_get_value_uint32(env, _args[10], &width);
    uint32_t height = 1; napi_get_value_uint32(env, _args[11], &height);
    uint32_t depth_or_layers = 1; napi_get_value_uint32(env, _args[12], &depth_or_layers);
    if (data_offset > 0 && data_offset < (uint32_t)data_len) {
        data = ((uint8_t*)data) + data_offset;
        data_len -= data_offset;
    }
    if (pfn_doeNativeQueueWriteTexture) {
        pfn_doeNativeQueueWriteTexture(queue, texture, data, data_len,
            bytes_per_row, rows_per_image,
            origin_x, origin_y, origin_z, mip_level, 0,
            width, height, depth_or_layers);
    }
    napi_value undefined_value;
    napi_get_undefined(env, &undefined_value);
    return undefined_value;
}

/* queueOnSubmittedWorkDone — immediate async no-op for synchronous Doe runtime. */
napi_value doe_queue_on_submitted_work_done(napi_env env, napi_callback_info info) {
    (void)info;
    return native_direct_resolved_promise(env, NULL);
}
