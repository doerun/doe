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

const char* HardwareDeviceTypeName(const OrtHardwareDeviceType device_type) {
  switch (device_type) {
    case OrtHardwareDeviceType_CPU:
      return "OrtHardwareDeviceType_CPU";
    case OrtHardwareDeviceType_GPU:
      return "OrtHardwareDeviceType_GPU";
    case OrtHardwareDeviceType_NPU:
      return "OrtHardwareDeviceType_NPU";
    default:
      return "OrtHardwareDeviceType_UNKNOWN";
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

struct SessionSmokeReport {
  bool success = false;
  std::string failure_reason;
  std::string plugin_path;
  std::string ort_lib_path;
  std::string ort_runtime_version;
  uint32_t ort_header_api_version = ORT_API_VERSION;
  uint32_t ort_api_version_requested = doe::ort_ep::kOrtPluginEpRuntimeApiVersion;
  size_t discovered_ep_device_count = 0;
  std::string selected_ep_name;
  std::string selected_ep_vendor;
  std::string selected_hardware_device_type;
  bool session_input_has_ep_device = false;
  float input_value = 0.0f;
  float output_value = 0.0f;
  StatusInfo register_library_status;
  StatusInfo get_ep_devices_status;
  StatusInfo append_ep_status;
  StatusInfo create_model_status;
  StatusInfo create_session_status;
  StatusInfo run_status;
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
          << "Usage: doe-ort-ep-session-smoke --plugin-path <path> [--ort-lib-path <path>] [--registration-name <name>] [--output <path>]\n";
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

std::string RenderReportJson(const SessionSmokeReport& report) {
  std::ostringstream json;
  json << "{\n";
  json << "  \"success\": " << (report.success ? "true" : "false") << ",\n";
  json << "  \"failureReason\": \"" << JsonEscape(report.failure_reason) << "\",\n";
  json << "  \"pluginPath\": \"" << JsonEscape(report.plugin_path) << "\",\n";
  json << "  \"ortLibraryPath\": \"" << JsonEscape(report.ort_lib_path) << "\",\n";
  json << "  \"ortRuntimeVersion\": \"" << JsonEscape(report.ort_runtime_version) << "\",\n";
  json << "  \"ortHeaderApiVersion\": " << report.ort_header_api_version << ",\n";
  json << "  \"ortApiVersionRequested\": " << report.ort_api_version_requested << ",\n";
  json << "  \"selectedEp\": {\n";
  json << "    \"discoveredDeviceCount\": " << report.discovered_ep_device_count << ",\n";
  json << "    \"name\": \"" << JsonEscape(report.selected_ep_name) << "\",\n";
  json << "    \"vendor\": \"" << JsonEscape(report.selected_ep_vendor) << "\",\n";
  json << "    \"hardwareDeviceType\": \"" << JsonEscape(report.selected_hardware_device_type) << "\"\n";
  json << "  },\n";
  json << "  \"session\": {\n";
  json << "    \"inputHasEpDevice\": " << (report.session_input_has_ep_device ? "true" : "false") << ",\n";
  json << "    \"inputValue\": " << std::to_string(report.input_value) << ",\n";
  json << "    \"outputValue\": " << std::to_string(report.output_value) << "\n";
  json << "  },\n";
  json << "  \"operations\": {\n";
  auto render_status = [&](const char* label, const StatusInfo& status) {
    json << "    \"" << label << "\": {\n";
    json << "      \"ok\": " << (status.ok ? "true" : "false") << ",\n";
    json << "      \"code\": \"" << JsonEscape(status.code) << "\",\n";
    json << "      \"message\": \"" << JsonEscape(status.message) << "\"\n";
    json << "    }";
  };
  render_status("registerExecutionProviderLibrary", report.register_library_status);
  json << ",\n";
  render_status("getEpDevices", report.get_ep_devices_status);
  json << ",\n";
  render_status("appendExecutionProviderV2", report.append_ep_status);
  json << ",\n";
  render_status("createIdentityModel", report.create_model_status);
  json << ",\n";
  render_status("createSessionFromModel", report.create_session_status);
  json << ",\n";
  render_status("runIdentitySession", report.run_status);
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

#ifdef _WIN32
std::wstring Utf8ToWide(const std::string& value) {
  if (value.empty()) {
    return {};
  }
  const int required = MultiByteToWideChar(CP_UTF8, 0, value.c_str(), -1, nullptr, 0);
  if (required <= 0) {
    return {};
  }
  std::wstring wide(static_cast<size_t>(required - 1), L'\0');
  MultiByteToWideChar(CP_UTF8, 0, value.c_str(), -1, wide.data(), required);
  return wide;
}
#endif

OrtStatus* CreateIdentityModel(const OrtApi* api, const OrtModelEditorApi* model_editor_api, OrtModel** out_model) {
  const char* const domains[] = {""};
  const int opsets[] = {13};
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtTensorTypeAndShapeInfo* tensor_info = nullptr;
  OrtTypeInfo* type_info = nullptr;
  OrtValueInfo* input_info = nullptr;
  OrtValueInfo* output_info = nullptr;
  OrtNode* node = nullptr;
  OrtStatus* status = nullptr;

  const int64_t dims[] = {1};
  status = model_editor_api->CreateModel(domains, opsets, 1, &model);
  if (status != nullptr) goto cleanup;
  status = model_editor_api->CreateGraph(&graph);
  if (status != nullptr) goto cleanup;
  status = api->CreateTensorTypeAndShapeInfo(&tensor_info);
  if (status != nullptr) goto cleanup;
  status = api->SetTensorElementType(tensor_info, ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT);
  if (status != nullptr) goto cleanup;
  status = api->SetDimensions(tensor_info, dims, 1);
  if (status != nullptr) goto cleanup;
  status = model_editor_api->CreateTensorTypeInfo(tensor_info, &type_info);
  if (status != nullptr) goto cleanup;
  status = model_editor_api->CreateValueInfo("input", type_info, &input_info);
  if (status != nullptr) goto cleanup;
  status = model_editor_api->CreateValueInfo("output", type_info, &output_info);
  if (status != nullptr) goto cleanup;
  {
    OrtValueInfo* inputs[] = {input_info};
    status = model_editor_api->SetGraphInputs(graph, inputs, 1);
    if (status != nullptr) goto cleanup;
  }
  input_info = nullptr;
  {
    OrtValueInfo* outputs[] = {output_info};
    status = model_editor_api->SetGraphOutputs(graph, outputs, 1);
    if (status != nullptr) goto cleanup;
  }
  output_info = nullptr;
  {
    const char* const input_names[] = {"input"};
    const char* const output_names[] = {"output"};
    status = model_editor_api->CreateNode("Identity", "", "identity0", input_names, 1, output_names, 1, nullptr, 0, &node);
    if (status != nullptr) goto cleanup;
  }
  status = model_editor_api->AddNodeToGraph(graph, node);
  if (status != nullptr) goto cleanup;
  node = nullptr;
  status = model_editor_api->AddGraphToModel(model, graph);
  if (status != nullptr) goto cleanup;
  graph = nullptr;
  *out_model = model;
  model = nullptr;

cleanup:
  if (node != nullptr) api->ReleaseNode(node);
  if (input_info != nullptr) api->ReleaseValueInfo(input_info);
  if (output_info != nullptr) api->ReleaseValueInfo(output_info);
  if (type_info != nullptr) api->ReleaseTypeInfo(type_info);
  if (tensor_info != nullptr) api->ReleaseTensorTypeAndShapeInfo(tensor_info);
  if (graph != nullptr) api->ReleaseGraph(graph);
  if (model != nullptr) api->ReleaseModel(model);
  return status;
}

int RunSessionSmoke(const CliOptions& options, SessionSmokeReport* report) {
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
    report->failure_reason = "OrtApiBase::GetApi returned null for the requested ORT runtime API version.";
    return 1;
  }

  OrtEnv* env = nullptr;
  OrtSessionOptions* session_options = nullptr;
  OrtModel* model = nullptr;
  OrtSession* session = nullptr;
  OrtValue* input = nullptr;
  OrtValue* outputs[] = {nullptr};
  const OrtModelEditorApi* model_editor_api = nullptr;

  OrtStatus* status = api->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "doe-ort-ep-session-smoke", &env);
  report->register_library_status = CaptureStatus(api, status);
  if (!report->register_library_status.ok) {
    report->failure_reason = "CreateEnv failed for ORT session smoke.";
    goto cleanup;
  }

#ifdef _WIN32
  const std::wstring plugin_path_w = Utf8ToWide(options.plugin_path);
  status = api->RegisterExecutionProviderLibrary(env, options.registration_name.c_str(), plugin_path_w.c_str());
#else
  status = api->RegisterExecutionProviderLibrary(env, options.registration_name.c_str(), options.plugin_path.c_str());
#endif
  report->register_library_status = CaptureStatus(api, status);
  if (!report->register_library_status.ok) {
    report->failure_reason = "RegisterExecutionProviderLibrary failed.";
    goto cleanup;
  }

  {
    const OrtEpDevice* const* ep_devices = nullptr;
    size_t num_ep_devices = 0;
    status = api->GetEpDevices(env, &ep_devices, &num_ep_devices);
    report->get_ep_devices_status = CaptureStatus(api, status);
    report->discovered_ep_device_count = num_ep_devices;
    if (!report->get_ep_devices_status.ok) {
      report->failure_reason = "GetEpDevices failed.";
      goto cleanup;
    }

    const OrtEpDevice* selected_ep_device = nullptr;
    for (size_t index = 0; index < num_ep_devices; ++index) {
      const char* ep_name = api->EpDevice_EpName(ep_devices[index]);
      if (ep_name != nullptr && options.registration_name == ep_name) {
        selected_ep_device = ep_devices[index];
        report->selected_ep_name = ep_name;
        const char* ep_vendor = api->EpDevice_EpVendor(ep_devices[index]);
        report->selected_ep_vendor = ep_vendor != nullptr ? ep_vendor : "";
        const OrtHardwareDevice* hardware_device = api->EpDevice_Device(ep_devices[index]);
        if (hardware_device != nullptr) {
          report->selected_hardware_device_type = HardwareDeviceTypeName(api->HardwareDevice_Type(hardware_device));
        }
        break;
      }
    }
    if (selected_ep_device == nullptr) {
      report->failure_reason = "ORT did not expose a Doe OrtEpDevice after plugin registration.";
      goto cleanup;
    }

    status = api->CreateSessionOptions(&session_options);
    report->append_ep_status = CaptureStatus(api, status);
    if (!report->append_ep_status.ok) {
      report->failure_reason = "CreateSessionOptions failed.";
      goto cleanup;
    }

    const OrtEpDevice* selected_devices[] = {selected_ep_device};
    status = api->SessionOptionsAppendExecutionProvider_V2(session_options, env, selected_devices, 1, nullptr, nullptr, 0);
    report->append_ep_status = CaptureStatus(api, status);
    if (!report->append_ep_status.ok) {
      report->failure_reason = "SessionOptionsAppendExecutionProvider_V2 failed.";
      goto cleanup;
    }
  }

  {
    model_editor_api = api->GetModelEditorApi();
    if (model_editor_api == nullptr) {
      report->failure_reason = "GetModelEditorApi returned null; host ORT build cannot create the in-memory session smoke model.";
      goto cleanup;
    }
    status = CreateIdentityModel(api, model_editor_api, &model);
    report->create_model_status = CaptureStatus(api, status);
    if (!report->create_model_status.ok) {
      report->failure_reason = "CreateIdentityModel failed.";
      goto cleanup;
    }
  }

  status = model_editor_api->CreateSessionFromModel(env, model, session_options, &session);
  report->create_session_status = CaptureStatus(api, status);
  if (!report->create_session_status.ok) {
    report->failure_reason = "CreateSessionFromModel failed.";
    goto cleanup;
  }

  {
    const OrtEpDevice* input_ep_devices[] = {nullptr};
    status = api->SessionGetEpDeviceForInputs(session, input_ep_devices, 1);
    if (status == nullptr && input_ep_devices[0] != nullptr) {
      report->session_input_has_ep_device = true;
    } else if (status != nullptr) {
      api->ReleaseStatus(status);
    }
  }

  {
    OrtAllocator* allocator = nullptr;
    status = api->GetAllocatorWithDefaultOptions(&allocator);
    report->run_status = CaptureStatus(api, status);
    if (!report->run_status.ok) {
      report->failure_reason = "GetAllocatorWithDefaultOptions failed.";
      goto cleanup;
    }

    const int64_t dims[] = {1};
    status = api->CreateTensorAsOrtValue(allocator, dims, 1, ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT, &input);
    report->run_status = CaptureStatus(api, status);
    if (!report->run_status.ok) {
      report->failure_reason = "CreateTensorAsOrtValue failed.";
      goto cleanup;
    }

    void* input_data = nullptr;
    status = api->GetTensorMutableData(input, &input_data);
    report->run_status = CaptureStatus(api, status);
    if (!report->run_status.ok) {
      report->failure_reason = "GetTensorMutableData failed for input.";
      goto cleanup;
    }

    report->input_value = 3.5f;
    static_cast<float*>(input_data)[0] = report->input_value;

    const char* const input_names[] = {"input"};
    const OrtValue* const inputs[] = {input};
    const char* const output_names[] = {"output"};
    status = api->Run(session, nullptr, input_names, inputs, 1, output_names, 1, outputs);
    report->run_status = CaptureStatus(api, status);
    if (!report->run_status.ok) {
      report->failure_reason = "Run failed.";
      goto cleanup;
    }
  }

  if (outputs[0] == nullptr) {
    report->failure_reason = "Run returned a null output OrtValue.";
    goto cleanup;
  }

  {
    void* output_data = nullptr;
    status = api->GetTensorMutableData(outputs[0], &output_data);
    report->run_status = CaptureStatus(api, status);
    if (!report->run_status.ok) {
      report->failure_reason = "GetTensorMutableData failed for output.";
      goto cleanup;
    }
    report->output_value = static_cast<float*>(output_data)[0];
    if (report->output_value != report->input_value) {
      report->failure_reason = "Session smoke output did not match the identity-model input.";
      goto cleanup;
    }
  }

  report->success = true;

cleanup:
  if (outputs[0] != nullptr) api->ReleaseValue(outputs[0]);
  if (input != nullptr) api->ReleaseValue(input);
  if (session != nullptr) api->ReleaseSession(session);
  if (model != nullptr) api->ReleaseModel(model);
  if (session_options != nullptr) api->ReleaseSessionOptions(session_options);
  if (env != nullptr) {
    (void)api->UnregisterExecutionProviderLibrary(env, options.registration_name.c_str());
    api->ReleaseEnv(env);
  }
  return report->success ? 0 : 1;
}

}  // namespace

extern "C" int doeOrtEpSessionSmokeMain(int argc, char** argv) {
  std::string parse_error;
  const std::optional<CliOptions> options = ParseArgs(argc, argv, &parse_error);
  SessionSmokeReport report{};
  if (!options.has_value()) {
    report.failure_reason = parse_error;
    const std::string report_json = RenderReportJson(report);
    std::cerr << report_json;
    return 1;
  }

  const int exit_code = RunSessionSmoke(*options, &report);
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
