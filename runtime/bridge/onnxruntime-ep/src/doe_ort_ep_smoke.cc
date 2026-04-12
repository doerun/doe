#include "../vendor/onnxruntime/include/onnxruntime_c_api.h"
#include "doe_ort_ep_api_version.h"

#include <cstddef>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <optional>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

#ifdef _WIN32
#include <windows.h>
#else
#include <dlfcn.h>
#endif

namespace {

constexpr size_t kMaxFactories = 4;
constexpr size_t kMaxEpDevices = 8;
constexpr const char* kDefaultRegistrationName = "DoeExecutionProvider";

using OrtGetApiBaseFn = const OrtApiBase* (*)();

std::string JsonEscape(const std::string& value) {
  std::string escaped;
  escaped.reserve(value.size() + 8);
  for (const char ch : value) {
    switch (ch) {
      case '\\':
        escaped += "\\\\";
        break;
      case '"':
        escaped += "\\\"";
        break;
      case '\n':
        escaped += "\\n";
        break;
      case '\r':
        escaped += "\\r";
        break;
      case '\t':
        escaped += "\\t";
        break;
      default:
        if (static_cast<unsigned char>(ch) < 0x20) {
          const char digits[] = "0123456789abcdef";
          escaped += "\\u00";
          escaped += digits[(ch >> 4) & 0x0f];
          escaped += digits[ch & 0x0f];
        } else {
          escaped += ch;
        }
        break;
    }
  }
  return escaped;
}

const char* ErrorCodeName(const OrtErrorCode code) {
  switch (code) {
    case ORT_OK:
      return "ORT_OK";
    case ORT_FAIL:
      return "ORT_FAIL";
    case ORT_INVALID_ARGUMENT:
      return "ORT_INVALID_ARGUMENT";
    case ORT_NO_SUCHFILE:
      return "ORT_NO_SUCHFILE";
    case ORT_NO_MODEL:
      return "ORT_NO_MODEL";
    case ORT_ENGINE_ERROR:
      return "ORT_ENGINE_ERROR";
    case ORT_RUNTIME_EXCEPTION:
      return "ORT_RUNTIME_EXCEPTION";
    case ORT_INVALID_PROTOBUF:
      return "ORT_INVALID_PROTOBUF";
    case ORT_MODEL_LOADED:
      return "ORT_MODEL_LOADED";
    case ORT_NOT_IMPLEMENTED:
      return "ORT_NOT_IMPLEMENTED";
    case ORT_INVALID_GRAPH:
      return "ORT_INVALID_GRAPH";
    case ORT_EP_FAIL:
      return "ORT_EP_FAIL";
    default:
      return "ORT_ERROR_UNKNOWN";
  }
}

const char* CompatibilityName(const OrtCompiledModelCompatibility compatibility) {
  switch (compatibility) {
    case OrtCompiledModelCompatibility_EP_NOT_APPLICABLE:
      return "OrtCompiledModelCompatibility_EP_NOT_APPLICABLE";
    case OrtCompiledModelCompatibility_EP_SUPPORTED_OPTIMAL:
      return "OrtCompiledModelCompatibility_EP_SUPPORTED_OPTIMAL";
    case OrtCompiledModelCompatibility_EP_SUPPORTED_PREFER_RECOMPILATION:
      return "OrtCompiledModelCompatibility_EP_SUPPORTED_PREFER_RECOMPILATION";
    case OrtCompiledModelCompatibility_EP_UNSUPPORTED:
      return "OrtCompiledModelCompatibility_EP_UNSUPPORTED";
    default:
      return "OrtCompiledModelCompatibility_UNKNOWN";
  }
}

struct CliOptions {
  std::string plugin_path;
  std::string ort_lib_path;
  std::string registration_name = kDefaultRegistrationName;
  std::optional<std::string> output_path;
};

struct StatusInfo {
  bool ok = true;
  std::string code = ErrorCodeName(ORT_OK);
  std::string message;
};

struct SmokeReport {
  bool success = false;
  std::string failure_reason;
  std::string plugin_path;
  std::string ort_lib_path;
  std::string ort_runtime_version;
  uint32_t ort_header_api_version = ORT_API_VERSION;
  uint32_t ort_api_version_requested = doe::ort_ep::kOrtPluginEpRuntimeApiVersion;
  uint32_t factory_ort_version_supported = 0;
  std::string factory_name;
  std::string factory_vendor;
  uint32_t factory_vendor_id = 0;
  std::string factory_version;
  size_t factory_count = 0;
  size_t supported_ep_device_count = 0;
  std::string compatibility_name = CompatibilityName(OrtCompiledModelCompatibility_EP_NOT_APPLICABLE);
  StatusInfo create_factories_status;
  StatusInfo get_supported_devices_status;
  StatusInfo validate_compiled_model_status;
  StatusInfo create_ep_status;
};

class DynamicLibrary {
 public:
  DynamicLibrary(std::string path, std::string* error_out) : path_(std::move(path)) {
#ifdef _WIN32
    handle_ = LoadLibraryA(path_.c_str());
    if (handle_ == nullptr && error_out != nullptr) {
      *error_out = "LoadLibraryA failed for '" + path_ + "'.";
    }
#else
    handle_ = dlopen(path_.c_str(), RTLD_NOW | RTLD_LOCAL);
    if (handle_ == nullptr && error_out != nullptr) {
      const char* dl_error = dlerror();
      *error_out = "dlopen failed for '" + path_ + "'";
      if (dl_error != nullptr) {
        *error_out += ": ";
        *error_out += dl_error;
      }
    }
#endif
  }

