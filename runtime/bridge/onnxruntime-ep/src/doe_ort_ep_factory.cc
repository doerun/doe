#include "doe_ort_ep_factory.h"
#include "doe_ort_ep.h"

#include <cstddef>
#include <string>
#include <utility>

namespace doe::ort_ep {

namespace {

constexpr const char* kDefaultRegistrationName = "DoeExecutionProvider";
constexpr const char* kVendorName = "Doe";
constexpr const char* kVersion = "0.0.4-basic-ops";
constexpr uint32_t kVendorId = 0;

std::string BuildUnsupportedMessage(const DoeOrtEpFactory& factory, const char* operation) {
  std::string message = "Doe ORT plugin EP remains intentionally narrow; ";
  message += operation;
  message += " is not implemented for registration '";
  message += factory.GetName(&factory);
  message += "'.";
  return message;
}

}  // namespace

OrtStatus* MakeStatus(const OrtApi* api, OrtErrorCode code, const char* message) {
  if (api == nullptr) return nullptr;
  return api->CreateStatus(code, message);
}

DoeOrtEpFactory::DoeOrtEpFactory(std::string registration_name, ApiBindings bindings)
    : OrtEpFactory{},
      registration_name_(registration_name.empty() ? kDefaultRegistrationName : std::move(registration_name)),
      bindings_(bindings) {
  ort_version_supported = kOrtPluginEpRuntimeApiVersion;
  GetName = &GetNameImpl;
  GetVendor = &GetVendorImpl;
  GetSupportedDevices = &GetSupportedDevicesImpl;
  CreateEp = &CreateEpImpl;
  ReleaseEp = &ReleaseEpImpl;
  GetVendorId = &GetVendorIdImpl;
  GetVersion = &GetVersionImpl;
  ValidateCompiledModelCompatibilityInfo = &ValidateCompiledModelCompatibilityInfoImpl;
  CreateAllocator = &CreateAllocatorImpl;
  ReleaseAllocator = &ReleaseAllocatorImpl;
  CreateDataTransfer = &CreateDataTransferImpl;
  IsStreamAware = &IsStreamAwareImpl;
  CreateSyncStreamForDevice = &CreateSyncStreamForDeviceImpl;
  GetHardwareDeviceIncompatibilityDetails = &GetHardwareDeviceIncompatibilityDetailsImpl;
  CreateExternalResourceImporterForDevice = &CreateExternalResourceImporterForDeviceImpl;
  GetNumCustomOpDomains = &GetNumCustomOpDomainsImpl;
  GetCustomOpDomains = &GetCustomOpDomainsImpl;
  InitGraphicsInterop = &InitGraphicsInteropImpl;
  DeinitGraphicsInterop = &DeinitGraphicsInteropImpl;
}

DoeOrtEpFactory& DoeOrtEpFactory::Self(OrtEpFactory* this_ptr) {
  return *static_cast<DoeOrtEpFactory*>(this_ptr);
}

const DoeOrtEpFactory& DoeOrtEpFactory::Self(const OrtEpFactory* this_ptr) {
  return *static_cast<const DoeOrtEpFactory*>(this_ptr);
}

OrtStatus* DoeOrtEpFactory::UnsupportedStatus(const char* operation) const {
  const std::string message = BuildUnsupportedMessage(*this, operation);
  return MakeStatus(bindings_.api, ORT_NOT_IMPLEMENTED, message.c_str());
}

const char* ORT_API_CALL DoeOrtEpFactory::GetNameImpl(const OrtEpFactory* this_ptr) NO_EXCEPTION {
  return Self(this_ptr).registration_name_.c_str();
}

const char* ORT_API_CALL DoeOrtEpFactory::GetVendorImpl(const OrtEpFactory* this_ptr) NO_EXCEPTION {
  (void)this_ptr;
  return kVendorName;
}

OrtStatus* ORT_API_CALL DoeOrtEpFactory::GetSupportedDevicesImpl(
    OrtEpFactory* this_ptr,
    const OrtHardwareDevice* const* devices,
    size_t num_devices,
    OrtEpDevice** ep_devices,
    size_t max_ep_devices,
    size_t* num_ep_devices) NO_EXCEPTION {
  if (num_ep_devices == nullptr) {
    return MakeStatus(Self(this_ptr).bindings_.api, ORT_INVALID_ARGUMENT, "Doe ORT plugin EP requires a num_ep_devices output pointer.");
  }
  *num_ep_devices = 0;
  if (ep_devices != nullptr) {
    for (size_t index = 0; index < max_ep_devices; ++index) {
      ep_devices[index] = nullptr;
    }
  }
  if (devices == nullptr || num_devices == 0) {
    return nullptr;
  }
  if (Self(this_ptr).bindings_.ep_api == nullptr) {
    return MakeStatus(Self(this_ptr).bindings_.api, ORT_NOT_IMPLEMENTED, "Doe ORT plugin EP requires OrtEpApi to create OrtEpDevice instances.");
  }
  size_t produced = 0;
  for (size_t index = 0; index < num_devices && produced < max_ep_devices; ++index) {
    OrtEpDevice* ep_device = nullptr;
    OrtStatus* status = Self(this_ptr).bindings_.ep_api->CreateEpDevice(
        this_ptr,
        devices[index],
        nullptr,
        nullptr,
        &ep_device);
    if (status != nullptr) {
      return status;
    }
    if (ep_devices != nullptr) {
      ep_devices[produced] = ep_device;
    }
    produced += 1;
  }
  *num_ep_devices = produced;
  return nullptr;
}

OrtStatus* ORT_API_CALL DoeOrtEpFactory::CreateEpImpl(
    OrtEpFactory* this_ptr,
    const OrtHardwareDevice* const* devices,
    const OrtKeyValuePairs* const* ep_metadata_pairs,
    size_t num_devices,
    const OrtSessionOptions* session_options,
    const OrtLogger* logger,
    OrtEp** ep) NO_EXCEPTION {
  (void)devices;
  (void)ep_metadata_pairs;
  (void)num_devices;
  (void)session_options;
  (void)logger;
  if (ep != nullptr) {
    *ep = new (std::nothrow) DoeOrtEp(Self(this_ptr).GetName(this_ptr), Self(this_ptr).bindings_);
    if (*ep == nullptr) {
      return MakeStatus(Self(this_ptr).bindings_.api, ORT_FAIL, "Doe ORT plugin EP failed to allocate its OrtEp instance.");
    }
  }
  return nullptr;
}

void ORT_API_CALL DoeOrtEpFactory::ReleaseEpImpl(OrtEpFactory* this_ptr, OrtEp* ep) NO_EXCEPTION {
  (void)this_ptr;
  delete static_cast<DoeOrtEp*>(ep);
}

uint32_t ORT_API_CALL DoeOrtEpFactory::GetVendorIdImpl(const OrtEpFactory* this_ptr) NO_EXCEPTION {
  (void)this_ptr;
  return kVendorId;
}

const char* ORT_API_CALL DoeOrtEpFactory::GetVersionImpl(const OrtEpFactory* this_ptr) NO_EXCEPTION {
  (void)this_ptr;
  return kVersion;
}

OrtStatus* ORT_API_CALL DoeOrtEpFactory::ValidateCompiledModelCompatibilityInfoImpl(
    OrtEpFactory* this_ptr,
    const OrtHardwareDevice* const* devices,
    size_t num_devices,
    const char* compatibility_info,
    OrtCompiledModelCompatibility* model_compatibility) NO_EXCEPTION {
  (void)devices;
  (void)num_devices;
  (void)compatibility_info;
  if (model_compatibility == nullptr) {
    return MakeStatus(Self(this_ptr).bindings_.api, ORT_INVALID_ARGUMENT, "Doe ORT plugin EP requires a model_compatibility output pointer.");
  }
  *model_compatibility = OrtCompiledModelCompatibility_EP_UNSUPPORTED;
  return nullptr;
}

OrtStatus* ORT_API_CALL DoeOrtEpFactory::CreateAllocatorImpl(
    OrtEpFactory* this_ptr,
    const OrtMemoryInfo* memory_info,
    const OrtKeyValuePairs* allocator_options,
    OrtAllocator** allocator) NO_EXCEPTION {
  (void)this_ptr;
  (void)memory_info;
  (void)allocator_options;
  if (allocator != nullptr) {
    *allocator = nullptr;
  }
  return nullptr;
}

void ORT_API_CALL DoeOrtEpFactory::ReleaseAllocatorImpl(OrtEpFactory* this_ptr, OrtAllocator* allocator) NO_EXCEPTION {
  (void)this_ptr;
  (void)allocator;
}

OrtStatus* ORT_API_CALL DoeOrtEpFactory::CreateDataTransferImpl(
    OrtEpFactory* this_ptr,
    OrtDataTransferImpl** data_transfer) NO_EXCEPTION {
  (void)this_ptr;
  if (data_transfer != nullptr) {
    *data_transfer = nullptr;
  }
  return nullptr;
}

bool ORT_API_CALL DoeOrtEpFactory::IsStreamAwareImpl(const OrtEpFactory* this_ptr) NO_EXCEPTION {
  (void)this_ptr;
  return false;
}

OrtStatus* ORT_API_CALL DoeOrtEpFactory::CreateSyncStreamForDeviceImpl(
    OrtEpFactory* this_ptr,
    const OrtMemoryDevice* memory_device,
    const OrtKeyValuePairs* stream_options,
    OrtSyncStreamImpl** stream) NO_EXCEPTION {
  (void)this_ptr;
  (void)memory_device;
  (void)stream_options;
  if (stream != nullptr) {
    *stream = nullptr;
  }
  return nullptr;
}

OrtStatus* ORT_API_CALL DoeOrtEpFactory::GetHardwareDeviceIncompatibilityDetailsImpl(
    OrtEpFactory* this_ptr,
    const OrtHardwareDevice* hw,
    OrtDeviceEpIncompatibilityDetails* details) NO_EXCEPTION {
  (void)this_ptr;
  (void)hw;
  (void)details;
  return nullptr;
}

OrtStatus* ORT_API_CALL DoeOrtEpFactory::CreateExternalResourceImporterForDeviceImpl(
    OrtEpFactory* this_ptr,
    const OrtEpDevice* ep_device,
    OrtExternalResourceImporterImpl** out_importer) NO_EXCEPTION {
  (void)this_ptr;
  (void)ep_device;
  if (out_importer != nullptr) {
    *out_importer = nullptr;
  }
  return nullptr;
}

OrtStatus* ORT_API_CALL DoeOrtEpFactory::GetNumCustomOpDomainsImpl(OrtEpFactory* this_ptr, size_t* num_domains) NO_EXCEPTION {
  if (num_domains == nullptr) {
    return MakeStatus(Self(this_ptr).bindings_.api, ORT_INVALID_ARGUMENT, "Doe ORT plugin EP requires a num_domains output pointer.");
  }
  *num_domains = 0;
  return nullptr;
}

OrtStatus* ORT_API_CALL DoeOrtEpFactory::GetCustomOpDomainsImpl(
    OrtEpFactory* this_ptr,
    OrtCustomOpDomain** domains,
    size_t num_domains) NO_EXCEPTION {
  (void)domains;
  if (num_domains == 0) {
    return nullptr;
  }
  return MakeStatus(Self(this_ptr).bindings_.api, ORT_INVALID_ARGUMENT, "Doe ORT plugin EP does not expose custom-op domains yet.");
}

OrtStatus* ORT_API_CALL DoeOrtEpFactory::InitGraphicsInteropImpl(
    OrtEpFactory* this_ptr,
    const OrtEpDevice* ep_device,
    const OrtGraphicsInteropConfig* config) NO_EXCEPTION {
  (void)ep_device;
  (void)config;
  return Self(this_ptr).UnsupportedStatus("InitGraphicsInterop");
}

OrtStatus* ORT_API_CALL DoeOrtEpFactory::DeinitGraphicsInteropImpl(
    OrtEpFactory* this_ptr,
    const OrtEpDevice* ep_device) NO_EXCEPTION {
  (void)ep_device;
  return Self(this_ptr).UnsupportedStatus("DeinitGraphicsInterop");
}

}  // namespace doe::ort_ep
