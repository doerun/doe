/*
 * doe_napi_render.c — Texture format converters, render pipeline, render pass,
 * debug markers, and render bundle N-API bindings.
 */
#include "doe_napi_internal.h"

/* Texture / primitive format converters */

uint32_t texture_format_from_string(napi_env env, napi_value val) {
    napi_valuetype vt; napi_typeof(env, val, &vt);
    if (vt == napi_number) { uint32_t out = 0; napi_get_value_uint32(env, val, &out); return out; }
    if (vt != napi_string) return 0x00000016; /* rgba8unorm */
    char buf[32] = {0}; size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "r8unorm") == 0)           return 0x00000001;
    if (strcmp(buf, "r8snorm") == 0)           return 0x00000002;
    if (strcmp(buf, "r8uint") == 0)            return 0x00000003;
    if (strcmp(buf, "r8sint") == 0)            return 0x00000004;
    if (strcmp(buf, "r16uint") == 0)           return 0x00000007;
    if (strcmp(buf, "r16sint") == 0)           return 0x00000008;
    if (strcmp(buf, "r16float") == 0)          return 0x00000009;
    if (strcmp(buf, "rg8unorm") == 0)          return 0x0000000A;
    if (strcmp(buf, "rg8snorm") == 0)          return 0x0000000B;
    if (strcmp(buf, "rg8uint") == 0)           return 0x0000000C;
    if (strcmp(buf, "rg8sint") == 0)           return 0x0000000D;
    if (strcmp(buf, "r32float") == 0)          return 0x0000000E;
    if (strcmp(buf, "r32uint") == 0)           return 0x0000000F;
    if (strcmp(buf, "r32sint") == 0)           return 0x00000010;
    if (strcmp(buf, "rg16uint") == 0)          return 0x00000013;
    if (strcmp(buf, "rg16sint") == 0)          return 0x00000014;
    if (strcmp(buf, "rg16float") == 0)         return 0x00000015;
    if (strcmp(buf, "rgba8unorm") == 0)        return 0x00000016;
    if (strcmp(buf, "rgba8unorm-srgb") == 0)   return 0x00000017;
    if (strcmp(buf, "rgba8snorm") == 0)        return 0x00000018;
    if (strcmp(buf, "rgba8uint") == 0)         return 0x00000019;
    if (strcmp(buf, "rgba8sint") == 0)         return 0x0000001A;
    if (strcmp(buf, "bgra8unorm") == 0)        return 0x0000001B;
    if (strcmp(buf, "bgra8unorm-srgb") == 0)   return 0x0000001C;
    if (strcmp(buf, "rgb10a2uint") == 0)       return 0x0000001D;
    if (strcmp(buf, "rgb10a2unorm") == 0)      return 0x0000001E;
    if (strcmp(buf, "rg11b10ufloat") == 0)     return 0x0000001F;
    if (strcmp(buf, "rgb9e5ufloat") == 0)      return 0x00000020;
    if (strcmp(buf, "rg32float") == 0)         return 0x00000021;
    if (strcmp(buf, "rg32uint") == 0)          return 0x00000022;
    if (strcmp(buf, "rg32sint") == 0)          return 0x00000023;
    if (strcmp(buf, "rgba16uint") == 0)        return 0x00000024;
    if (strcmp(buf, "rgba16sint") == 0)        return 0x00000025;
    if (strcmp(buf, "rgba16float") == 0)       return 0x00000026;
    if (strcmp(buf, "rgba32float") == 0)       return 0x00000027;
    if (strcmp(buf, "rgba32uint") == 0)        return 0x00000028;
    if (strcmp(buf, "rgba32sint") == 0)        return 0x00000029;
    if (strcmp(buf, "stencil8") == 0)          return 0x0000002C;
    if (strcmp(buf, "depth16unorm") == 0)      return 0x0000002D;
    if (strcmp(buf, "depth24plus") == 0)       return 0x0000002E;
    if (strcmp(buf, "depth24plus-stencil8") == 0) return 0x0000002F;
    if (strcmp(buf, "depth32float") == 0)      return 0x00000030;
    if (strcmp(buf, "depth32float-stencil8") == 0) return 0x00000031;
    /* BC compressed */
    if (strcmp(buf, "bc1-rgba-unorm") == 0)       return 0x00000032;
    if (strcmp(buf, "bc1-rgba-unorm-srgb") == 0)  return 0x00000033;
    if (strcmp(buf, "bc2-rgba-unorm") == 0)       return 0x00000034;
    if (strcmp(buf, "bc2-rgba-unorm-srgb") == 0)  return 0x00000035;
    if (strcmp(buf, "bc3-rgba-unorm") == 0)       return 0x00000036;
    if (strcmp(buf, "bc3-rgba-unorm-srgb") == 0)  return 0x00000037;
    if (strcmp(buf, "bc4-r-unorm") == 0)          return 0x00000038;
    if (strcmp(buf, "bc4-r-snorm") == 0)          return 0x00000039;
    if (strcmp(buf, "bc5-rg-unorm") == 0)         return 0x0000003A;
    if (strcmp(buf, "bc5-rg-snorm") == 0)         return 0x0000003B;
    if (strcmp(buf, "bc6h-rgb-ufloat") == 0)      return 0x0000003C;
    if (strcmp(buf, "bc6h-rgb-float") == 0)       return 0x0000003D;
    if (strcmp(buf, "bc7-rgba-unorm") == 0)       return 0x0000003E;
    if (strcmp(buf, "bc7-rgba-unorm-srgb") == 0)  return 0x0000003F;
    /* ETC2/EAC compressed */
    if (strcmp(buf, "etc2-rgb8unorm") == 0)        return 0x00000040;
    if (strcmp(buf, "etc2-rgb8unorm-srgb") == 0)   return 0x00000041;
    if (strcmp(buf, "etc2-rgb8a1unorm") == 0)      return 0x00000042;
    if (strcmp(buf, "etc2-rgb8a1unorm-srgb") == 0) return 0x00000043;
    if (strcmp(buf, "etc2-rgba8unorm") == 0)       return 0x00000044;
    if (strcmp(buf, "etc2-rgba8unorm-srgb") == 0)  return 0x00000045;
    if (strcmp(buf, "eac-r11unorm") == 0)          return 0x00000046;
    if (strcmp(buf, "eac-r11snorm") == 0)          return 0x00000047;
    if (strcmp(buf, "eac-rg11unorm") == 0)         return 0x00000048;
    if (strcmp(buf, "eac-rg11snorm") == 0)         return 0x00000049;
    /* ASTC compressed */
    if (strcmp(buf, "astc-4x4-unorm") == 0)        return 0x0000004A;
    if (strcmp(buf, "astc-4x4-unorm-srgb") == 0)   return 0x0000004B;
    if (strcmp(buf, "astc-5x4-unorm") == 0)        return 0x0000004C;
    if (strcmp(buf, "astc-5x4-unorm-srgb") == 0)   return 0x0000004D;
    if (strcmp(buf, "astc-5x5-unorm") == 0)        return 0x0000004E;
    if (strcmp(buf, "astc-5x5-unorm-srgb") == 0)   return 0x0000004F;
    if (strcmp(buf, "astc-6x5-unorm") == 0)        return 0x00000050;
    if (strcmp(buf, "astc-6x5-unorm-srgb") == 0)   return 0x00000051;
    if (strcmp(buf, "astc-6x6-unorm") == 0)        return 0x00000052;
    if (strcmp(buf, "astc-6x6-unorm-srgb") == 0)   return 0x00000053;
    if (strcmp(buf, "astc-8x5-unorm") == 0)        return 0x00000054;
    if (strcmp(buf, "astc-8x5-unorm-srgb") == 0)   return 0x00000055;
    if (strcmp(buf, "astc-8x6-unorm") == 0)        return 0x00000056;
    if (strcmp(buf, "astc-8x6-unorm-srgb") == 0)   return 0x00000057;
    if (strcmp(buf, "astc-8x8-unorm") == 0)        return 0x00000058;
    if (strcmp(buf, "astc-8x8-unorm-srgb") == 0)   return 0x00000059;
    if (strcmp(buf, "astc-10x5-unorm") == 0)       return 0x0000005A;
    if (strcmp(buf, "astc-10x5-unorm-srgb") == 0)  return 0x0000005B;
    if (strcmp(buf, "astc-10x6-unorm") == 0)       return 0x0000005C;
    if (strcmp(buf, "astc-10x6-unorm-srgb") == 0)  return 0x0000005D;
    if (strcmp(buf, "astc-10x8-unorm") == 0)       return 0x0000005E;
    if (strcmp(buf, "astc-10x8-unorm-srgb") == 0)  return 0x0000005F;
    if (strcmp(buf, "astc-10x10-unorm") == 0)      return 0x00000060;
    if (strcmp(buf, "astc-10x10-unorm-srgb") == 0) return 0x00000061;
    if (strcmp(buf, "astc-12x10-unorm") == 0)      return 0x00000062;
    if (strcmp(buf, "astc-12x10-unorm-srgb") == 0) return 0x00000063;
    if (strcmp(buf, "astc-12x12-unorm") == 0)      return 0x00000064;
    if (strcmp(buf, "astc-12x12-unorm-srgb") == 0) return 0x00000065;
    return 0x00000016;
}

