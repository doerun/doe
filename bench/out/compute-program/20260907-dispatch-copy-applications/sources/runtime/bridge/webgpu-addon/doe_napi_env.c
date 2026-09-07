#include "doe_napi_internal.h"

DoeEnvState* doe_env_state(napi_env env) {
    DoeEnvState* state = NULL;
    napi_get_instance_data(env, (void**)&state);
    return state;
}

static void env_cleanup(void* data) {
    DoeEnvState* state = (DoeEnvState*)data;
    // Cleanup hooks run before Node independently finalizes TSFNs and instance data.
    while (state->uncaptured_bindings) {
        DeviceCallbackBinding* binding = state->uncaptured_bindings;
        state->uncaptured_bindings = binding->next;
        pfn_doeNativeDeviceSetUncapturedErrorCallback(binding->device, NULL, NULL, NULL);
        release_binding(binding);
    }
    while (state->lost_bindings) {
        DeviceCallbackBinding* binding = state->lost_bindings;
        state->lost_bindings = binding->next;
        pfn_doeNativeDeviceRegisterLostCallback(binding->device, NULL, NULL);
        release_binding(binding);
    }
}

static void env_finalize(napi_env env, void* data, void* hint) {
    (void)env;
    (void)hint;
    // N-API owns reference teardown; cached references never outlive this environment.
    free(data);
}

bool doe_env_init(napi_env env) {
    DoeEnvState* state = (DoeEnvState*)calloc(1, sizeof(DoeEnvState));
    if (!state) return false;
    state->timeout_ns = DOE_DEFAULT_TIMEOUT_NS;
    const char* timeout = getenv("DOE_TIMEOUT_MS");
    if (timeout && timeout[0] != '\0') {
        char* end = NULL;
        unsigned long parsed = strtoul(timeout, &end, 10);
        if (end && *end == '\0') state->timeout_ns = (uint64_t)parsed * 1000000ULL;
    }
    if (napi_add_env_cleanup_hook(env, env_cleanup, state) != napi_ok) {
        free(state);
        return false;
    }
    if (napi_set_instance_data(env, state, env_finalize, NULL) != napi_ok) {
        napi_remove_env_cleanup_hook(env, env_cleanup, state);
        free(state);
        return false;
    }
    return true;
}
