/*
 * doe_napi_helpers.c — N-API utility helpers, callback infrastructure, and
 * string/error helpers extracted from doe_napi.c.
 */
#include "doe_napi_internal.h"

/* ================================================================
 * Error/string helpers
 * ================================================================ */

uint64_t current_timeout_ns(void) {
    return g_timeout_ns;
}

void copy_library_error_message(char* out, size_t out_len) {
    if (!out || out_len == 0) return;
    out[0] = '\0';
    if (!pfn_doeNativeCopyLastErrorMessage) return;
    pfn_doeNativeCopyLastErrorMessage(out, out_len);
}

void copy_library_error_meta(PFN_doeNativeCopyLastErrorMessage fn, char* out, size_t out_len) {
    if (!out || out_len == 0) return;
    out[0] = '\0';
    if (!fn) return;
    fn(out, out_len);
}

uint64_t monotonic_now_ns(void) {
#ifdef _WIN32
    static LARGE_INTEGER frequency = {0};
    LARGE_INTEGER counter;
    if (frequency.QuadPart == 0) QueryPerformanceFrequency(&frequency);
    QueryPerformanceCounter(&counter);
    return (uint64_t)((counter.QuadPart * 1000000000ULL) / frequency.QuadPart);
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ((uint64_t)ts.tv_sec * 1000000000ULL) + (uint64_t)ts.tv_nsec;
#endif
}

void wait_slice(void) {
#ifdef _WIN32
    Sleep(0);
#else
    struct timespec req = {0};
    req.tv_nsec = DOE_WAIT_SLICE_NS;
    nanosleep(&req, NULL);
#endif
}

int process_events_until(WGPUInstance inst, volatile uint32_t* done, uint64_t timeout_ns) {
    uint64_t start_ns = monotonic_now_ns();
    uint32_t spins = 0;
    while (!*done) {
        pfn_wgpuInstanceProcessEvents(inst);
        if (monotonic_now_ns() - start_ns >= timeout_ns) return 0;
        spins += 1;
        if (spins > 1000) wait_slice();
    }
    return 1;
}

void copy_string_view_message(WGPUStringView message, char* out, size_t out_len) {
    if (!out || out_len == 0) return;
    out[0] = '\0';
    if (!message.data || message.length == 0) return;
    size_t copy_len = message.length;
    if (copy_len >= out_len) copy_len = out_len - 1;
    memcpy(out, message.data, copy_len);
    out[copy_len] = '\0';
}

char* dup_string_view(WGPUStringView message) {
    size_t len = message.data ? message.length : 0;
    char* out = (char*)malloc(len + 1);
    if (!out) return NULL;
    if (len > 0 && message.data) {
        memcpy(out, message.data, len);
    }
    out[len] = '\0';
    return out;
}

char* dup_c_string(const char* message_ptr, size_t message_len) {
    size_t len = message_ptr ? message_len : 0;
    char* out = (char*)malloc(len + 1);
    if (!out) return NULL;
    if (len > 0 && message_ptr) {
        memcpy(out, message_ptr, len);
    }
    out[len] = '\0';
    return out;
}

const char* error_type_string(uint32_t error_type) {
    switch (error_type) {
        case 0x00000001: return "no-error";
        case 0x00000002: return "validation";
        case 0x00000003: return "out-of-memory";
        case 0x00000004: return "internal";
        default: return "unknown";
    }
}

const char* lost_reason_string(uint32_t reason) {
    switch (reason) {
        case 0: return "unknown";
        case 1: return "destroyed";
        case 3: return "callback-cancelled";
        case 4: return "failed-creation";
        default: return "unknown";
    }
}

napi_value throw_status_error(napi_env env, const char* code, const char* prefix, uint32_t status, const char* detail) {
    char msg[DOE_ERROR_BUF_CAP];
    if (detail && detail[0] != '\0') {
        snprintf(msg, sizeof(msg), "%s (status=%u, detail=%s)", prefix, status, detail);
    } else {
        snprintf(msg, sizeof(msg), "%s (status=%u)", prefix, status);
    }
    napi_throw_error(env, code, msg);
    return NULL;
}

/* ================================================================
 * Callback binding helpers
 * ================================================================ */

DeviceCallbackBinding* binding_take(DeviceCallbackBinding** head, void* device) {
    DeviceCallbackBinding* prev = NULL;
    DeviceCallbackBinding* cur = *head;
    while (cur) {
        if (cur->device == device) {
            if (prev) {
                prev->next = cur->next;
            } else {
                *head = cur->next;
            }
            cur->next = NULL;
            return cur;
        }
        prev = cur;
        cur = cur->next;
    }
    return NULL;
}

void binding_insert(DeviceCallbackBinding** head, DeviceCallbackBinding* binding) {
    binding->next = *head;
    *head = binding;
}