const char* texture_format_u32_to_string(uint32_t fmt) {
    switch (fmt) {
        case 0x00000001: return "r8unorm";      case 0x00000002: return "r8snorm";
        case 0x00000003: return "r8uint";       case 0x00000004: return "r8sint";
        case 0x00000007: return "r16uint";      case 0x00000008: return "r16sint";
        case 0x00000009: return "r16float";     case 0x0000000A: return "rg8unorm";
        case 0x0000000B: return "rg8snorm";     case 0x0000000C: return "rg8uint";
        case 0x0000000D: return "rg8sint";      case 0x0000000E: return "r32float";
        case 0x0000000F: return "r32uint";      case 0x00000010: return "r32sint";
        case 0x00000013: return "rg16uint";     case 0x00000014: return "rg16sint";
        case 0x00000015: return "rg16float";    case 0x00000016: return "rgba8unorm";
        case 0x00000017: return "rgba8unorm-srgb"; case 0x00000018: return "rgba8snorm";
        case 0x00000019: return "rgba8uint";    case 0x0000001A: return "rgba8sint";
        case 0x0000001B: return "bgra8unorm";   case 0x0000001C: return "bgra8unorm-srgb";
        case 0x0000001D: return "rgb10a2uint";  case 0x0000001E: return "rgb10a2unorm";
        case 0x0000001F: return "rg11b10ufloat"; case 0x00000020: return "rgb9e5ufloat";
        case 0x00000021: return "rg32float";    case 0x00000022: return "rg32uint";
        case 0x00000023: return "rg32sint";     case 0x00000024: return "rgba16uint";
        case 0x00000025: return "rgba16sint";   case 0x00000026: return "rgba16float";
        case 0x00000027: return "rgba32float";  case 0x00000028: return "rgba32uint";
        case 0x00000029: return "rgba32sint";   case 0x0000002C: return "stencil8";
        case 0x0000002D: return "depth16unorm"; case 0x0000002E: return "depth24plus";
        case 0x0000002F: return "depth24plus-stencil8";
        case 0x00000030: return "depth32float"; case 0x00000031: return "depth32float-stencil8";
        default: return NULL;
    }
}

uint32_t primitive_topology_from_string(napi_env env, napi_value val) {
    napi_valuetype vt; napi_typeof(env, val, &vt);
    if (vt == napi_number) { uint32_t out = 0; napi_get_value_uint32(env, val, &out); return out; }
    char buf[32] = {0}; size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "point-list") == 0)     return 0x00000001;
    if (strcmp(buf, "line-list") == 0)      return 0x00000002;
    if (strcmp(buf, "line-strip") == 0)     return 0x00000003;
    if (strcmp(buf, "triangle-list") == 0)  return 0x00000004;
    if (strcmp(buf, "triangle-strip") == 0) return 0x00000005;
    napi_throw_error(env, "DOE_ERROR", "Unsupported primitive topology");
    return 0;
}

