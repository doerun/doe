#include "doe_ort_ep.h"

#include <new>

#ifdef _WIN32
#define DOE_ORT_EP_EXPORT __declspec(dllexport)
#else
#define DOE_ORT_EP_EXPORT __attribute__((visibility("default")))
#endif

extern "C" {

DOE_ORT_EP_EXPORT OrtStatus* CreateEpFactories(
    const char* registered_name,
    const OrtApiBase* ort_api_base,
    const OrtLogger* default_logger,
    OrtEpFactory** factories,
    size_t max_factories,
    size_t* num_factories) {
  const OrtApi* ort_api = ort_api_base != nullptr ? ort_api_base->GetApi(doe::ort_ep::kOrtPluginEpRuntimeApiVersion) : nullptr;
  if (num_factories != nullptr) {
    *num_factories = 0;
  }
  if (factories == nullptr || num_factories == nullptr) {
    return doe::ort_ep::MakeStatus(ort_api, ORT_INVALID_ARGUMENT, "Doe ORT plugin EP requires factories and num_factories output pointers.");
  }
  if (max_factories < 1) {
    return doe::ort_ep::MakeStatus(ort_api, ORT_INVALID_ARGUMENT, "Doe ORT plugin EP requires space for at least one factory.");
  }

  auto* factory = new (std::nothrow) doe::ort_ep::DoeOrtEpFactory(
      registered_name == nullptr ? "" : registered_name,
      doe::ort_ep::ApiBindings{
          .api_base = ort_api_base,
          .api = ort_api,
          .ep_api = ort_api != nullptr ? ort_api->GetEpApi() : nullptr,
          .default_logger = default_logger,
      });
  if (factory == nullptr) {
    return doe::ort_ep::MakeStatus(ort_api, ORT_FAIL, "Doe ORT plugin EP failed to allocate its factory.");
  }

  factories[0] = factory;
  *num_factories = 1;
  return nullptr;
}

DOE_ORT_EP_EXPORT OrtStatus* ReleaseEpFactory(OrtEpFactory* factory) {
  delete static_cast<doe::ort_ep::DoeOrtEpFactory*>(factory);
  return nullptr;
}

DOE_ORT_EP_EXPORT void DoeOrtEpResetDebugCounters() {
  doe::ort_ep::ResetDebugCounters();
}

DOE_ORT_EP_EXPORT void DoeOrtEpGetDebugCounters(doe::ort_ep::DoeOrtEpDebugCounters* out) {
  if (out == nullptr) {
    return;
  }
  *out = doe::ort_ep::SnapshotDebugCounters();
}

}  // extern "C"