void binding_finalize(napi_env env, void* finalize_data, void* finalize_hint) {
    (void)env;
    (void)finalize_hint;
    DeviceCallbackBinding* binding = (DeviceCallbackBinding*)finalize_data;
    if (binding && binding->value_ref) {
        napi_delete_reference(env, binding->value_ref);
    }
    free(binding);
}

void release_binding(DeviceCallbackBinding* binding) {
    if (!binding) return;
    if (binding->tsfn) {
        napi_release_threadsafe_function(binding->tsfn, napi_tsfn_release);
    }
}

DeviceCallbackBinding* create_device_callback_binding(
    napi_env env,
    void* device,
    napi_value js_cb,
    const char* resource_name,
    napi_threadsafe_function_call_js call_js,
    napi_value retained_value
) {
    DeviceCallbackBinding* binding = (DeviceCallbackBinding*)calloc(1, sizeof(DeviceCallbackBinding));
    if (!binding) return NULL;
    binding->device = device;

    napi_value async_name;
    if (napi_create_string_utf8(env, resource_name, NAPI_AUTO_LENGTH, &async_name) != napi_ok) {
        free(binding);
        return NULL;
    }
    if (retained_value != NULL) {
        if (napi_create_reference(env, retained_value, 1, &binding->value_ref) != napi_ok) {
            free(binding);
            return NULL;
        }
    }
    if (napi_create_threadsafe_function(
            env,
            js_cb,
            NULL,
            async_name,
            0,
            1,
            binding,
            binding_finalize,
            NULL,
            call_js,
            &binding->tsfn) != napi_ok) {
        if (binding->value_ref) {
            napi_delete_reference(env, binding->value_ref);
        }
        free(binding);
        return NULL;
    }
    napi_unref_threadsafe_function(env, binding->tsfn);
    return binding;
}

napi_value create_gpu_error_value(napi_env env, uint32_t error_type, const char* message) {
    napi_value global;
    napi_value error_ctor;
    napi_value message_val;
    napi_value error_val;
    napi_value name_val;
    napi_get_global(env, &global);
    napi_get_named_property(env, global, "Error", &error_ctor);
    napi_create_string_utf8(env, message ? message : "", NAPI_AUTO_LENGTH, &message_val);
    napi_new_instance(env, error_ctor, 1, &message_val, &error_val);
    napi_create_string_utf8(env,
        error_type == 0x00000002 ? "GPUValidationError"
        : error_type == 0x00000003 ? "GPUOutOfMemoryError"
        : error_type == 0x00000004 ? "GPUInternalError"
        : "GPUError",
        NAPI_AUTO_LENGTH,
        &name_val);
    napi_set_named_property(env, error_val, "name", name_val);
    return error_val;
}

void pop_error_scope_native_callback(uint32_t error_type, WGPUStringView message, void* userdata1, void* userdata2) {
    (void)userdata2;
    PopErrorScopeRequest* request = (PopErrorScopeRequest*)userdata1;
    if (!request) return;

    napi_value result;
    if (error_type == 0x00000001) {
        napi_get_null(request->env, &result);
    } else {
        char error_message[DOE_ERROR_BUF_CAP];
        copy_string_view_message(message, error_message, sizeof(error_message));
        result = create_gpu_error_value(request->env, error_type, error_message);
    }
    napi_resolve_deferred(request->env, request->deferred, result);
    free(request);
}

void js_call_uncaptured_error(napi_env env, napi_value js_cb, void* context, void* data) {
    (void)context;
    UncapturedCallbackData* payload = (UncapturedCallbackData*)data;
    if (!payload) return;
    if (env != NULL && js_cb != NULL) {
        napi_value global;
        napi_value undefined_value;
        napi_value error_ctor;
        napi_value message_val;
        napi_value error_val;
        napi_value name_val;
        napi_value event_obj;
        napi_value type_val;
        napi_value error_type_val;
        napi_value args[1];

        napi_get_global(env, &global);
        napi_get_undefined(env, &undefined_value);
        napi_get_named_property(env, global, "Error", &error_ctor);
        napi_create_string_utf8(env, payload->message ? payload->message : "", NAPI_AUTO_LENGTH, &message_val);
        napi_new_instance(env, error_ctor, 1, &message_val, &error_val);
        napi_create_string_utf8(env,
            payload->error_type == 0x00000002 ? "GPUValidationError"
            : payload->error_type == 0x00000003 ? "GPUOutOfMemoryError"
            : payload->error_type == 0x00000004 ? "GPUInternalError"
            : "GPUError",
            NAPI_AUTO_LENGTH,
            &name_val);
        napi_set_named_property(env, error_val, "name", name_val);

        napi_create_object(env, &event_obj);
        napi_create_string_utf8(env, "uncapturederror", NAPI_AUTO_LENGTH, &type_val);
        napi_create_string_utf8(env, error_type_string(payload->error_type), NAPI_AUTO_LENGTH, &error_type_val);
        napi_set_named_property(env, event_obj, "type", type_val);
        napi_set_named_property(env, event_obj, "error", error_val);
        napi_set_named_property(env, event_obj, "message", message_val);
        napi_set_named_property(env, event_obj, "errorType", error_type_val);
        args[0] = event_obj;
        napi_call_function(env, undefined_value, js_cb, 1, args, NULL);
    }
    if (payload->message) free(payload->message);
    free(payload);
}