uint32_t front_face_from_string(napi_env env, napi_value val) {
    napi_valuetype vt; napi_typeof(env, val, &vt);
    if (vt == napi_number) { uint32_t out = 0; napi_get_value_uint32(env, val, &out); return out; }
    char buf[16] = {0}; size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "ccw") == 0) return 0x00000001;
    if (strcmp(buf, "cw") == 0)  return 0x00000002;
    napi_throw_error(env, "DOE_ERROR", "Unsupported frontFace"); return 0;
}

uint32_t cull_mode_from_string(napi_env env, napi_value val) {
    napi_valuetype vt; napi_typeof(env, val, &vt);
    if (vt == napi_number) { uint32_t out = 0; napi_get_value_uint32(env, val, &out); return out; }
    char buf[16] = {0}; size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "none") == 0)  return 0x00000001;
    if (strcmp(buf, "front") == 0) return 0x00000002;
    if (strcmp(buf, "back") == 0)  return 0x00000003;
    napi_throw_error(env, "DOE_ERROR", "Unsupported cullMode"); return 0;
}

uint32_t filter_mode_from_string(napi_env env, napi_value val) {
    napi_valuetype vt; napi_typeof(env, val, &vt);
    if (vt != napi_string) return 0; /* nearest */
    char buf[16] = {0}; size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "linear") == 0) return 1;
    return 0;
}

uint32_t address_mode_from_string(napi_env env, napi_value val) {
    napi_valuetype vt; napi_typeof(env, val, &vt);
    if (vt != napi_string) return 1; /* clamp-to-edge */
    char buf[24] = {0}; size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "repeat") == 0)        return 2;
    if (strcmp(buf, "mirror-repeat") == 0) return 3;
    return 1;
}

uint32_t compare_func_from_value(napi_env env, napi_value val) {
    napi_valuetype vt; napi_typeof(env, val, &vt);
    if (vt == napi_number) { uint32_t out = 0; napi_get_value_uint32(env, val, &out); return out; }
    char buf[24] = {0}; size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "never") == 0)        return 0x00000001;
    if (strcmp(buf, "less") == 0)         return 0x00000002;
    if (strcmp(buf, "equal") == 0)        return 0x00000003;
    if (strcmp(buf, "less-equal") == 0)   return 0x00000004;
    if (strcmp(buf, "greater") == 0)      return 0x00000005;
    if (strcmp(buf, "not-equal") == 0)    return 0x00000006;
    if (strcmp(buf, "greater-equal") == 0) return 0x00000007;
    if (strcmp(buf, "always") == 0)       return 0x00000008;
    napi_throw_error(env, "DOE_ERROR", "Unsupported compare function"); return 0;
}

uint32_t vertex_step_mode_from_value(napi_env env, napi_value val) {
    napi_valuetype vt; napi_typeof(env, val, &vt);
    if (vt == napi_number) { uint32_t out = 0; napi_get_value_uint32(env, val, &out); return out; }
    char buf[24] = {0}; size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "vertex") == 0)   return 0x00000001;
    if (strcmp(buf, "instance") == 0) return 0x00000002;
    napi_throw_error(env, "DOE_ERROR", "Unsupported vertex stepMode"); return 0;
}

uint32_t vertex_format_from_value(napi_env env, napi_value val) {
    napi_valuetype vt; napi_typeof(env, val, &vt);
    if (vt == napi_number) { uint32_t out = 0; napi_get_value_uint32(env, val, &out); return out; }
    char buf[32] = {0}; size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "float32") == 0)   return 0x00000019;
    if (strcmp(buf, "float32x2") == 0) return 0x0000001A;
    if (strcmp(buf, "float32x3") == 0) return 0x0000001B;
    if (strcmp(buf, "float32x4") == 0) return 0x0000001C;
    if (strcmp(buf, "uint32") == 0)    return 0x00000021;
    if (strcmp(buf, "uint32x2") == 0)  return 0x00000022;
    if (strcmp(buf, "uint32x3") == 0)  return 0x00000023;
    if (strcmp(buf, "uint32x4") == 0)  return 0x00000024;
    if (strcmp(buf, "sint32") == 0)    return 0x00000025;
    if (strcmp(buf, "sint32x2") == 0)  return 0x00000026;
    if (strcmp(buf, "sint32x3") == 0)  return 0x00000027;
    if (strcmp(buf, "sint32x4") == 0)  return 0x00000028;
    napi_throw_error(env, "DOE_ERROR", "Unsupported vertex format"); return 0;
}

uint32_t index_format_from_value(napi_env env, napi_value val) {
    napi_valuetype vt; napi_typeof(env, val, &vt);
    if (vt == napi_number) { uint32_t out = 0; napi_get_value_uint32(env, val, &out); return out; }
    char buf[16] = {0}; size_t len = 0;
    napi_get_value_string_utf8(env, val, buf, sizeof(buf), &len);
    if (strcmp(buf, "uint16") == 0) return 0x00000001;
    if (strcmp(buf, "uint32") == 0) return 0x00000002;
    napi_throw_error(env, "DOE_ERROR", "Unsupported index format"); return 0;
}

/* Render Pipeline */

