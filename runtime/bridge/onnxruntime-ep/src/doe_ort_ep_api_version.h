#pragma once

#include "../vendor/onnxruntime/include/onnxruntime_c_api.h"

#include <cstdint>

namespace doe::ort_ep {

constexpr uint32_t kOrtPluginEpRuntimeApiVersion = 23;

static_assert(
    ORT_API_VERSION >= kOrtPluginEpRuntimeApiVersion,
    "Doe ORT plugin EP runtime API floor must not exceed the vendored ORT header API version.");

}  // namespace doe::ort_ep
