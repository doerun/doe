#include "../vendor/onnxruntime/include/onnxruntime_c_api.h"
#include "doe_ort_ep.h"
#include "doe_ort_ep_api_version.h"

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
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
constexpr ONNXTensorElementDataType kSmokeElementType = ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;
constexpr size_t kSingleOutputCount = 1;

using OrtGetApiBaseFn = const OrtApiBase* (*)();
using DoeOrtEpResetDebugCountersFn = void (*)();
using DoeOrtEpGetDebugCountersFn = void (*)(doe::ort_ep::DoeOrtEpDebugCounters*);

enum class SmokeModelKind : uint8_t {
  kAdd,
  kRelu,
  kAddRelu,
};

struct CliOptions {
  std::string plugin_path;
  std::string ort_lib_path;
  std::string registration_name = kDefaultRegistrationName;
  std::optional<std::string> output_path;
};

struct StatusInfo {
  bool ok = true;
  std::string code = "ORT_OK";
  std::string message;
};

struct SmokeCaseSpec {
  std::string case_name;
  SmokeModelKind model_kind = SmokeModelKind::kAdd;
  std::vector<int64_t> dims;
  std::vector<std::vector<float>> inputs;
  std::vector<float> expected_output;
};

struct SmokeCaseResult {
  std::string case_name;
  std::string model_kind;
  bool success = false;
  std::string failure_reason;
  bool session_inputs_have_ep_device = false;
  bool outputs_match = false;
  bool routed_through_doe = false;
  uint64_t expected_claimed_nodes = 0;
  std::vector<int64_t> expected_output_shape;
  std::vector<int64_t> actual_output_shape;
  std::vector<float> expected_output;
  std::vector<float> actual_output;
  doe::ort_ep::DoeOrtEpDebugCounters debug_counters_before{};
  doe::ort_ep::DoeOrtEpDebugCounters debug_counters_after{};
  doe::ort_ep::DoeOrtEpDebugCounters debug_counters_delta{};
  StatusInfo create_model_status;
  StatusInfo create_session_status;
  StatusInfo run_status;
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
  bool debug_symbols_loaded = false;
  doe::ort_ep::DoeOrtEpDebugCounters debug_counters{};
  StatusInfo register_library_status;
  StatusInfo get_ep_devices_status;
  StatusInfo append_ep_status;
  std::vector<SmokeCaseResult> cases;
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

std::string Indent(const int spaces) {
  return std::string(static_cast<size_t>(spaces), ' ');
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

const char* SmokeModelKindName(const SmokeModelKind kind) {
  switch (kind) {
    case SmokeModelKind::kAdd:
      return "Add";
    case SmokeModelKind::kRelu:
      return "Relu";
    case SmokeModelKind::kAddRelu:
      return "Add->Relu";
  }
  return "Unknown";
}

size_t ExpectedInputCount(const SmokeModelKind kind) {
  switch (kind) {
    case SmokeModelKind::kAdd:
    case SmokeModelKind::kAddRelu:
      return 2;
    case SmokeModelKind::kRelu:
      return 1;
  }
  return 0;
}

uint64_t ExpectedClaimedNodes(const SmokeModelKind kind) {
  return kind == SmokeModelKind::kAddRelu ? 2 : 1;
}

std::vector<const char*> InputNamesForKind(const SmokeModelKind kind) {
  switch (kind) {
    case SmokeModelKind::kAdd:
    case SmokeModelKind::kAddRelu:
      return {"lhs", "rhs"};
    case SmokeModelKind::kRelu:
      return {"input"};
  }
  return {};
}

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

doe::ort_ep::DoeOrtEpDebugCounters CounterDelta(
    const doe::ort_ep::DoeOrtEpDebugCounters& before,
    const doe::ort_ep::DoeOrtEpDebugCounters& after) {
  return doe::ort_ep::DoeOrtEpDebugCounters{
      .get_capability_calls = after.get_capability_calls - before.get_capability_calls,
      .claimed_nodes = after.claimed_nodes - before.claimed_nodes,
      .claimed_identity_nodes = after.claimed_identity_nodes - before.claimed_identity_nodes,
      .claimed_add_nodes = after.claimed_add_nodes - before.claimed_add_nodes,
      .claimed_relu_nodes = after.claimed_relu_nodes - before.claimed_relu_nodes,
      .compile_calls = after.compile_calls - before.compile_calls,
      .compiled_identity_groups = after.compiled_identity_groups - before.compiled_identity_groups,
      .compiled_add_groups = after.compiled_add_groups - before.compiled_add_groups,
      .compiled_relu_groups = after.compiled_relu_groups - before.compiled_relu_groups,
      .compiled_add_relu_groups = after.compiled_add_relu_groups - before.compiled_add_relu_groups,
      .create_state_calls = after.create_state_calls - before.create_state_calls,
      .compute_calls = after.compute_calls - before.compute_calls,
      .compute_identity_calls = after.compute_identity_calls - before.compute_identity_calls,
      .compute_add_calls = after.compute_add_calls - before.compute_add_calls,
      .compute_relu_calls = after.compute_relu_calls - before.compute_relu_calls,
      .compute_add_relu_calls = after.compute_add_relu_calls - before.compute_add_relu_calls,
      .release_state_calls = after.release_state_calls - before.release_state_calls,
  };
}

bool FloatVectorsEqual(const std::vector<float>& lhs, const std::vector<float>& rhs) {
  return lhs == rhs;
}

std::string RenderFloatArrayJson(const std::vector<float>& values) {
  std::ostringstream json;
  json << '[';
  for (size_t index = 0; index < values.size(); ++index) {
    if (index != 0) {
      json << ", ";
    }
    json << values[index];
  }
  json << ']';
  return json.str();
}

std::string RenderInt64ArrayJson(const std::vector<int64_t>& values) {
  std::ostringstream json;
  json << '[';
  for (size_t index = 0; index < values.size(); ++index) {
    if (index != 0) {
      json << ", ";
    }
    json << values[index];
  }
  json << ']';
  return json.str();
}

std::string RenderStatusJson(const StatusInfo& status, const int indent_spaces) {
  const std::string indent = Indent(indent_spaces);
  const std::string child_indent = Indent(indent_spaces + 2);
  std::ostringstream json;
  json << "{\n";
  json << child_indent << "\"ok\": " << (status.ok ? "true" : "false") << ",\n";
  json << child_indent << "\"code\": \"" << JsonEscape(status.code) << "\",\n";
  json << child_indent << "\"message\": \"" << JsonEscape(status.message) << "\"\n";
  json << indent << '}';
  return json.str();
}

std::string RenderCountersJson(const doe::ort_ep::DoeOrtEpDebugCounters& counters, const int indent_spaces) {
  const std::string indent = Indent(indent_spaces);
  const std::string child_indent = Indent(indent_spaces + 2);
  std::ostringstream json;
  json << "{\n";
  json << child_indent << "\"getCapabilityCalls\": " << counters.get_capability_calls << ",\n";
  json << child_indent << "\"claimedNodes\": " << counters.claimed_nodes << ",\n";
  json << child_indent << "\"claimedIdentityNodes\": " << counters.claimed_identity_nodes << ",\n";
  json << child_indent << "\"claimedAddNodes\": " << counters.claimed_add_nodes << ",\n";
  json << child_indent << "\"claimedReluNodes\": " << counters.claimed_relu_nodes << ",\n";
  json << child_indent << "\"compileCalls\": " << counters.compile_calls << ",\n";
  json << child_indent << "\"compiledIdentityGroups\": " << counters.compiled_identity_groups << ",\n";
  json << child_indent << "\"compiledAddGroups\": " << counters.compiled_add_groups << ",\n";
  json << child_indent << "\"compiledReluGroups\": " << counters.compiled_relu_groups << ",\n";
  json << child_indent << "\"compiledAddReluGroups\": " << counters.compiled_add_relu_groups << ",\n";
  json << child_indent << "\"createStateCalls\": " << counters.create_state_calls << ",\n";
  json << child_indent << "\"computeCalls\": " << counters.compute_calls << ",\n";
  json << child_indent << "\"computeIdentityCalls\": " << counters.compute_identity_calls << ",\n";
  json << child_indent << "\"computeAddCalls\": " << counters.compute_add_calls << ",\n";
  json << child_indent << "\"computeReluCalls\": " << counters.compute_relu_calls << ",\n";
  json << child_indent << "\"computeAddReluCalls\": " << counters.compute_add_relu_calls << ",\n";
  json << child_indent << "\"releaseStateCalls\": " << counters.release_state_calls << '\n';
  json << indent << '}';
  return json.str();
}

std::string RenderCaseJson(const SmokeCaseResult& result, const int indent_spaces) {
  const std::string indent = Indent(indent_spaces);
  const std::string child_indent = Indent(indent_spaces + 2);
  std::ostringstream json;
  json << "{\n";
  json << child_indent << "\"caseName\": \"" << JsonEscape(result.case_name) << "\",\n";
  json << child_indent << "\"modelKind\": \"" << JsonEscape(result.model_kind) << "\",\n";
  json << child_indent << "\"success\": " << (result.success ? "true" : "false") << ",\n";
  json << child_indent << "\"failureReason\": \"" << JsonEscape(result.failure_reason) << "\",\n";
  json << child_indent << "\"sessionInputsHaveEpDevice\": "
       << (result.session_inputs_have_ep_device ? "true" : "false") << ",\n";
  json << child_indent << "\"outputsMatch\": " << (result.outputs_match ? "true" : "false") << ",\n";
  json << child_indent << "\"routedThroughDoe\": " << (result.routed_through_doe ? "true" : "false") << ",\n";
  json << child_indent << "\"expectedClaimedNodes\": " << result.expected_claimed_nodes << ",\n";
  json << child_indent << "\"expectedOutputShape\": " << RenderInt64ArrayJson(result.expected_output_shape) << ",\n";
  json << child_indent << "\"actualOutputShape\": " << RenderInt64ArrayJson(result.actual_output_shape) << ",\n";
  json << child_indent << "\"expectedOutput\": " << RenderFloatArrayJson(result.expected_output) << ",\n";
  json << child_indent << "\"actualOutput\": " << RenderFloatArrayJson(result.actual_output) << ",\n";
  json << child_indent << "\"debugCountersBefore\": " << RenderCountersJson(result.debug_counters_before, indent_spaces + 2)
       << ",\n";
  json << child_indent << "\"debugCountersAfter\": " << RenderCountersJson(result.debug_counters_after, indent_spaces + 2)
       << ",\n";
  json << child_indent << "\"debugCountersDelta\": " << RenderCountersJson(result.debug_counters_delta, indent_spaces + 2)
       << ",\n";
  json << child_indent << "\"operations\": {\n";
  json << child_indent << "  \"createModel\": " << RenderStatusJson(result.create_model_status, indent_spaces + 4) << ",\n";
  json << child_indent << "  \"createSessionFromModel\": "
       << RenderStatusJson(result.create_session_status, indent_spaces + 4) << ",\n";
  json << child_indent << "  \"run\": " << RenderStatusJson(result.run_status, indent_spaces + 4) << '\n';
  json << child_indent << "}\n";
  json << indent << '}';
  return json.str();
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
  json << "  \"pluginDebug\": {\n";
  json << "    \"symbolsLoaded\": " << (report.debug_symbols_loaded ? "true" : "false") << ",\n";
  json << "    \"finalCounters\": " << RenderCountersJson(report.debug_counters, 4) << '\n';
  json << "  },\n";
  json << "  \"operations\": {\n";
  json << "    \"registerExecutionProviderLibrary\": " << RenderStatusJson(report.register_library_status, 4) << ",\n";
  json << "    \"getEpDevices\": " << RenderStatusJson(report.get_ep_devices_status, 4) << ",\n";
  json << "    \"appendExecutionProviderV2\": " << RenderStatusJson(report.append_ep_status, 4) << '\n';
  json << "  },\n";
  json << "  \"cases\": [\n";
  for (size_t index = 0; index < report.cases.size(); ++index) {
    json << "    " << RenderCaseJson(report.cases[index], 4);
    if (index + 1 != report.cases.size()) {
      json << ',';
    }
    json << '\n';
  }
  json << "  ]\n";
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

std::vector<SmokeCaseSpec> BuildSmokeCases() {
  return {
      SmokeCaseSpec{
          .case_name = "add",
          .model_kind = SmokeModelKind::kAdd,
          .dims = {1, 4},
          .inputs = {{1.0f, 2.0f, 3.0f, 4.0f}, {10.0f, 20.0f, 30.0f, 40.0f}},
          .expected_output = {11.0f, 22.0f, 33.0f, 44.0f},
      },
      SmokeCaseSpec{
          .case_name = "relu",
          .model_kind = SmokeModelKind::kRelu,
          .dims = {1, 4},
          .inputs = {{-2.0f, -1.0f, 0.0f, 3.0f}},
          .expected_output = {0.0f, 0.0f, 0.0f, 3.0f},
      },
      SmokeCaseSpec{
          .case_name = "add_relu",
          .model_kind = SmokeModelKind::kAddRelu,
          .dims = {1, 4},
          .inputs = {{-5.0f, 1.0f, -2.0f, 7.0f}, {3.0f, -4.0f, 5.0f, -1.0f}},
          .expected_output = {0.0f, 0.0f, 3.0f, 6.0f},
      },
  };
}

OrtStatus* CreateFloatValueInfo(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const char* name,
    const std::vector<int64_t>& dims,
    OrtValueInfo** value_info_out) {
  if (value_info_out == nullptr) {
    return api->CreateStatus(ORT_INVALID_ARGUMENT, "Doe ORT plugin EP smoke requires a value_info_out pointer.");
  }

  OrtTensorTypeAndShapeInfo* tensor_info = nullptr;
  OrtTypeInfo* type_info = nullptr;
  OrtStatus* status = api->CreateTensorTypeAndShapeInfo(&tensor_info);
  if (status != nullptr) goto cleanup;
  status = api->SetTensorElementType(tensor_info, kSmokeElementType);
  if (status != nullptr) goto cleanup;
  status = api->SetDimensions(tensor_info, dims.empty() ? nullptr : dims.data(), dims.size());
  if (status != nullptr) goto cleanup;
  status = model_editor_api->CreateTensorTypeInfo(tensor_info, &type_info);
  if (status != nullptr) goto cleanup;
  status = model_editor_api->CreateValueInfo(name, type_info, value_info_out);

cleanup:
  if (type_info != nullptr) api->ReleaseTypeInfo(type_info);
  if (tensor_info != nullptr) api->ReleaseTensorTypeAndShapeInfo(tensor_info);
  return status;
}

OrtStatus* CreateModelShell(const OrtModelEditorApi* model_editor_api, OrtModel** model_out, OrtGraph** graph_out) {
  const char* const domains[] = {""};
  const int opsets[] = {13};
  OrtStatus* status = model_editor_api->CreateModel(domains, opsets, 1, model_out);
  if (status != nullptr) return status;
  return model_editor_api->CreateGraph(graph_out);
}

OrtStatus* CreateAddModel(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const std::vector<int64_t>& dims,
    OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* lhs = nullptr;
  OrtValueInfo* rhs = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* add_node = nullptr;
  OrtStatus* status = CreateModelShell(model_editor_api, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "lhs", dims, &lhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "rhs", dims, &rhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", dims, &output);
  if (status != nullptr) goto cleanup;

  {
    OrtValueInfo* inputs[] = {lhs, rhs};
    status = model_editor_api->SetGraphInputs(graph, inputs, 2);
    if (status != nullptr) goto cleanup;
    lhs = nullptr;
    rhs = nullptr;
  }
  {
    OrtValueInfo* outputs[] = {output};
    status = model_editor_api->SetGraphOutputs(graph, outputs, 1);
    if (status != nullptr) goto cleanup;
    output = nullptr;
  }
  {
    const char* const input_names[] = {"lhs", "rhs"};
    const char* const output_names[] = {"output"};
    status = model_editor_api->CreateNode("Add", "", "add0", input_names, 2, output_names, 1, nullptr, 0, &add_node);
    if (status != nullptr) goto cleanup;
  }
  status = model_editor_api->AddNodeToGraph(graph, add_node);
  if (status != nullptr) goto cleanup;
  add_node = nullptr;
  status = model_editor_api->AddGraphToModel(model, graph);
  if (status != nullptr) goto cleanup;
  graph = nullptr;
  *out_model = model;
  model = nullptr;

cleanup:
  if (add_node != nullptr) api->ReleaseNode(add_node);
  if (lhs != nullptr) api->ReleaseValueInfo(lhs);
  if (rhs != nullptr) api->ReleaseValueInfo(rhs);
  if (output != nullptr) api->ReleaseValueInfo(output);
  if (graph != nullptr) api->ReleaseGraph(graph);
  if (model != nullptr) api->ReleaseModel(model);
  return status;
}

OrtStatus* CreateReluModel(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const std::vector<int64_t>& dims,
    OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* input = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* relu_node = nullptr;
  OrtStatus* status = CreateModelShell(model_editor_api, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "input", dims, &input);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", dims, &output);
  if (status != nullptr) goto cleanup;

  {
    OrtValueInfo* inputs[] = {input};
    status = model_editor_api->SetGraphInputs(graph, inputs, 1);
    if (status != nullptr) goto cleanup;
    input = nullptr;
  }
  {
    OrtValueInfo* outputs[] = {output};
    status = model_editor_api->SetGraphOutputs(graph, outputs, 1);
    if (status != nullptr) goto cleanup;
    output = nullptr;
  }
  {
    const char* const input_names[] = {"input"};
    const char* const output_names[] = {"output"};
    status = model_editor_api->CreateNode("Relu", "", "relu0", input_names, 1, output_names, 1, nullptr, 0, &relu_node);
    if (status != nullptr) goto cleanup;
  }
  status = model_editor_api->AddNodeToGraph(graph, relu_node);
  if (status != nullptr) goto cleanup;
  relu_node = nullptr;
  status = model_editor_api->AddGraphToModel(model, graph);
  if (status != nullptr) goto cleanup;
  graph = nullptr;
  *out_model = model;
  model = nullptr;

cleanup:
  if (relu_node != nullptr) api->ReleaseNode(relu_node);
  if (input != nullptr) api->ReleaseValueInfo(input);
  if (output != nullptr) api->ReleaseValueInfo(output);
  if (graph != nullptr) api->ReleaseGraph(graph);
  if (model != nullptr) api->ReleaseModel(model);
  return status;
}

OrtStatus* CreateAddReluModel(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const std::vector<int64_t>& dims,
    OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* lhs = nullptr;
  OrtValueInfo* rhs = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* add_node = nullptr;
  OrtNode* relu_node = nullptr;
  OrtStatus* status = CreateModelShell(model_editor_api, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "lhs", dims, &lhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "rhs", dims, &rhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", dims, &output);
  if (status != nullptr) goto cleanup;

  {
    OrtValueInfo* inputs[] = {lhs, rhs};
    status = model_editor_api->SetGraphInputs(graph, inputs, 2);
    if (status != nullptr) goto cleanup;
    lhs = nullptr;
    rhs = nullptr;
  }
  {
    OrtValueInfo* outputs[] = {output};
    status = model_editor_api->SetGraphOutputs(graph, outputs, 1);
    if (status != nullptr) goto cleanup;
    output = nullptr;
  }
  {
    const char* const input_names[] = {"lhs", "rhs"};
    const char* const output_names[] = {"sum"};
    status = model_editor_api->CreateNode("Add", "", "add0", input_names, 2, output_names, 1, nullptr, 0, &add_node);
    if (status != nullptr) goto cleanup;
  }
  status = model_editor_api->AddNodeToGraph(graph, add_node);
  if (status != nullptr) goto cleanup;
  add_node = nullptr;
  {
    const char* const input_names[] = {"sum"};
    const char* const output_names[] = {"output"};
    status = model_editor_api->CreateNode("Relu", "", "relu0", input_names, 1, output_names, 1, nullptr, 0, &relu_node);
    if (status != nullptr) goto cleanup;
  }
  status = model_editor_api->AddNodeToGraph(graph, relu_node);
  if (status != nullptr) goto cleanup;
  relu_node = nullptr;
  status = model_editor_api->AddGraphToModel(model, graph);
  if (status != nullptr) goto cleanup;
  graph = nullptr;
  *out_model = model;
  model = nullptr;

cleanup:
  if (add_node != nullptr) api->ReleaseNode(add_node);
  if (relu_node != nullptr) api->ReleaseNode(relu_node);
  if (lhs != nullptr) api->ReleaseValueInfo(lhs);
  if (rhs != nullptr) api->ReleaseValueInfo(rhs);
  if (output != nullptr) api->ReleaseValueInfo(output);
  if (graph != nullptr) api->ReleaseGraph(graph);
  if (model != nullptr) api->ReleaseModel(model);
  return status;
}

OrtStatus* CreateSmokeModel(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const SmokeCaseSpec& spec,
    OrtModel** out_model) {
  switch (spec.model_kind) {
    case SmokeModelKind::kAdd:
      return CreateAddModel(api, model_editor_api, spec.dims, out_model);
    case SmokeModelKind::kRelu:
      return CreateReluModel(api, model_editor_api, spec.dims, out_model);
    case SmokeModelKind::kAddRelu:
      return CreateAddReluModel(api, model_editor_api, spec.dims, out_model);
  }
  return api->CreateStatus(ORT_FAIL, "Doe ORT plugin EP smoke reached an unknown model kind.");
}

OrtStatus* ReadFloatTensor(
    const OrtApi* api,
    const OrtValue* value,
    std::vector<int64_t>* dims_out,
    std::vector<float>* values_out) {
  if (dims_out == nullptr || values_out == nullptr) {
    return api->CreateStatus(ORT_INVALID_ARGUMENT, "Doe ORT plugin EP smoke requires dims_out and values_out pointers.");
  }

  OrtTensorTypeAndShapeInfo* tensor_info = nullptr;
  OrtStatus* status = api->GetTensorTypeAndShape(value, &tensor_info);
  if (status != nullptr) return status;

  ONNXTensorElementDataType element_type = ONNX_TENSOR_ELEMENT_DATA_TYPE_UNDEFINED;
  status = api->GetTensorElementType(tensor_info, &element_type);
  if (status != nullptr) {
    api->ReleaseTensorTypeAndShapeInfo(tensor_info);
    return status;
  }
  if (element_type != kSmokeElementType) {
    api->ReleaseTensorTypeAndShapeInfo(tensor_info);
    return api->CreateStatus(ORT_NOT_IMPLEMENTED, "Doe ORT plugin EP smoke expects float32 outputs.");
  }

  size_t rank = 0;
  status = api->GetDimensionsCount(tensor_info, &rank);
  if (status != nullptr) {
    api->ReleaseTensorTypeAndShapeInfo(tensor_info);
    return status;
  }

  dims_out->assign(rank, 0);
  if (rank != 0) {
    status = api->GetDimensions(tensor_info, dims_out->data(), dims_out->size());
    if (status != nullptr) {
      api->ReleaseTensorTypeAndShapeInfo(tensor_info);
      return status;
    }
  }

  size_t element_count = 0;
  status = api->GetTensorShapeElementCount(tensor_info, &element_count);
  api->ReleaseTensorTypeAndShapeInfo(tensor_info);
  if (status != nullptr) return status;

  const void* data = nullptr;
  status = api->GetTensorData(value, &data);
  if (status != nullptr) return status;
  if (data == nullptr) {
    return api->CreateStatus(ORT_FAIL, "Doe ORT plugin EP smoke received null output data.");
  }

  const auto* floats = static_cast<const float*>(data);
  values_out->assign(floats, floats + element_count);
  return nullptr;
}

bool ValidateCaseRouting(
    const SmokeCaseSpec& spec,
    const doe::ort_ep::DoeOrtEpDebugCounters& delta,
    std::string* error_out) {
  auto fail = [&](const std::string& message) {
    if (error_out != nullptr) {
      *error_out = message;
    }
    return false;
  };

  if (delta.get_capability_calls == 0) {
    return fail("GetCapability did not run for the case.");
  }
  if (delta.claimed_nodes != ExpectedClaimedNodes(spec.model_kind)) {
    std::ostringstream message;
    message << "expected claimedNodes=" << ExpectedClaimedNodes(spec.model_kind) << " but observed "
            << delta.claimed_nodes << '.';
    return fail(message.str());
  }
  if (delta.compile_calls == 0) {
    return fail("Compile did not run for the case.");
  }
  if (delta.create_state_calls == 0) {
    return fail("CreateState did not run for the case.");
  }
  if (delta.compute_calls == 0) {
    return fail("Compute did not run for the case.");
  }
  if (delta.release_state_calls == 0) {
    return fail("ReleaseState did not run for the case.");
  }

  switch (spec.model_kind) {
    case SmokeModelKind::kAdd:
      if (delta.claimed_add_nodes == 0 || delta.compiled_add_groups == 0 || delta.compute_add_calls == 0) {
        return fail("Add case did not report Add-specific claim/compile/compute counters.");
      }
      break;
    case SmokeModelKind::kRelu:
      if (delta.claimed_relu_nodes == 0 || delta.compiled_relu_groups == 0 || delta.compute_relu_calls == 0) {
        return fail("Relu case did not report Relu-specific claim/compile/compute counters.");
      }
      break;
    case SmokeModelKind::kAddRelu:
      if (delta.claimed_add_nodes == 0 || delta.claimed_relu_nodes == 0 || delta.compiled_add_relu_groups == 0 ||
          delta.compute_add_relu_calls == 0) {
        return fail("Add->Relu case did not report fused Add/Relu claim/compile/compute counters.");
      }
      break;
  }

  return true;
}

bool RunSmokeCase(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    OrtEnv* env,
    OrtSessionOptions* session_options,
    DoeOrtEpGetDebugCountersFn get_debug_counters,
    const SmokeCaseSpec& spec,
    SmokeCaseResult* result) {
  result->case_name = spec.case_name;
  result->model_kind = SmokeModelKindName(spec.model_kind);
  result->expected_output_shape = spec.dims;
  result->expected_output = spec.expected_output;
  result->expected_claimed_nodes = ExpectedClaimedNodes(spec.model_kind);

  get_debug_counters(&result->debug_counters_before);

  OrtModel* model = nullptr;
  OrtSession* session = nullptr;
  std::vector<OrtValue*> inputs(ExpectedInputCount(spec.model_kind), nullptr);
  std::vector<OrtValue*> outputs(kSingleOutputCount, nullptr);

  OrtStatus* status = CreateSmokeModel(api, model_editor_api, spec, &model);
  result->create_model_status = CaptureStatus(api, status);
  if (!result->create_model_status.ok) {
    result->failure_reason = "CreateSmokeModel failed.";
    goto cleanup;
  }

  status = model_editor_api->CreateSessionFromModel(env, model, session_options, &session);
  result->create_session_status = CaptureStatus(api, status);
  if (!result->create_session_status.ok) {
    result->failure_reason = "CreateSessionFromModel failed.";
    goto cleanup;
  }

  {
    std::vector<const OrtEpDevice*> input_ep_devices(inputs.size(), nullptr);
    status = api->SessionGetEpDeviceForInputs(session, input_ep_devices.data(), input_ep_devices.size());
    if (status == nullptr) {
      result->session_inputs_have_ep_device = true;
      for (const OrtEpDevice* ep_device : input_ep_devices) {
        if (ep_device == nullptr) {
          result->session_inputs_have_ep_device = false;
          break;
        }
      }
    } else {
      api->ReleaseStatus(status);
    }
  }

  {
    OrtAllocator* allocator = nullptr;
    status = api->GetAllocatorWithDefaultOptions(&allocator);
    result->run_status = CaptureStatus(api, status);
    if (!result->run_status.ok) {
      result->failure_reason = "GetAllocatorWithDefaultOptions failed.";
      goto cleanup;
    }

    for (size_t index = 0; index < inputs.size(); ++index) {
      status = api->CreateTensorAsOrtValue(
          allocator,
          spec.dims.empty() ? nullptr : spec.dims.data(),
          spec.dims.size(),
          kSmokeElementType,
          &inputs[index]);
      result->run_status = CaptureStatus(api, status);
      if (!result->run_status.ok) {
        result->failure_reason = "CreateTensorAsOrtValue failed for an input.";
        goto cleanup;
      }

      void* input_data = nullptr;
      status = api->GetTensorMutableData(inputs[index], &input_data);
      result->run_status = CaptureStatus(api, status);
      if (!result->run_status.ok) {
        result->failure_reason = "GetTensorMutableData failed for an input.";
        goto cleanup;
      }
      if (input_data == nullptr) {
        result->failure_reason = "Input tensor data pointer was null.";
        goto cleanup;
      }

      if (spec.inputs[index].size() != spec.expected_output.size()) {
        result->failure_reason = "Smoke case input element count did not match the declared shape.";
        goto cleanup;
      }

      std::memcpy(
          input_data,
          spec.inputs[index].data(),
          spec.inputs[index].size() * sizeof(float));
    }

    const std::vector<const char*> input_names = InputNamesForKind(spec.model_kind);
    std::vector<const OrtValue*> input_ptrs(inputs.size(), nullptr);
    for (size_t index = 0; index < inputs.size(); ++index) {
      input_ptrs[index] = inputs[index];
    }
    const char* const output_names[] = {"output"};
    status = api->Run(
        session,
        nullptr,
        input_names.data(),
        input_ptrs.data(),
        input_ptrs.size(),
        output_names,
        1,
        outputs.data());
    result->run_status = CaptureStatus(api, status);
    if (!result->run_status.ok) {
      result->failure_reason = "Run failed.";
      goto cleanup;
    }
  }

  if (outputs[0] == nullptr) {
    result->failure_reason = "Run returned a null output OrtValue.";
    goto cleanup;
  }

  status = ReadFloatTensor(api, outputs[0], &result->actual_output_shape, &result->actual_output);
  result->run_status = CaptureStatus(api, status);
  if (!result->run_status.ok) {
    result->failure_reason = "ReadFloatTensor failed for the output.";
    goto cleanup;
  }

  result->outputs_match =
      result->actual_output_shape == result->expected_output_shape &&
      FloatVectorsEqual(result->actual_output, result->expected_output);
  if (!result->outputs_match) {
    result->failure_reason = "Actual output did not match the expected smoke output.";
  }

cleanup:
  for (OrtValue*& output : outputs) {
    if (output != nullptr) {
      api->ReleaseValue(output);
      output = nullptr;
    }
  }
  for (OrtValue*& input : inputs) {
    if (input != nullptr) {
      api->ReleaseValue(input);
      input = nullptr;
    }
  }
  if (session != nullptr) {
    api->ReleaseSession(session);
    session = nullptr;
  }
  if (model != nullptr) {
    api->ReleaseModel(model);
    model = nullptr;
  }

  get_debug_counters(&result->debug_counters_after);
  result->debug_counters_delta = CounterDelta(result->debug_counters_before, result->debug_counters_after);

  if (result->failure_reason.empty()) {
    std::string routing_error;
    result->routed_through_doe = ValidateCaseRouting(spec, result->debug_counters_delta, &routing_error);
    if (!result->routed_through_doe) {
      result->failure_reason = routing_error;
    }
  }

  result->success = result->failure_reason.empty();
  return result->success;
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

  DynamicLibrary plugin_debug_library(options.plugin_path, &loader_error);
  if (!plugin_debug_library.IsOpen()) {
    report->failure_reason = loader_error;
    return 1;
  }
  DoeOrtEpResetDebugCountersFn reset_debug_counters =
      plugin_debug_library.LoadSymbol<DoeOrtEpResetDebugCountersFn>("DoeOrtEpResetDebugCounters", &loader_error);
  if (reset_debug_counters == nullptr) {
    report->failure_reason = loader_error;
    return 1;
  }
  DoeOrtEpGetDebugCountersFn get_debug_counters =
      plugin_debug_library.LoadSymbol<DoeOrtEpGetDebugCountersFn>("DoeOrtEpGetDebugCounters", &loader_error);
  if (get_debug_counters == nullptr) {
    report->failure_reason = loader_error;
    return 1;
  }
  report->debug_symbols_loaded = true;
  reset_debug_counters();

  OrtEnv* env = nullptr;
  OrtSessionOptions* session_options = nullptr;
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

  model_editor_api = api->GetModelEditorApi();
  if (model_editor_api == nullptr) {
    report->failure_reason = "GetModelEditorApi returned null; host ORT build cannot create the in-memory session smoke models.";
    goto cleanup;
  }

  for (const SmokeCaseSpec& spec : BuildSmokeCases()) {
    SmokeCaseResult case_result{};
    const bool case_ok = RunSmokeCase(
        api,
        model_editor_api,
        env,
        session_options,
        get_debug_counters,
        spec,
        &case_result);
    report->cases.push_back(std::move(case_result));
    if (!case_ok) {
      report->failure_reason = "Smoke case '" + spec.case_name + "' failed";
      if (!report->cases.back().failure_reason.empty()) {
        report->failure_reason += ": ";
        report->failure_reason += report->cases.back().failure_reason;
      } else {
        report->failure_reason += '.';
      }
      break;
    }
  }

cleanup:
  if (session_options != nullptr) {
    api->ReleaseSessionOptions(session_options);
    session_options = nullptr;
  }
  if (env != nullptr) {
    (void)api->UnregisterExecutionProviderLibrary(env, options.registration_name.c_str());
    api->ReleaseEnv(env);
    env = nullptr;
  }
  get_debug_counters(&report->debug_counters);
  report->success = report->failure_reason.empty();
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