napi_value doe_create_render_pipeline(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUDevice device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "Invalid device");
    napi_valuetype descriptor_type; napi_typeof(env, _args[1], &descriptor_type);
    if (descriptor_type != napi_object) NAPI_THROW(env, "createRenderPipeline requires a descriptor object");
    if (prop_type(env, _args[1], "vertex") != napi_object)
        NAPI_THROW(env, "createRenderPipeline requires descriptor.vertex");
    if (prop_type(env, _args[1], "fragment") != napi_object)
        NAPI_THROW(env, "createRenderPipeline requires descriptor.fragment");

    napi_value vertex   = get_prop(env, _args[1], "vertex");
    napi_value fragment = get_prop(env, _args[1], "fragment");
    napi_value targets  = get_prop(env, fragment, "targets");
    bool is_targets_array = false;
    napi_is_array(env, targets, &is_targets_array);
    if (!is_targets_array) NAPI_THROW(env, "createRenderPipeline requires descriptor.fragment.targets");
    uint32_t target_count = 0; napi_get_array_length(env, targets, &target_count);
    if (target_count == 0) NAPI_THROW(env, "createRenderPipeline requires at least one fragment target");
    if (target_count > 1) NAPI_THROW(env, "createRenderPipeline currently supports one color target on this package surface");

    WGPUShaderModule vertex_module   = unwrap_ptr(env, get_prop(env, vertex, "module"));
    WGPUShaderModule fragment_module = unwrap_ptr(env, get_prop(env, fragment, "module"));
    if (!vertex_module)   NAPI_THROW(env, "createRenderPipeline: descriptor.vertex.module must be a shader module");
    if (!fragment_module) NAPI_THROW(env, "createRenderPipeline: descriptor.fragment.module must be a shader module");

    size_t vertex_entry_len = 0, fragment_entry_len = 0;
    char* vertex_entry = has_prop(env, vertex, "entryPoint")
        ? dup_string_value(env, get_prop(env, vertex, "entryPoint"), &vertex_entry_len)
        : strdup("main");
    if (!has_prop(env, vertex, "entryPoint")) vertex_entry_len = 4;
    char* fragment_entry = has_prop(env, fragment, "entryPoint")
        ? dup_string_value(env, get_prop(env, fragment, "entryPoint"), &fragment_entry_len)
        : strdup("main");
    if (!has_prop(env, fragment, "entryPoint")) fragment_entry_len = 4;
    if (!vertex_entry || !fragment_entry) {
        free(vertex_entry); free(fragment_entry);
        NAPI_THROW(env, "createRenderPipeline: out of memory");
    }

    WGPURenderVertexBufferLayout* vertex_buffers = NULL;
    WGPURenderVertexAttribute*    vertex_attributes = NULL;
    WGPURenderDepthStencilState*  depth_stencil = NULL;
    uint32_t vertex_buffer_count = 0;

    if (has_prop(env, vertex, "buffers")) {
        napi_value buffers = get_prop(env, vertex, "buffers");
        bool is_array = false; napi_is_array(env, buffers, &is_array);
        if (!is_array) { free(vertex_entry); free(fragment_entry); NAPI_THROW(env, "createRenderPipeline: descriptor.vertex.buffers must be an array"); }
        napi_get_array_length(env, buffers, &vertex_buffer_count);
        if (vertex_buffer_count > 0) {
            size_t total_attributes = 0;
            for (uint32_t i = 0; i < vertex_buffer_count; i++) {
                napi_value buffer_desc; napi_get_element(env, buffers, i, &buffer_desc);
                if (prop_type(env, buffer_desc, "attributes") == napi_object) {
                    napi_value attrs = get_prop(env, buffer_desc, "attributes");
                    bool attrs_is_array = false; napi_is_array(env, attrs, &attrs_is_array);
                    if (!attrs_is_array) { free(vertex_entry); free(fragment_entry); NAPI_THROW(env, "createRenderPipeline: descriptor.vertex.buffers[*].attributes must be an array"); }
                    uint32_t attr_count = 0; napi_get_array_length(env, attrs, &attr_count);
                    total_attributes += attr_count;
                }
            }
            vertex_buffers = (WGPURenderVertexBufferLayout*)calloc(vertex_buffer_count, sizeof(WGPURenderVertexBufferLayout));
            if (!vertex_buffers) { free(vertex_entry); free(fragment_entry); NAPI_THROW(env, "createRenderPipeline: out of memory"); }
            if (total_attributes > 0) {
                vertex_attributes = (WGPURenderVertexAttribute*)calloc(total_attributes, sizeof(WGPURenderVertexAttribute));
                if (!vertex_attributes) { free(vertex_buffers); free(vertex_entry); free(fragment_entry); NAPI_THROW(env, "createRenderPipeline: out of memory"); }
            }
            size_t attr_index = 0;
            for (uint32_t i = 0; i < vertex_buffer_count; i++) {
                napi_value buffer_desc; napi_get_element(env, buffers, i, &buffer_desc);
                vertex_buffers[i].nextInChain = NULL;
                vertex_buffers[i].stepMode = has_prop(env, buffer_desc, "stepMode")
                    ? vertex_step_mode_from_value(env, get_prop(env, buffer_desc, "stepMode")) : 0x00000001;
                vertex_buffers[i].arrayStride = has_prop(env, buffer_desc, "arrayStride")
                    ? (uint64_t)get_int64_prop(env, buffer_desc, "arrayStride") : 0;
                vertex_buffers[i].attributeCount = 0;
                vertex_buffers[i].attributes = NULL;
                if (prop_type(env, buffer_desc, "attributes") == napi_object) {
                    napi_value attrs = get_prop(env, buffer_desc, "attributes");
                    uint32_t attr_count = 0; napi_get_array_length(env, attrs, &attr_count);
                    vertex_buffers[i].attributeCount = attr_count;
                    vertex_buffers[i].attributes = attr_count > 0 ? &vertex_attributes[attr_index] : NULL;
                    for (uint32_t j = 0; j < attr_count; j++) {
                        napi_value attr; napi_get_element(env, attrs, j, &attr);
                        vertex_attributes[attr_index].nextInChain = NULL;
                        vertex_attributes[attr_index].format = vertex_format_from_value(env, get_prop(env, attr, "format"));
                        vertex_attributes[attr_index].offset = has_prop(env, attr, "offset")
                            ? (uint64_t)get_int64_prop(env, attr, "offset") : 0;
                        vertex_attributes[attr_index].shaderLocation = get_uint32_prop(env, attr, "shaderLocation");
                        attr_index += 1;
                    }
                }
            }
        }
    }

    napi_value target0; napi_get_element(env, targets, 0, &target0);
    WGPURenderColorTargetState color_target; memset(&color_target, 0, sizeof(color_target));
    color_target.format = texture_format_from_string(env, get_prop(env, target0, "format"));
    color_target.writeMask = 0xF;

    WGPURenderFragmentState fragment_state; memset(&fragment_state, 0, sizeof(fragment_state));
    fragment_state.module = fragment_module;
    fragment_state.entryPoint.data = fragment_entry; fragment_state.entryPoint.length = fragment_entry_len;
    fragment_state.targetCount = 1; fragment_state.targets = &color_target;

    WGPURenderPipelineDescriptor desc; memset(&desc, 0, sizeof(desc));
    desc.layout = has_prop(env, _args[1], "layout") && prop_type(env, _args[1], "layout") == napi_external
        ? unwrap_ptr(env, get_prop(env, _args[1], "layout")) : NULL;
    desc.vertex.module = vertex_module;
    desc.vertex.entryPoint.data = vertex_entry; desc.vertex.entryPoint.length = vertex_entry_len;
    desc.vertex.bufferCount = vertex_buffer_count; desc.vertex.buffers = vertex_buffers;
    desc.primitive.topology = 0x00000004; desc.primitive.frontFace = 0x00000001; desc.primitive.cullMode = 0x00000001;
    if (has_prop(env, _args[1], "primitive") && prop_type(env, _args[1], "primitive") == napi_object) {
        napi_value primitive = get_prop(env, _args[1], "primitive");
        if (has_prop(env, primitive, "topology"))
            desc.primitive.topology = primitive_topology_from_string(env, get_prop(env, primitive, "topology"));
        if (has_prop(env, primitive, "frontFace"))
            desc.primitive.frontFace = front_face_from_string(env, get_prop(env, primitive, "frontFace"));
        if (has_prop(env, primitive, "cullMode"))
            desc.primitive.cullMode = cull_mode_from_string(env, get_prop(env, primitive, "cullMode"));
        if (has_prop(env, primitive, "unclippedDepth"))
            desc.primitive.unclippedDepth = get_bool_prop(env, primitive, "unclippedDepth") ? 1 : 0;
    }
    if (has_prop(env, _args[1], "depthStencil") && prop_type(env, _args[1], "depthStencil") == napi_object) {
        napi_value depth_obj = get_prop(env, _args[1], "depthStencil");
        depth_stencil = (WGPURenderDepthStencilState*)calloc(1, sizeof(WGPURenderDepthStencilState));
        if (!depth_stencil) { free(vertex_buffers); free(vertex_attributes); free(vertex_entry); free(fragment_entry); NAPI_THROW(env, "createRenderPipeline: out of memory"); }
        depth_stencil->format = texture_format_from_string(env, get_prop(env, depth_obj, "format"));
        depth_stencil->depthWriteEnabled = has_prop(env, depth_obj, "depthWriteEnabled") ? (get_bool_prop(env, depth_obj, "depthWriteEnabled") ? 1 : 0) : 0;
        depth_stencil->depthCompare = has_prop(env, depth_obj, "depthCompare") ? compare_func_from_value(env, get_prop(env, depth_obj, "depthCompare")) : 0x00000008;
        depth_stencil->stencilReadMask = 0xFFFFFFFFu; depth_stencil->stencilWriteMask = 0xFFFFFFFFu;
        desc.depthStencil = depth_stencil;
    }
    desc.multisample.count = 1; desc.multisample.mask = 0xFFFFffffu;
    if (has_prop(env, _args[1], "multisample") && prop_type(env, _args[1], "multisample") == napi_object) {
        napi_value ms = get_prop(env, _args[1], "multisample");
        if (has_prop(env, ms, "count")) desc.multisample.count = get_uint32_prop(env, ms, "count");
        if (has_prop(env, ms, "mask"))  desc.multisample.mask  = get_uint32_prop(env, ms, "mask");
        if (has_prop(env, ms, "alphaToCoverageEnabled"))
            desc.multisample.alphaToCoverageEnabled = get_bool_prop(env, ms, "alphaToCoverageEnabled") ? 1 : 0;
    }
    desc.fragment = &fragment_state;

    WGPURenderPipeline rp = pfn_wgpuDeviceCreateRenderPipeline(device, &desc);
    free(depth_stencil); free(vertex_attributes); free(vertex_buffers);
    free(vertex_entry);  free(fragment_entry);
    if (!rp) NAPI_THROW(env, "createRenderPipeline failed");
    return wrap_ptr(env, rp);
}

