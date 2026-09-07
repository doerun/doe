#include "doe_napi_internal.h"

typedef struct CanvasSurfaceBinding {
    WGPUSurface surface;
    void* host;
    struct CanvasSurfaceBinding* next;
} CanvasSurfaceBinding;

static CanvasSurfaceBinding* g_canvas_surface_bindings = NULL;

static CanvasSurfaceBinding* find_canvas_surface_binding(WGPUSurface surface) {
    CanvasSurfaceBinding* current = g_canvas_surface_bindings;
    while (current) {
        if (current->surface == surface) {
            return current;
        }
        current = current->next;
    }
    return NULL;
}

static void remove_canvas_surface_binding(WGPUSurface surface) {
    CanvasSurfaceBinding** current = &g_canvas_surface_bindings;
    while (*current) {
        if ((*current)->surface == surface) {
            CanvasSurfaceBinding* removed = *current;
            *current = removed->next;
            free(removed);
            return;
        }
        current = &(*current)->next;
    }
}

static void insert_canvas_surface_binding(WGPUSurface surface, void* host) {
    CanvasSurfaceBinding* binding = (CanvasSurfaceBinding*)calloc(1, sizeof(CanvasSurfaceBinding));
    if (!binding) {
        return;
    }
    binding->surface = surface;
    binding->host = host;
    binding->next = g_canvas_surface_bindings;
    g_canvas_surface_bindings = binding;
}

static int canvas_surface_api_ready(void) {
    return pfn_wgpuInstanceCreateSurface &&
        pfn_wgpuSurfaceConfigure &&
        pfn_wgpuSurfaceGetCurrentTexture &&
        pfn_wgpuSurfacePresent &&
        pfn_wgpuSurfaceUnconfigure &&
        pfn_wgpuSurfaceRelease &&
        pfn_metalBridgeCreateSurfaceHost &&
        pfn_metalBridgeConfigureSurfaceHost &&
        pfn_metalBridgeRelease;
}

static uint32_t canvas_surface_texture_status_ok(uint32_t status) {
    return status == WGPU_SURFACE_TEXTURE_STATUS_SUCCESS_OPTIMAL ||
        status == WGPU_SURFACE_TEXTURE_STATUS_SUCCESS_SUBOPTIMAL;
}

static uint32_t get_array_length_or_zero(napi_env env, napi_value value) {
    bool is_array = false;
    if (napi_is_array(env, value, &is_array) != napi_ok || !is_array) {
        return 0;
    }
    uint32_t length = 0;
    napi_get_array_length(env, value, &length);
    return length;
}

napi_value doe_canvas_surface_create(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    if (!canvas_surface_api_ready()) {
        NAPI_THROW(env, "native Metal canvas surface support is unavailable in the loaded runtime");
    }

    WGPUInstance instance = unwrap_ptr(env, _args[0]);
    if (!instance) {
        NAPI_THROW(env, "Invalid instance");
    }

    void* layer = NULL;
    void* host = pfn_metalBridgeCreateSurfaceHost(&layer);
    if (!host || !layer) {
        if (host && pfn_metalBridgeRelease) {
            pfn_metalBridgeRelease(host);
        }
        NAPI_THROW(env, "failed to create Metal surface host");
    }

    WGPUSurfaceSourceMetalLayer source = {
        .chain = {
            .next = NULL,
            .sType = WGPU_SURFACE_SOURCE_METAL_LAYER_STYPE,
        },
        .layer = layer,
    };
    WGPUSurfaceDescriptor descriptor = {
        .nextInChain = &source.chain,
        .label = { .data = NULL, .length = 0 },
    };
    WGPUSurface surface = pfn_wgpuInstanceCreateSurface(instance, &descriptor);
    if (!surface) {
        pfn_metalBridgeRelease(host);
        NAPI_THROW(env, "wgpuInstanceCreateSurface failed for Metal layer");
    }

    insert_canvas_surface_binding(surface, host);
    if (!find_canvas_surface_binding(surface)) {
        pfn_wgpuSurfaceRelease(surface);
        pfn_metalBridgeRelease(host);
        NAPI_THROW(env, "failed to track native Metal canvas surface");
    }
    return wrap_ptr(env, surface);
}