  DynamicLibrary(const DynamicLibrary&) = delete;
  DynamicLibrary& operator=(const DynamicLibrary&) = delete;

  ~DynamicLibrary() {
#ifdef _WIN32
    if (handle_ != nullptr) {
      FreeLibrary(handle_);
    }
#else
    if (handle_ != nullptr) {
      dlclose(handle_);
    }
#endif
  }

  bool IsOpen() const {
    return handle_ != nullptr;
  }

  template <typename Fn>
  Fn LoadSymbol(const char* name, std::string* error_out) const {
    if (handle_ == nullptr) {
      if (error_out != nullptr) {
        *error_out = "library handle for '" + path_ + "' is not open.";
      }
      return nullptr;
    }
#ifdef _WIN32
    auto* symbol = reinterpret_cast<Fn>(GetProcAddress(handle_, name));
    if (symbol == nullptr && error_out != nullptr) {
      *error_out = "GetProcAddress failed for symbol '" + std::string(name) + "' in '" + path_ + "'.";
    }
    return symbol;
#else
    dlerror();
    auto* symbol = reinterpret_cast<Fn>(dlsym(handle_, name));
    const char* dl_error = dlerror();
    if (dl_error != nullptr) {
      if (error_out != nullptr) {
        *error_out = "dlsym failed for symbol '" + std::string(name) + "' in '" + path_ + "': " + dl_error;
      }
      return nullptr;
    }
    return symbol;
#endif
  }