napi_value doe_render_pipeline_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuRenderPipelineRelease(p);
    return NULL;
}

napi_value doe_render_pipeline_get_bind_group_layout(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    void* pipeline = unwrap_ptr(env, _args[0]);
    if (!pipeline) NAPI_THROW(env, "Invalid render pipeline");
    uint32_t index; napi_get_value_uint32(env, _args[1], &index);
    if (!pfn_doeNativeRenderPipelineGetBindGroupLayout) NAPI_THROW(env, "renderPipelineGetBindGroupLayout not available");
    void* layout = pfn_doeNativeRenderPipelineGetBindGroupLayout(pipeline, index);
    if (!layout) NAPI_THROW(env, "renderPipelineGetBindGroupLayout failed");
    return wrap_ptr(env, layout);
}

/* Render Pass */

napi_value doe_begin_render_pass(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    CHECK_LIB_LOADED(env);
    WGPUCommandEncoder enc = unwrap_ptr(env, _args[0]);
    if (!enc) NAPI_THROW(env, "Invalid encoder");
    if (prop_type(env, _args[1], "colorAttachments") != napi_object)
        NAPI_THROW(env, "beginRenderPass requires descriptor.colorAttachments");
    napi_value color_attachments = get_prop(env, _args[1], "colorAttachments");
    uint32_t att_count = 0; napi_get_array_length(env, color_attachments, &att_count);
    if (att_count == 0) NAPI_THROW(env, "beginRenderPass: need at least one color attachment");
    WGPURenderPassColorAttachment* atts = (WGPURenderPassColorAttachment*)calloc(att_count, sizeof(WGPURenderPassColorAttachment));
    WGPURenderPassDepthStencilAttachment depth_att; memset(&depth_att, 0, sizeof(depth_att));
    bool has_depth_att = false;
    for (uint32_t i = 0; i < att_count; i++) {
        napi_value elem; napi_get_element(env, color_attachments, i, &elem);
        atts[i].view = unwrap_ptr(env, get_prop(env, elem, "view"));
        atts[i].loadOp = 1; atts[i].storeOp = 1;
        if (has_prop(env, elem, "clearValue") && prop_type(env, elem, "clearValue") == napi_object) {
            napi_value cv = get_prop(env, elem, "clearValue");
            double r = 0, g = 0, b = 0, a = 1; napi_value tmp;
            if (napi_get_named_property(env, cv, "r", &tmp) == napi_ok) napi_get_value_double(env, tmp, &r);
            if (napi_get_named_property(env, cv, "g", &tmp) == napi_ok) napi_get_value_double(env, tmp, &g);
            if (napi_get_named_property(env, cv, "b", &tmp) == napi_ok) napi_get_value_double(env, tmp, &b);
            if (napi_get_named_property(env, cv, "a", &tmp) == napi_ok) napi_get_value_double(env, tmp, &a);
            atts[i].clearValue = (WGPUColor){ r, g, b, a };
        }
    }
    if (has_prop(env, _args[1], "depthStencilAttachment") && prop_type(env, _args[1], "depthStencilAttachment") == napi_object) {
        napi_value depth_obj = get_prop(env, _args[1], "depthStencilAttachment");
        depth_att.view = unwrap_ptr(env, get_prop(env, depth_obj, "view"));
        depth_att.depthLoadOp = 1; depth_att.depthStoreOp = 1;
        depth_att.depthClearValue = has_prop(env, depth_obj, "depthClearValue")
            ? (float)get_double_prop(env, depth_obj, "depthClearValue") : 1.0f;
        depth_att.depthReadOnly = has_prop(env, depth_obj, "depthReadOnly")
            ? (get_bool_prop(env, depth_obj, "depthReadOnly") ? 1 : 0) : 0;
        depth_att.stencilLoadOp = 1; depth_att.stencilStoreOp = 1;
        depth_att.stencilClearValue = has_prop(env, depth_obj, "stencilClearValue")
            ? get_uint32_prop(env, depth_obj, "stencilClearValue") : 0;
        depth_att.stencilReadOnly = has_prop(env, depth_obj, "stencilReadOnly")
            ? (get_bool_prop(env, depth_obj, "stencilReadOnly") ? 1 : 0) : 0;
        has_depth_att = true;
    }
    WGPURenderPassDescriptor desc; memset(&desc, 0, sizeof(desc));
    desc.colorAttachmentCount = att_count; desc.colorAttachments = atts;
    desc.depthStencilAttachment = has_depth_att ? &depth_att : NULL;
    WGPURenderPassEncoder pass = pfn_wgpuCommandEncoderBeginRenderPass(enc, &desc);
    free(atts);
    if (!pass) NAPI_THROW(env, "beginRenderPass failed");
    return wrap_ptr(env, pass);
}

