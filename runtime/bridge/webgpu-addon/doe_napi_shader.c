#include "doe_napi_internal.h"

/* ================================================================
 * Shader Module
 * ================================================================ */

napi_value doe_create_shader_module(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");

    /* _args[1] is the WGSL source code string */
    size_t code_len = 0;
    napi_get_value_string_utf8(env, _args[1], NULL, 0, &code_len);
    char* code = (char*)malloc(code_len + 1);
    napi_get_value_string_utf8(env, _args[1], code, code_len + 1, &code_len);

    WGPUShaderSourceWGSL wgsl_source = {
        .chain = { .next = NULL, .sType = WGPU_STYPE_SHADER_SOURCE_WGSL },
        .code = { .data = code, .length = code_len },
    };
    WGPUShaderModuleDescriptor desc = {
        .nextInChain = (void*)&wgsl_source,
        .label = { .data = NULL, .length = 0 },
    };

    WGPUShaderModule mod = pfn_wgpuDeviceCreateShaderModule(device, &desc);
    free(code);
    if (!mod) {
        char msg[DOE_ERROR_BUF_CAP];
        char stage[64];
        char kind[64];
        copy_library_error_message(msg, sizeof(msg));
        copy_library_error_meta(pfn_doeNativeCopyLastErrorStage, stage, sizeof(stage));
        copy_library_error_meta(pfn_doeNativeCopyLastErrorKind, kind, sizeof(kind));
        if (msg[0] != '\0') {
            char full_msg[DOE_ERROR_BUF_CAP];
            if (stage[0] != '\0' && kind[0] != '\0') {
                snprintf(full_msg, sizeof(full_msg), "[%s/%s] %s", stage, kind, msg);
            } else if (stage[0] != '\0') {
                snprintf(full_msg, sizeof(full_msg), "[%s] %s", stage, msg);
            } else {
                snprintf(full_msg, sizeof(full_msg), "%s", msg);
            }
            napi_throw_error(env, "DOE_SHADER_MODULE_ERROR", full_msg);
        } else {
            napi_throw_error(env, "DOE_SHADER_MODULE_ERROR", "createShaderModule failed (WGSL translation or compilation error)");
        }
        return NULL;
    }
    return wrap_ptr(env, mod);
}

napi_value doe_check_shader_source(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    napi_valuetype value_type;
    if (napi_typeof(env, _args[0], &value_type) != napi_ok || value_type != napi_string) {
        NAPI_THROW(env, "checkShaderSource requires a WGSL source string");
    }
    napi_value result;
    napi_create_object(env, &result);
    if (!pfn_doeNativeCheckShaderSource) {
        napi_value ok;
        napi_get_boolean(env, true, &ok);
        napi_set_named_property(env, result, "ok", ok);
        return result;
    }

    size_t code_len = 0;
    napi_get_value_string_utf8(env, _args[0], NULL, 0, &code_len);
    char* code = (char*)malloc(code_len + 1);
    if (!code) NAPI_THROW(env, "checkShaderSource: out of memory");
    napi_get_value_string_utf8(env, _args[0], code, code_len + 1, &code_len);

    const uint32_t ok_status = pfn_doeNativeCheckShaderSource(code, code_len);
    free(code);

    napi_value ok;
    napi_get_boolean(env, ok_status != 0, &ok);
    napi_set_named_property(env, result, "ok", ok);
    if (ok_status != 0) return result;

    char message[DOE_ERROR_BUF_CAP];
    char stage[64];
    char kind[64];
    copy_library_error_message(message, sizeof(message));
    copy_library_error_meta(pfn_doeNativeCopyLastErrorStage, stage, sizeof(stage));
    copy_library_error_meta(pfn_doeNativeCopyLastErrorKind, kind, sizeof(kind));

    napi_value message_val;
    napi_create_string_utf8(env, message, NAPI_AUTO_LENGTH, &message_val);
    napi_set_named_property(env, result, "message", message_val);
    if (stage[0] != '\0') {
        napi_value stage_val;
        napi_create_string_utf8(env, stage, NAPI_AUTO_LENGTH, &stage_val);
        napi_set_named_property(env, result, "stage", stage_val);
    }
    if (kind[0] != '\0') {
        napi_value kind_val;
        napi_create_string_utf8(env, kind, NAPI_AUTO_LENGTH, &kind_val);
        napi_set_named_property(env, result, "kind", kind_val);
    }
    if (pfn_doeNativeGetLastErrorLine) {
        uint32_t line = pfn_doeNativeGetLastErrorLine();
        if (line > 0) {
            napi_value line_val;
            napi_create_uint32(env, line, &line_val);
            napi_set_named_property(env, result, "line", line_val);
        }
    }
    if (pfn_doeNativeGetLastErrorColumn) {
        uint32_t col = pfn_doeNativeGetLastErrorColumn();
        if (col > 0) {
            napi_value col_val;
            napi_create_uint32(env, col, &col_val);
            napi_set_named_property(env, result, "column", col_val);
        }
    }
    return result;
}

napi_value doe_shader_module_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* mod = unwrap_ptr(env, _args[0]);
    if (mod) pfn_wgpuShaderModuleRelease(mod);
    return NULL;
}

const char* doe_binding_kind_name(uint32_t kind) {
    switch (kind) {
        case 0: return "buffer";
        case 1: return "sampler";
        case 2: return "texture";
        case 3: return "storage_texture";
        default: return "unknown";
    }
}

const char* doe_binding_space_name(uint32_t addr_space) {
    switch (addr_space) {
        case 0: return "function";
        case 1: return "private";
        case 2: return "workgroup";
        case 3: return "uniform";
        case 4: return "storage";
        case 5: return "handle";
        default: return "unknown";
    }
}

const char* doe_binding_access_name(uint32_t access) {
    switch (access) {
        case 0: return "read";
        case 1: return "write";
        case 2: return "read_write";
        default: return "unknown";
    }
}

napi_value doe_shader_module_get_bindings(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    WGPUShaderModule shader_module = unwrap_ptr(env, _args[0]);
    if (!shader_module) NAPI_THROW(env, "shaderModuleGetBindings: null shader module");
    if (!pfn_doeNativeShaderModuleGetBindings) NAPI_THROW(env, "shaderModuleGetBindings: native binding metadata not available");

    DoeShaderBindingInfo bindings[16];
    size_t count = pfn_doeNativeShaderModuleGetBindings(shader_module, bindings, 16);

    napi_value array;
    napi_create_array_with_length(env, count, &array);
    for (size_t i = 0; i < count; i++) {
        napi_value entry;
        napi_create_object(env, &entry);

        napi_value group, binding, kind, space, access;
        napi_create_uint32(env, bindings[i].group, &group);
        napi_create_uint32(env, bindings[i].binding, &binding);
        napi_create_string_utf8(env, doe_binding_kind_name(bindings[i].kind), NAPI_AUTO_LENGTH, &kind);
        napi_create_string_utf8(env, doe_binding_space_name(bindings[i].addr_space), NAPI_AUTO_LENGTH, &space);
        napi_create_string_utf8(env, doe_binding_access_name(bindings[i].access), NAPI_AUTO_LENGTH, &access);

        napi_set_named_property(env, entry, "group", group);
        napi_set_named_property(env, entry, "binding", binding);
        napi_set_named_property(env, entry, "type", kind);
        napi_set_named_property(env, entry, "space", space);
        napi_set_named_property(env, entry, "access", access);
        napi_set_element(env, array, i, entry);
    }

    return array;
}