 private:
  std::string path_;
#ifdef _WIN32
  HMODULE handle_ = nullptr;
#else
  void* handle_ = nullptr;
#endif
};

std::vector<std::string> DefaultOrtLibraryCandidates() {
#ifdef _WIN32
  return {"onnxruntime.dll"};
#elif defined(__APPLE__)
  return {
      "libonnxruntime.dylib",
      "/usr/local/lib/libonnxruntime.dylib",
      "/opt/homebrew/lib/libonnxruntime.dylib",
  };
#else
  return {
      "libonnxruntime.so",
      "libonnxruntime.so.1.23",
      "/usr/lib/x86_64-linux-gnu/libonnxruntime.so.1.23",
  };
#endif
}

std::optional<CliOptions> ParseArgs(const int argc, char** argv, std::string* error_out) {
  CliOptions options;
  for (int index = 1; index < argc; ++index) {
    const std::string argument = argv[index];
    auto require_value = [&](const char* flag) -> const char* {
      if (index + 1 >= argc) {
        if (error_out != nullptr) {
          *error_out = std::string("missing value for ") + flag + ".";
        }
        return nullptr;
      }
      return argv[++index];
    };
    if (argument == "--plugin-path") {
      const char* value = require_value("--plugin-path");
      if (value == nullptr) return std::nullopt;
      options.plugin_path = value;
    } else if (argument == "--ort-lib-path") {
      const char* value = require_value("--ort-lib-path");
      if (value == nullptr) return std::nullopt;
      options.ort_lib_path = value;
    } else if (argument == "--registration-name") {
      const char* value = require_value("--registration-name");
      if (value == nullptr) return std::nullopt;
      options.registration_name = value;
    } else if (argument == "--output") {
      const char* value = require_value("--output");
      if (value == nullptr) return std::nullopt;
      options.output_path = value;
    } else if (argument == "--help" || argument == "-h") {
      std::cout
          << "Usage: doe-ort-ep-smoke --plugin-path <path> [--ort-lib-path <path>] [--registration-name <name>] [--output <path>]\n";
      std::exit(0);
    } else {
      if (error_out != nullptr) {
        *error_out = "unknown argument '" + argument + "'.";
      }
      return std::nullopt;
    }
  }

  if (options.plugin_path.empty()) {
    if (error_out != nullptr) {
      *error_out = "missing required --plugin-path.";
    }
    return std::nullopt;
  }

  if (options.ort_lib_path.empty()) {
    for (const auto& candidate : DefaultOrtLibraryCandidates()) {
      std::string error;
      DynamicLibrary library(candidate, &error);
      if (library.IsOpen()) {
        options.ort_lib_path = candidate;
        break;
      }
    }
    if (options.ort_lib_path.empty()) {
      if (error_out != nullptr) {
        *error_out = "unable to locate an ONNX Runtime shared library; pass --ort-lib-path explicitly.";
      }
      return std::nullopt;
    }
  }

  return options;
}

StatusInfo CaptureStatus(const OrtApi* api, OrtStatus* status) {
  StatusInfo info{};
  if (status == nullptr) {
    return info;
  }
  info.ok = false;
  if (api != nullptr) {
    info.code = ErrorCodeName(api->GetErrorCode(status));
    const char* message = api->GetErrorMessage(status);
    info.message = message != nullptr ? message : "";
    api->ReleaseStatus(status);
  } else {
    info.code = "ORT_ERROR_UNKNOWN";
    info.message = "status returned but OrtApi was null.";
  }
  return info;
}

std::string RenderReportJson(const SmokeReport& report) {
  std::ostringstream json;
  json << "{\n";
  json << "  \"success\": " << (report.success ? "true" : "false") << ",\n";
  json << "  \"failureReason\": \"" << JsonEscape(report.failure_reason) << "\",\n";
  json << "  \"pluginPath\": \"" << JsonEscape(report.plugin_path) << "\",\n";
  json << "  \"ortLibraryPath\": \"" << JsonEscape(report.ort_lib_path) << "\",\n";
  json << "  \"ortRuntimeVersion\": \"" << JsonEscape(report.ort_runtime_version) << "\",\n";
  json << "  \"ortHeaderApiVersion\": " << report.ort_header_api_version << ",\n";
  json << "  \"ortApiVersionRequested\": " << report.ort_api_version_requested << ",\n";
  json << "  \"factory\": {\n";
  json << "    \"count\": " << report.factory_count << ",\n";
  json << "    \"ortVersionSupported\": " << report.factory_ort_version_supported << ",\n";
  json << "    \"name\": \"" << JsonEscape(report.factory_name) << "\",\n";
  json << "    \"vendor\": \"" << JsonEscape(report.factory_vendor) << "\",\n";
  json << "    \"vendorId\": " << report.factory_vendor_id << ",\n";
  json << "    \"version\": \"" << JsonEscape(report.factory_version) << "\"\n";
  json << "  },\n";
  json << "  \"operations\": {\n";
  auto render_status = [&](const char* label, const StatusInfo& status, const std::string& extra_field) {
    json << "    \"" << label << "\": {\n";
    json << "      \"ok\": " << (status.ok ? "true" : "false") << ",\n";
    json << "      \"code\": \"" << JsonEscape(status.code) << "\",\n";
    json << "      \"message\": \"" << JsonEscape(status.message) << "\"";
    if (!extra_field.empty()) {
      json << ",\n" << extra_field << "\n";
    } else {
      json << "\n";
    }
    json << "    }";
  };
  render_status(
      "createEpFactories",
      report.create_factories_status,
      "      \"factoryCount\": " + std::to_string(report.factory_count));
  json << ",\n";
  render_status(
      "getSupportedDevices",
      report.get_supported_devices_status,
      "      \"epDeviceCount\": " + std::to_string(report.supported_ep_device_count));
  json << ",\n";
  render_status(
      "validateCompiledModelCompatibilityInfo",
      report.validate_compiled_model_status,
      "      \"compatibility\": \"" + JsonEscape(report.compatibility_name) + "\"");
  json << ",\n";
  render_status("createEp", report.create_ep_status, "");
  json << "\n";
  json << "  }\n";
  json << "}\n";
  return json.str();
}

bool WriteOutputIfRequested(const std::optional<std::string>& output_path, const std::string& contents, std::string* error_out) {
  if (!output_path.has_value()) {
    return true;
  }
  std::ofstream stream(*output_path, std::ios::binary | std::ios::trunc);
  if (!stream.is_open()) {
    if (error_out != nullptr) {
      *error_out = "failed to open output path '" + *output_path + "'.";
    }
    return false;
  }
  stream << contents;
  if (!stream.good()) {
    if (error_out != nullptr) {
      *error_out = "failed to write output path '" + *output_path + "'.";
    }
    return false;
  }
  return true;
}

int RunSmoke(const CliOptions& options, SmokeReport* report) {
  report->plugin_path = options.plugin_path;
  report->ort_lib_path = options.ort_lib_path;

  std::string loader_error;
  DynamicLibrary ort_library(options.ort_lib_path, &loader_error);
  if (!ort_library.IsOpen()) {
    report->failure_reason = loader_error;
    return 1;
  }

  OrtGetApiBaseFn get_api_base = ort_library.LoadSymbol<OrtGetApiBaseFn>("OrtGetApiBase", &loader_error);
  if (get_api_base == nullptr) {
    report->failure_reason = loader_error;
    return 1;
  }

  const OrtApiBase* api_base = get_api_base();
  if (api_base == nullptr) {
    report->failure_reason = "OrtGetApiBase returned null.";
    return 1;
  }
  report->ort_runtime_version = api_base->GetVersionString != nullptr ? api_base->GetVersionString() : "";

  const OrtApi* api = api_base->GetApi(doe::ort_ep::kOrtPluginEpRuntimeApiVersion);
  if (api == nullptr) {
    report->failure_reason = "OrtApiBase::GetApi returned null for the requested ORT_API_VERSION.";
    return 1;
  }

  DynamicLibrary plugin_library(options.plugin_path, &loader_error);
  if (!plugin_library.IsOpen()) {
    report->failure_reason = loader_error;
    return 1;
  }

  auto create_factories = plugin_library.LoadSymbol<CreateEpApiFactoriesFn>("CreateEpFactories", &loader_error);
  if (create_factories == nullptr) {
    report->failure_reason = loader_error;
    return 1;
  }
  auto release_factory = plugin_library.LoadSymbol<ReleaseEpApiFactoryFn>("ReleaseEpFactory", &loader_error);
  if (release_factory == nullptr) {
    report->failure_reason = loader_error;
    return 1;
  }

  OrtEpFactory* factories[kMaxFactories] = {};
  size_t num_factories = 0;
  report->create_factories_status = CaptureStatus(
      api,
      create_factories(
          options.registration_name.c_str(),
          api_base,
          nullptr,
          factories,
          kMaxFactories,
          &num_factories));
  report->factory_count = num_factories;
  if (!report->create_factories_status.ok) {
    report->failure_reason = "CreateEpFactories returned an unexpected error.";
    return 1;
  }
  if (num_factories != 1 || factories[0] == nullptr) {
    report->failure_reason = "CreateEpFactories did not return exactly one factory.";
    return 1;
  }

  OrtEpFactory* factory = factories[0];
  report->factory_ort_version_supported = factory->ort_version_supported;
  report->factory_name = factory->GetName(factory);
  report->factory_vendor = factory->GetVendor(factory);
  report->factory_vendor_id = factory->GetVendorId(factory);
  report->factory_version = factory->GetVersion(factory);

  OrtEpDevice* ep_devices[kMaxEpDevices] = {};
  size_t num_ep_devices = 0;
  report->get_supported_devices_status = CaptureStatus(
      api,
      factory->GetSupportedDevices(factory, nullptr, 0, ep_devices, kMaxEpDevices, &num_ep_devices));
  report->supported_ep_device_count = num_ep_devices;
  if (!report->get_supported_devices_status.ok || num_ep_devices != 0) {
    report->failure_reason = "GetSupportedDevices did not return the current zero-device scaffold contract.";
    release_factory(factory);
    return 1;
  }

  OrtCompiledModelCompatibility compatibility = OrtCompiledModelCompatibility_EP_NOT_APPLICABLE;
  report->validate_compiled_model_status = CaptureStatus(
      api,
      factory->ValidateCompiledModelCompatibilityInfo(factory, nullptr, 0, nullptr, &compatibility));
  report->compatibility_name = CompatibilityName(compatibility);
  if (!report->validate_compiled_model_status.ok || compatibility != OrtCompiledModelCompatibility_EP_UNSUPPORTED) {
    report->failure_reason = "ValidateCompiledModelCompatibilityInfo did not report EP_UNSUPPORTED.";
    release_factory(factory);
    return 1;
  }

  OrtSessionOptions* session_options = nullptr;
  OrtStatus* create_session_options_status = api->CreateSessionOptions(&session_options);
  if (create_session_options_status != nullptr) {
    report->failure_reason = CaptureStatus(api, create_session_options_status).message;
    release_factory(factory);
    return 1;
  }

  OrtEp* ep = nullptr;
  report->create_ep_status = CaptureStatus(
      api,
      factory->CreateEp(factory, nullptr, nullptr, 0, session_options, nullptr, &ep));
  api->ReleaseSessionOptions(session_options);
  if (ep != nullptr) {
    factory->ReleaseEp(factory, ep);
  }
  release_factory(factory);
  if (!report->create_ep_status.ok) {
    report->failure_reason = "CreateEp did not return a real OrtEp instance.";
    return 1;
  }

  report->success = true;
  return 0;
}

}  // namespace

extern "C" int doeOrtEpSmokeMain(int argc, char** argv) {
  std::string parse_error;
  const std::optional<CliOptions> options = ParseArgs(argc, argv, &parse_error);
  SmokeReport report{};
  if (!options.has_value()) {
    report.failure_reason = parse_error;
    const std::string report_json = RenderReportJson(report);
    std::cerr << report_json;
    return 1;
  }

  const int exit_code = RunSmoke(*options, &report);
  const std::string report_json = RenderReportJson(report);
  std::string output_error;
  if (!WriteOutputIfRequested(options->output_path, report_json, &output_error)) {
    std::cerr << output_error << '\n';
    std::cerr << report_json;
    return 1;
  }
  std::cout << report_json;
  return exit_code;
}