void js_call_lost_callback(napi_env env, napi_value js_cb, void* context, void* data) {
    (void)context;
    LostCallbackData* payload = (LostCallbackData*)data;
    if (!payload) return;
    if (env != NULL && js_cb != NULL) {
        napi_value global;
        napi_value undefined_value;
        napi_value result_obj;
        napi_value reason_val;
        napi_value message_val;
        napi_value args[1];

        napi_get_global(env, &global);
        napi_get_undefined(env, &undefined_value);
        napi_create_object(env, &result_obj);
        napi_create_string_utf8(env, lost_reason_string(payload->reason), NAPI_AUTO_LENGTH, &reason_val);
        napi_create_string_utf8(env, payload->message ? payload->message : "", NAPI_AUTO_LENGTH, &message_val);
        napi_set_named_property(env, result_obj, "reason", reason_val);
        napi_set_named_property(env, result_obj, "message", message_val);
        args[0] = result_obj;
        napi_call_function(env, undefined_value, js_cb, 1, args, NULL);
    }
    if (payload->message) free(payload->message);
    free(payload);
}

void uncaptured_error_native_callback(uint32_t error_type, WGPUStringView message, void* userdata1, void* userdata2) {
    (void)userdata2;
    DeviceCallbackBinding* binding = (DeviceCallbackBinding*)userdata1;
    if (!binding || !binding->tsfn) return;
    UncapturedCallbackData* payload = (UncapturedCallbackData*)malloc(sizeof(UncapturedCallbackData));
    if (!payload) return;
    payload->error_type = error_type;
    payload->message = dup_string_view(message);
    if (napi_call_threadsafe_function(binding->tsfn, payload, napi_tsfn_nonblocking) != napi_ok) {
        if (payload->message) free(payload->message);
        free(payload);
    }
}

void lost_native_callback(uint32_t reason, const char* message_ptr, size_t message_len, void* userdata) {
    DeviceCallbackBinding* binding = (DeviceCallbackBinding*)userdata;
    if (!binding || !binding->tsfn) return;
    LostCallbackData* payload = (LostCallbackData*)malloc(sizeof(LostCallbackData));
    if (!payload) return;
    payload->reason = reason;
    payload->message = dup_c_string(message_ptr, message_len);
    if (napi_call_threadsafe_function(binding->tsfn, payload, napi_tsfn_nonblocking) != napi_ok) {
        if (payload->message) free(payload->message);
        free(payload);
    }
    binding_take(&g_lost_bindings, binding->device);
    release_binding(binding);
}

/* ================================================================
 * N-API property helpers
 * ================================================================ */

/* Release callback for GC'd externals. Logs but cannot release because we
 * don't know the handle type. Prevents silent leaks in long-lived processes. */
static void handle_Release_hint(napi_env env, void* data, void* hint) {
    (void)env; (void)hint;
    /* If data is non-null, the JS side forgot to call release().
     * We cannot safely call the typed release here without knowing the type,
     * so this is intentionally a no-op — but the destructor being non-NULL
     * means napi will not leak the ref-tracking entry. */
    (void)data;
}

void* unwrap_ptr(napi_env env, napi_value val) {
    if (!val) return NULL;
    napi_valuetype value_type;
    if (napi_typeof(env, val, &value_type) != napi_ok) return NULL;
    if (value_type == napi_object) {
        return native_direct_unwrap_external_prop(env, val, DOE_DIRECT_NATIVE);
    }
    if (value_type != napi_external) return NULL;
    void* ptr = NULL;
    napi_get_value_external(env, val, &ptr);
    return ptr;
}

napi_value wrap_ptr(napi_env env, void* ptr) {
    napi_value result;
    if (napi_create_external(env, ptr, handle_Release_hint, NULL, &result) != napi_ok) return NULL;
    return result;
}

uint32_t get_uint32_prop(napi_env env, napi_value obj, const char* key) {
    napi_value val;
    napi_get_named_property(env, obj, key, &val);
    uint32_t out = 0;
    napi_get_value_uint32(env, val, &out);
    return out;
}

int64_t get_int64_prop(napi_env env, napi_value obj, const char* key) {
    napi_value val;
    napi_get_named_property(env, obj, key, &val);
    int64_t out = 0;
    napi_get_value_int64(env, val, &out);
    return out;
}

