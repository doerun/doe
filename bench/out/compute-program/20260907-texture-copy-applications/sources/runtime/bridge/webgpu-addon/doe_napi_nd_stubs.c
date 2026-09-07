#include "doe_napi_internal.h"

/* Forward declaration for render bundle encoder setImmediates (defined in doe_napi_nd_encoder.c) */
napi_value native_direct_render_bundle_encoder_set_immediates(napi_env env, napi_callback_info info);

/* addEventListener/removeEventListener are DOM EventTarget APIs. The native
 * Doe runtime does not expose a DOM event source, so these methods fail
 * explicitly instead of silently accepting listener registration. */
napi_value native_direct_device_add_event_listener(napi_env env, napi_callback_info info) {
    (void)info;
    napi_throw_type_error(env, "DOE_UNSUPPORTED",
        "device.addEventListener is not supported in the native Doe runtime "
        "(no DOM event source is available)");
    return NULL;
}

napi_value native_direct_device_remove_event_listener(napi_env env, napi_callback_info info) {
    (void)info;
    napi_throw_type_error(env, "DOE_UNSUPPORTED",
        "device.removeEventListener is not supported in the native Doe runtime "
        "(no DOM event source is available)");
    return NULL;
}

/* External texture import requires platform video-frame OS APIs that are
 * not available in the Doe headless runtime. Throw a TypeError with a
 * clear unsupported message so callers get actionable feedback. */
napi_value native_direct_device_import_external_texture(napi_env env, napi_callback_info info) {
    (void)info;
    napi_throw_type_error(env, "DOE_UNSUPPORTED",
        "importExternalTexture is not supported in this runtime "
        "(external video frame import requires platform-specific OS APIs)");
    return NULL;
}

/* create_native_direct_render_bundle_encoder_object: wraps a WGPURenderBundleEncoder
 * with setImmediates registered. The render bundle encoder is not yet plumbed through
 * the full native-direct object model; this creator is provided so that callers
 * constructing bundle encoders can attach setImmediates without special-casing. */
napi_value __attribute__((unused))
create_native_direct_render_bundle_encoder_object(napi_env env, void* encoder) {
    napi_value obj;
    napi_create_object(env, &obj);
    native_direct_set_external_prop(env, obj, DOE_DIRECT_NATIVE, encoder);
    native_direct_wrap_handle_cache(env, obj, NULL, encoder);
    /* GPURenderBundleEncoder#setImmediates (GPUBindingCommandsMixin) */
    native_direct_add_cached_method(env, obj, "setImmediates", native_direct_render_bundle_encoder_set_immediates, &native_direct_method_render_bundle_encoder_set_immediates_ref);
    return obj;
}
