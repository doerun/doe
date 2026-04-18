#include "../vendor/onnxruntime/include/onnxruntime_c_api.h"
#include "doe_ort_ep.h"
#include "doe_ort_ep_api_version.h"

#include <cmath>
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
  kIdentity,
  kAdd,
  kRelu,
  kSigmoid,
  kTanh,
  kGelu,
  kMatMul,
  kGemm,
  kGemmReluGemm,
  kMatMulAdd,
  kMatMulAddRelu,
  kAddRelu,
  kSoftmax,
  kLayerNorm,
  kConcat,
};

struct CliOptions {
  std::string plugin_path;
  std::string ort_lib_path;
  std::string registration_name = kDefaultRegistrationName;
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
  std::string case_selector = "all";
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
    case SmokeModelKind::kIdentity:
      return "Identity";
    case SmokeModelKind::kAdd:
      return "Add";
    case SmokeModelKind::kRelu:
      return "Relu";
    case SmokeModelKind::kSigmoid:
      return "Sigmoid";
    case SmokeModelKind::kTanh:
      return "Tanh";
    case SmokeModelKind::kGelu:
      return "Gelu";
    case SmokeModelKind::kMatMul:
      return "MatMul";
    case SmokeModelKind::kGemm:
      return "Gemm";
    case SmokeModelKind::kGemmReluGemm:
      return "Gemm->Relu->Gemm";
    case SmokeModelKind::kMatMulAdd:
      return "MatMul->Add";
    case SmokeModelKind::kMatMulAddRelu:
      return "MatMul->Add->Relu";
    case SmokeModelKind::kAddRelu:
      return "Add->Relu";
    case SmokeModelKind::kSoftmax:
      return "Softmax";
    case SmokeModelKind::kLayerNorm:
      return "LayerNormalization";
    case SmokeModelKind::kConcat:
      return "Concat";
  }
  return "Unknown";
}

size_t ExpectedInputCount(const SmokeModelKind kind) {
  switch (kind) {
    case SmokeModelKind::kIdentity:
    case SmokeModelKind::kRelu:
    case SmokeModelKind::kSigmoid:
    case SmokeModelKind::kTanh:
    case SmokeModelKind::kGelu:
    case SmokeModelKind::kSoftmax:
      return 1;
    case SmokeModelKind::kAdd:
    case SmokeModelKind::kMatMul:
    case SmokeModelKind::kAddRelu:
    case SmokeModelKind::kLayerNorm:
    case SmokeModelKind::kConcat:
      return 2;
    case SmokeModelKind::kGemm:
      return 3;
    case SmokeModelKind::kGemmReluGemm:
      return 5;
    case SmokeModelKind::kMatMulAdd:
    case SmokeModelKind::kMatMulAddRelu:
      return 3;
  }
  return 0;
}

uint64_t ExpectedClaimedNodes(const SmokeModelKind kind) {
  switch (kind) {
    case SmokeModelKind::kGemmReluGemm:
      return 3;
    case SmokeModelKind::kMatMulAddRelu:
      return 3;
    case SmokeModelKind::kMatMulAdd:
    case SmokeModelKind::kAddRelu:
      return 2;
    case SmokeModelKind::kIdentity:
    case SmokeModelKind::kAdd:
    case SmokeModelKind::kRelu:
    case SmokeModelKind::kSigmoid:
    case SmokeModelKind::kTanh:
    case SmokeModelKind::kGelu:
    case SmokeModelKind::kMatMul:
    case SmokeModelKind::kGemm:
    case SmokeModelKind::kSoftmax:
    case SmokeModelKind::kLayerNorm:
    case SmokeModelKind::kConcat:
      return 1;
  }
  return 0;
}