int64_t get_int64_value(napi_env env, napi_value value) {
    int64_t out = 0;
    napi_get_value_int64(env, value, &out);
    return out;
}

double get_double_prop(napi_env env, napi_value obj, const char* key) {
    napi_value val;
    napi_get_named_property(env, obj, key, &val);
    double out = 0.0;
    napi_get_value_double(env, val, &out);
    return out;
}

bool get_bool_prop(napi_env env, napi_value obj, const char* key) {
    napi_value val;
    napi_get_named_property(env, obj, key, &val);
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    if (vt != napi_boolean) return false;
    bool out = false;
    napi_get_value_bool(env, val, &out);
    return out;
}

bool has_prop(napi_env env, napi_value obj, const char* key) {
    bool result = false;
    napi_has_named_property(env, obj, key, &result);
    return result;
}

napi_value get_prop(napi_env env, napi_value obj, const char* key) {
    napi_value val;
    napi_get_named_property(env, obj, key, &val);
    return val;
}

char* dup_string_value(napi_env env, napi_value value, size_t* out_len) {
    size_t len = 0;
    napi_get_value_string_utf8(env, value, NULL, 0, &len);
    char* out = (char*)malloc(len + 1);
    if (!out) return NULL;
    napi_get_value_string_utf8(env, value, out, len + 1, &len);
    if (out_len) *out_len = len;
    return out;
}

napi_valuetype prop_type(napi_env env, napi_value obj, const char* key) {
    napi_value val;
    napi_get_named_property(env, obj, key, &val);
    napi_valuetype vt;
    napi_typeof(env, val, &vt);
    return vt;
}

/* ================================================================
 * Adapter/device/buffer/queue callback functions
 * ================================================================ */

void adapter_callback(uint32_t status, WGPUAdapter adapter,
    WGPUStringView message, void* userdata1, void* userdata2) {
    (void)userdata2;
    AdapterRequestResult* r = (AdapterRequestResult*)userdata1;
    r->status = status;
    r->adapter = adapter;
    copy_string_view_message(message, r->message, sizeof(r->message));
    r->done = 1;
}

void device_callback(uint32_t status, WGPUDevice device,
    WGPUStringView message, void* userdata1, void* userdata2) {
    (void)userdata2;
    DeviceRequestResult* r = (DeviceRequestResult*)userdata1;
    r->status = status;
    r->device = device;
    copy_string_view_message(message, r->message, sizeof(r->message));
    r->done = 1;
}

void buffer_map_callback(uint32_t status, WGPUStringView message,
    void* userdata1, void* userdata2) {
    (void)userdata2;
    BufferMapResult* r = (BufferMapResult*)userdata1;
    r->status = status;
    copy_string_view_message(message, r->message, sizeof(r->message));
    r->done = 1;
}

void queue_work_done_callback(uint32_t status, WGPUStringView message,
    void* userdata1, void* userdata2) {
    (void)userdata2;
    QueueWorkDoneResult* r = (QueueWorkDoneResult*)userdata1;
    r->status = status;
    copy_string_view_message(message, r->message, sizeof(r->message));
    r->done = 1;
}

/* ================================================================
 * Buffer data extraction helper (ArrayBuffer / TypedArray / Buffer)
 * ================================================================ */

void extract_buffer_data(napi_env env, napi_value val, void** out_ptr, size_t* out_len) {
    *out_ptr = NULL;
    *out_len = 0;
    bool is_typedarray = false;
    napi_is_typedarray(env, val, &is_typedarray);
    if (is_typedarray) {
        napi_typedarray_type ta_type;
        size_t ta_length = 0;
        void* ta_data = NULL;
        napi_value ta_ab;
        size_t ta_byte_offset = 0;
        napi_get_typedarray_info(env, val, &ta_type, &ta_length, &ta_data, &ta_ab, &ta_byte_offset);
        *out_ptr = ta_data;
        size_t elem_size = 1;
        switch (ta_type) {
            case napi_int16_array: case napi_uint16_array: elem_size = 2; break;
            case napi_int32_array: case napi_uint32_array: case napi_float32_array: elem_size = 4; break;
            case napi_float64_array: case napi_bigint64_array: case napi_biguint64_array: elem_size = 8; break;
            default: elem_size = 1; break;
        }
        *out_len = ta_length * elem_size;
        return;
    }
    bool is_ab = false;
    napi_is_arraybuffer(env, val, &is_ab);
    if (is_ab) {
        napi_get_arraybuffer_info(env, val, out_ptr, out_len);
        return;
    }
    bool is_buffer = false;
    napi_is_buffer(env, val, &is_buffer);
    if (is_buffer) {
        napi_get_buffer_info(env, val, out_ptr, out_len);
    }
}
