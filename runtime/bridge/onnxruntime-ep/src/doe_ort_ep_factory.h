#pragma once

#include "doe_ort_ep_api_version.h"

#include "../vendor/onnxruntime/include/onnxruntime_c_api.h"

#include <string>

namespace doe::ort_ep {

struct ApiBindings {
  const OrtApiBase* api_base;
  const OrtApi* api;
  const OrtEpApi* ep_api;
  const OrtLogger* default_logger;
};

OrtStatus* MakeStatus(const OrtApi* api, OrtErrorCode code, const char* message);

class DoeOrtEpFactory final : public OrtEpFactory {
 public:
  DoeOrtEpFactory(std::string registration_name, ApiBindings bindings);

 private:
  static DoeOrtEpFactory& Self(OrtEpFactory* this_ptr);
  static const DoeOrtEpFactory& Self(const OrtEpFactory* this_ptr);

  OrtStatus* UnsupportedStatus(const char* operation) const;

  static const char* ORT_API_CALL GetNameImpl(const OrtEpFactory* this_ptr) NO_EXCEPTION;
  static const char* ORT_API_CALL GetVendorImpl(const OrtEpFactory* this_ptr) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL GetSupportedDevicesImpl(
      OrtEpFactory* this_ptr,
      const OrtHardwareDevice* const* devices,
      size_t num_devices,
      OrtEpDevice** ep_devices,
      size_t max_ep_devices,
      size_t* num_ep_devices) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL CreateEpImpl(
      OrtEpFactory* this_ptr,
      const OrtHardwareDevice* const* devices,
      const OrtKeyValuePairs* const* ep_metadata_pairs,
      size_t num_devices,
      const OrtSessionOptions* session_options,
      const OrtLogger* logger,
      OrtEp** ep) NO_EXCEPTION;
  static void ORT_API_CALL ReleaseEpImpl(OrtEpFactory* this_ptr, OrtEp* ep) NO_EXCEPTION;
  static uint32_t ORT_API_CALL GetVendorIdImpl(const OrtEpFactory* this_ptr) NO_EXCEPTION;
  static const char* ORT_API_CALL GetVersionImpl(const OrtEpFactory* this_ptr) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL ValidateCompiledModelCompatibilityInfoImpl(
      OrtEpFactory* this_ptr,
      const OrtHardwareDevice* const* devices,
      size_t num_devices,
      const char* compatibility_info,
      OrtCompiledModelCompatibility* model_compatibility) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL CreateAllocatorImpl(
      OrtEpFactory* this_ptr,
      const OrtMemoryInfo* memory_info,
      const OrtKeyValuePairs* allocator_options,
      OrtAllocator** allocator) NO_EXCEPTION;
  static void ORT_API_CALL ReleaseAllocatorImpl(OrtEpFactory* this_ptr, OrtAllocator* allocator) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL CreateDataTransferImpl(
      OrtEpFactory* this_ptr,
      OrtDataTransferImpl** data_transfer) NO_EXCEPTION;
  static bool ORT_API_CALL IsStreamAwareImpl(const OrtEpFactory* this_ptr) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL CreateSyncStreamForDeviceImpl(
      OrtEpFactory* this_ptr,
      const OrtMemoryDevice* memory_device,
      const OrtKeyValuePairs* stream_options,
      OrtSyncStreamImpl** stream) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL GetHardwareDeviceIncompatibilityDetailsImpl(
      OrtEpFactory* this_ptr,
      const OrtHardwareDevice* hw,
      OrtDeviceEpIncompatibilityDetails* details) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL CreateExternalResourceImporterForDeviceImpl(
      OrtEpFactory* this_ptr,
      const OrtEpDevice* ep_device,
      OrtExternalResourceImporterImpl** out_importer) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL GetNumCustomOpDomainsImpl(OrtEpFactory* this_ptr, size_t* num_domains) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL GetCustomOpDomainsImpl(
      OrtEpFactory* this_ptr,
      OrtCustomOpDomain** domains,
      size_t num_domains) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL InitGraphicsInteropImpl(
      OrtEpFactory* this_ptr,
      const OrtEpDevice* ep_device,
      const OrtGraphicsInteropConfig* config) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL DeinitGraphicsInteropImpl(
      OrtEpFactory* this_ptr,
      const OrtEpDevice* ep_device) NO_EXCEPTION;

  std::string registration_name_;
  ApiBindings bindings_;
};

}  // namespace doe::ort_ep