napi_value doe_render_pass_set_pipeline(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    pfn_wgpuRenderPassEncoderSetPipeline(unwrap_ptr(env, _args[0]), unwrap_ptr(env, _args[1]));
    return NULL;
}

napi_value doe_render_pass_set_bind_group(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    WGPURenderPassEncoder pass = unwrap_ptr(env, _args[0]);
    uint32_t index = 0; napi_get_value_uint32(env, _args[1], &index);
    WGPUBindGroup bg = unwrap_ptr(env, _args[2]);
    pfn_wgpuRenderPassEncoderSetBindGroup(pass, index, bg, 0, NULL);
    return NULL;
}

napi_value doe_render_pass_set_vertex_buffer(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    WGPURenderPassEncoder pass = unwrap_ptr(env, _args[0]);
    uint32_t slot = 0; napi_get_value_uint32(env, _args[1], &slot);
    WGPUBuffer buffer = unwrap_ptr(env, _args[2]);
    uint64_t offset = (uint64_t)get_int64_value(env, _args[3]);
    uint64_t size   = (uint64_t)get_int64_value(env, _args[4]);
    pfn_wgpuRenderPassEncoderSetVertexBuffer(pass, slot, buffer, offset, size);
    return NULL;
}

napi_value doe_render_pass_set_index_buffer(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    WGPURenderPassEncoder pass = unwrap_ptr(env, _args[0]);
    WGPUBuffer buffer = unwrap_ptr(env, _args[1]);
    uint32_t format = index_format_from_value(env, _args[2]);
    uint64_t offset = (uint64_t)get_int64_value(env, _args[3]);
    uint64_t size   = (uint64_t)get_int64_value(env, _args[4]);
    pfn_wgpuRenderPassEncoderSetIndexBuffer(pass, buffer, format, offset, size);
    return NULL;
}

napi_value doe_render_pass_draw(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    WGPURenderPassEncoder pass = unwrap_ptr(env, _args[0]);
    uint32_t vc, ic, fv, fi;
    napi_get_value_uint32(env, _args[1], &vc); napi_get_value_uint32(env, _args[2], &ic);
    napi_get_value_uint32(env, _args[3], &fv); napi_get_value_uint32(env, _args[4], &fi);
    pfn_wgpuRenderPassEncoderDraw(pass, vc, ic, fv, fi);
    return NULL;
}

napi_value doe_render_pass_draw_indexed(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 6);
    WGPURenderPassEncoder pass = unwrap_ptr(env, _args[0]);
    uint32_t index_count = 0, instance_count = 0, first_index = 0; int32_t base_vertex = 0; uint32_t first_instance = 0;
    napi_get_value_uint32(env, _args[1], &index_count); napi_get_value_uint32(env, _args[2], &instance_count);
    napi_get_value_uint32(env, _args[3], &first_index); napi_get_value_int32(env, _args[4], &base_vertex);
    napi_get_value_uint32(env, _args[5], &first_instance);
    pfn_wgpuRenderPassEncoderDrawIndexed(pass, index_count, instance_count, first_index, base_vertex, first_instance);
    return NULL;
}