napi_value doe_canvas_surface_configure(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 3);
    CHECK_LIB_LOADED(env);
    if (!canvas_surface_api_ready()) {
        NAPI_THROW(env, "native Metal canvas surface support is unavailable in the loaded runtime");
    }

    WGPUSurface surface = unwrap_ptr(env, _args[0]);
    WGPUDevice device = unwrap_ptr(env, _args[1]);
    if (!surface || !device) {
        NAPI_THROW(env, "canvasSurfaceConfigure requires surface and device");
    }
    CanvasSurfaceBinding* binding = find_canvas_surface_binding(surface);
    if (!binding || !binding->host) {
        NAPI_THROW(env, "canvasSurfaceConfigure could not resolve the Metal surface host");
    }

    napi_value config = _args[2];
    uint32_t width = get_uint32_prop(env, config, "width");
    uint32_t height = get_uint32_prop(env, config, "height");
    if (width == 0 || height == 0) {
        NAPI_THROW(env, "canvasSurfaceConfigure requires positive width and height");
    }

    uint32_t format = texture_format_from_string(env, get_prop(env, config, "format"));
    uint64_t usage = (uint64_t)get_int64_prop(env, config, "usage");
    uint32_t alpha_mode = get_uint32_prop(env, config, "alphaMode");
    uint32_t present_mode = get_uint32_prop(env, config, "presentMode");

    napi_value view_formats_value = has_prop(env, config, "viewFormats")
        ? get_prop(env, config, "viewFormats")
        : NULL;
    uint32_t view_format_count = view_formats_value ? get_array_length_or_zero(env, view_formats_value) : 0;
    uint32_t* view_formats = NULL;
    if (view_format_count > 0) {
        view_formats = (uint32_t*)calloc(view_format_count, sizeof(uint32_t));
        if (!view_formats) {
            NAPI_THROW(env, "canvasSurfaceConfigure could not allocate viewFormats");
        }
        for (uint32_t index = 0; index < view_format_count; index += 1) {
            napi_value element;
            napi_get_element(env, view_formats_value, index, &element);
            view_formats[index] = texture_format_from_string(env, element);
        }
    }

    pfn_metalBridgeConfigureSurfaceHost(binding->host, width, height);
    WGPUSurfaceConfiguration configuration = {
        .nextInChain = NULL,
        .device = device,
        .format = format,
        .usage = usage,
        .width = width,
        .height = height,
        .viewFormatCount = view_format_count,
        .viewFormats = view_formats,
        .alphaMode = alpha_mode,
        .presentMode = present_mode,
    };
    pfn_wgpuSurfaceConfigure(surface, &configuration);
    if (view_formats) {
        free(view_formats);
    }
    return NULL;
}

napi_value doe_canvas_surface_get_current_texture(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    if (!canvas_surface_api_ready()) {
        NAPI_THROW(env, "native Metal canvas surface support is unavailable in the loaded runtime");
    }

    WGPUSurface surface = unwrap_ptr(env, _args[0]);
    if (!surface) {
        NAPI_THROW(env, "Invalid surface");
    }

    WGPUSurfaceTexture surface_texture;
    memset(&surface_texture, 0, sizeof(surface_texture));
    pfn_wgpuSurfaceGetCurrentTexture(surface, &surface_texture);
    if (!canvas_surface_texture_status_ok(surface_texture.status) || !surface_texture.texture) {
        NAPI_THROW(env, "wgpuSurfaceGetCurrentTexture failed");
    }
    return wrap_ptr(env, surface_texture.texture);
}

napi_value doe_canvas_surface_present(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    if (!canvas_surface_api_ready()) {
        NAPI_THROW(env, "native Metal canvas surface support is unavailable in the loaded runtime");
    }

    WGPUSurface surface = unwrap_ptr(env, _args[0]);
    if (!surface) {
        NAPI_THROW(env, "Invalid surface");
    }
    if (pfn_wgpuSurfacePresent(surface) != WGPU_STATUS_SUCCESS) {
        NAPI_THROW(env, "wgpuSurfacePresent failed");
    }
    return NULL;
}

napi_value doe_canvas_surface_unconfigure(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);
    if (!canvas_surface_api_ready()) {
        NAPI_THROW(env, "native Metal canvas surface support is unavailable in the loaded runtime");
    }

    WGPUSurface surface = unwrap_ptr(env, _args[0]);
    if (!surface) {
        NAPI_THROW(env, "Invalid surface");
    }
    pfn_wgpuSurfaceUnconfigure(surface);
    return NULL;
}

napi_value doe_canvas_surface_release(napi_env env, napi_callback_info info) {
    NAPI_ASSERT_ARGC(env, info, 1);
    CHECK_LIB_LOADED(env);

    WGPUSurface surface = unwrap_ptr(env, _args[0]);
    if (!surface) {
        return NULL;
    }

    CanvasSurfaceBinding* binding = find_canvas_surface_binding(surface);
    if (canvas_surface_api_ready()) {
        pfn_wgpuSurfaceUnconfigure(surface);
        pfn_wgpuSurfaceRelease(surface);
    }
    if (binding && binding->host && pfn_metalBridgeRelease) {
        pfn_metalBridgeRelease(binding->host);
    }
    remove_canvas_surface_binding(surface);
    return NULL;
}
