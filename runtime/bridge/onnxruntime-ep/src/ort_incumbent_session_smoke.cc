#include "../vendor/onnxruntime/include/onnxruntime_c_api.h"
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

constexpr const char* kDefaultProviderName = "WebGPU";
constexpr ONNXTensorElementDataType kSmokeElementType = ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;
constexpr size_t kSingleOutputCount = 1;

using OrtGetApiBaseFn = const OrtApiBase* (*)();

enum class SmokeModelKind : uint8_t {
  kAdd,
  kRelu,
  kMatMul,
  kMatMulAdd,
  kMatMulAddRelu,
  kAddRelu,
};

struct CliOptions {
  std::string ort_lib_path;
  std::string provider_name = kDefaultProviderName;
  std::string case_selector = "all";
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
  std::vector<std::vector<int64_t>> input_dims;
  std::vector<int64_t> output_dims;
  std::vector<std::vector<float>> inputs;
  std::vector<float> expected_output;
};

struct SmokeCaseResult {
  std::string case_name;
  std::string model_kind;
  bool success = false;
  std::string failure_reason;
  bool outputs_match = false;
  std::vector<int64_t> expected_output_shape;
  std::vector<int64_t> actual_output_shape;
  std::vector<float> expected_output;
  std::vector<float> actual_output;
  StatusInfo create_model_status;
  StatusInfo create_session_status;
  StatusInfo run_status;
};