napi_value doe_render_pass_end(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    pfn_wgpuRenderPassEncoderEnd(unwrap_ptr(env, _args[0]));
    return NULL;
}

napi_value doe_render_pass_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* p = unwrap_ptr(env, _args[0]);
    if (p) pfn_wgpuRenderPassEncoderRelease(p);
    return NULL;
}

napi_value doe_render_pass_set_viewport(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 7);
    void* pass = unwrap_ptr(env, _args[0]);
    if (!pass || !pfn_doeNativeRenderPassSetViewport) return NULL;
    double x = 0, y = 0, width = 0, height = 0, min_depth = 0, max_depth = 1;
    napi_get_value_double(env, _args[1], &x); napi_get_value_double(env, _args[2], &y);
    napi_get_value_double(env, _args[3], &width); napi_get_value_double(env, _args[4], &height);
    napi_get_value_double(env, _args[5], &min_depth); napi_get_value_double(env, _args[6], &max_depth);
    pfn_doeNativeRenderPassSetViewport(pass, x, y, width, height, min_depth, max_depth);
    return NULL;
}

napi_value doe_render_pass_set_scissor_rect(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    void* pass = unwrap_ptr(env, _args[0]);
    if (!pass || !pfn_doeNativeRenderPassSetScissorRect) return NULL;
    uint32_t x = 0, y = 0, width = 0, height = 0;
    napi_get_value_uint32(env, _args[1], &x); napi_get_value_uint32(env, _args[2], &y);
    napi_get_value_uint32(env, _args[3], &width); napi_get_value_uint32(env, _args[4], &height);
    pfn_doeNativeRenderPassSetScissorRect(pass, x, y, width, height);
    return NULL;
}

napi_value doe_render_pass_set_blend_constant(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    void* pass = unwrap_ptr(env, _args[0]);
    if (!pass || !pfn_doeNativeRenderPassSetBlendConstant) return NULL;
    double r = 0, g = 0, b = 0, a = 1;
    napi_get_value_double(env, _args[1], &r); napi_get_value_double(env, _args[2], &g);
    napi_get_value_double(env, _args[3], &b); napi_get_value_double(env, _args[4], &a);
    pfn_doeNativeRenderPassSetBlendConstant(pass, r, g, b, a);
    return NULL;
}

napi_value doe_render_pass_set_stencil_reference(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    void* pass = unwrap_ptr(env, _args[0]);
    if (!pass || !pfn_doeNativeRenderPassSetStencilReference) return NULL;
    uint32_t reference = 0; napi_get_value_uint32(env, _args[1], &reference);
    pfn_doeNativeRenderPassSetStencilReference(pass, reference);
    return NULL;
}

/* Debug markers */

napi_value doe_render_pass_push_debug_group(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    void* pass = unwrap_ptr(env, _args[0]);
    if (!pass || !pfn_doeNativeRenderPassPushDebugGroup) return NULL;
    size_t label_len = 0;
    napi_get_value_string_utf8(env, _args[1], NULL, 0, &label_len);
    char* label = (char*)malloc(label_len + 1); if (!label) return NULL;
    napi_get_value_string_utf8(env, _args[1], label, label_len + 1, &label_len);
    pfn_doeNativeRenderPassPushDebugGroup(pass, label, label_len);
    free(label); return NULL;
}

napi_value doe_render_pass_pop_debug_group(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* pass = unwrap_ptr(env, _args[0]);
    if (!pass || !pfn_doeNativeRenderPassPopDebugGroup) return NULL;
    pfn_doeNativeRenderPassPopDebugGroup(pass);
    return NULL;
}

napi_value doe_render_pass_insert_debug_marker(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    void* pass = unwrap_ptr(env, _args[0]);
    if (!pass || !pfn_doeNativeRenderPassInsertDebugMarker) return NULL;
    size_t label_len = 0;
    napi_get_value_string_utf8(env, _args[1], NULL, 0, &label_len);
    char* label = (char*)malloc(label_len + 1); if (!label) return NULL;
    napi_get_value_string_utf8(env, _args[1], label, label_len + 1, &label_len);
    pfn_doeNativeRenderPassInsertDebugMarker(pass, label, label_len);
    free(label); return NULL;
}

/* Render Bundle Encoder */

/* RenderBundleEncoderDescriptor layout matching wgpu_render_types.zig. */
typedef struct {
    void*    nextInChain;
    void*    label_data;
    size_t   label_len;
    size_t   colorFormatCount;
    uint32_t* colorFormats;
    uint32_t depthStencilFormat;
    uint32_t sampleCount;
    uint32_t depthReadOnly;
    uint32_t stencilReadOnly;
} BundleEncoderDescC;

napi_value doe_create_render_bundle_encoder(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 6);
    CHECK_LIB_LOADED(env);
    if (!pfn_doeNativeDeviceCreateRenderBundleEncoder) NAPI_THROW(env, "doeNativeDeviceCreateRenderBundleEncoder not available");
    void* device = unwrap_ptr(env, _args[0]);
    if (!device) NAPI_THROW(env, "createRenderBundleEncoder: invalid device");
    uint32_t fmt_count = 0; bool is_array = false;
    napi_is_array(env, _args[1], &is_array);
    if (is_array) napi_get_array_length(env, _args[1], &fmt_count);
    uint32_t* fmts = fmt_count > 0 ? (uint32_t*)malloc(fmt_count * sizeof(uint32_t)) : NULL;
    for (uint32_t i = 0; i < fmt_count; i++) {
        napi_value elem; napi_get_element(env, _args[1], i, &elem);
        napi_get_value_uint32(env, elem, &fmts[i]);
    }
    uint32_t depth_stencil_format = 0; napi_get_value_uint32(env, _args[2], &depth_stencil_format);
    uint32_t sample_count = 1;         napi_get_value_uint32(env, _args[3], &sample_count);
    bool depth_read_only = false;      napi_get_value_bool(env, _args[4], &depth_read_only);
    bool stencil_read_only = false;    napi_get_value_bool(env, _args[5], &stencil_read_only);
    BundleEncoderDescC desc = {
        .nextInChain = NULL, .label_data = NULL, .label_len = 0,
        .colorFormatCount   = (size_t)fmt_count, .colorFormats = fmts,
        .depthStencilFormat = depth_stencil_format,
        .sampleCount        = sample_count == 0 ? 1 : sample_count,
        .depthReadOnly      = depth_read_only ? 1 : 0,
        .stencilReadOnly    = stencil_read_only ? 1 : 0,
    };
    void* enc = pfn_doeNativeDeviceCreateRenderBundleEncoder(device, &desc);
    free(fmts);
    if (!enc) NAPI_THROW(env, "createRenderBundleEncoder failed");
    return wrap_ptr(env, enc);
}