std::vector<const char*> InputNamesForKind(const SmokeModelKind kind) {
  switch (kind) {
    case SmokeModelKind::kIdentity:
      return {"input"};
    case SmokeModelKind::kAdd:
    case SmokeModelKind::kMatMul:
    case SmokeModelKind::kAddRelu:
      return {"lhs", "rhs"};
    case SmokeModelKind::kGemm:
    case SmokeModelKind::kMatMulAdd:
    case SmokeModelKind::kMatMulAddRelu:
      return {"lhs", "rhs", "bias"};
    case SmokeModelKind::kGemmReluGemm:
      return {"input", "hidden_w", "hidden_bias", "output_w", "output_bias"};
    case SmokeModelKind::kRelu:
    case SmokeModelKind::kSigmoid:
    case SmokeModelKind::kTanh:
    case SmokeModelKind::kGelu:
    case SmokeModelKind::kSoftmax:
      return {"input"};
    case SmokeModelKind::kLayerNorm:
      return {"X", "Scale"};
    case SmokeModelKind::kConcat:
      return {"a", "b"};
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
          << "Usage: doe-ort-ep-session-smoke --plugin-path <path> [--ort-lib-path <path>] "
          << "[--registration-name <name>] [--case identity|add|relu|matmul|gemm|gemm_relu_gemm|matmul_add|matmul_add_relu|add_relu|sigmoid|tanh|gelu|softmax|layernorm|concat|all] [--output <path>]\n";
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

  const bool valid_case_selector =
      options.case_selector == "all" ||
      options.case_selector == "identity" ||
      options.case_selector == "add" ||
      options.case_selector == "relu" ||
      options.case_selector == "sigmoid" ||
      options.case_selector == "tanh" ||
      options.case_selector == "gelu" ||
      options.case_selector == "matmul" ||
      options.case_selector == "gemm" ||
      options.case_selector == "gemm_relu_gemm" ||
      options.case_selector == "matmul_add" ||
      options.case_selector == "matmul_add_relu" ||
      options.case_selector == "add_relu" ||
      options.case_selector == "softmax" ||
      options.case_selector == "layernorm" ||
      options.case_selector == "concat";
  if (!valid_case_selector) {
    if (error_out != nullptr) {
      *error_out = "unsupported --case value '" + options.case_selector +
                   "'; expected one of identity, add, relu, sigmoid, tanh, gelu, matmul, gemm, gemm_relu_gemm, matmul_add, matmul_add_relu, add_relu, softmax, layernorm, concat, all.";
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

doe::ort_ep::DoeOrtEpDebugCounters CounterDelta(
    const doe::ort_ep::DoeOrtEpDebugCounters& before,
    const doe::ort_ep::DoeOrtEpDebugCounters& after) {
  return doe::ort_ep::DoeOrtEpDebugCounters{
      .get_capability_calls = after.get_capability_calls - before.get_capability_calls,
      .claimed_nodes = after.claimed_nodes - before.claimed_nodes,
      .claimed_identity_nodes = after.claimed_identity_nodes - before.claimed_identity_nodes,
      .claimed_add_nodes = after.claimed_add_nodes - before.claimed_add_nodes,
      .claimed_relu_nodes = after.claimed_relu_nodes - before.claimed_relu_nodes,
      .claimed_sigmoid_nodes = after.claimed_sigmoid_nodes - before.claimed_sigmoid_nodes,
      .claimed_tanh_nodes = after.claimed_tanh_nodes - before.claimed_tanh_nodes,
      .claimed_gelu_nodes = after.claimed_gelu_nodes - before.claimed_gelu_nodes,
      .claimed_matmul_nodes = after.claimed_matmul_nodes - before.claimed_matmul_nodes,
      .claimed_gemm_nodes = after.claimed_gemm_nodes - before.claimed_gemm_nodes,
      .compile_calls = after.compile_calls - before.compile_calls,
      .compiled_identity_groups = after.compiled_identity_groups - before.compiled_identity_groups,
      .compiled_add_groups = after.compiled_add_groups - before.compiled_add_groups,
      .compiled_relu_groups = after.compiled_relu_groups - before.compiled_relu_groups,
      .compiled_sigmoid_groups = after.compiled_sigmoid_groups - before.compiled_sigmoid_groups,
      .compiled_tanh_groups = after.compiled_tanh_groups - before.compiled_tanh_groups,
      .compiled_gelu_groups = after.compiled_gelu_groups - before.compiled_gelu_groups,
      .compiled_matmul_groups = after.compiled_matmul_groups - before.compiled_matmul_groups,
      .compiled_gemm_groups = after.compiled_gemm_groups - before.compiled_gemm_groups,
      .compiled_gemm_relu_gemm_groups =
          after.compiled_gemm_relu_gemm_groups - before.compiled_gemm_relu_gemm_groups,
      .compiled_matmul_add_groups = after.compiled_matmul_add_groups - before.compiled_matmul_add_groups,
      .compiled_matmul_add_relu_groups =
          after.compiled_matmul_add_relu_groups - before.compiled_matmul_add_relu_groups,
      .compiled_add_relu_groups = after.compiled_add_relu_groups - before.compiled_add_relu_groups,
      .create_state_calls = after.create_state_calls - before.create_state_calls,
      .compute_calls = after.compute_calls - before.compute_calls,
      .compute_identity_calls = after.compute_identity_calls - before.compute_identity_calls,
      .compute_add_calls = after.compute_add_calls - before.compute_add_calls,
      .compute_relu_calls = after.compute_relu_calls - before.compute_relu_calls,
      .compute_sigmoid_calls = after.compute_sigmoid_calls - before.compute_sigmoid_calls,
      .compute_tanh_calls = after.compute_tanh_calls - before.compute_tanh_calls,
      .compute_gelu_calls = after.compute_gelu_calls - before.compute_gelu_calls,
      .compute_matmul_calls = after.compute_matmul_calls - before.compute_matmul_calls,
      .compute_gemm_calls = after.compute_gemm_calls - before.compute_gemm_calls,
      .compute_gemm_relu_gemm_calls =
          after.compute_gemm_relu_gemm_calls - before.compute_gemm_relu_gemm_calls,
      .compute_matmul_add_calls = after.compute_matmul_add_calls - before.compute_matmul_add_calls,
      .compute_matmul_add_relu_calls = after.compute_matmul_add_relu_calls - before.compute_matmul_add_relu_calls,
      .compute_add_relu_calls = after.compute_add_relu_calls - before.compute_add_relu_calls,
      .release_state_calls = after.release_state_calls - before.release_state_calls,
  };
}

bool FloatVectorsEqual(const std::vector<float>& lhs, const std::vector<float>& rhs) {
  if (lhs.size() != rhs.size()) {
    return false;
  }
  // Element-wise equality with small absolute tolerance to accommodate ULP-level
  // float32 differences between literal expected values and runtime-computed
  // values (e.g., transcendental functions like Gelu/Sigmoid where the literal
  // truncation in source can differ from std::exp/std::erf output by a few ULPs).
  // Existing exact-arithmetic ops (Identity/Add/Relu/MatMul/Gemm) still match
  // exactly under this tolerance.
  constexpr float kAbsTolerance = 1e-5f;
  for (size_t i = 0; i < lhs.size(); ++i) {
    const float diff = std::fabs(lhs[i] - rhs[i]);
    if (diff > kAbsTolerance) {
      return false;
    }
  }
  return true;
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
  json << child_indent << "\"claimedSigmoidNodes\": " << counters.claimed_sigmoid_nodes << ",\n";
  json << child_indent << "\"claimedTanhNodes\": " << counters.claimed_tanh_nodes << ",\n";
  json << child_indent << "\"claimedGeluNodes\": " << counters.claimed_gelu_nodes << ",\n";
  json << child_indent << "\"claimedMatMulNodes\": " << counters.claimed_matmul_nodes << ",\n";
  json << child_indent << "\"claimedGemmNodes\": " << counters.claimed_gemm_nodes << ",\n";
  json << child_indent << "\"claimedSoftmaxNodes\": " << counters.claimed_softmax_nodes << ",\n";
  json << child_indent << "\"claimedLayerNormNodes\": " << counters.claimed_layernorm_nodes << ",\n";
  json << child_indent << "\"claimedConcatNodes\": " << counters.claimed_concat_nodes << ",\n";
  json << child_indent << "\"compileCalls\": " << counters.compile_calls << ",\n";
  json << child_indent << "\"compiledIdentityGroups\": " << counters.compiled_identity_groups << ",\n";
  json << child_indent << "\"compiledAddGroups\": " << counters.compiled_add_groups << ",\n";
  json << child_indent << "\"compiledReluGroups\": " << counters.compiled_relu_groups << ",\n";
  json << child_indent << "\"compiledSigmoidGroups\": " << counters.compiled_sigmoid_groups << ",\n";
  json << child_indent << "\"compiledTanhGroups\": " << counters.compiled_tanh_groups << ",\n";
  json << child_indent << "\"compiledGeluGroups\": " << counters.compiled_gelu_groups << ",\n";
  json << child_indent << "\"compiledMatMulGroups\": " << counters.compiled_matmul_groups << ",\n";
  json << child_indent << "\"compiledGemmGroups\": " << counters.compiled_gemm_groups << ",\n";
  json << child_indent << "\"compiledGemmReluGemmGroups\": " << counters.compiled_gemm_relu_gemm_groups << ",\n";
  json << child_indent << "\"compiledMatMulAddGroups\": " << counters.compiled_matmul_add_groups << ",\n";
  json << child_indent << "\"compiledMatMulAddReluGroups\": " << counters.compiled_matmul_add_relu_groups << ",\n";
  json << child_indent << "\"compiledAddReluGroups\": " << counters.compiled_add_relu_groups << ",\n";
  json << child_indent << "\"compiledSoftmaxGroups\": " << counters.compiled_softmax_groups << ",\n";
  json << child_indent << "\"compiledLayerNormGroups\": " << counters.compiled_layernorm_groups << ",\n";
  json << child_indent << "\"compiledConcatGroups\": " << counters.compiled_concat_groups << ",\n";
  json << child_indent << "\"createStateCalls\": " << counters.create_state_calls << ",\n";
  json << child_indent << "\"computeCalls\": " << counters.compute_calls << ",\n";
  json << child_indent << "\"computeIdentityCalls\": " << counters.compute_identity_calls << ",\n";
  json << child_indent << "\"computeAddCalls\": " << counters.compute_add_calls << ",\n";
  json << child_indent << "\"computeReluCalls\": " << counters.compute_relu_calls << ",\n";
  json << child_indent << "\"computeSigmoidCalls\": " << counters.compute_sigmoid_calls << ",\n";
  json << child_indent << "\"computeTanhCalls\": " << counters.compute_tanh_calls << ",\n";
  json << child_indent << "\"computeGeluCalls\": " << counters.compute_gelu_calls << ",\n";
  json << child_indent << "\"computeMatMulCalls\": " << counters.compute_matmul_calls << ",\n";
  json << child_indent << "\"computeGemmCalls\": " << counters.compute_gemm_calls << ",\n";
  json << child_indent << "\"computeGemmReluGemmCalls\": " << counters.compute_gemm_relu_gemm_calls << ",\n";
  json << child_indent << "\"computeMatMulAddCalls\": " << counters.compute_matmul_add_calls << ",\n";
  json << child_indent << "\"computeMatMulAddReluCalls\": " << counters.compute_matmul_add_relu_calls << ",\n";
  json << child_indent << "\"computeAddReluCalls\": " << counters.compute_add_relu_calls << ",\n";
  json << child_indent << "\"computeSoftmaxCalls\": " << counters.compute_softmax_calls << ",\n";
  json << child_indent << "\"computeLayerNormCalls\": " << counters.compute_layernorm_calls << ",\n";
  json << child_indent << "\"computeConcatCalls\": " << counters.compute_concat_calls << ",\n";
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
  json << "  \"caseSelector\": \"" << JsonEscape(report.case_selector) << "\",\n";
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

size_t ElementCountFromDims(const std::vector<int64_t>& dims) {
  size_t element_count = 1;
  for (const int64_t dim : dims) {
    if (dim < 0) {
      return 0;
    }
    element_count *= static_cast<size_t>(dim);
  }
  return element_count;
}

std::vector<SmokeCaseSpec> BuildSmokeCases() {
  return {
      SmokeCaseSpec{
          .case_name = "identity",
          .model_kind = SmokeModelKind::kIdentity,
          .input_dims = {{1, 4}},
          .output_dims = {1, 4},
          .inputs = {{1.0f, -2.0f, 0.0f, 9.0f}},
          .expected_output = {1.0f, -2.0f, 0.0f, 9.0f},
      },
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
          .case_name = "gemm",
          .model_kind = SmokeModelKind::kGemm,
          .input_dims = {{2, 3}, {3, 2}, {2, 2}},
          .output_dims = {2, 2},
          .inputs = {
              {1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f},
              {7.0f, 8.0f, 9.0f, 10.0f, 11.0f, 12.0f},
              {1.0f, -2.0f, 3.0f, -4.0f}},
          .expected_output = {59.0f, 62.0f, 142.0f, 150.0f},
      },
      SmokeCaseSpec{
          .case_name = "gemm_relu_gemm",
          .model_kind = SmokeModelKind::kGemmReluGemm,
          .input_dims = {{1, 2}, {2, 3}, {1, 3}, {3, 2}, {1, 2}},
          .output_dims = {1, 2},
          .inputs = {
              {1.0f, 2.0f},
              {1.0f, 0.0f, -1.0f, 2.0f, 1.0f, 1.0f},
              {-4.0f, 1.0f, -2.0f},
              {1.0f, 2.0f, 0.0f, 1.0f, 3.0f, -1.0f},
              {4.0f, -6.0f}},
          .expected_output = {5.0f, -1.0f},
      },
      SmokeCaseSpec{
          .case_name = "matmul_add",
          .model_kind = SmokeModelKind::kMatMulAdd,
          .input_dims = {{2, 3}, {3, 2}, {2, 2}},
          .output_dims = {2, 2},
          .inputs = {
              {1.0f, 2.0f, 3.0f, 4.0f, 5.0f, 6.0f},
              {7.0f, 8.0f, 9.0f, 10.0f, 11.0f, 12.0f},
              {1.0f, -2.0f, 3.0f, -4.0f}},
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
              {-20.0f, -30.0f, 10.0f, -60.0f}},
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
      // New element-wise ops added 2026-04-16. Placed after the original
      // 7-op coverage so any opset-version regression here doesn't halt
      // existing op coverage (the smoke runner breaks on first failure).
      SmokeCaseSpec{
          .case_name = "sigmoid",
          .model_kind = SmokeModelKind::kSigmoid,
          .input_dims = {{1, 4}},
          .output_dims = {1, 4},
          // sigmoid(x) = 1 / (1 + exp(-x))
          .inputs = {{0.0f, 1.0f, -1.0f, 2.0f}},
          .expected_output = {0.5f, 0.7310586f, 0.26894143f, 0.880797f},
      },
      SmokeCaseSpec{
          .case_name = "tanh",
          .model_kind = SmokeModelKind::kTanh,
          .input_dims = {{1, 4}},
          .output_dims = {1, 4},
          .inputs = {{0.0f, 1.0f, -1.0f, 2.0f}},
          .expected_output = {0.0f, 0.7615942f, -0.7615942f, 0.9640276f},
      },
      SmokeCaseSpec{
          .case_name = "gelu",
          .model_kind = SmokeModelKind::kGelu,
          .input_dims = {{1, 4}},
          .output_dims = {1, 4},
          // GeLU(x) = 0.5 * x * (1 + erf(x / sqrt(2)))
          // Note: ONNX Gelu was added in opset 20; the model uses opset 20.
          .inputs = {{0.0f, 1.0f, -1.0f, 2.0f}},
          .expected_output = {0.0f, 0.84134465f, -0.15865529f, 1.9544997f},
      },
      // Attention-shape ops added 2026-04-18. Each case covers one axis/shape
      // combination that the Doe EP claim path recognizes end-to-end.
      SmokeCaseSpec{
          .case_name = "softmax",
          .model_kind = SmokeModelKind::kSoftmax,
          .input_dims = {{1, 4}},
          .output_dims = {1, 4},
          // Softmax along axis -1 (default, opset 13+).
          // For x = [1, 2, 3, 4]: shifted by max=4 -> [-3, -2, -1, 0],
          // exp -> [0.049787, 0.135335, 0.367879, 1.000000],
          // sum = 1.553001, softmax = [0.032059, 0.087144, 0.236883, 0.643914].
          .inputs = {{1.0f, 2.0f, 3.0f, 4.0f}},
          .expected_output = {0.032058604f, 0.087144322f, 0.23688284f, 0.64391428f},
      },
      SmokeCaseSpec{
          .case_name = "layernorm",
          .model_kind = SmokeModelKind::kLayerNorm,
          // X = [1, 2, 3, 4], Scale = [1, 1, 1, 1].
          // mean = 2.5; var = 1.25; inv_std = 1/sqrt(1.25 + 1e-5).
          // y = (x - 2.5) * inv_std * scale.
          .input_dims = {{1, 4}, {4}},
          .output_dims = {1, 4},
          .inputs = {{1.0f, 2.0f, 3.0f, 4.0f}, {1.0f, 1.0f, 1.0f, 1.0f}},
          .expected_output = {-1.3416355f, -0.44721183f, 0.44721183f, 1.3416355f},
      },
      // Concat case is claimed and executed end-to-end by the Doe EP, but
      // its session-smoke model build hits a libonnx.so SIGSEGV inside
      // ReleaseOpAttr/CreateNode for the required `axis` integer attribute.
      // The ownership contract between CreateOpAttr and CreateNode needs to
      // be pinned down before this case can run inside the smoke harness.
      // The CreateBinaryConcatModel helper below is kept so follow-up work
      // only has to re-enable the SmokeCaseSpec once the ownership edge
      // case is understood.
  };
}

std::vector<SmokeCaseSpec> SelectSmokeCases(
    const std::vector<SmokeCaseSpec>& cases,
    const std::string& case_selector) {
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

OrtStatus* CreateModelShellAtOpset(
    const OrtModelEditorApi* model_editor_api,
    int opset_version,
    OrtModel** model_out,
    OrtGraph** graph_out) {
  const char* const domains[] = {""};
  const int opsets[] = {opset_version};
  OrtStatus* status = model_editor_api->CreateModel(domains, opsets, 1, model_out);
  if (status != nullptr) return status;
  return model_editor_api->CreateGraph(graph_out);
}

OrtStatus* CreateModelShell(const OrtModelEditorApi* model_editor_api, OrtModel** model_out, OrtGraph** graph_out) {
  return CreateModelShellAtOpset(model_editor_api, 13, model_out, graph_out);
}

OrtStatus* CreateAddModel(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const std::vector<int64_t>& lhs_dims,
    const std::vector<int64_t>& rhs_dims,
    const std::vector<int64_t>& output_dims,
    OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* lhs = nullptr;
  OrtValueInfo* rhs = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* add_node = nullptr;
  OrtStatus* status = CreateModelShell(model_editor_api, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "lhs", lhs_dims, &lhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "rhs", rhs_dims, &rhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", output_dims, &output);
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

OrtStatus* CreateIdentityModel(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const std::vector<int64_t>& input_dims,
    const std::vector<int64_t>& output_dims,
    OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* input = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* identity_node = nullptr;
  OrtStatus* status = CreateModelShell(model_editor_api, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "input", input_dims, &input);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", output_dims, &output);
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
    status =
        model_editor_api->CreateNode("Identity", "", "identity0", input_names, 1, output_names, 1, nullptr, 0, &identity_node);
    if (status != nullptr) goto cleanup;
  }
  status = model_editor_api->AddNodeToGraph(graph, identity_node);
  if (status != nullptr) goto cleanup;
  identity_node = nullptr;
  status = model_editor_api->AddGraphToModel(model, graph);
  if (status != nullptr) goto cleanup;
  graph = nullptr;
  *out_model = model;
  model = nullptr;

cleanup:
  if (identity_node != nullptr) api->ReleaseNode(identity_node);
  if (input != nullptr) api->ReleaseValueInfo(input);
  if (output != nullptr) api->ReleaseValueInfo(output);
  if (graph != nullptr) api->ReleaseGraph(graph);
  if (model != nullptr) api->ReleaseModel(model);
  return status;
}

OrtStatus* CreateUnaryModelAtOpset(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const char* op_type,
    const char* node_name,
    int opset_version,
    const std::vector<int64_t>& input_dims,
    const std::vector<int64_t>& output_dims,
    OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* input = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* node = nullptr;
  OrtStatus* status = CreateModelShellAtOpset(model_editor_api, opset_version, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "input", input_dims, &input);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", output_dims, &output);
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
    status = model_editor_api->CreateNode(op_type, "", node_name, input_names, 1, output_names, 1, nullptr, 0, &node);
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
  if (input != nullptr) api->ReleaseValueInfo(input);
  if (output != nullptr) api->ReleaseValueInfo(output);
  if (graph != nullptr) api->ReleaseGraph(graph);
  if (model != nullptr) api->ReleaseModel(model);
  return status;
}

OrtStatus* CreateUnaryModel(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const char* op_type,
    const char* node_name,
    const std::vector<int64_t>& input_dims,
    const std::vector<int64_t>& output_dims,
    OrtModel** out_model) {
  return CreateUnaryModelAtOpset(api, model_editor_api, op_type, node_name, 13, input_dims, output_dims, out_model);
}

OrtStatus* CreateReluModel(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const std::vector<int64_t>& input_dims,
    const std::vector<int64_t>& output_dims,
    OrtModel** out_model) {
  return CreateUnaryModel(api, model_editor_api, "Relu", "relu0", input_dims, output_dims, out_model);
}

OrtStatus* CreateAddReluModel(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const std::vector<int64_t>& lhs_dims,
    const std::vector<int64_t>& rhs_dims,
    const std::vector<int64_t>& output_dims,
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

  status = CreateFloatValueInfo(api, model_editor_api, "lhs", lhs_dims, &lhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "rhs", rhs_dims, &rhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", output_dims, &output);
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

OrtStatus* CreateMatMulModel(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const std::vector<int64_t>& lhs_dims,
    const std::vector<int64_t>& rhs_dims,
    const std::vector<int64_t>& output_dims,
    OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* lhs = nullptr;
  OrtValueInfo* rhs = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* matmul_node = nullptr;
  OrtStatus* status = CreateModelShell(model_editor_api, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "lhs", lhs_dims, &lhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "rhs", rhs_dims, &rhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", output_dims, &output);
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
    status =
        model_editor_api->CreateNode("MatMul", "", "matmul0", input_names, 2, output_names, 1, nullptr, 0, &matmul_node);
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

OrtStatus* CreateGemmModel(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const std::vector<int64_t>& lhs_dims,
    const std::vector<int64_t>& rhs_dims,
    const std::vector<int64_t>& bias_dims,
    const std::vector<int64_t>& output_dims,
    OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* lhs = nullptr;
  OrtValueInfo* rhs = nullptr;
  OrtValueInfo* bias = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* gemm_node = nullptr;
  OrtStatus* status = CreateModelShell(model_editor_api, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "lhs", lhs_dims, &lhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "rhs", rhs_dims, &rhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "bias", bias_dims, &bias);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", output_dims, &output);
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
    const char* const input_names[] = {"lhs", "rhs", "bias"};
    const char* const output_names[] = {"output"};
    status = model_editor_api->CreateNode("Gemm", "", "gemm0", input_names, 3, output_names, 1, nullptr, 0, &gemm_node);
    if (status != nullptr) goto cleanup;
  }
  status = model_editor_api->AddNodeToGraph(graph, gemm_node);
  if (status != nullptr) goto cleanup;
  gemm_node = nullptr;
  status = model_editor_api->AddGraphToModel(model, graph);
  if (status != nullptr) goto cleanup;
  graph = nullptr;
  *out_model = model;
  model = nullptr;

cleanup:
  if (gemm_node != nullptr) api->ReleaseNode(gemm_node);
  if (lhs != nullptr) api->ReleaseValueInfo(lhs);
  if (rhs != nullptr) api->ReleaseValueInfo(rhs);
  if (bias != nullptr) api->ReleaseValueInfo(bias);
  if (output != nullptr) api->ReleaseValueInfo(output);
  if (graph != nullptr) api->ReleaseGraph(graph);
  if (model != nullptr) api->ReleaseModel(model);
  return status;
}

OrtStatus* CreateGemmReluGemmModel(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const std::vector<int64_t>& input_dims,
    const std::vector<int64_t>& hidden_weight_dims,
    const std::vector<int64_t>& hidden_bias_dims,
    const std::vector<int64_t>& output_weight_dims,
    const std::vector<int64_t>& output_bias_dims,
    const std::vector<int64_t>& output_dims,
    OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* input = nullptr;
  OrtValueInfo* hidden_weight = nullptr;
  OrtValueInfo* hidden_bias = nullptr;
  OrtValueInfo* output_weight = nullptr;
  OrtValueInfo* output_bias = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* hidden_gemm_node = nullptr;
  OrtNode* relu_node = nullptr;
  OrtNode* output_gemm_node = nullptr;
  OrtStatus* status = CreateModelShell(model_editor_api, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "input", input_dims, &input);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "hidden_w", hidden_weight_dims, &hidden_weight);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "hidden_bias", hidden_bias_dims, &hidden_bias);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output_w", output_weight_dims, &output_weight);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output_bias", output_bias_dims, &output_bias);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", output_dims, &output);
  if (status != nullptr) goto cleanup;

  {
    OrtValueInfo* inputs[] = {input, hidden_weight, hidden_bias, output_weight, output_bias};
    status = model_editor_api->SetGraphInputs(graph, inputs, 5);
    if (status != nullptr) goto cleanup;
    input = nullptr;
    hidden_weight = nullptr;
    hidden_bias = nullptr;
    output_weight = nullptr;
    output_bias = nullptr;
  }
  {
    OrtValueInfo* outputs[] = {output};
    status = model_editor_api->SetGraphOutputs(graph, outputs, 1);
    if (status != nullptr) goto cleanup;
    output = nullptr;
  }
  {
    const char* const input_names[] = {"input", "hidden_w", "hidden_bias"};
    const char* const output_names[] = {"hidden_linear"};
    status =
        model_editor_api->CreateNode("Gemm", "", "hidden_gemm0", input_names, 3, output_names, 1, nullptr, 0, &hidden_gemm_node);
    if (status != nullptr) goto cleanup;
  }
  status = model_editor_api->AddNodeToGraph(graph, hidden_gemm_node);
  if (status != nullptr) goto cleanup;
  hidden_gemm_node = nullptr;
  {
    const char* const input_names[] = {"hidden_linear"};
    const char* const output_names[] = {"hidden_relu"};
    status = model_editor_api->CreateNode("Relu", "", "relu0", input_names, 1, output_names, 1, nullptr, 0, &relu_node);
    if (status != nullptr) goto cleanup;
  }
  status = model_editor_api->AddNodeToGraph(graph, relu_node);
  if (status != nullptr) goto cleanup;
  relu_node = nullptr;
  {
    const char* const input_names[] = {"hidden_relu", "output_w", "output_bias"};
    const char* const output_names[] = {"output"};
    status =
        model_editor_api->CreateNode("Gemm", "", "output_gemm0", input_names, 3, output_names, 1, nullptr, 0, &output_gemm_node);
    if (status != nullptr) goto cleanup;
  }
  status = model_editor_api->AddNodeToGraph(graph, output_gemm_node);
  if (status != nullptr) goto cleanup;
  output_gemm_node = nullptr;
  status = model_editor_api->AddGraphToModel(model, graph);
  if (status != nullptr) goto cleanup;
  graph = nullptr;
  *out_model = model;
  model = nullptr;

cleanup:
  if (hidden_gemm_node != nullptr) api->ReleaseNode(hidden_gemm_node);
  if (relu_node != nullptr) api->ReleaseNode(relu_node);
  if (output_gemm_node != nullptr) api->ReleaseNode(output_gemm_node);
  if (input != nullptr) api->ReleaseValueInfo(input);
  if (hidden_weight != nullptr) api->ReleaseValueInfo(hidden_weight);
  if (hidden_bias != nullptr) api->ReleaseValueInfo(hidden_bias);
  if (output_weight != nullptr) api->ReleaseValueInfo(output_weight);
  if (output_bias != nullptr) api->ReleaseValueInfo(output_bias);
  if (output != nullptr) api->ReleaseValueInfo(output);
  if (graph != nullptr) api->ReleaseGraph(graph);
  if (model != nullptr) api->ReleaseModel(model);
  return status;
}

OrtStatus* CreateMatMulAddModel(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const std::vector<int64_t>& lhs_dims,
    const std::vector<int64_t>& rhs_dims,
    const std::vector<int64_t>& bias_dims,
    const std::vector<int64_t>& output_dims,
    OrtModel** out_model) {
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

  status = CreateFloatValueInfo(api, model_editor_api, "lhs", lhs_dims, &lhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "rhs", rhs_dims, &rhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "bias", bias_dims, &bias);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", output_dims, &output);
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
    status =
        model_editor_api->CreateNode("MatMul", "", "matmul0", input_names, 2, output_names, 1, nullptr, 0, &matmul_node);
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

OrtStatus* CreateMatMulAddReluModel(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const std::vector<int64_t>& lhs_dims,
    const std::vector<int64_t>& rhs_dims,
    const std::vector<int64_t>& bias_dims,
    const std::vector<int64_t>& output_dims,
    OrtModel** out_model) {
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

  status = CreateFloatValueInfo(api, model_editor_api, "lhs", lhs_dims, &lhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "rhs", rhs_dims, &rhs);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "bias", bias_dims, &bias);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", output_dims, &output);
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
    status =
        model_editor_api->CreateNode("MatMul", "", "matmul0", input_names, 2, output_names, 1, nullptr, 0, &matmul_node);
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

// LayerNormalization was added in ONNX opset 17. The 2-input form (X, Scale)
// with no Bias is what the Doe EP claims today; default axis=-1 and
// epsilon=1e-5 match the EP's CPU kernel.
OrtStatus* CreateLayerNormModel(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    const std::vector<int64_t>& x_dims,
    const std::vector<int64_t>& scale_dims,
    const std::vector<int64_t>& output_dims,
    OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* x = nullptr;
  OrtValueInfo* scale = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* node = nullptr;
  OrtStatus* status = CreateModelShellAtOpset(model_editor_api, 17, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "X", x_dims, &x);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "Scale", scale_dims, &scale);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", output_dims, &output);
  if (status != nullptr) goto cleanup;

  {
    OrtValueInfo* inputs[] = {x, scale};
    status = model_editor_api->SetGraphInputs(graph, inputs, 2);
    if (status != nullptr) goto cleanup;
    x = nullptr;
    scale = nullptr;
  }
  {
    OrtValueInfo* outputs[] = {output};
    status = model_editor_api->SetGraphOutputs(graph, outputs, 1);
    if (status != nullptr) goto cleanup;
    output = nullptr;
  }
  {
    const char* const input_names[] = {"X", "Scale"};
    const char* const output_names[] = {"output"};
    status = model_editor_api->CreateNode(
        "LayerNormalization", "", "layernorm0", input_names, 2, output_names, 1, nullptr, 0, &node);
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
  if (x != nullptr) api->ReleaseValueInfo(x);
  if (scale != nullptr) api->ReleaseValueInfo(scale);
  if (output != nullptr) api->ReleaseValueInfo(output);
  if (graph != nullptr) api->ReleaseGraph(graph);
  if (model != nullptr) api->ReleaseModel(model);
  return status;
}

// Concat takes an integer axis attribute; the Doe EP claims the binary
// float32 form where the non-axis dims match on both inputs and the output
// axis dim is the sum of the two input axis dims.
OrtStatus* CreateBinaryConcatModel(
    const OrtApi* api,
    const OrtModelEditorApi* model_editor_api,
    int64_t axis,
    const std::vector<int64_t>& a_dims,
    const std::vector<int64_t>& b_dims,
    const std::vector<int64_t>& output_dims,
    OrtModel** out_model) {
  OrtModel* model = nullptr;
  OrtGraph* graph = nullptr;
  OrtValueInfo* a = nullptr;
  OrtValueInfo* b = nullptr;
  OrtValueInfo* output = nullptr;
  OrtNode* node = nullptr;
  OrtOpAttr* axis_attr = nullptr;
  OrtStatus* status = CreateModelShell(model_editor_api, &model, &graph);
  if (status != nullptr) goto cleanup;

  status = CreateFloatValueInfo(api, model_editor_api, "a", a_dims, &a);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "b", b_dims, &b);
  if (status != nullptr) goto cleanup;
  status = CreateFloatValueInfo(api, model_editor_api, "output", output_dims, &output);
  if (status != nullptr) goto cleanup;

  {
    OrtValueInfo* inputs[] = {a, b};
    status = model_editor_api->SetGraphInputs(graph, inputs, 2);
    if (status != nullptr) goto cleanup;
    a = nullptr;
    b = nullptr;
  }
  {
    OrtValueInfo* outputs[] = {output};
    status = model_editor_api->SetGraphOutputs(graph, outputs, 1);
    if (status != nullptr) goto cleanup;
    output = nullptr;
  }
  status = api->CreateOpAttr("axis", &axis, 1, ORT_OP_ATTR_INT, &axis_attr);
  if (status != nullptr) goto cleanup;
  {
    const char* const input_names[] = {"a", "b"};
    const char* const output_names[] = {"output"};
    OrtOpAttr* attrs[] = {axis_attr};
    status = model_editor_api->CreateNode(
        "Concat", "", "concat0", input_names, 2, output_names, 1, attrs, 1, &node);
  }
  // Release the attr immediately after CreateNode returns. CreateNode copies
  // the attribute, and retaining the original past this point risks double
  // free when the graph later tears down its owned copies.
  api->ReleaseOpAttr(axis_attr);
  axis_attr = nullptr;
  if (status != nullptr) goto cleanup;
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
  if (axis_attr != nullptr) api->ReleaseOpAttr(axis_attr);
  if (a != nullptr) api->ReleaseValueInfo(a);
  if (b != nullptr) api->ReleaseValueInfo(b);
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
    case SmokeModelKind::kIdentity:
      return CreateIdentityModel(api, model_editor_api, spec.input_dims[0], spec.output_dims, out_model);
    case SmokeModelKind::kAdd:
      return CreateAddModel(api, model_editor_api, spec.input_dims[0], spec.input_dims[1], spec.output_dims, out_model);
    case SmokeModelKind::kRelu:
      return CreateReluModel(api, model_editor_api, spec.input_dims[0], spec.output_dims, out_model);
    case SmokeModelKind::kSigmoid:
      return CreateUnaryModel(api, model_editor_api, "Sigmoid", "sigmoid0", spec.input_dims[0], spec.output_dims, out_model);
    case SmokeModelKind::kTanh:
      return CreateUnaryModel(api, model_editor_api, "Tanh", "tanh0", spec.input_dims[0], spec.output_dims, out_model);
    case SmokeModelKind::kGelu:
      // Gelu was added in ONNX opset 20; the default opset 13 model shell
      // would fail at session-creation time.
      return CreateUnaryModelAtOpset(api, model_editor_api, "Gelu", "gelu0", 20, spec.input_dims[0], spec.output_dims, out_model);
    case SmokeModelKind::kMatMul:
      return CreateMatMulModel(api, model_editor_api, spec.input_dims[0], spec.input_dims[1], spec.output_dims, out_model);
    case SmokeModelKind::kGemm:
      return CreateGemmModel(
          api,
          model_editor_api,
          spec.input_dims[0],
          spec.input_dims[1],
          spec.input_dims[2],
          spec.output_dims,
          out_model);
    case SmokeModelKind::kGemmReluGemm:
      return CreateGemmReluGemmModel(
          api,
          model_editor_api,
          spec.input_dims[0],
          spec.input_dims[1],
          spec.input_dims[2],
          spec.input_dims[3],
          spec.input_dims[4],
          spec.output_dims,
          out_model);
    case SmokeModelKind::kMatMulAdd:
      return CreateMatMulAddModel(
          api,
          model_editor_api,
          spec.input_dims[0],
          spec.input_dims[1],
          spec.input_dims[2],
          spec.output_dims,
          out_model);
    case SmokeModelKind::kMatMulAddRelu:
      return CreateMatMulAddReluModel(
          api,
          model_editor_api,
          spec.input_dims[0],
          spec.input_dims[1],
          spec.input_dims[2],
          spec.output_dims,
          out_model);
    case SmokeModelKind::kAddRelu:
      return CreateAddReluModel(api, model_editor_api, spec.input_dims[0], spec.input_dims[1], spec.output_dims, out_model);
    case SmokeModelKind::kSoftmax:
      // Softmax is in opset 13+; default axis=-1 matches the Doe EP kernel's
      // last-axis reduction. No attribute needed.
      return CreateUnaryModelAtOpset(api, model_editor_api, "Softmax", "softmax0", 13, spec.input_dims[0], spec.output_dims, out_model);
    case SmokeModelKind::kLayerNorm:
      return CreateLayerNormModel(api, model_editor_api, spec.input_dims[0], spec.input_dims[1], spec.output_dims, out_model);
    case SmokeModelKind::kConcat:
      return CreateBinaryConcatModel(api, model_editor_api, /*axis=*/0, spec.input_dims[0], spec.input_dims[1], spec.output_dims, out_model);
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
    case SmokeModelKind::kIdentity:
      if (delta.claimed_identity_nodes == 0 || delta.compiled_identity_groups == 0 || delta.compute_identity_calls == 0) {
        return fail("Identity case did not report Identity-specific claim/compile/compute counters.");
      }
      break;
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
    case SmokeModelKind::kSigmoid:
      if (delta.claimed_sigmoid_nodes == 0 || delta.compiled_sigmoid_groups == 0 || delta.compute_sigmoid_calls == 0) {
        return fail("Sigmoid case did not report Sigmoid-specific claim/compile/compute counters.");
      }
      break;
    case SmokeModelKind::kTanh:
      if (delta.claimed_tanh_nodes == 0 || delta.compiled_tanh_groups == 0 || delta.compute_tanh_calls == 0) {
        return fail("Tanh case did not report Tanh-specific claim/compile/compute counters.");
      }
      break;
    case SmokeModelKind::kGelu:
      if (delta.claimed_gelu_nodes == 0 || delta.compiled_gelu_groups == 0 || delta.compute_gelu_calls == 0) {
        return fail("Gelu case did not report Gelu-specific claim/compile/compute counters.");
      }
      break;
    case SmokeModelKind::kMatMul:
      if (delta.claimed_matmul_nodes == 0 || delta.compiled_matmul_groups == 0 || delta.compute_matmul_calls == 0) {
        return fail("MatMul case did not report MatMul-specific claim/compile/compute counters.");
      }
      break;
    case SmokeModelKind::kGemm:
      if (delta.claimed_gemm_nodes == 0 || delta.compiled_gemm_groups == 0 || delta.compute_gemm_calls == 0) {
        return fail("Gemm case did not report Gemm-specific claim/compile/compute counters.");
      }
      break;
    case SmokeModelKind::kGemmReluGemm:
      if (delta.claimed_gemm_nodes != 2 || delta.claimed_relu_nodes == 0 ||
          delta.compiled_gemm_relu_gemm_groups == 0 || delta.compute_gemm_relu_gemm_calls == 0) {
        return fail("Gemm->Relu->Gemm case did not report fused Gemm/Relu/Gemm claim/compile/compute counters.");
      }
      break;
    case SmokeModelKind::kMatMulAdd:
      if (delta.claimed_matmul_nodes == 0 || delta.claimed_add_nodes == 0 || delta.compiled_matmul_add_groups == 0 ||
          delta.compute_matmul_add_calls == 0) {
        return fail("MatMul->Add case did not report fused MatMul/Add claim/compile/compute counters.");
      }
      break;
    case SmokeModelKind::kMatMulAddRelu:
      if (delta.claimed_matmul_nodes == 0 || delta.claimed_add_nodes == 0 || delta.claimed_relu_nodes == 0 ||
          delta.compiled_matmul_add_relu_groups == 0 || delta.compute_matmul_add_relu_calls == 0) {
        return fail("MatMul->Add->Relu case did not report fused MatMul/Add/Relu claim/compile/compute counters.");
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
  result->expected_output_shape = spec.output_dims;
  result->expected_output = spec.expected_output;
  result->expected_claimed_nodes = ExpectedClaimedNodes(spec.model_kind);

  if (spec.input_dims.size() != ExpectedInputCount(spec.model_kind) || spec.inputs.size() != ExpectedInputCount(spec.model_kind)) {
    result->failure_reason = "Smoke case spec did not provide the expected number of input shapes and input tensors.";
    result->success = false;
    return false;
  }
  if (spec.expected_output.size() != ElementCountFromDims(spec.output_dims)) {
    result->failure_reason = "Smoke case expected output element count did not match the declared output shape.";
    result->success = false;
    return false;
  }

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
          spec.input_dims[index].empty() ? nullptr : spec.input_dims[index].data(),
          spec.input_dims[index].size(),
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

      if (spec.inputs[index].size() != ElementCountFromDims(spec.input_dims[index])) {
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
  std::vector<SmokeCaseSpec> selected_cases;

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

    status = api->SetSessionGraphOptimizationLevel(session_options, ORT_DISABLE_ALL);
    report->append_ep_status = CaptureStatus(api, status);
    if (!report->append_ep_status.ok) {
      report->failure_reason = "SetSessionGraphOptimizationLevel failed.";
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

  selected_cases = SelectSmokeCases(BuildSmokeCases(), options.case_selector);
  if (selected_cases.empty()) {
    report->failure_reason = "No smoke cases matched the requested case selector.";
    goto cleanup;
  }

  for (const SmokeCaseSpec& spec : selected_cases) {
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