struct SessionSmokeReport {
  bool success = false;
  std::string failure_reason;
  std::string ort_lib_path;
  std::string provider_name = kDefaultProviderName;
  std::string case_selector = "all";
  std::string ort_runtime_version;
  uint32_t ort_header_api_version = ORT_API_VERSION;
  uint32_t ort_api_version_requested = doe::ort_ep::kOrtPluginEpRuntimeApiVersion;
  std::vector<std::string> available_providers;
  StatusInfo create_env_status;
  StatusInfo create_session_options_status;
  StatusInfo append_provider_status;
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

std::string Indent(int spaces) {
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

const char* SmokeModelKindName(const SmokeModelKind kind) {
  switch (kind) {
    case SmokeModelKind::kAdd:
      return "Add";
    case SmokeModelKind::kRelu:
      return "Relu";
    case SmokeModelKind::kMatMul:
      return "MatMul";
    case SmokeModelKind::kMatMulAdd:
      return "MatMul->Add";
    case SmokeModelKind::kMatMulAddRelu:
      return "MatMul->Add->Relu";
    case SmokeModelKind::kAddRelu:
      return "Add->Relu";
  }
  return "Unknown";
}

size_t ExpectedInputCount(const SmokeModelKind kind) {
  switch (kind) {
    case SmokeModelKind::kAdd:
    case SmokeModelKind::kMatMul:
    case SmokeModelKind::kAddRelu:
      return 2;
    case SmokeModelKind::kMatMulAdd:
    case SmokeModelKind::kMatMulAddRelu:
      return 3;
    case SmokeModelKind::kRelu:
      return 1;
  }
  return 0;
}

std::vector<const char*> InputNamesForKind(const SmokeModelKind kind) {
  switch (kind) {
    case SmokeModelKind::kAdd:
    case SmokeModelKind::kMatMul:
      return {"lhs", "rhs"};
    case SmokeModelKind::kMatMulAdd:
      return {"lhs", "rhs", "bias"};
    case SmokeModelKind::kMatMulAddRelu:
      return {"lhs", "rhs", "bias"};
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
      "/home/x/deco/doppler/node_modules/onnxruntime-node/bin/napi-v6/linux/x64/libonnxruntime.so.1",
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
    if (argument == "--ort-lib-path") {
      const char* value = require_value("--ort-lib-path");
      if (value == nullptr) return std::nullopt;
      options.ort_lib_path = value;
    } else if (argument == "--provider-name") {
      const char* value = require_value("--provider-name");
      if (value == nullptr) return std::nullopt;
      options.provider_name = value;
    } else if (argument == "--case") {
      const char* value = require_value("--case");
      if (value == nullptr) return std::nullopt;
      options.case_selector = value;
    } else if (argument == "--output") {
      const char* value = require_value("--output");
      if (value == nullptr) return std::nullopt;
      options.output_path = value;
    } else if (argument == "--help" || argument == "-h") {
      std::cout
          << "Usage: doe-ort-incumbent-session-smoke [--ort-lib-path <path>] "
          << "[--provider-name WebGPU] [--case add|relu|matmul|matmul_add|matmul_add_relu|add_relu|all] [--output <path>]\n";
      std::exit(0);
    } else {
      if (error_out != nullptr) {
        *error_out = "unknown argument '" + argument + "'.";
      }
      return std::nullopt;
    }
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

  const bool valid_case_selector =
      options.case_selector == "all" ||
      options.case_selector == "add" ||
      options.case_selector == "relu" ||
      options.case_selector == "matmul" ||
      options.case_selector == "matmul_add" ||
      options.case_selector == "matmul_add_relu" ||
      options.case_selector == "add_relu";
  if (!valid_case_selector) {
    if (error_out != nullptr) {
      *error_out = "unsupported --case value '" + options.case_selector + "'; expected add, relu, matmul, matmul_add, matmul_add_relu, add_relu, or all.";
    }
    return std::nullopt;
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

std::string RenderStringArrayJson(const std::vector<std::string>& values, const int indent_spaces) {
  const std::string indent = Indent(indent_spaces);
  const std::string child_indent = Indent(indent_spaces + 2);
  std::ostringstream json;
  json << "[\n";
  for (size_t index = 0; index < values.size(); ++index) {
    json << child_indent << "\"" << JsonEscape(values[index]) << "\"";
    if (index + 1 != values.size()) {
      json << ',';
    }
    json << '\n';
  }
  json << indent << ']';
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

std::string RenderCaseJson(const SmokeCaseResult& result, const int indent_spaces) {
  const std::string indent = Indent(indent_spaces);
  const std::string child_indent = Indent(indent_spaces + 2);
  std::ostringstream json;
  json << "{\n";
  json << child_indent << "\"caseName\": \"" << JsonEscape(result.case_name) << "\",\n";
  json << child_indent << "\"modelKind\": \"" << JsonEscape(result.model_kind) << "\",\n";
  json << child_indent << "\"success\": " << (result.success ? "true" : "false") << ",\n";
  json << child_indent << "\"failureReason\": \"" << JsonEscape(result.failure_reason) << "\",\n";
  json << child_indent << "\"outputsMatch\": " << (result.outputs_match ? "true" : "false") << ",\n";
  json << child_indent << "\"expectedOutputShape\": " << RenderInt64ArrayJson(result.expected_output_shape) << ",\n";
  json << child_indent << "\"actualOutputShape\": " << RenderInt64ArrayJson(result.actual_output_shape) << ",\n";
  json << child_indent << "\"expectedOutput\": " << RenderFloatArrayJson(result.expected_output) << ",\n";
  json << child_indent << "\"actualOutput\": " << RenderFloatArrayJson(result.actual_output) << ",\n";
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
  json << "  \"ortLibraryPath\": \"" << JsonEscape(report.ort_lib_path) << "\",\n";
  json << "  \"providerName\": \"" << JsonEscape(report.provider_name) << "\",\n";
  json << "  \"caseSelector\": \"" << JsonEscape(report.case_selector) << "\",\n";
  json << "  \"ortRuntimeVersion\": \"" << JsonEscape(report.ort_runtime_version) << "\",\n";
  json << "  \"ortHeaderApiVersion\": " << report.ort_header_api_version << ",\n";
  json << "  \"ortApiVersionRequested\": " << report.ort_api_version_requested << ",\n";
  json << "  \"availableProviders\": " << RenderStringArrayJson(report.available_providers, 2) << ",\n";
  json << "  \"operations\": {\n";
  json << "    \"createEnv\": " << RenderStatusJson(report.create_env_status, 4) << ",\n";
  json << "    \"createSessionOptions\": " << RenderStatusJson(report.create_session_options_status, 4) << ",\n";
  json << "    \"appendProvider\": " << RenderStatusJson(report.append_provider_status, 4) << '\n';
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

std::vector<SmokeCaseSpec> BuildSmokeCases() {
  return {
      SmokeCaseSpec{
          .case_name = "add",
          .model_kind = SmokeModelKind::kAdd,
          .input_dims = {{1, 4}, {1, 4}},
          .output_dims = {1, 4},
          .inputs = {{1.0f, 2.0f, 3.0f, 4.0f}, {10.0f, 20.0f, 30.0f, 40.0f}},
          .expected_output = {11.0f, 22.0f, 33.0f, 44.0f},
      },
      SmokeCaseSpec{
          .case_name = "relu",
          .model_kind = SmokeModelKind::kRelu,
          .input_dims = {{1, 4}},
          .output_dims = {1, 4},
          .inputs = {{-2.0f, -1.0f, 0.0f, 3.0f}},
          .expected_output = {0.0f, 0.0f, 0.0f, 3.0f},
      },
      SmokeCaseSpec{
          .case_name = "matmul",
          .model_kind = SmokeModelKind::kMatMul,
          .input_dims = {{2, 3}, {3, 2}},
          .output_dims = {2, 2},
          .inputs = {{1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f}, {7.0f, 8.0f, 9.0f, 10.0f, 11.0f, 12.0f}},
          .expected_output = {58.0f, 64.0f, 139.0f, 154.0f},
      },
      SmokeCaseSpec{
          .case_name = "matmul_add",
          .model_kind = SmokeModelKind::kMatMulAdd,
          .input_dims = {{2, 3}, {3, 2}, {2, 2}},
          .output_dims = {2, 2},
          .inputs = {
              {1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f},
              {7.0f, 8.0f, 9.0f, 10.0f, 11.0f, 12.0f},
              {1.0f, -2.0f, 3.0f, -4.0f},
          },
          .expected_output = {59.0f, 62.0f, 142.0f, 150.0f},
      },
      SmokeCaseSpec{
          .case_name = "matmul_add_relu",
          .model_kind = SmokeModelKind::kMatMulAddRelu,
          .input_dims = {{2, 2}, {2, 2}, {2, 2}},
          .output_dims = {2, 2},
          .inputs = {
              {1.0f, 2.0f, 3.0f, 4.0f},
              {5.0f, 6.0f, 7.0f, 8.0f},
              {-20.0f, -30.0f, 10.0f, -60.0f},
          },
          .expected_output = {0.0f, 0.0f, 53.0f, 0.0f},
      },
      SmokeCaseSpec{
          .case_name = "add_relu",
          .model_kind = SmokeModelKind::kAddRelu,
          .input_dims = {{1, 4}, {1, 4}},
          .output_dims = {1, 4},
          .inputs = {{-5.0f, 1.0f, -2.0f, 7.0f}, {3.0f, -4.0f, 5.0f, -1.0f}},
          .expected_output = {0.0f, 0.0f, 3.0f, 6.0f},
      },
  };
}

std::vector<SmokeCaseSpec> SelectSmokeCases(const std::vector<SmokeCaseSpec>& cases, const std::string& case_selector) {
  if (case_selector == "all") {
    return cases;
  }
  std::vector<SmokeCaseSpec> selected;
  for (const SmokeCaseSpec& spec : cases) {
    if (spec.case_name == case_selector) {
      selected.push_back(spec);
      break;
    }
  }
  return selected;
}

OrtStatus* CreateFloatValueInfo(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const char* name,
    const std::vector<int64_t>& dims,
    OrtValueInfo** value_info_out) {
  if (value_info_out == nullptr) {
    return api->CreateStatus(ORT_INVALID_ARGUMENT, "incumbent session smoke requires a value_info_out pointer.");
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

OrtStatus* CreateAddModel(const OrtApi* api, const OrtModelEditorApi* model_editor_api, const SmokeCaseSpec& spec, OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* lhs = nullptr;
  OrtValueInfo* rhs = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* add_node = nullptr;
  OrtStatus* status = CreateModelShell(model_editor_api, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "lhs", spec.input_dims[0], &lhs);
  status = CreateFloatValueInfo(api, model_editor_api, "lhs", spec.input_dims[0], &lhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "rhs", spec.input_dims[1], &rhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", spec.output_dims, &output);
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

OrtStatus* CreateReluModel(const OrtApi* api, const OrtModelEditorApi* model_editor_api, const SmokeCaseSpec& spec, OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* input = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* relu_node = nullptr;
  OrtStatus* status = CreateModelShell(model_editor_api, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "input", spec.input_dims[0], &input);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", spec.output_dims, &output);
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

OrtStatus* CreateMatMulModel(const OrtApi* api, const OrtModelEditorApi* model_editor_api, const SmokeCaseSpec& spec, OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* lhs = nullptr;
  OrtValueInfo* rhs = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* matmul_node = nullptr;
  OrtStatus* status = CreateModelShell(model_editor_api, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "lhs", spec.input_dims[0], &lhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "rhs", spec.input_dims[1], &rhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", spec.output_dims, &output);
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
    status = model_editor_api->CreateNode("MatMul", "", "matmul0", input_names, 2, output_names, 1, nullptr, 0, &matmul_node);
    if (status != nullptr) goto cleanup;
  }
  status = model_editor_api->AddNodeToGraph(graph, matmul_node);
  if (status != nullptr) goto cleanup;
  matmul_node = nullptr;
  status = model_editor_api->AddGraphToModel(model, graph);
  if (status != nullptr) goto cleanup;
  graph = nullptr;
  *out_model = model;
  model = nullptr;

cleanup:
  if (matmul_node != nullptr) api->ReleaseNode(matmul_node);
  if (lhs != nullptr) api->ReleaseValueInfo(lhs);
  if (rhs != nullptr) api->ReleaseValueInfo(rhs);
  if (output != nullptr) api->ReleaseValueInfo(output);
  if (graph != nullptr) api->ReleaseGraph(graph);
  if (model != nullptr) api->ReleaseModel(model);
  return status;
}

OrtStatus* CreateAddReluModel(const OrtApi* api, const OrtModelEditorApi* model_editor_api, const SmokeCaseSpec& spec, OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* lhs = nullptr;
  OrtValueInfo* rhs = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* add_node = nullptr;
  OrtNode* relu_node = nullptr;
  OrtStatus* status = CreateModelShell(model_editor_api, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "lhs", spec.input_dims[0], &lhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "rhs", spec.input_dims[1], &rhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", spec.output_dims, &output);
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

OrtStatus* CreateMatMulAddModel(const OrtApi* api, const OrtModelEditorApi* model_editor_api, const SmokeCaseSpec& spec, OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* lhs = nullptr;
  OrtValueInfo* rhs = nullptr;
  OrtValueInfo* bias = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* matmul_node = nullptr;
  OrtNode* add_node = nullptr;
  OrtStatus* status = CreateModelShell(model_editor_api, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "lhs", spec.input_dims[0], &lhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "rhs", spec.input_dims[1], &rhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "bias", spec.input_dims[2], &bias);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", spec.output_dims, &output);
  if (status != nullptr) goto cleanup;

  {
    OrtValueInfo* inputs[] = {lhs, rhs, bias};
    status = model_editor_api->SetGraphInputs(graph, inputs, 3);
    if (status != nullptr) goto cleanup;
    lhs = nullptr;
    rhs = nullptr;
    bias = nullptr;
  }
  {
    OrtValueInfo* outputs[] = {output};
    status = model_editor_api->SetGraphOutputs(graph, outputs, 1);
    if (status != nullptr) goto cleanup;
    output = nullptr;
  }
  {
    const char* const input_names[] = {"lhs", "rhs"};
    const char* const output_names[] = {"product"};
    status = model_editor_api->CreateNode("MatMul", "", "matmul0", input_names, 2, output_names, 1, nullptr, 0, &matmul_node);
    if (status != nullptr) goto cleanup;
  }
  status = model_editor_api->AddNodeToGraph(graph, matmul_node);
  if (status != nullptr) goto cleanup;
  matmul_node = nullptr;
  {
    const char* const input_names[] = {"product", "bias"};
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
  if (matmul_node != nullptr) api->ReleaseNode(matmul_node);
  if (add_node != nullptr) api->ReleaseNode(add_node);
  if (lhs != nullptr) api->ReleaseValueInfo(lhs);
  if (rhs != nullptr) api->ReleaseValueInfo(rhs);
  if (bias != nullptr) api->ReleaseValueInfo(bias);
  if (output != nullptr) api->ReleaseValueInfo(output);
  if (graph != nullptr) api->ReleaseGraph(graph);
  if (model != nullptr) api->ReleaseModel(model);
  return status;
}

OrtStatus* CreateMatMulAddReluModel(const OrtApi* api, const OrtModelEditorApi* model_editor_api, const SmokeCaseSpec& spec, OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* lhs = nullptr;
  OrtValueInfo* rhs = nullptr;
  OrtValueInfo* bias = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* matmul_node = nullptr;
  OrtNode* add_node = nullptr;
  OrtNode* relu_node = nullptr;
  OrtStatus* status = CreateModelShell(model_editor_api, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "lhs", spec.input_dims[0], &lhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "rhs", spec.input_dims[1], &rhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "bias", spec.input_dims[2], &bias);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", spec.output_dims, &output);
  if (status != nullptr) goto cleanup;

  {
    OrtValueInfo* inputs[] = {lhs, rhs, bias};
    status = model_editor_api->SetGraphInputs(graph, inputs, 3);
    if (status != nullptr) goto cleanup;
    lhs = nullptr;
    rhs = nullptr;
    bias = nullptr;
  }
  {
    OrtValueInfo* outputs[] = {output};
    status = model_editor_api->SetGraphOutputs(graph, outputs, 1);
    if (status != nullptr) goto cleanup;
    output = nullptr;
  }
  {
    const char* const input_names[] = {"lhs", "rhs"};
    const char* const output_names[] = {"product"};
    status = model_editor_api->CreateNode("MatMul", "", "matmul0", input_names, 2, output_names, 1, nullptr, 0, &matmul_node);
    if (status != nullptr) goto cleanup;
  }
  status = model_editor_api->AddNodeToGraph(graph, matmul_node);
  if (status != nullptr) goto cleanup;
  matmul_node = nullptr;
  {
    const char* const input_names[] = {"product", "bias"};
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
  if (matmul_node != nullptr) api->ReleaseNode(matmul_node);
  if (add_node != nullptr) api->ReleaseNode(add_node);
  if (relu_node != nullptr) api->ReleaseNode(relu_node);
  if (lhs != nullptr) api->ReleaseValueInfo(lhs);
  if (rhs != nullptr) api->ReleaseValueInfo(rhs);
  if (bias != nullptr) api->ReleaseValueInfo(bias);
  if (output != nullptr) api->ReleaseValueInfo(output);
  if (graph != nullptr) api->ReleaseGraph(graph);
  if (model != nullptr) api->ReleaseModel(model);
  return status;
}

OrtStatus* CreateSmokeModel(const OrtApi* api, const OrtModelEditorApi* model_editor_api, const SmokeCaseSpec& spec, OrtModel** out_model) {
  switch (spec.model_kind) {
    case SmokeModelKind::kAdd:
      return CreateAddModel(api, model_editor_api, spec, out_model);
    case SmokeModelKind::kRelu:
      return CreateReluModel(api, model_editor_api, spec, out_model);
    case SmokeModelKind::kMatMul:
      return CreateMatMulModel(api, model_editor_api, spec, out_model);
    case SmokeModelKind::kMatMulAdd:
      return CreateMatMulAddModel(api, model_editor_api, spec, out_model);
    case SmokeModelKind::kMatMulAddRelu:
      return CreateMatMulAddReluModel(api, model_editor_api, spec, out_model);
    case SmokeModelKind::kAddRelu:
      return CreateAddReluModel(api, model_editor_api, spec, out_model);
  }
  return api->CreateStatus(ORT_FAIL, "incumbent session smoke reached an unknown model kind.");
}

OrtStatus* ReadFloatTensor(const OrtApi* api, const OrtValue* value, std::vector<int64_t>* dims_out, std::vector<float>* values_out) {
  if (dims_out == nullptr || values_out == nullptr) {
    return api->CreateStatus(ORT_INVALID_ARGUMENT, "incumbent session smoke requires dims_out and values_out pointers.");
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
    return api->CreateStatus(ORT_NOT_IMPLEMENTED, "incumbent session smoke expects float32 outputs.");
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
    return api->CreateStatus(ORT_FAIL, "incumbent session smoke received null output data.");
  }

  const auto* floats = static_cast<const float*>(data);
  values_out->assign(floats, floats + element_count);
  return nullptr;
}

bool RunSmokeCase(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    OrtEnv* env,
    OrtSessionOptions* session_options,
    const SmokeCaseSpec& spec,
    SmokeCaseResult* result) {
  result->case_name = spec.case_name;
  result->model_kind = SmokeModelKindName(spec.model_kind);
  result->expected_output_shape = spec.output_dims;
  result->expected_output = spec.expected_output;

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
    OrtAllocator* allocator = nullptr;
    status = api->GetAllocatorWithDefaultOptions(&allocator);
    result->run_status = CaptureStatus(api, status);
    if (!result->run_status.ok) {
      result->failure_reason = "GetAllocatorWithDefaultOptions failed.";
      goto cleanup;
    }

    for (size_t index = 0; index < inputs.size(); ++index) {
      const std::vector<int64_t>& dims = spec.input_dims[index];
      status = api->CreateTensorAsOrtValue(
          allocator,
          dims.empty() ? nullptr : dims.data(),
          dims.size(),
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

      std::memcpy(input_data, spec.inputs[index].data(), spec.inputs[index].size() * sizeof(float));
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

  result->success = result->failure_reason.empty();
  return result->success;
}

int RunSessionSmoke(const CliOptions& options, SessionSmokeReport* report) {
  report->ort_lib_path = options.ort_lib_path;
  report->provider_name = options.provider_name;
  report->case_selector = options.case_selector;

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
  const OrtModelEditorApi* model_editor_api = nullptr;

  OrtStatus* status = api->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "doe-ort-incumbent-session-smoke", &env);
  report->create_env_status = CaptureStatus(api, status);
  if (!report->create_env_status.ok) {
    report->failure_reason = "CreateEnv failed for ORT incumbent session smoke.";
    goto cleanup;
  }

  {
    char** providers = nullptr;
    int provider_count = 0;
    status = api->GetAvailableProviders(&providers, &provider_count);
    if (status == nullptr) {
      for (int index = 0; index < provider_count; ++index) {
        if (providers[index] != nullptr) {
          report->available_providers.emplace_back(providers[index]);
        }
      }
      api->ReleaseAvailableProviders(providers, provider_count);
    } else {
      api->ReleaseStatus(status);
    }
  }

  status = api->CreateSessionOptions(&session_options);
  report->create_session_options_status = CaptureStatus(api, status);
  if (!report->create_session_options_status.ok) {
    report->failure_reason = "CreateSessionOptions failed.";
    goto cleanup;
  }

  status = api->SessionOptionsAppendExecutionProvider(session_options, options.provider_name.c_str(), nullptr, nullptr, 0);
  report->append_provider_status = CaptureStatus(api, status);
  if (!report->append_provider_status.ok) {
    report->failure_reason = "SessionOptionsAppendExecutionProvider failed.";
    goto cleanup;
  }

  model_editor_api = api->GetModelEditorApi();
  if (model_editor_api == nullptr) {
    report->failure_reason = "GetModelEditorApi returned null; host ORT build cannot create the in-memory session smoke models.";
    goto cleanup;
  }

  {
    const std::vector<SmokeCaseSpec> selected_cases = SelectSmokeCases(BuildSmokeCases(), options.case_selector);
    if (selected_cases.empty()) {
      report->failure_reason = "No smoke cases matched the requested case selector.";
      goto cleanup;
    }
    for (const SmokeCaseSpec& spec : selected_cases) {
      SmokeCaseResult case_result{};
      const bool case_ok = RunSmokeCase(api, model_editor_api, env, session_options, spec, &case_result);
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
  }

cleanup:
  if (session_options != nullptr) {
    api->ReleaseSessionOptions(session_options);
    session_options = nullptr;
  }
  if (env != nullptr) {
    api->ReleaseEnv(env);
    env = nullptr;
  }
  report->success = report->failure_reason.empty();
  return report->success ? 0 : 1;
}

}  // namespace

extern "C" int doeOrtIncumbentSessionSmokeMain(int argc, char** argv) {
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