napi_value doe_render_bundle_encoder_set_pipeline(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 2);
    void* enc = unwrap_ptr(env, _args[0]); void* pipeline = unwrap_ptr(env, _args[1]);
    if (!enc || !pipeline) return NULL;
    if (pfn_doeNativeRenderBundleEncoderSetPipeline) pfn_doeNativeRenderBundleEncoderSetPipeline(enc, pipeline);
    return NULL;
}

napi_value doe_render_bundle_encoder_set_bind_group(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    void* enc = unwrap_ptr(env, _args[0]); if (!enc) return NULL;
    uint32_t index = 0; napi_get_value_uint32(env, _args[1], &index);
    void* bg = unwrap_ptr(env, _args[2]); if (!bg) return NULL;
    if (pfn_doeNativeRenderBundleEncoderSetBindGroup) pfn_doeNativeRenderBundleEncoderSetBindGroup(enc, index, bg, 0, NULL);
    return NULL;
}

napi_value doe_render_bundle_encoder_set_vertex_buffer(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    void* enc = unwrap_ptr(env, _args[0]); if (!enc) return NULL;
    uint32_t slot = 0; napi_get_value_uint32(env, _args[1], &slot);
    void* buf = unwrap_ptr(env, _args[2]); if (!buf) return NULL;
    int64_t offset = 0; napi_get_value_int64(env, _args[3], &offset);
    int64_t size   = 0; napi_get_value_int64(env, _args[4], &size);
    if (pfn_doeNativeRenderBundleEncoderSetVertexBuffer)
        pfn_doeNativeRenderBundleEncoderSetVertexBuffer(enc, slot, buf, (uint64_t)offset, (uint64_t)size);
    return NULL;
}

napi_value doe_render_bundle_encoder_set_index_buffer(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    void* enc = unwrap_ptr(env, _args[0]); if (!enc) return NULL;
    void* buf = unwrap_ptr(env, _args[1]); if (!buf) return NULL;
    uint32_t format = 0; napi_get_value_uint32(env, _args[2], &format);
    int64_t offset = 0; napi_get_value_int64(env, _args[3], &offset);
    int64_t size   = 0; napi_get_value_int64(env, _args[4], &size);
    if (pfn_doeNativeRenderBundleEncoderSetIndexBuffer)
        pfn_doeNativeRenderBundleEncoderSetIndexBuffer(enc, buf, format, (uint64_t)offset, (uint64_t)size);
    return NULL;
}

napi_value doe_render_bundle_encoder_draw(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 5);
    void* enc = unwrap_ptr(env, _args[0]); if (!enc) return NULL;
    uint32_t vertex_count = 0, instance_count = 1, first_vertex = 0, first_instance = 0;
    napi_get_value_uint32(env, _args[1], &vertex_count); napi_get_value_uint32(env, _args[2], &instance_count);
    napi_get_value_uint32(env, _args[3], &first_vertex); napi_get_value_uint32(env, _args[4], &first_instance);
    if (pfn_doeNativeRenderBundleEncoderDraw)
        pfn_doeNativeRenderBundleEncoderDraw(enc, vertex_count, instance_count, first_vertex, first_instance);
    return NULL;
}

napi_value doe_render_bundle_encoder_draw_indexed(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 6);
    void* enc = unwrap_ptr(env, _args[0]); if (!enc) return NULL;
    uint32_t index_count = 0, instance_count = 1, first_index = 0; int32_t base_vertex = 0; uint32_t first_instance = 0;
    napi_get_value_uint32(env, _args[1], &index_count); napi_get_value_uint32(env, _args[2], &instance_count);
    napi_get_value_uint32(env, _args[3], &first_index);
    napi_valuetype bv_type; napi_typeof(env, _args[4], &bv_type);
    if (bv_type == napi_number) { int64_t bv = 0; napi_get_value_int64(env, _args[4], &bv); base_vertex = (int32_t)bv; }
    napi_get_value_uint32(env, _args[5], &first_instance);
    if (pfn_doeNativeRenderBundleEncoderDrawIndexed)
        pfn_doeNativeRenderBundleEncoderDrawIndexed(enc, index_count, instance_count, first_index, base_vertex, first_instance);
    return NULL;
}

napi_value doe_render_bundle_encoder_finish(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    if (!pfn_doeNativeRenderBundleEncoderFinish) NAPI_THROW(env, "doeNativeRenderBundleEncoderFinish not available");
    void* enc = unwrap_ptr(env, _args[0]);
    if (!enc) NAPI_THROW(env, "renderBundleEncoderFinish: invalid encoder");
    void* bundle = pfn_doeNativeRenderBundleEncoderFinish(enc, NULL);
    if (!bundle) NAPI_THROW(env, "renderBundleEncoderFinish failed");
    return wrap_ptr(env, bundle);
}

napi_value doe_render_bundle_encoder_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* enc = unwrap_ptr(env, _args[0]);
    if (enc && pfn_doeNativeRenderBundleEncoderRelease) pfn_doeNativeRenderBundleEncoderRelease(enc);
    return NULL;
}

napi_value doe_render_bundle_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    void* bundle = unwrap_ptr(env, _args[0]);
    if (bundle && pfn_doeNativeRenderBundleRelease) pfn_doeNativeRenderBundleRelease(bundle);
    return NULL;
}
