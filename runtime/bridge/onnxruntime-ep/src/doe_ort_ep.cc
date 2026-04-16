#include "doe_ort_ep.h"

#include <atomic>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <memory>
#include <sstream>
#include <string>
#include <string_view>
#include <unordered_set>
#include <utility>
#include <vector>

namespace doe::ort_ep {

namespace {

constexpr const char* kCompatibilityInfo = "doe-ort-basic-ops-ep-v6";
constexpr const char* kIdentityOperatorType = "Identity";
constexpr const char* kAddOperatorType = "Add";
constexpr const char* kReluOperatorType = "Relu";
constexpr const char* kSigmoidOperatorType = "Sigmoid";
constexpr const char* kTanhOperatorType = "Tanh";
constexpr const char* kGeluOperatorType = "Gelu";
constexpr const char* kMatMulOperatorType = "MatMul";
constexpr const char* kGemmOperatorType = "Gemm";
constexpr const char* kOnnxDomain = "";
constexpr const char* kOnnxAiDomain = "ai.onnx";
constexpr const char* kGemmAlphaAttribute = "alpha";
constexpr const char* kGemmBetaAttribute = "beta";
constexpr const char* kGemmTransAAttribute = "transA";
constexpr const char* kGemmTransBAttribute = "transB";
constexpr ONNXTensorElementDataType kSupportedElementType = ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;
constexpr size_t kUnaryInputCount = 1;
constexpr size_t kBinaryInputCount = 2;
constexpr size_t kTernaryInputCount = 3;
constexpr size_t kQuinaryInputCount = 5;
constexpr size_t kSingleOutputCount = 1;
constexpr size_t kMatrixRank = 2;
constexpr float kSupportedGemmAlpha = 1.0f;
constexpr float kSupportedGemmBeta = 1.0f;
constexpr int64_t kSupportedGemmTransA = 0;
constexpr int64_t kSupportedGemmTransB = 0;

enum class CompiledOpKind : uint8_t {
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
};

std::atomic<uint64_t> g_get_capability_calls{0};
std::atomic<uint64_t> g_claimed_nodes{0};
std::atomic<uint64_t> g_claimed_identity_nodes{0};
std::atomic<uint64_t> g_claimed_add_nodes{0};
std::atomic<uint64_t> g_claimed_relu_nodes{0};
std::atomic<uint64_t> g_claimed_sigmoid_nodes{0};
std::atomic<uint64_t> g_claimed_tanh_nodes{0};
std::atomic<uint64_t> g_claimed_gelu_nodes{0};
std::atomic<uint64_t> g_claimed_matmul_nodes{0};
std::atomic<uint64_t> g_claimed_gemm_nodes{0};
std::atomic<uint64_t> g_compile_calls{0};
std::atomic<uint64_t> g_compiled_identity_groups{0};
std::atomic<uint64_t> g_compiled_add_groups{0};
std::atomic<uint64_t> g_compiled_relu_groups{0};
std::atomic<uint64_t> g_compiled_sigmoid_groups{0};
std::atomic<uint64_t> g_compiled_tanh_groups{0};
std::atomic<uint64_t> g_compiled_gelu_groups{0};
std::atomic<uint64_t> g_compiled_matmul_groups{0};
std::atomic<uint64_t> g_compiled_gemm_groups{0};
std::atomic<uint64_t> g_compiled_gemm_relu_gemm_groups{0};
std::atomic<uint64_t> g_compiled_matmul_add_groups{0};
std::atomic<uint64_t> g_compiled_matmul_add_relu_groups{0};
std::atomic<uint64_t> g_compiled_add_relu_groups{0};
std::atomic<uint64_t> g_create_state_calls{0};
std::atomic<uint64_t> g_compute_calls{0};
std::atomic<uint64_t> g_compute_identity_calls{0};
std::atomic<uint64_t> g_compute_add_calls{0};
std::atomic<uint64_t> g_compute_relu_calls{0};
std::atomic<uint64_t> g_compute_sigmoid_calls{0};
std::atomic<uint64_t> g_compute_tanh_calls{0};
std::atomic<uint64_t> g_compute_gelu_calls{0};
std::atomic<uint64_t> g_compute_matmul_calls{0};
std::atomic<uint64_t> g_compute_gemm_calls{0};
std::atomic<uint64_t> g_compute_gemm_relu_gemm_calls{0};
std::atomic<uint64_t> g_compute_matmul_add_calls{0};
std::atomic<uint64_t> g_compute_matmul_add_relu_calls{0};
std::atomic<uint64_t> g_compute_add_relu_calls{0};
std::atomic<uint64_t> g_release_state_calls{0};

struct TensorValueDescriptor {
  const OrtValueInfo* value_info = nullptr;
  std::string name;
  ONNXTensorElementDataType element_type = ONNX_TENSOR_ELEMENT_DATA_TYPE_UNDEFINED;
  std::vector<int64_t> dims;
  size_t element_count = 0;
};

struct SupportedNodeSpec {
  const OrtNode* node = nullptr;
  CompiledOpKind kind = CompiledOpKind::kIdentity;
  std::string node_name;
  std::vector<TensorValueDescriptor> inputs;
  std::vector<TensorValueDescriptor> outputs;
};

struct SupportedGraphSpec {
  CompiledOpKind kind = CompiledOpKind::kIdentity;
  std::string default_node_name;
  std::vector<const OrtNode*> fused_nodes;
  std::vector<std::string> logical_input_names;
};

struct CompiledComputeState {
  std::string node_name;
  CompiledOpKind op_kind = CompiledOpKind::kIdentity;
};

struct CompiledNodeComputeInfo {
  OrtNodeComputeInfo base{};
  ApiBindings bindings{};
  std::string node_name;
  CompiledOpKind op_kind = CompiledOpKind::kIdentity;
  std::array<size_t, kQuinaryInputCount> input_binding_indices{0, 1, 2, 3, 4};
  size_t input_binding_count = 0;
};

struct RuntimeTensorDescriptor {
  ONNXTensorElementDataType element_type = ONNX_TENSOR_ELEMENT_DATA_TYPE_UNDEFINED;
  std::vector<int64_t> dims;
  size_t element_count = 0;
};

CompiledNodeComputeInfo& ComputeInfoSelf(OrtNodeComputeInfo* this_ptr) {
  return *reinterpret_cast<CompiledNodeComputeInfo*>(this_ptr);
}

const CompiledNodeComputeInfo& ComputeInfoSelf(const OrtNodeComputeInfo* this_ptr) {
  return *reinterpret_cast<const CompiledNodeComputeInfo*>(this_ptr);
}

OrtStatus* MakeInvalidArgumentStatus(const OrtApi* api, const char* message) {
  return MakeStatus(api, ORT_INVALID_ARGUMENT, message);
}

OrtStatus* MakeInvalidGraphStatus(const OrtApi* api, const std::string& message) {
  return MakeStatus(api, ORT_INVALID_GRAPH, message.c_str());
}

OrtStatus* MakeNotImplementedStatus(const OrtApi* api, const std::string& message) {
  return MakeStatus(api, ORT_NOT_IMPLEMENTED, message.c_str());
}

const char* CompiledOpKindName(const CompiledOpKind kind) {
  switch (kind) {
    case CompiledOpKind::kIdentity:
      return kIdentityOperatorType;
    case CompiledOpKind::kAdd:
      return kAddOperatorType;
    case CompiledOpKind::kRelu:
      return kReluOperatorType;
    case CompiledOpKind::kSigmoid:
      return kSigmoidOperatorType;
    case CompiledOpKind::kTanh:
      return kTanhOperatorType;
    case CompiledOpKind::kGelu:
      return kGeluOperatorType;
    case CompiledOpKind::kMatMul:
      return kMatMulOperatorType;
    case CompiledOpKind::kGemm:
      return kGemmOperatorType;
    case CompiledOpKind::kGemmReluGemm:
      return "Gemm->Relu->Gemm";
    case CompiledOpKind::kMatMulAdd:
      return "MatMul->Add";
    case CompiledOpKind::kMatMulAddRelu:
      return "MatMul->Add->Relu";
    case CompiledOpKind::kAddRelu:
      return "Add->Relu";
  }
  return "unknown";
}

size_t ClaimedNodeCountForKind(const CompiledOpKind kind) {
  switch (kind) {
    case CompiledOpKind::kGemmReluGemm:
      return 3;
    case CompiledOpKind::kMatMulAddRelu:
      return 3;
    case CompiledOpKind::kMatMulAdd:
    case CompiledOpKind::kAddRelu:
      return 2;
    case CompiledOpKind::kIdentity:
    case CompiledOpKind::kAdd:
    case CompiledOpKind::kRelu:
    case CompiledOpKind::kSigmoid:
    case CompiledOpKind::kTanh:
    case CompiledOpKind::kGelu:
    case CompiledOpKind::kMatMul:
    case CompiledOpKind::kGemm:
      return 1;
  }
  return 0;
}

size_t ExpectedInputCountForKind(const CompiledOpKind kind) {
  switch (kind) {
    case CompiledOpKind::kIdentity:
    case CompiledOpKind::kRelu:
    case CompiledOpKind::kSigmoid:
    case CompiledOpKind::kTanh:
    case CompiledOpKind::kGelu:
      return kUnaryInputCount;
    case CompiledOpKind::kAdd:
    case CompiledOpKind::kMatMul:
    case CompiledOpKind::kAddRelu:
      return kBinaryInputCount;
    case CompiledOpKind::kGemmReluGemm:
      return kQuinaryInputCount;
    case CompiledOpKind::kGemm:
    case CompiledOpKind::kMatMulAdd:
    case CompiledOpKind::kMatMulAddRelu:
      return kTernaryInputCount;
  }
  return 0;
}

bool IsSupportedOnnxDomain(const char* domain) {
  if (domain == nullptr) {
    return true;
  }
  const std::string_view domain_view(domain);
  return domain_view == kOnnxDomain || domain_view == kOnnxAiDomain;
}

void IncrementClaimCounters(const CompiledOpKind kind) {
  g_claimed_nodes.fetch_add(ClaimedNodeCountForKind(kind), std::memory_order_relaxed);
  switch (kind) {
    case CompiledOpKind::kIdentity:
      g_claimed_identity_nodes.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kAdd:
      g_claimed_add_nodes.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kRelu:
      g_claimed_relu_nodes.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kSigmoid:
      g_claimed_sigmoid_nodes.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kTanh:
      g_claimed_tanh_nodes.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kGelu:
      g_claimed_gelu_nodes.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kMatMul:
      g_claimed_matmul_nodes.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kGemm:
      g_claimed_gemm_nodes.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kGemmReluGemm:
      g_claimed_gemm_nodes.fetch_add(2, std::memory_order_relaxed);
      g_claimed_relu_nodes.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kMatMulAdd:
      g_claimed_matmul_nodes.fetch_add(1, std::memory_order_relaxed);
      g_claimed_add_nodes.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kMatMulAddRelu:
      g_claimed_matmul_nodes.fetch_add(1, std::memory_order_relaxed);
      g_claimed_add_nodes.fetch_add(1, std::memory_order_relaxed);
      g_claimed_relu_nodes.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kAddRelu:
      g_claimed_add_nodes.fetch_add(1, std::memory_order_relaxed);
      g_claimed_relu_nodes.fetch_add(1, std::memory_order_relaxed);
      break;
  }
}

void IncrementCompiledGroupCounters(const CompiledOpKind kind) {
  switch (kind) {
    case CompiledOpKind::kIdentity:
      g_compiled_identity_groups.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kAdd:
      g_compiled_add_groups.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kRelu:
      g_compiled_relu_groups.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kSigmoid:
      g_compiled_sigmoid_groups.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kTanh:
      g_compiled_tanh_groups.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kGelu:
      g_compiled_gelu_groups.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kMatMul:
      g_compiled_matmul_groups.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kGemm:
      g_compiled_gemm_groups.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kGemmReluGemm:
      g_compiled_gemm_relu_gemm_groups.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kMatMulAdd:
      g_compiled_matmul_add_groups.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kMatMulAddRelu:
      g_compiled_matmul_add_relu_groups.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kAddRelu:
      g_compiled_add_relu_groups.fetch_add(1, std::memory_order_relaxed);
      break;
  }
}

void IncrementComputeCounters(const CompiledOpKind kind) {
  switch (kind) {
    case CompiledOpKind::kIdentity:
      g_compute_identity_calls.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kAdd:
      g_compute_add_calls.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kRelu:
      g_compute_relu_calls.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kSigmoid:
      g_compute_sigmoid_calls.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kTanh:
      g_compute_tanh_calls.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kGelu:
      g_compute_gelu_calls.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kMatMul:
      g_compute_matmul_calls.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kGemm:
      g_compute_gemm_calls.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kGemmReluGemm:
      g_compute_gemm_relu_gemm_calls.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kMatMulAdd:
      g_compute_matmul_add_calls.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kMatMulAddRelu:
      g_compute_matmul_add_relu_calls.fetch_add(1, std::memory_order_relaxed);
      break;
    case CompiledOpKind::kAddRelu:
      g_compute_add_relu_calls.fetch_add(1, std::memory_order_relaxed);
      break;
  }
}

std::string ShapeString(const std::vector<int64_t>& dims) {
  std::ostringstream shape;
  shape << '[';
  for (size_t index = 0; index < dims.size(); ++index) {
    if (index != 0) {
      shape << ", ";
    }
    shape << dims[index];
  }
  shape << ']';
  return shape.str();
}

template <typename TensorDescriptor>
bool SameShape(const TensorDescriptor& lhs, const TensorDescriptor& rhs) {
  return lhs.dims == rhs.dims;
}

template <typename TensorDescriptor>
bool SameTypeAndShape(const TensorDescriptor& lhs, const TensorDescriptor& rhs) {
  return lhs.element_type == rhs.element_type && SameShape(lhs, rhs);
}

template <typename TensorDescriptor>
bool IsRank2Matrix(const TensorDescriptor& descriptor) {
  return descriptor.dims.size() == kMatrixRank;
}

template <typename TensorDescriptor>
bool IsStaticMatMulShape(
    const TensorDescriptor& lhs,
    const TensorDescriptor& rhs,
    const TensorDescriptor& output) {
  if (!IsRank2Matrix(lhs) || !IsRank2Matrix(rhs) || !IsRank2Matrix(output)) {
    return false;
  }
  if (lhs.element_type != rhs.element_type || lhs.element_type != output.element_type) {
    return false;
  }
  if (lhs.dims[1] != rhs.dims[0]) {
    return false;
  }
  return output.dims[0] == lhs.dims[0] && output.dims[1] == rhs.dims[1];
}

template <typename TensorDescriptor>
bool InferStaticMatMulOutput(
    const TensorDescriptor& lhs,
    const TensorDescriptor& rhs,
    TensorDescriptor* output_out) {
  if (output_out == nullptr) {
    return false;
  }
  if (!IsRank2Matrix(lhs) || !IsRank2Matrix(rhs) || lhs.element_type != rhs.element_type || lhs.dims[1] != rhs.dims[0]) {
    return false;
  }
  output_out->element_type = lhs.element_type;
  output_out->dims = {lhs.dims[0], rhs.dims[1]};
  output_out->element_count = static_cast<size_t>(lhs.dims[0] * rhs.dims[1]);
  return true;
}

OrtStatus* ReadOptionalFloatAttribute(
    const OrtApi* api,
    const OrtNode* node,
    const char* attribute_name,
    const float default_value,
    float* value_out) {
  if (value_out == nullptr) {
    return MakeInvalidArgumentStatus(
        api,
        "Doe ORT plugin EP requires a value_out pointer when reading float node attributes.");
  }
  *value_out = default_value;

  const OrtOpAttr* attribute = nullptr;
  OrtStatus* status = api->Node_GetAttributeByName(node, attribute_name, &attribute);
  if (status != nullptr) return status;
  if (attribute == nullptr) {
    return nullptr;
  }

  OrtOpAttrType attribute_type = ORT_OP_ATTR_UNDEFINED;
  status = api->OpAttr_GetType(attribute, &attribute_type);
  if (status != nullptr) return status;
  if (attribute_type != ORT_OP_ATTR_FLOAT) {
    std::ostringstream message;
    message << "Doe ORT plugin EP Gemm slice expected float attribute '" << attribute_name << "'.";
    return MakeInvalidGraphStatus(api, message.str());
  }

  size_t values_read = 0;
  status = api->ReadOpAttr(attribute, ORT_OP_ATTR_FLOAT, value_out, sizeof(*value_out), &values_read);
  if (status != nullptr) return status;
  if (values_read == 0) {
    std::ostringstream message;
    message << "Doe ORT plugin EP Gemm slice could not read float attribute '" << attribute_name << "'.";
    return MakeInvalidGraphStatus(api, message.str());
  }
  return nullptr;
}

OrtStatus* ReadOptionalIntAttribute(
    const OrtApi* api,
    const OrtNode* node,
    const char* attribute_name,
    const int64_t default_value,
    int64_t* value_out) {
  if (value_out == nullptr) {
    return MakeInvalidArgumentStatus(
        api,
        "Doe ORT plugin EP requires a value_out pointer when reading int node attributes.");
  }
  *value_out = default_value;

  const OrtOpAttr* attribute = nullptr;
  OrtStatus* status = api->Node_GetAttributeByName(node, attribute_name, &attribute);
  if (status != nullptr) return status;
  if (attribute == nullptr) {
    return nullptr;
  }

  OrtOpAttrType attribute_type = ORT_OP_ATTR_UNDEFINED;
  status = api->OpAttr_GetType(attribute, &attribute_type);
  if (status != nullptr) return status;
  if (attribute_type != ORT_OP_ATTR_INT) {
    std::ostringstream message;
    message << "Doe ORT plugin EP Gemm slice expected int attribute '" << attribute_name << "'.";
    return MakeInvalidGraphStatus(api, message.str());
  }

  size_t values_read = 0;
  status = api->ReadOpAttr(attribute, ORT_OP_ATTR_INT, value_out, sizeof(*value_out), &values_read);
  if (status != nullptr) return status;
  if (values_read == 0) {
    std::ostringstream message;
    message << "Doe ORT plugin EP Gemm slice could not read int attribute '" << attribute_name << "'.";
    return MakeInvalidGraphStatus(api, message.str());
  }
  return nullptr;
}

OrtStatus* HasSupportedGemmAttributes(const OrtApi* api, const OrtNode* node, bool* is_supported) {
  if (is_supported == nullptr) {
    return MakeInvalidArgumentStatus(
        api,
        "Doe ORT plugin EP requires an is_supported output pointer when validating Gemm attributes.");
  }
  *is_supported = false;

  float alpha = kSupportedGemmAlpha;
  float beta = kSupportedGemmBeta;
  int64_t trans_a = kSupportedGemmTransA;
  int64_t trans_b = kSupportedGemmTransB;
  OrtStatus* status = ReadOptionalFloatAttribute(api, node, kGemmAlphaAttribute, kSupportedGemmAlpha, &alpha);
  if (status != nullptr) return status;
  status = ReadOptionalFloatAttribute(api, node, kGemmBetaAttribute, kSupportedGemmBeta, &beta);
  if (status != nullptr) return status;
  status = ReadOptionalIntAttribute(api, node, kGemmTransAAttribute, kSupportedGemmTransA, &trans_a);
  if (status != nullptr) return status;
  status = ReadOptionalIntAttribute(api, node, kGemmTransBAttribute, kSupportedGemmTransB, &trans_b);
  if (status != nullptr) return status;

  *is_supported = alpha == kSupportedGemmAlpha && beta == kSupportedGemmBeta && trans_a == kSupportedGemmTransA &&
                  trans_b == kSupportedGemmTransB;
  return nullptr;
}

OrtStatus* GetGraphNodes(const OrtApi* api, const OrtGraph* graph, std::vector<const OrtNode*>* nodes_out) {
  if (graph == nullptr) {
    return MakeInvalidArgumentStatus(api, "Doe ORT plugin EP cannot inspect a null OrtGraph.");
  }
  if (nodes_out == nullptr) {
    return MakeInvalidArgumentStatus(api, "Doe ORT plugin EP requires a nodes_out output vector.");
  }

  size_t num_nodes = 0;
  OrtStatus* status = api->Graph_GetNumNodes(graph, &num_nodes);
  if (status != nullptr) return status;

  nodes_out->assign(num_nodes, nullptr);
  if (num_nodes == 0) {
    return nullptr;
  }
  return api->Graph_GetNodes(graph, nodes_out->data(), nodes_out->size());
}

OrtStatus* GetGraphInputs(const OrtApi* api, const OrtGraph* graph, std::vector<const OrtValueInfo*>* inputs_out) {
  if (graph == nullptr) {
    return MakeInvalidArgumentStatus(api, "Doe ORT plugin EP cannot inspect graph inputs for a null OrtGraph.");
  }
  if (inputs_out == nullptr) {
    return MakeInvalidArgumentStatus(api, "Doe ORT plugin EP requires an inputs_out output vector.");
  }

  size_t num_inputs = 0;
  OrtStatus* status = api->Graph_GetNumInputs(graph, &num_inputs);
  if (status != nullptr) return status;

  inputs_out->assign(num_inputs, nullptr);
  if (num_inputs == 0) {
    return nullptr;
  }
  return api->Graph_GetInputs(graph, inputs_out->data(), inputs_out->size());
}

OrtStatus* GetValueInfoNameString(const OrtApi* api, const OrtValueInfo* value_info, std::string* name_out) {
  if (name_out == nullptr) {
    return MakeInvalidArgumentStatus(api, "Doe ORT plugin EP requires a name_out output pointer.");
  }
  name_out->clear();
  if (value_info == nullptr) {
    return nullptr;
  }

  const char* value_name = nullptr;
  OrtStatus* status = api->GetValueInfoName(value_info, &value_name);
  if (status != nullptr) return status;
  *name_out = value_name != nullptr ? value_name : "";
  return nullptr;
}

OrtStatus* GetNodeValueInfos(
    const OrtApi* api,
    const OrtNode* node,
    const bool want_inputs,
    std::vector<const OrtValueInfo*>* values_out) {
  if (node == nullptr) {
    return MakeInvalidArgumentStatus(api, "Doe ORT plugin EP cannot inspect a null OrtNode.");
  }
  if (values_out == nullptr) {
    return MakeInvalidArgumentStatus(api, "Doe ORT plugin EP requires a values_out output vector.");
  }

  size_t value_count = 0;
  OrtStatus* status =
      want_inputs ? api->Node_GetNumInputs(node, &value_count) : api->Node_GetNumOutputs(node, &value_count);
  if (status != nullptr) return status;

  values_out->assign(value_count, nullptr);
  if (value_count == 0) {
    return nullptr;
  }

  return want_inputs ? api->Node_GetInputs(node, values_out->data(), values_out->size())
                     : api->Node_GetOutputs(node, values_out->data(), values_out->size());
}

OrtStatus* DescribeSupportedTensorValue(
    const OrtApi* api,
    const OrtValueInfo* value_info,
    TensorValueDescriptor* descriptor_out,
    bool* is_supported) {
  if (descriptor_out == nullptr || is_supported == nullptr) {
    return MakeInvalidArgumentStatus(
        api,
        "Doe ORT plugin EP requires descriptor and is_supported output pointers when validating tensor values.");
  }
  *descriptor_out = TensorValueDescriptor{};
  *is_supported = false;

  if (value_info == nullptr) {
    return nullptr;
  }

  descriptor_out->value_info = value_info;
  OrtStatus* status = GetValueInfoNameString(api, value_info, &descriptor_out->name);
  if (status != nullptr) return status;

  const OrtTypeInfo* type_info = nullptr;
  status = api->GetValueInfoTypeInfo(value_info, &type_info);
  if (status != nullptr) return status;
  if (type_info == nullptr) {
    return nullptr;
  }

  ONNXType onnx_type = ONNX_TYPE_UNKNOWN;
  status = api->GetOnnxTypeFromTypeInfo(type_info, &onnx_type);
  if (status != nullptr) {
    return status;
  }
  if (onnx_type != ONNX_TYPE_TENSOR) {
    return nullptr;
  }

  const OrtTensorTypeAndShapeInfo* tensor_info = nullptr;
  status = api->CastTypeInfoToTensorInfo(type_info, &tensor_info);
  if (status != nullptr) {
    return status;
  }
  if (tensor_info == nullptr) {
    return nullptr;
  }

  status = api->GetTensorElementType(tensor_info, &descriptor_out->element_type);
  if (status != nullptr) {
    return status;
  }
  if (descriptor_out->element_type != kSupportedElementType) {
    return nullptr;
  }

  size_t rank = 0;
  status = api->GetDimensionsCount(tensor_info, &rank);
  if (status != nullptr) {
    return status;
  }

  descriptor_out->dims.assign(rank, 0);
  if (rank != 0) {
    status = api->GetDimensions(tensor_info, descriptor_out->dims.data(), descriptor_out->dims.size());
    if (status != nullptr) {
      return status;
    }
  }

  for (const int64_t dim : descriptor_out->dims) {
    if (dim < 0) {
      return nullptr;
    }
  }

  status = api->GetTensorShapeElementCount(tensor_info, &descriptor_out->element_count);
  if (status != nullptr) return status;

  *is_supported = true;
  return nullptr;
}

OrtStatus* GetSupportedNodeSpec(
    const OrtApi* api,
    const OrtNode* node,
    SupportedNodeSpec* spec_out,
    bool* is_supported) {
  if (spec_out == nullptr || is_supported == nullptr) {
    return MakeInvalidArgumentStatus(
        api,
        "Doe ORT plugin EP requires spec_out and is_supported output pointers when validating nodes.");
  }
  *spec_out = SupportedNodeSpec{};
  *is_supported = false;
  if (node == nullptr) {
    return MakeInvalidArgumentStatus(api, "Doe ORT plugin EP cannot inspect a null OrtNode.");
  }

  spec_out->node = node;

  const char* node_name = nullptr;
  OrtStatus* status = api->Node_GetName(node, &node_name);
  if (status != nullptr) return status;
  spec_out->node_name = node_name != nullptr ? node_name : "";

  const char* operator_type = nullptr;
  status = api->Node_GetOperatorType(node, &operator_type);
  if (status != nullptr) return status;
  if (operator_type == nullptr) {
    return nullptr;
  }

  const char* domain = nullptr;
  status = api->Node_GetDomain(node, &domain);
  if (status != nullptr) return status;
  if (!IsSupportedOnnxDomain(domain)) {
    return nullptr;
  }

  size_t expected_inputs = 0;
  if (std::string_view(operator_type) == kIdentityOperatorType) {
    spec_out->kind = CompiledOpKind::kIdentity;
    expected_inputs = kUnaryInputCount;
  } else if (std::string_view(operator_type) == kAddOperatorType) {
    spec_out->kind = CompiledOpKind::kAdd;
    expected_inputs = kBinaryInputCount;
  } else if (std::string_view(operator_type) == kReluOperatorType) {
    spec_out->kind = CompiledOpKind::kRelu;
    expected_inputs = kUnaryInputCount;
  } else if (std::string_view(operator_type) == kSigmoidOperatorType) {
    spec_out->kind = CompiledOpKind::kSigmoid;
    expected_inputs = kUnaryInputCount;
  } else if (std::string_view(operator_type) == kTanhOperatorType) {
    spec_out->kind = CompiledOpKind::kTanh;
    expected_inputs = kUnaryInputCount;
  } else if (std::string_view(operator_type) == kGeluOperatorType) {
    spec_out->kind = CompiledOpKind::kGelu;
    expected_inputs = kUnaryInputCount;
  } else if (std::string_view(operator_type) == kMatMulOperatorType) {
    spec_out->kind = CompiledOpKind::kMatMul;
    expected_inputs = kBinaryInputCount;
  } else if (std::string_view(operator_type) == kGemmOperatorType) {
    spec_out->kind = CompiledOpKind::kGemm;
    expected_inputs = kTernaryInputCount;
  } else {
    return nullptr;
  }

  std::vector<const OrtValueInfo*> inputs;
  status = GetNodeValueInfos(api, node, true, &inputs);
  if (status != nullptr) return status;
  if (inputs.size() != expected_inputs) {
    return nullptr;
  }

  std::vector<const OrtValueInfo*> outputs;
  status = GetNodeValueInfos(api, node, false, &outputs);
  if (status != nullptr) return status;
  if (outputs.size() != kSingleOutputCount) {
    return nullptr;
  }

  spec_out->inputs.reserve(inputs.size());
  for (const OrtValueInfo* input_info : inputs) {
    TensorValueDescriptor descriptor;
    bool tensor_supported = false;
    status = DescribeSupportedTensorValue(api, input_info, &descriptor, &tensor_supported);
    if (status != nullptr) return status;
    if (!tensor_supported) {
      return nullptr;
    }
    spec_out->inputs.push_back(std::move(descriptor));
  }

  spec_out->outputs.reserve(outputs.size());
  for (const OrtValueInfo* output_info : outputs) {
    TensorValueDescriptor descriptor;
    bool tensor_supported = false;
    status = DescribeSupportedTensorValue(api, output_info, &descriptor, &tensor_supported);
    if (status != nullptr) return status;
    if (!tensor_supported) {
      if (spec_out->kind != CompiledOpKind::kMatMul && spec_out->kind != CompiledOpKind::kGemm) {
        return nullptr;
      }
    }
    spec_out->outputs.push_back(std::move(descriptor));
  }

  switch (spec_out->kind) {
    case CompiledOpKind::kIdentity:
    case CompiledOpKind::kRelu:
    case CompiledOpKind::kSigmoid:
    case CompiledOpKind::kTanh:
    case CompiledOpKind::kGelu:
      if (!SameTypeAndShape(spec_out->inputs[0], spec_out->outputs[0])) {
        return nullptr;
      }
      break;
    case CompiledOpKind::kAdd:
      if (!SameTypeAndShape(spec_out->inputs[0], spec_out->inputs[1]) ||
          !SameTypeAndShape(spec_out->inputs[0], spec_out->outputs[0])) {
        return nullptr;
      }
      break;
    case CompiledOpKind::kMatMul:
      {
        TensorValueDescriptor inferred_output;
        if (!InferStaticMatMulOutput(spec_out->inputs[0], spec_out->inputs[1], &inferred_output)) {
          return nullptr;
        }
        const bool output_has_supported_shape =
            spec_out->outputs[0].element_type == kSupportedElementType && IsRank2Matrix(spec_out->outputs[0]);
        if (output_has_supported_shape && !IsStaticMatMulShape(spec_out->inputs[0], spec_out->inputs[1], spec_out->outputs[0])) {
          return nullptr;
        }
        if (!output_has_supported_shape) {
          spec_out->outputs[0].element_type = inferred_output.element_type;
          spec_out->outputs[0].dims = inferred_output.dims;
          spec_out->outputs[0].element_count = inferred_output.element_count;
        }
      }
      break;
    case CompiledOpKind::kGemm:
      {
        bool gemm_attributes_supported = false;
        status = HasSupportedGemmAttributes(api, node, &gemm_attributes_supported);
        if (status != nullptr) return status;
        if (!gemm_attributes_supported) {
          return nullptr;
        }

        TensorValueDescriptor inferred_output;
        if (!InferStaticMatMulOutput(spec_out->inputs[0], spec_out->inputs[1], &inferred_output)) {
          return nullptr;
        }
        if (!SameTypeAndShape(inferred_output, spec_out->inputs[2])) {
          return nullptr;
        }
        const bool output_has_supported_shape =
            spec_out->outputs[0].element_type == kSupportedElementType && IsRank2Matrix(spec_out->outputs[0]);
        if (output_has_supported_shape && !SameTypeAndShape(inferred_output, spec_out->outputs[0])) {
          return nullptr;
        }
        if (!output_has_supported_shape) {
          spec_out->outputs[0].element_type = inferred_output.element_type;
          spec_out->outputs[0].dims = inferred_output.dims;
          spec_out->outputs[0].element_count = inferred_output.element_count;
        }
      }
      break;
    case CompiledOpKind::kMatMulAdd:
    case CompiledOpKind::kMatMulAddRelu:
    case CompiledOpKind::kAddRelu:
      return MakeInvalidArgumentStatus(
          api,
          "Doe ORT plugin EP does not validate fused groups as a single OrtNode.");
  }

  *is_supported = true;
  return nullptr;
}

OrtStatus* FindSupportedReluConsumer(
    const OrtApi* api,
    const SupportedNodeSpec& producer_spec,
    const std::unordered_set<const OrtNode*>& already_claimed,
    SupportedNodeSpec* relu_spec_out,
    bool* found) {
  if (relu_spec_out == nullptr || found == nullptr) {
    return MakeInvalidArgumentStatus(
        api,
        "Doe ORT plugin EP requires relu_spec_out and found output pointers when searching for Relu fusion.");
  }
  *relu_spec_out = SupportedNodeSpec{};
  *found = false;

  if ((producer_spec.kind != CompiledOpKind::kAdd && producer_spec.kind != CompiledOpKind::kGemm) ||
      producer_spec.outputs.size() != 1 || producer_spec.outputs[0].value_info == nullptr) {
    return nullptr;
  }

  bool is_graph_output = false;
  OrtStatus* status = api->ValueInfo_IsGraphOutput(producer_spec.outputs[0].value_info, &is_graph_output);
  if (status != nullptr) return status;
  if (is_graph_output) {
    return nullptr;
  }

  size_t num_consumers = 0;
  status = api->ValueInfo_GetValueNumConsumers(producer_spec.outputs[0].value_info, &num_consumers);
  if (status != nullptr) return status;
  if (num_consumers != 1) {
    return nullptr;
  }

  std::vector<const OrtNode*> consumer_nodes(num_consumers, nullptr);
  std::vector<int64_t> consumer_input_indices(num_consumers, -1);
  status = api->ValueInfo_GetValueConsumers(
      producer_spec.outputs[0].value_info,
      consumer_nodes.data(),
      consumer_input_indices.data(),
      consumer_nodes.size());
  if (status != nullptr) return status;
  if (consumer_nodes[0] == nullptr || consumer_input_indices[0] != 0 ||
      already_claimed.find(consumer_nodes[0]) != already_claimed.end()) {
    return nullptr;
  }

  SupportedNodeSpec relu_spec;
  bool relu_supported = false;
  status = GetSupportedNodeSpec(api, consumer_nodes[0], &relu_spec, &relu_supported);
  if (status != nullptr) return status;
  if (!relu_supported || relu_spec.kind != CompiledOpKind::kRelu) {
    return nullptr;
  }

  *relu_spec_out = std::move(relu_spec);
  *found = true;
  return nullptr;
}

OrtStatus* FindSupportedAddConsumer(
    const OrtApi* api,
    const SupportedNodeSpec& matmul_spec,
    const std::unordered_set<const OrtNode*>& already_claimed,
    SupportedNodeSpec* add_spec_out,
    size_t* add_input_index_out,
    bool* found) {
  if (add_spec_out == nullptr || add_input_index_out == nullptr || found == nullptr) {
    return MakeInvalidArgumentStatus(
        api,
        "Doe ORT plugin EP requires add_spec_out, add_input_index_out, and found pointers for MatMul->Add fusion.");
  }
  *add_spec_out = SupportedNodeSpec{};
  *add_input_index_out = 0;
  *found = false;

  if (matmul_spec.kind != CompiledOpKind::kMatMul || matmul_spec.outputs.size() != 1 ||
      matmul_spec.outputs[0].value_info == nullptr) {
    return nullptr;
  }

  bool is_graph_output = false;
  OrtStatus* status = api->ValueInfo_IsGraphOutput(matmul_spec.outputs[0].value_info, &is_graph_output);
  if (status != nullptr) return status;
  if (is_graph_output) {
    return nullptr;
  }

  size_t num_consumers = 0;
  status = api->ValueInfo_GetValueNumConsumers(matmul_spec.outputs[0].value_info, &num_consumers);
  if (status != nullptr) return status;
  if (num_consumers != 1) {
    return nullptr;
  }

  std::vector<const OrtNode*> consumer_nodes(num_consumers, nullptr);
  std::vector<int64_t> consumer_input_indices(num_consumers, -1);
  status = api->ValueInfo_GetValueConsumers(
      matmul_spec.outputs[0].value_info,
      consumer_nodes.data(),
      consumer_input_indices.data(),
      consumer_nodes.size());
  if (status != nullptr) return status;

  if (consumer_nodes[0] == nullptr || consumer_input_indices[0] < 0 ||
      static_cast<size_t>(consumer_input_indices[0]) >= kBinaryInputCount ||
      already_claimed.find(consumer_nodes[0]) != already_claimed.end()) {
    return nullptr;
  }
  *add_input_index_out = static_cast<size_t>(consumer_input_indices[0]);

  SupportedNodeSpec add_spec;
  add_spec.node = consumer_nodes[0];
  add_spec.kind = CompiledOpKind::kAdd;

  const char* node_name = nullptr;
  status = api->Node_GetName(add_spec.node, &node_name);
  if (status != nullptr) return status;
  add_spec.node_name = node_name != nullptr ? node_name : "";

  const char* operator_type = nullptr;
  status = api->Node_GetOperatorType(add_spec.node, &operator_type);
  if (status != nullptr) return status;
  if (operator_type == nullptr || std::string_view(operator_type) != kAddOperatorType) {
    return nullptr;
  }

  const char* domain = nullptr;
  status = api->Node_GetDomain(add_spec.node, &domain);
  if (status != nullptr) return status;
  if (!IsSupportedOnnxDomain(domain)) {
    return nullptr;
  }

  std::vector<const OrtValueInfo*> inputs;
  status = GetNodeValueInfos(api, add_spec.node, true, &inputs);
  if (status != nullptr) return status;
  if (inputs.size() != kBinaryInputCount) {
    return nullptr;
  }

  std::vector<const OrtValueInfo*> outputs;
  status = GetNodeValueInfos(api, add_spec.node, false, &outputs);
  if (status != nullptr) return status;
  if (outputs.size() != kSingleOutputCount) {
    return nullptr;
  }

  TensorValueDescriptor inferred_matmul_output;
  if (!InferStaticMatMulOutput(matmul_spec.inputs[0], matmul_spec.inputs[1], &inferred_matmul_output)) {
    return nullptr;
  }

  add_spec.inputs.reserve(inputs.size());
  for (size_t input_index = 0; input_index < inputs.size(); ++input_index) {
    TensorValueDescriptor descriptor;
    bool tensor_supported = false;
    status = DescribeSupportedTensorValue(api, inputs[input_index], &descriptor, &tensor_supported);
    if (status != nullptr) return status;
    if (!tensor_supported) {
      if (input_index != *add_input_index_out) {
        return nullptr;
      }
      descriptor.element_type = inferred_matmul_output.element_type;
      descriptor.dims = inferred_matmul_output.dims;
      descriptor.element_count = inferred_matmul_output.element_count;
    } else if (input_index == *add_input_index_out && !SameTypeAndShape(descriptor, inferred_matmul_output)) {
      return nullptr;
    }
    add_spec.inputs.push_back(std::move(descriptor));
  }

  add_spec.outputs.reserve(outputs.size());
  for (const OrtValueInfo* output_info : outputs) {
    TensorValueDescriptor descriptor;
    bool tensor_supported = false;
    status = DescribeSupportedTensorValue(api, output_info, &descriptor, &tensor_supported);
    if (status != nullptr) return status;
    if (!tensor_supported) {
      return nullptr;
    }
    add_spec.outputs.push_back(std::move(descriptor));
  }

  const size_t addend_input_index = *add_input_index_out == 0 ? 1 : 0;
  if (!SameTypeAndShape(add_spec.inputs[addend_input_index], inferred_matmul_output) ||
      !SameTypeAndShape(add_spec.outputs[0], inferred_matmul_output)) {
    return nullptr;
  }

  *add_spec_out = std::move(add_spec);
  *found = true;
  return nullptr;
}

size_t AddendInputIndex(const size_t matmul_output_input_index) {
  return matmul_output_input_index == 0 ? 1 : 0;
}

SupportedGraphSpec BuildAddReluGraphSpec(const SupportedNodeSpec& add_spec, const SupportedNodeSpec& relu_spec) {
  SupportedGraphSpec graph_spec;
  graph_spec.kind = CompiledOpKind::kAddRelu;
  graph_spec.default_node_name = "doe_add_relu";
  graph_spec.fused_nodes = {add_spec.node, relu_spec.node};
  graph_spec.logical_input_names = {add_spec.inputs[0].name, add_spec.inputs[1].name};
  return graph_spec;
}

SupportedGraphSpec BuildMatMulAddGraphSpec(
    const SupportedNodeSpec& matmul_spec,
    const SupportedNodeSpec& add_spec,
    const size_t matmul_output_input_index) {
  const size_t addend_input_index = AddendInputIndex(matmul_output_input_index);
  SupportedGraphSpec graph_spec;
  graph_spec.kind = CompiledOpKind::kMatMulAdd;
  graph_spec.default_node_name = "doe_matmul_add";
  graph_spec.fused_nodes = {matmul_spec.node, add_spec.node};
  graph_spec.logical_input_names = {
      matmul_spec.inputs[0].name,
      matmul_spec.inputs[1].name,
      add_spec.inputs[addend_input_index].name};
  return graph_spec;
}

SupportedGraphSpec BuildMatMulAddReluGraphSpec(
    const SupportedNodeSpec& matmul_spec,
    const SupportedNodeSpec& add_spec,
    const size_t matmul_output_input_index,
    const SupportedNodeSpec& relu_spec) {
  SupportedGraphSpec graph_spec = BuildMatMulAddGraphSpec(matmul_spec, add_spec, matmul_output_input_index);
  graph_spec.kind = CompiledOpKind::kMatMulAddRelu;
  graph_spec.default_node_name = "doe_matmul_add_relu";
  graph_spec.fused_nodes = {matmul_spec.node, add_spec.node, relu_spec.node};
  return graph_spec;
}

OrtStatus* FindSupportedGemmConsumer(
    const OrtApi* api,
    const SupportedNodeSpec& relu_spec,
    const std::unordered_set<const OrtNode*>& already_claimed,
    SupportedNodeSpec* gemm_spec_out,
    bool* found) {
  if (gemm_spec_out == nullptr || found == nullptr) {
    return MakeInvalidArgumentStatus(
        api,
        "Doe ORT plugin EP requires gemm_spec_out and found output pointers when searching for Gemm->Relu->Gemm fusion.");
  }
  *gemm_spec_out = SupportedNodeSpec{};
  *found = false;

  if (relu_spec.kind != CompiledOpKind::kRelu || relu_spec.outputs.size() != 1 || relu_spec.outputs[0].value_info == nullptr) {
    return nullptr;
  }

  bool is_graph_output = false;
  OrtStatus* status = api->ValueInfo_IsGraphOutput(relu_spec.outputs[0].value_info, &is_graph_output);
  if (status != nullptr) return status;
  if (is_graph_output) {
    return nullptr;
  }

  size_t num_consumers = 0;
  status = api->ValueInfo_GetValueNumConsumers(relu_spec.outputs[0].value_info, &num_consumers);
  if (status != nullptr) return status;
  if (num_consumers != 1) {
    return nullptr;
  }

  std::vector<const OrtNode*> consumer_nodes(num_consumers, nullptr);
  std::vector<int64_t> consumer_input_indices(num_consumers, -1);
  status = api->ValueInfo_GetValueConsumers(
      relu_spec.outputs[0].value_info,
      consumer_nodes.data(),
      consumer_input_indices.data(),
      consumer_nodes.size());
  if (status != nullptr) return status;
  if (consumer_nodes[0] == nullptr || consumer_input_indices[0] != 0 ||
      already_claimed.find(consumer_nodes[0]) != already_claimed.end()) {
    return nullptr;
  }

  SupportedNodeSpec gemm_spec;
  gemm_spec.node = consumer_nodes[0];
  gemm_spec.kind = CompiledOpKind::kGemm;

  const char* node_name = nullptr;
  status = api->Node_GetName(gemm_spec.node, &node_name);
  if (status != nullptr) return status;
  gemm_spec.node_name = node_name != nullptr ? node_name : "";

  const char* operator_type = nullptr;
  status = api->Node_GetOperatorType(gemm_spec.node, &operator_type);
  if (status != nullptr) return status;
  if (operator_type == nullptr || std::string_view(operator_type) != kGemmOperatorType) {
    return nullptr;
  }

  const char* domain = nullptr;
  status = api->Node_GetDomain(gemm_spec.node, &domain);
  if (status != nullptr) return status;
  if (!IsSupportedOnnxDomain(domain)) {
    return nullptr;
  }

  bool gemm_attributes_supported = false;
  status = HasSupportedGemmAttributes(api, gemm_spec.node, &gemm_attributes_supported);
  if (status != nullptr) return status;
  if (!gemm_attributes_supported) {
    return nullptr;
  }

  std::vector<const OrtValueInfo*> inputs;
  status = GetNodeValueInfos(api, gemm_spec.node, true, &inputs);
  if (status != nullptr) return status;
  if (inputs.size() != kTernaryInputCount) {
    return nullptr;
  }

  std::vector<const OrtValueInfo*> outputs;
  status = GetNodeValueInfos(api, gemm_spec.node, false, &outputs);
  if (status != nullptr) return status;
  if (outputs.size() != kSingleOutputCount) {
    return nullptr;
  }

  gemm_spec.inputs.reserve(inputs.size());
  for (size_t input_index = 0; input_index < inputs.size(); ++input_index) {
    TensorValueDescriptor descriptor;
    bool tensor_supported = false;
    status = DescribeSupportedTensorValue(api, inputs[input_index], &descriptor, &tensor_supported);
    if (status != nullptr) return status;
    if (!tensor_supported) {
      if (input_index != 0) {
        return nullptr;
      }
      descriptor = relu_spec.outputs[0];
    } else if (input_index == 0 && !SameTypeAndShape(descriptor, relu_spec.outputs[0])) {
      return nullptr;
    }
    gemm_spec.inputs.push_back(std::move(descriptor));
  }

  gemm_spec.outputs.reserve(outputs.size());
  for (const OrtValueInfo* output_info : outputs) {
    TensorValueDescriptor descriptor;
    bool tensor_supported = false;
    status = DescribeSupportedTensorValue(api, output_info, &descriptor, &tensor_supported);
    if (status != nullptr) return status;
    if (!tensor_supported) {
      // Allow ORT to omit concrete output shape info and infer it from Gemm inputs.
    }
    gemm_spec.outputs.push_back(std::move(descriptor));
  }

  TensorValueDescriptor inferred_output;
  if (!InferStaticMatMulOutput(gemm_spec.inputs[0], gemm_spec.inputs[1], &inferred_output)) {
    return nullptr;
  }
  if (!SameTypeAndShape(inferred_output, gemm_spec.inputs[2])) {
    return nullptr;
  }
  const bool output_has_supported_shape =
      gemm_spec.outputs[0].element_type == kSupportedElementType && IsRank2Matrix(gemm_spec.outputs[0]);
  if (output_has_supported_shape && !SameTypeAndShape(inferred_output, gemm_spec.outputs[0])) {
    return nullptr;
  }
  if (!output_has_supported_shape) {
    gemm_spec.outputs[0].element_type = inferred_output.element_type;
    gemm_spec.outputs[0].dims = inferred_output.dims;
    gemm_spec.outputs[0].element_count = inferred_output.element_count;
  }

  *gemm_spec_out = std::move(gemm_spec);
  *found = true;
  return nullptr;
}

SupportedGraphSpec BuildGemmReluGemmGraphSpec(
    const SupportedNodeSpec& first_gemm_spec,
    const SupportedNodeSpec& relu_spec,
    const SupportedNodeSpec& second_gemm_spec) {
  SupportedGraphSpec graph_spec;
  graph_spec.kind = CompiledOpKind::kGemmReluGemm;
  graph_spec.default_node_name = "doe_gemm_relu_gemm";
  graph_spec.fused_nodes = {first_gemm_spec.node, relu_spec.node, second_gemm_spec.node};
  graph_spec.logical_input_names = {
      first_gemm_spec.inputs[0].name,
      first_gemm_spec.inputs[1].name,
      first_gemm_spec.inputs[2].name,
      second_gemm_spec.inputs[1].name,
      second_gemm_spec.inputs[2].name};
  return graph_spec;
}

OrtStatus* ResolveGraphInputBindings(
    const OrtApi* api,
    const OrtGraph* graph,
    const SupportedGraphSpec& graph_spec,
    std::array<size_t, kQuinaryInputCount>* indices_out,
    size_t* input_count_out) {
  if (indices_out == nullptr || input_count_out == nullptr) {
    return MakeInvalidArgumentStatus(
        api,
        "Doe ORT plugin EP requires indices_out and input_count_out when resolving graph input bindings.");
  }

  indices_out->fill(0);
  *input_count_out = 0;
  if (graph_spec.logical_input_names.size() > indices_out->size()) {
    return MakeInvalidGraphStatus(api, "Doe ORT plugin EP fused graph exceeded its supported external input count.");
  }

  std::vector<const OrtValueInfo*> graph_inputs;
  OrtStatus* status = GetGraphInputs(api, graph, &graph_inputs);
  if (status != nullptr) return status;
  if (graph_inputs.size() != graph_spec.logical_input_names.size()) {
    std::ostringstream message;
    message << "Doe ORT plugin EP " << CompiledOpKindName(graph_spec.kind) << " slice expects exactly "
            << graph_spec.logical_input_names.size() << " external graph inputs but received " << graph_inputs.size()
            << '.';
    return MakeInvalidGraphStatus(api, message.str());
  }

  for (size_t logical_index = 0; logical_index < graph_spec.logical_input_names.size(); ++logical_index) {
    const std::string& logical_name = graph_spec.logical_input_names[logical_index];
    bool matched = false;
    for (size_t graph_index = 0; graph_index < graph_inputs.size(); ++graph_index) {
      std::string graph_input_name;
      status = GetValueInfoNameString(api, graph_inputs[graph_index], &graph_input_name);
      if (status != nullptr) return status;
      if (graph_input_name == logical_name) {
        (*indices_out)[logical_index] = graph_index;
        matched = true;
        break;
      }
    }
    if (!matched) {
      std::ostringstream message;
      message << "Doe ORT plugin EP " << CompiledOpKindName(graph_spec.kind)
              << " slice could not resolve fused graph input '" << logical_name << "'.";
      return MakeInvalidGraphStatus(api, message.str());
    }
  }

  *input_count_out = graph_spec.logical_input_names.size();
  return nullptr;
}

OrtStatus* AnalyzeSupportedGraph(
    const OrtApi* api,
    const OrtGraph* graph,
    SupportedGraphSpec* spec_out,
    bool* is_supported) {
  if (spec_out == nullptr || is_supported == nullptr) {
    return MakeInvalidArgumentStatus(
        api,
        "Doe ORT plugin EP requires spec_out and is_supported output pointers when validating graphs.");
  }
  *spec_out = SupportedGraphSpec{};
  *is_supported = false;

  std::vector<const OrtNode*> nodes;
  OrtStatus* status = GetGraphNodes(api, graph, &nodes);
  if (status != nullptr) return status;
  if (nodes.empty()) {
    return nullptr;
  }

  if (nodes.size() == 1) {
    SupportedNodeSpec node_spec;
    bool node_supported = false;
    status = GetSupportedNodeSpec(api, nodes[0], &node_spec, &node_supported);
    if (status != nullptr) return status;
    if (!node_supported) {
      return nullptr;
    }
    spec_out->kind = node_spec.kind;
    spec_out->default_node_name = node_spec.node_name.empty() ? CompiledOpKindName(node_spec.kind) : node_spec.node_name;
    spec_out->fused_nodes = {nodes[0]};
    spec_out->logical_input_names.reserve(node_spec.inputs.size());
    for (const TensorValueDescriptor& input : node_spec.inputs) {
      spec_out->logical_input_names.push_back(input.name);
    }
    *is_supported = true;
    return nullptr;
  }

  if (nodes.size() == 2) {
    SupportedNodeSpec first_spec;
    SupportedNodeSpec second_spec;
    bool first_supported = false;
    bool second_supported = false;
    status = GetSupportedNodeSpec(api, nodes[0], &first_spec, &first_supported);
    if (status != nullptr) return status;
    status = GetSupportedNodeSpec(api, nodes[1], &second_spec, &second_supported);
    if (status != nullptr) return status;
    if (!first_supported || !second_supported) {
      return nullptr;
    }

    const SupportedNodeSpec* add_spec = nullptr;
    const SupportedNodeSpec* relu_spec = nullptr;
    if (first_spec.kind == CompiledOpKind::kAdd && second_spec.kind == CompiledOpKind::kRelu) {
      add_spec = &first_spec;
      relu_spec = &second_spec;
    } else if (first_spec.kind == CompiledOpKind::kRelu && second_spec.kind == CompiledOpKind::kAdd) {
      add_spec = &second_spec;
      relu_spec = &first_spec;
    }

    if (add_spec != nullptr && relu_spec != nullptr) {
      SupportedNodeSpec fused_relu_spec;
      bool fused = false;
      status = FindSupportedReluConsumer(api, *add_spec, {}, &fused_relu_spec, &fused);
      if (status != nullptr) return status;
      if (fused && fused_relu_spec.node == relu_spec->node) {
        *spec_out = BuildAddReluGraphSpec(*add_spec, fused_relu_spec);
        *is_supported = true;
        return nullptr;
      }
    }

    const SupportedNodeSpec* matmul_spec = nullptr;
    add_spec = nullptr;
    if (first_spec.kind == CompiledOpKind::kMatMul && second_spec.kind == CompiledOpKind::kAdd) {
      matmul_spec = &first_spec;
      add_spec = &second_spec;
    } else if (first_spec.kind == CompiledOpKind::kAdd && second_spec.kind == CompiledOpKind::kMatMul) {
      matmul_spec = &second_spec;
      add_spec = &first_spec;
    }

    if (matmul_spec != nullptr && add_spec != nullptr) {
      SupportedNodeSpec fused_add_spec;
      size_t matmul_output_input_index = 0;
      bool fused = false;
      status = FindSupportedAddConsumer(
          api,
          *matmul_spec,
          {},
          &fused_add_spec,
          &matmul_output_input_index,
          &fused);
      if (status != nullptr) return status;
      if (fused && fused_add_spec.node == add_spec->node) {
        *spec_out = BuildMatMulAddGraphSpec(*matmul_spec, fused_add_spec, matmul_output_input_index);
        *is_supported = true;
        return nullptr;
      }
    }

    return nullptr;
  }

  if (nodes.size() == 3) {
    std::vector<SupportedNodeSpec> supported_specs(nodes.size());
    size_t matmul_index = nodes.size();
    size_t first_gemm_index = nodes.size();
    size_t second_gemm_index = nodes.size();
    size_t add_index = nodes.size();
    size_t relu_index = nodes.size();
    for (size_t index = 0; index < nodes.size(); ++index) {
      bool node_supported = false;
      status = GetSupportedNodeSpec(api, nodes[index], &supported_specs[index], &node_supported);
      if (status != nullptr) return status;
      if (!node_supported) {
        return nullptr;
      }
      switch (supported_specs[index].kind) {
        case CompiledOpKind::kMatMul:
          if (matmul_index != nodes.size()) return nullptr;
          matmul_index = index;
          break;
        case CompiledOpKind::kGemm:
          if (first_gemm_index == nodes.size()) {
            first_gemm_index = index;
          } else if (second_gemm_index == nodes.size()) {
            second_gemm_index = index;
          } else {
            return nullptr;
          }
          break;
        case CompiledOpKind::kAdd:
          if (add_index != nodes.size()) return nullptr;
          add_index = index;
          break;
        case CompiledOpKind::kRelu:
          if (relu_index != nodes.size()) return nullptr;
          relu_index = index;
          break;
        case CompiledOpKind::kIdentity:
        case CompiledOpKind::kMatMulAdd:
        case CompiledOpKind::kMatMulAddRelu:
        case CompiledOpKind::kAddRelu:
          return nullptr;
      }
    }

    if (first_gemm_index != nodes.size() && second_gemm_index != nodes.size() && relu_index != nodes.size() &&
        matmul_index == nodes.size() && add_index == nodes.size()) {
      const SupportedNodeSpec& relu_spec = supported_specs[relu_index];

      const SupportedNodeSpec* first_gemm_spec = nullptr;
      const SupportedNodeSpec* second_gemm_spec = nullptr;
      for (const size_t gemm_index : {first_gemm_index, second_gemm_index}) {
        const SupportedNodeSpec& candidate = supported_specs[gemm_index];
        SupportedNodeSpec fused_relu_spec;
        bool fused_relu = false;
        status = FindSupportedReluConsumer(api, candidate, {}, &fused_relu_spec, &fused_relu);
        if (status != nullptr) return status;
        if (fused_relu && fused_relu_spec.node == relu_spec.node) {
          first_gemm_spec = &candidate;
          const size_t other_gemm_index = gemm_index == first_gemm_index ? second_gemm_index : first_gemm_index;
          second_gemm_spec = &supported_specs[other_gemm_index];
          break;
        }
      }
      if (first_gemm_spec == nullptr || second_gemm_spec == nullptr) {
        return nullptr;
      }

      SupportedNodeSpec fused_second_gemm_spec;
      bool fused_second_gemm = false;
      status = FindSupportedGemmConsumer(api, relu_spec, {}, &fused_second_gemm_spec, &fused_second_gemm);
      if (status != nullptr) return status;
      if (!fused_second_gemm || fused_second_gemm_spec.node != second_gemm_spec->node) {
        return nullptr;
      }

      *spec_out = BuildGemmReluGemmGraphSpec(*first_gemm_spec, relu_spec, fused_second_gemm_spec);
      *is_supported = true;
      return nullptr;
    }

    if (matmul_index == nodes.size() || add_index == nodes.size() || relu_index == nodes.size() ||
        first_gemm_index != nodes.size() || second_gemm_index != nodes.size()) {
      return nullptr;
    }

    const SupportedNodeSpec& matmul_spec = supported_specs[matmul_index];
    const SupportedNodeSpec& add_spec = supported_specs[add_index];
    const SupportedNodeSpec& relu_spec = supported_specs[relu_index];

    SupportedNodeSpec fused_add_spec;
    size_t matmul_output_input_index = 0;
    bool fused_add = false;
    status = FindSupportedAddConsumer(api, matmul_spec, {}, &fused_add_spec, &matmul_output_input_index, &fused_add);
    if (status != nullptr) return status;
    if (!fused_add || fused_add_spec.node != add_spec.node) {
      return nullptr;
    }

    SupportedNodeSpec fused_relu_spec;
    bool fused_relu = false;
    status = FindSupportedReluConsumer(api, fused_add_spec, {}, &fused_relu_spec, &fused_relu);
    if (status != nullptr) return status;
    if (!fused_relu || fused_relu_spec.node != relu_spec.node) {
      return nullptr;
    }

    *spec_out = BuildMatMulAddReluGraphSpec(matmul_spec, fused_add_spec, matmul_output_input_index, fused_relu_spec);
    *is_supported = true;
    return nullptr;
  }

  return nullptr;
}

OrtStatus* GetRuntimeTensorDescriptor(
    const OrtApi* api,
    const OrtValue* value,
    RuntimeTensorDescriptor* descriptor_out) {
  if (descriptor_out == nullptr) {
    return MakeInvalidArgumentStatus(api, "Doe ORT plugin EP requires a descriptor_out output pointer.");
  }
  *descriptor_out = RuntimeTensorDescriptor{};
  if (value == nullptr) {
    return MakeInvalidArgumentStatus(api, "Doe ORT plugin EP received a null tensor value.");
  }

  OrtTensorTypeAndShapeInfo* tensor_info = nullptr;
  OrtStatus* status = api->GetTensorTypeAndShape(value, &tensor_info);
  if (status != nullptr) return status;

  status = api->GetTensorElementType(tensor_info, &descriptor_out->element_type);
  if (status != nullptr) {
    api->ReleaseTensorTypeAndShapeInfo(tensor_info);
    return status;
  }
  if (descriptor_out->element_type != kSupportedElementType) {
    api->ReleaseTensorTypeAndShapeInfo(tensor_info);
    return MakeNotImplementedStatus(api, "Doe ORT plugin EP currently supports float32 tensors only.");
  }

  size_t rank = 0;
  status = api->GetDimensionsCount(tensor_info, &rank);
  if (status != nullptr) {
    api->ReleaseTensorTypeAndShapeInfo(tensor_info);
    return status;
  }

  descriptor_out->dims.assign(rank, 0);
  if (rank != 0) {
    status = api->GetDimensions(tensor_info, descriptor_out->dims.data(), descriptor_out->dims.size());
    if (status != nullptr) {
      api->ReleaseTensorTypeAndShapeInfo(tensor_info);
      return status;
    }
  }

  for (const int64_t dim : descriptor_out->dims) {
    if (dim < 0) {
      api->ReleaseTensorTypeAndShapeInfo(tensor_info);
      return MakeInvalidGraphStatus(api, "Doe ORT plugin EP requires concrete runtime tensor shapes.");
    }
  }

  status = api->GetTensorShapeElementCount(tensor_info, &descriptor_out->element_count);
  api->ReleaseTensorTypeAndShapeInfo(tensor_info);
  return status;
}

OrtStatus* ValidateRuntimeArity(
    const CompiledNodeComputeInfo& info,
    OrtKernelContext* kernel_context,
    const size_t expected_inputs,
    const size_t expected_outputs) {
  size_t input_count = 0;
  OrtStatus* status = info.bindings.api->KernelContext_GetInputCount(kernel_context, &input_count);
  if (status != nullptr) return status;
  if (input_count != expected_inputs) {
    std::ostringstream message;
    message << "Doe ORT plugin EP " << CompiledOpKindName(info.op_kind) << " slice expects exactly " << expected_inputs
            << " inputs but received " << input_count << '.';
    return MakeInvalidGraphStatus(info.bindings.api, message.str());
  }

  size_t output_count = 0;
  status = info.bindings.api->KernelContext_GetOutputCount(kernel_context, &output_count);
  if (status != nullptr) return status;
  if (output_count != expected_outputs) {
    std::ostringstream message;
    message << "Doe ORT plugin EP " << CompiledOpKindName(info.op_kind) << " slice expects exactly "
            << expected_outputs << " outputs but received " << output_count << '.';
    return MakeInvalidGraphStatus(info.bindings.api, message.str());
  }

  return nullptr;
}

OrtStatus* GetKernelInputData(
    const CompiledNodeComputeInfo& info,
    OrtKernelContext* kernel_context,
    const size_t logical_input_index,
    RuntimeTensorDescriptor* descriptor_out,
    const float** data_out) {
  if (logical_input_index >= info.input_binding_count || logical_input_index >= info.input_binding_indices.size()) {
    std::ostringstream message;
    message << "Doe ORT plugin EP " << CompiledOpKindName(info.op_kind)
            << " slice does not have a bound graph input at logical index " << logical_input_index << '.';
    return MakeInvalidGraphStatus(info.bindings.api, message.str());
  }

  const size_t input_index = info.input_binding_indices[logical_input_index];
  if (input_index >= info.input_binding_count) {
    std::ostringstream message;
    message << "Doe ORT plugin EP " << CompiledOpKindName(info.op_kind)
            << " slice resolved logical input " << logical_input_index << " to invalid kernel input index "
            << input_index << '.';
    return MakeInvalidGraphStatus(info.bindings.api, message.str());
  }

  if (descriptor_out == nullptr || data_out == nullptr) {
    return MakeInvalidArgumentStatus(
        info.bindings.api,
        "Doe ORT plugin EP requires descriptor_out and data_out output pointers when reading kernel inputs.");
  }

  const OrtValue* input = nullptr;
  OrtStatus* status = info.bindings.api->KernelContext_GetInput(kernel_context, input_index, &input);
  if (status != nullptr) return status;
  if (input == nullptr) {
    std::ostringstream message;
    message << "Doe ORT plugin EP received a null input tensor at index " << input_index << '.';
    return MakeInvalidGraphStatus(info.bindings.api, message.str());
  }

  status = GetRuntimeTensorDescriptor(info.bindings.api, input, descriptor_out);
  if (status != nullptr) return status;

  const void* data = nullptr;
  status = info.bindings.api->GetTensorData(input, &data);
  if (status != nullptr) return status;
  if (data == nullptr) {
    std::ostringstream message;
    message << "Doe ORT plugin EP received null tensor data for input " << input_index << '.';
    return MakeInvalidGraphStatus(info.bindings.api, message.str());
  }

  *data_out = static_cast<const float*>(data);
  return nullptr;
}

OrtStatus* GetKernelInputDataMapped(
    const CompiledNodeComputeInfo& info,
    OrtKernelContext* kernel_context,
    const size_t input_index,
    RuntimeTensorDescriptor* descriptor_out,
    const float** data_out) {
  return GetKernelInputData(info, kernel_context, input_index, descriptor_out, data_out);
}

OrtStatus* CreateKernelOutput(
    const CompiledNodeComputeInfo& info,
    OrtKernelContext* kernel_context,
    const RuntimeTensorDescriptor& shape_source,
    float** output_data_out) {
  if (output_data_out == nullptr) {
    return MakeInvalidArgumentStatus(info.bindings.api, "Doe ORT plugin EP requires an output_data_out pointer.");
  }

  OrtValue* output = nullptr;
  OrtStatus* status = info.bindings.api->KernelContext_GetOutput(
      kernel_context,
      0,
      shape_source.dims.empty() ? nullptr : shape_source.dims.data(),
      shape_source.dims.size(),
      &output);
  if (status != nullptr) return status;
  if (output == nullptr) {
    return MakeStatus(info.bindings.api, ORT_FAIL, "Doe ORT plugin EP failed to allocate an output tensor.");
  }

  void* output_data = nullptr;
  status = info.bindings.api->GetTensorMutableData(output, &output_data);
  if (status != nullptr) return status;
  if (output_data == nullptr) {
    return MakeStatus(info.bindings.api, ORT_FAIL, "Doe ORT plugin EP received null output storage from ORT.");
  }

  *output_data_out = static_cast<float*>(output_data);
  return nullptr;
}

OrtStatus* ValidateSameRuntimeShape(
    const CompiledNodeComputeInfo& info,
    const char* lhs_label,
    const RuntimeTensorDescriptor& lhs,
    const char* rhs_label,
    const RuntimeTensorDescriptor& rhs) {
  if (SameTypeAndShape(lhs, rhs)) {
    return nullptr;
  }

  std::ostringstream message;
  message << "Doe ORT plugin EP " << CompiledOpKindName(info.op_kind) << " slice requires exact-shape float32 tensors; "
          << lhs_label << " has shape " << ShapeString(lhs.dims) << " while " << rhs_label << " has shape "
          << ShapeString(rhs.dims) << '.';
  return MakeInvalidGraphStatus(info.bindings.api, message.str());
}

OrtStatus* ValidateRuntimeMatMulShape(
    const CompiledNodeComputeInfo& info,
    const RuntimeTensorDescriptor& lhs,
    const RuntimeTensorDescriptor& rhs,
    RuntimeTensorDescriptor* output_descriptor_out) {
  if (output_descriptor_out == nullptr) {
    return MakeInvalidArgumentStatus(
        info.bindings.api,
        "Doe ORT plugin EP requires an output_descriptor_out pointer when validating MatMul.");
  }

  if (!IsRank2Matrix(lhs) || !IsRank2Matrix(rhs)) {
    std::ostringstream message;
    message << "Doe ORT plugin EP MatMul slice requires rank-2 float32 inputs; input0 has shape "
            << ShapeString(lhs.dims) << " and input1 has shape " << ShapeString(rhs.dims) << '.';
    return MakeInvalidGraphStatus(info.bindings.api, message.str());
  }
  if (lhs.element_type != rhs.element_type) {
    return MakeInvalidGraphStatus(info.bindings.api, "Doe ORT plugin EP MatMul slice requires matching float32 inputs.");
  }
  if (lhs.dims[1] != rhs.dims[0]) {
    std::ostringstream message;
    message << "Doe ORT plugin EP MatMul slice requires exact matrix inner dimensions; input0 has shape "
            << ShapeString(lhs.dims) << " and input1 has shape " << ShapeString(rhs.dims) << '.';
    return MakeInvalidGraphStatus(info.bindings.api, message.str());
  }

  *output_descriptor_out = RuntimeTensorDescriptor{
      .element_type = lhs.element_type,
      .dims = {lhs.dims[0], rhs.dims[1]},
      .element_count = static_cast<size_t>(lhs.dims[0] * rhs.dims[1]),
  };
  return nullptr;
}

float ReluValue(const float value) {
  return value < 0.0f ? 0.0f : value;
}

float SigmoidValue(const float value) {
  return 1.0f / (1.0f + std::exp(-value));
}

float TanhValue(const float value) {
  return std::tanh(value);
}

// GeLU using the exact erf formulation: 0.5 * x * (1 + erf(x / sqrt(2))).
// This matches the ONNX reference implementation. The "approximate=tanh"
// attribute variant is not supported in this slice.
float GeluValue(const float value) {
  constexpr float kInvSqrt2 = 0.70710678118654752440f;
  return 0.5f * value * (1.0f + std::erf(value * kInvSqrt2));
}

OrtStatus* ExecuteIdentity(const CompiledNodeComputeInfo& info, OrtKernelContext* kernel_context) {
  RuntimeTensorDescriptor input_descriptor;
  const float* input_data = nullptr;
  OrtStatus* status = GetKernelInputDataMapped(info, kernel_context, 0, &input_descriptor, &input_data);
  if (status != nullptr) return status;

  float* output_data = nullptr;
  status = CreateKernelOutput(info, kernel_context, input_descriptor, &output_data);
  if (status != nullptr) return status;

  std::memmove(output_data, input_data, input_descriptor.element_count * sizeof(float));
  return nullptr;
}

OrtStatus* ExecuteAdd(const CompiledNodeComputeInfo& info, OrtKernelContext* kernel_context) {
  RuntimeTensorDescriptor lhs_descriptor;
  RuntimeTensorDescriptor rhs_descriptor;
  const float* lhs_data = nullptr;
  const float* rhs_data = nullptr;
  OrtStatus* status = GetKernelInputDataMapped(info, kernel_context, 0, &lhs_descriptor, &lhs_data);
  if (status != nullptr) return status;
  status = GetKernelInputDataMapped(info, kernel_context, 1, &rhs_descriptor, &rhs_data);
  if (status != nullptr) return status;
  status = ValidateSameRuntimeShape(info, "input0", lhs_descriptor, "input1", rhs_descriptor);
  if (status != nullptr) return status;

  float* output_data = nullptr;
  status = CreateKernelOutput(info, kernel_context, lhs_descriptor, &output_data);
  if (status != nullptr) return status;

  for (size_t index = 0; index < lhs_descriptor.element_count; ++index) {
    output_data[index] = lhs_data[index] + rhs_data[index];
  }
  return nullptr;
}

OrtStatus* ExecuteRelu(const CompiledNodeComputeInfo& info, OrtKernelContext* kernel_context) {
  RuntimeTensorDescriptor input_descriptor;
  const float* input_data = nullptr;
  OrtStatus* status = GetKernelInputDataMapped(info, kernel_context, 0, &input_descriptor, &input_data);
  if (status != nullptr) return status;

  float* output_data = nullptr;
  status = CreateKernelOutput(info, kernel_context, input_descriptor, &output_data);
  if (status != nullptr) return status;

  for (size_t index = 0; index < input_descriptor.element_count; ++index) {
    output_data[index] = ReluValue(input_data[index]);
  }
  return nullptr;
}

OrtStatus* ExecuteSigmoid(const CompiledNodeComputeInfo& info, OrtKernelContext* kernel_context) {
  RuntimeTensorDescriptor input_descriptor;
  const float* input_data = nullptr;
  OrtStatus* status = GetKernelInputDataMapped(info, kernel_context, 0, &input_descriptor, &input_data);
  if (status != nullptr) return status;

  float* output_data = nullptr;
  status = CreateKernelOutput(info, kernel_context, input_descriptor, &output_data);
  if (status != nullptr) return status;

  for (size_t index = 0; index < input_descriptor.element_count; ++index) {
    output_data[index] = SigmoidValue(input_data[index]);
  }
  return nullptr;
}

OrtStatus* ExecuteTanh(const CompiledNodeComputeInfo& info, OrtKernelContext* kernel_context) {
  RuntimeTensorDescriptor input_descriptor;
  const float* input_data = nullptr;
  OrtStatus* status = GetKernelInputDataMapped(info, kernel_context, 0, &input_descriptor, &input_data);
  if (status != nullptr) return status;

  float* output_data = nullptr;
  status = CreateKernelOutput(info, kernel_context, input_descriptor, &output_data);
  if (status != nullptr) return status;

  for (size_t index = 0; index < input_descriptor.element_count; ++index) {
    output_data[index] = TanhValue(input_data[index]);
  }
  return nullptr;
}

OrtStatus* ExecuteGelu(const CompiledNodeComputeInfo& info, OrtKernelContext* kernel_context) {
  RuntimeTensorDescriptor input_descriptor;
  const float* input_data = nullptr;
  OrtStatus* status = GetKernelInputDataMapped(info, kernel_context, 0, &input_descriptor, &input_data);
  if (status != nullptr) return status;

  float* output_data = nullptr;
  status = CreateKernelOutput(info, kernel_context, input_descriptor, &output_data);
  if (status != nullptr) return status;

  for (size_t index = 0; index < input_descriptor.element_count; ++index) {
    output_data[index] = GeluValue(input_data[index]);
  }
  return nullptr;
}

OrtStatus* ExecuteMatMul(const CompiledNodeComputeInfo& info, OrtKernelContext* kernel_context) {
  RuntimeTensorDescriptor lhs_descriptor;
  RuntimeTensorDescriptor rhs_descriptor;
  RuntimeTensorDescriptor output_descriptor;
  const float* lhs_data = nullptr;
  const float* rhs_data = nullptr;
  OrtStatus* status = GetKernelInputDataMapped(info, kernel_context, 0, &lhs_descriptor, &lhs_data);
  if (status != nullptr) return status;
  status = GetKernelInputDataMapped(info, kernel_context, 1, &rhs_descriptor, &rhs_data);
  if (status != nullptr) return status;
  status = ValidateRuntimeMatMulShape(info, lhs_descriptor, rhs_descriptor, &output_descriptor);
  if (status != nullptr) return status;

  float* output_data = nullptr;
  status = CreateKernelOutput(info, kernel_context, output_descriptor, &output_data);
  if (status != nullptr) return status;

  const size_t m_dim = static_cast<size_t>(lhs_descriptor.dims[0]);
  const size_t k_dim = static_cast<size_t>(lhs_descriptor.dims[1]);
  const size_t n_dim = static_cast<size_t>(rhs_descriptor.dims[1]);
  for (size_t row = 0; row < m_dim; ++row) {
    for (size_t col = 0; col < n_dim; ++col) {
      float sum = 0.0f;
      for (size_t k_index = 0; k_index < k_dim; ++k_index) {
        sum += lhs_data[row * k_dim + k_index] * rhs_data[k_index * n_dim + col];
      }
      output_data[row * n_dim + col] = sum;
    }
  }
  return nullptr;
}

OrtStatus* ExecuteGemm(const CompiledNodeComputeInfo& info, OrtKernelContext* kernel_context) {
  RuntimeTensorDescriptor lhs_descriptor;
  RuntimeTensorDescriptor rhs_descriptor;
  RuntimeTensorDescriptor addend_descriptor;
  RuntimeTensorDescriptor output_descriptor;
  const float* lhs_data = nullptr;
  const float* rhs_data = nullptr;
  const float* addend_data = nullptr;
  OrtStatus* status = GetKernelInputDataMapped(info, kernel_context, 0, &lhs_descriptor, &lhs_data);
  if (status != nullptr) return status;
  status = GetKernelInputDataMapped(info, kernel_context, 1, &rhs_descriptor, &rhs_data);
  if (status != nullptr) return status;
  status = GetKernelInputDataMapped(info, kernel_context, 2, &addend_descriptor, &addend_data);
  if (status != nullptr) return status;
  status = ValidateRuntimeMatMulShape(info, lhs_descriptor, rhs_descriptor, &output_descriptor);
  if (status != nullptr) return status;
  status = ValidateSameRuntimeShape(info, "matmul_output", output_descriptor, "gemm_bias", addend_descriptor);
  if (status != nullptr) return status;

  float* output_data = nullptr;
  status = CreateKernelOutput(info, kernel_context, output_descriptor, &output_data);
  if (status != nullptr) return status;

  const size_t m_dim = static_cast<size_t>(lhs_descriptor.dims[0]);
  const size_t k_dim = static_cast<size_t>(lhs_descriptor.dims[1]);
  const size_t n_dim = static_cast<size_t>(rhs_descriptor.dims[1]);
  for (size_t row = 0; row < m_dim; ++row) {
    for (size_t col = 0; col < n_dim; ++col) {
      float sum = 0.0f;
      for (size_t k_index = 0; k_index < k_dim; ++k_index) {
        sum += lhs_data[row * k_dim + k_index] * rhs_data[k_index * n_dim + col];
      }
      const size_t output_index = row * n_dim + col;
      output_data[output_index] = sum + addend_data[output_index];
    }
  }
  return nullptr;
}

OrtStatus* ExecuteGemmReluGemm(const CompiledNodeComputeInfo& info, OrtKernelContext* kernel_context) {
  RuntimeTensorDescriptor input_descriptor;
  RuntimeTensorDescriptor hidden_weight_descriptor;
  RuntimeTensorDescriptor hidden_bias_descriptor;
  RuntimeTensorDescriptor output_weight_descriptor;
  RuntimeTensorDescriptor output_bias_descriptor;
  RuntimeTensorDescriptor hidden_descriptor;
  RuntimeTensorDescriptor output_descriptor;
  const float* input_data = nullptr;
  const float* hidden_weight_data = nullptr;
  const float* hidden_bias_data = nullptr;
  const float* output_weight_data = nullptr;
  const float* output_bias_data = nullptr;
  OrtStatus* status = GetKernelInputDataMapped(info, kernel_context, 0, &input_descriptor, &input_data);
  if (status != nullptr) return status;
  status = GetKernelInputDataMapped(info, kernel_context, 1, &hidden_weight_descriptor, &hidden_weight_data);
  if (status != nullptr) return status;
  status = GetKernelInputDataMapped(info, kernel_context, 2, &hidden_bias_descriptor, &hidden_bias_data);
  if (status != nullptr) return status;
  status = GetKernelInputDataMapped(info, kernel_context, 3, &output_weight_descriptor, &output_weight_data);
  if (status != nullptr) return status;
  status = GetKernelInputDataMapped(info, kernel_context, 4, &output_bias_descriptor, &output_bias_data);
  if (status != nullptr) return status;

  status = ValidateRuntimeMatMulShape(info, input_descriptor, hidden_weight_descriptor, &hidden_descriptor);
  if (status != nullptr) return status;
  status = ValidateSameRuntimeShape(info, "hidden_gemm_output", hidden_descriptor, "hidden_bias", hidden_bias_descriptor);
  if (status != nullptr) return status;
  status = ValidateRuntimeMatMulShape(info, hidden_descriptor, output_weight_descriptor, &output_descriptor);
  if (status != nullptr) return status;
  status = ValidateSameRuntimeShape(info, "output_gemm_output", output_descriptor, "output_bias", output_bias_descriptor);
  if (status != nullptr) return status;

  std::vector<float> hidden_activations(hidden_descriptor.element_count, 0.0f);
  const size_t batch_dim = static_cast<size_t>(input_descriptor.dims[0]);
  const size_t input_dim = static_cast<size_t>(input_descriptor.dims[1]);
  const size_t hidden_dim = static_cast<size_t>(hidden_weight_descriptor.dims[1]);
  for (size_t row = 0; row < batch_dim; ++row) {
    for (size_t col = 0; col < hidden_dim; ++col) {
      float sum = 0.0f;
      for (size_t k_index = 0; k_index < input_dim; ++k_index) {
        sum += input_data[row * input_dim + k_index] * hidden_weight_data[k_index * hidden_dim + col];
      }
      const size_t hidden_index = row * hidden_dim + col;
      hidden_activations[hidden_index] = ReluValue(sum + hidden_bias_data[hidden_index]);
    }
  }

  float* output_data = nullptr;
  status = CreateKernelOutput(info, kernel_context, output_descriptor, &output_data);
  if (status != nullptr) return status;

  const size_t output_dim = static_cast<size_t>(output_weight_descriptor.dims[1]);
  for (size_t row = 0; row < batch_dim; ++row) {
    for (size_t col = 0; col < output_dim; ++col) {
      float sum = 0.0f;
      for (size_t k_index = 0; k_index < hidden_dim; ++k_index) {
        sum += hidden_activations[row * hidden_dim + k_index] * output_weight_data[k_index * output_dim + col];
      }
      const size_t output_index = row * output_dim + col;
      output_data[output_index] = sum + output_bias_data[output_index];
    }
  }
  return nullptr;
}

OrtStatus* ExecuteMatMulAdd(const CompiledNodeComputeInfo& info, OrtKernelContext* kernel_context) {
  RuntimeTensorDescriptor lhs_descriptor;
  RuntimeTensorDescriptor rhs_descriptor;
  RuntimeTensorDescriptor addend_descriptor;
  RuntimeTensorDescriptor output_descriptor;
  const float* lhs_data = nullptr;
  const float* rhs_data = nullptr;
  const float* addend_data = nullptr;
  OrtStatus* status = GetKernelInputDataMapped(info, kernel_context, 0, &lhs_descriptor, &lhs_data);
  if (status != nullptr) return status;
  status = GetKernelInputDataMapped(info, kernel_context, 1, &rhs_descriptor, &rhs_data);
  if (status != nullptr) return status;
  status = GetKernelInputDataMapped(info, kernel_context, 2, &addend_descriptor, &addend_data);
  if (status != nullptr) return status;
  status = ValidateRuntimeMatMulShape(info, lhs_descriptor, rhs_descriptor, &output_descriptor);
  if (status != nullptr) return status;
  status = ValidateSameRuntimeShape(info, "matmul_output", output_descriptor, "add_input", addend_descriptor);
  if (status != nullptr) return status;

  float* output_data = nullptr;
  status = CreateKernelOutput(info, kernel_context, output_descriptor, &output_data);
  if (status != nullptr) return status;

  const size_t m_dim = static_cast<size_t>(lhs_descriptor.dims[0]);
  const size_t k_dim = static_cast<size_t>(lhs_descriptor.dims[1]);
  const size_t n_dim = static_cast<size_t>(rhs_descriptor.dims[1]);
  for (size_t row = 0; row < m_dim; ++row) {
    for (size_t col = 0; col < n_dim; ++col) {
      float sum = 0.0f;
      for (size_t k_index = 0; k_index < k_dim; ++k_index) {
        sum += lhs_data[row * k_dim + k_index] * rhs_data[k_index * n_dim + col];
      }
      const size_t output_index = row * n_dim + col;
      output_data[output_index] = sum + addend_data[output_index];
    }
  }
  return nullptr;
}

OrtStatus* ExecuteMatMulAddRelu(const CompiledNodeComputeInfo& info, OrtKernelContext* kernel_context) {
  RuntimeTensorDescriptor lhs_descriptor;
  RuntimeTensorDescriptor rhs_descriptor;
  RuntimeTensorDescriptor addend_descriptor;
  RuntimeTensorDescriptor output_descriptor;
  const float* lhs_data = nullptr;
  const float* rhs_data = nullptr;
  const float* addend_data = nullptr;
  OrtStatus* status = GetKernelInputDataMapped(info, kernel_context, 0, &lhs_descriptor, &lhs_data);
  if (status != nullptr) return status;
  status = GetKernelInputDataMapped(info, kernel_context, 1, &rhs_descriptor, &rhs_data);
  if (status != nullptr) return status;
  status = GetKernelInputDataMapped(info, kernel_context, 2, &addend_descriptor, &addend_data);
  if (status != nullptr) return status;
  status = ValidateRuntimeMatMulShape(info, lhs_descriptor, rhs_descriptor, &output_descriptor);
  if (status != nullptr) return status;
  status = ValidateSameRuntimeShape(info, "matmul_output", output_descriptor, "add_input", addend_descriptor);
  if (status != nullptr) return status;

  float* output_data = nullptr;
  status = CreateKernelOutput(info, kernel_context, output_descriptor, &output_data);
  if (status != nullptr) return status;

  const size_t m_dim = static_cast<size_t>(lhs_descriptor.dims[0]);
  const size_t k_dim = static_cast<size_t>(lhs_descriptor.dims[1]);
  const size_t n_dim = static_cast<size_t>(rhs_descriptor.dims[1]);
  for (size_t row = 0; row < m_dim; ++row) {
    for (size_t col = 0; col < n_dim; ++col) {
      float sum = 0.0f;
      for (size_t k_index = 0; k_index < k_dim; ++k_index) {
        sum += lhs_data[row * k_dim + k_index] * rhs_data[k_index * n_dim + col];
      }
      const size_t output_index = row * n_dim + col;
      output_data[output_index] = ReluValue(sum + addend_data[output_index]);
    }
  }
  return nullptr;
}

OrtStatus* ExecuteAddRelu(const CompiledNodeComputeInfo& info, OrtKernelContext* kernel_context) {
  RuntimeTensorDescriptor lhs_descriptor;
  RuntimeTensorDescriptor rhs_descriptor;
  const float* lhs_data = nullptr;
  const float* rhs_data = nullptr;
  OrtStatus* status = GetKernelInputDataMapped(info, kernel_context, 0, &lhs_descriptor, &lhs_data);
  if (status != nullptr) return status;
  status = GetKernelInputDataMapped(info, kernel_context, 1, &rhs_descriptor, &rhs_data);
  if (status != nullptr) return status;
  status = ValidateSameRuntimeShape(info, "input0", lhs_descriptor, "input1", rhs_descriptor);
  if (status != nullptr) return status;

  float* output_data = nullptr;
  status = CreateKernelOutput(info, kernel_context, lhs_descriptor, &output_data);
  if (status != nullptr) return status;

  for (size_t index = 0; index < lhs_descriptor.element_count; ++index) {
    const float sum = lhs_data[index] + rhs_data[index];
    output_data[index] = ReluValue(sum);
  }
  return nullptr;
}

OrtStatus* ORT_API_CALL CreateStateImpl(
    OrtNodeComputeInfo* this_ptr,
    OrtNodeComputeContext* compute_context,
    void** compute_state) {
  auto& info = ComputeInfoSelf(this_ptr);
  if (compute_state == nullptr) {
    return MakeInvalidArgumentStatus(info.bindings.api, "Doe ORT plugin EP requires a compute_state output pointer.");
  }

  g_create_state_calls.fetch_add(1, std::memory_order_relaxed);
  const char* context_node_name =
      info.bindings.ep_api != nullptr && compute_context != nullptr
          ? info.bindings.ep_api->NodeComputeContext_NodeName(compute_context)
          : nullptr;

  auto state = std::make_unique<CompiledComputeState>();
  state->node_name = context_node_name != nullptr ? context_node_name : info.node_name;
  state->op_kind = info.op_kind;
  *compute_state = state.release();
  return nullptr;
}

OrtStatus* ORT_API_CALL ComputeImpl(
    OrtNodeComputeInfo* this_ptr,
    void* compute_state,
    OrtKernelContext* kernel_context) {
  (void)compute_state;
  auto& info = ComputeInfoSelf(this_ptr);
  if (kernel_context == nullptr) {
    return MakeInvalidArgumentStatus(info.bindings.api, "Doe ORT plugin EP requires a kernel_context input.");
  }

  g_compute_calls.fetch_add(1, std::memory_order_relaxed);
  IncrementComputeCounters(info.op_kind);

  OrtStatus* status =
      ValidateRuntimeArity(info, kernel_context, ExpectedInputCountForKind(info.op_kind), kSingleOutputCount);
  if (status != nullptr) return status;

  switch (info.op_kind) {
    case CompiledOpKind::kIdentity:
      return ExecuteIdentity(info, kernel_context);
    case CompiledOpKind::kAdd:
      return ExecuteAdd(info, kernel_context);
    case CompiledOpKind::kRelu:
      return ExecuteRelu(info, kernel_context);
    case CompiledOpKind::kSigmoid:
      return ExecuteSigmoid(info, kernel_context);
    case CompiledOpKind::kTanh:
      return ExecuteTanh(info, kernel_context);
    case CompiledOpKind::kGelu:
      return ExecuteGelu(info, kernel_context);
    case CompiledOpKind::kMatMul:
      return ExecuteMatMul(info, kernel_context);
    case CompiledOpKind::kGemm:
      return ExecuteGemm(info, kernel_context);
    case CompiledOpKind::kGemmReluGemm:
      return ExecuteGemmReluGemm(info, kernel_context);
    case CompiledOpKind::kMatMulAdd:
      return ExecuteMatMulAdd(info, kernel_context);
    case CompiledOpKind::kMatMulAddRelu:
      return ExecuteMatMulAddRelu(info, kernel_context);
    case CompiledOpKind::kAddRelu:
      return ExecuteAddRelu(info, kernel_context);
  }

  return MakeStatus(info.bindings.api, ORT_FAIL, "Doe ORT plugin EP reached an unknown compiled op kind.");
}

void ORT_API_CALL ReleaseStateImpl(OrtNodeComputeInfo* this_ptr, void* compute_state) {
  (void)this_ptr;
  g_release_state_calls.fetch_add(1, std::memory_order_relaxed);
  delete static_cast<CompiledComputeState*>(compute_state);
}

}  // namespace

DoeOrtEp::DoeOrtEp(std::string registration_name, ApiBindings bindings)
    : OrtEp{},
      registration_name_(registration_name.empty() ? "DoeExecutionProvider" : std::move(registration_name)),
      bindings_(bindings) {
  ort_version_supported = kOrtPluginEpRuntimeApiVersion;
  GetName = &GetNameImpl;
  GetCapability = &GetCapabilityImpl;
  Compile = &CompileImpl;
  ReleaseNodeComputeInfos = &ReleaseNodeComputeInfosImpl;
  GetPreferredDataLayout = &GetPreferredDataLayoutImpl;
  OnRunStart = &OnRunStartImpl;
  OnRunEnd = &OnRunEndImpl;
  GetCompiledModelCompatibilityInfo = &GetCompiledModelCompatibilityInfoImpl;
}

DoeOrtEp& DoeOrtEp::Self(OrtEp* this_ptr) {
  return *static_cast<DoeOrtEp*>(this_ptr);
}

const DoeOrtEp& DoeOrtEp::Self(const OrtEp* this_ptr) {
  return *static_cast<const DoeOrtEp*>(this_ptr);
}

const char* ORT_API_CALL DoeOrtEp::GetNameImpl(const OrtEp* this_ptr) NO_EXCEPTION {
  return Self(this_ptr).registration_name_.c_str();
}

void ResetDebugCounters() NO_EXCEPTION {
  g_get_capability_calls.store(0, std::memory_order_relaxed);
  g_claimed_nodes.store(0, std::memory_order_relaxed);
  g_claimed_identity_nodes.store(0, std::memory_order_relaxed);
  g_claimed_add_nodes.store(0, std::memory_order_relaxed);
  g_claimed_relu_nodes.store(0, std::memory_order_relaxed);
  g_claimed_sigmoid_nodes.store(0, std::memory_order_relaxed);
  g_claimed_tanh_nodes.store(0, std::memory_order_relaxed);
  g_claimed_gelu_nodes.store(0, std::memory_order_relaxed);
  g_claimed_matmul_nodes.store(0, std::memory_order_relaxed);
  g_claimed_gemm_nodes.store(0, std::memory_order_relaxed);
  g_compile_calls.store(0, std::memory_order_relaxed);
  g_compiled_identity_groups.store(0, std::memory_order_relaxed);
  g_compiled_add_groups.store(0, std::memory_order_relaxed);
  g_compiled_relu_groups.store(0, std::memory_order_relaxed);
  g_compiled_sigmoid_groups.store(0, std::memory_order_relaxed);
  g_compiled_tanh_groups.store(0, std::memory_order_relaxed);
  g_compiled_gelu_groups.store(0, std::memory_order_relaxed);
  g_compiled_matmul_groups.store(0, std::memory_order_relaxed);
  g_compiled_gemm_groups.store(0, std::memory_order_relaxed);
  g_compiled_gemm_relu_gemm_groups.store(0, std::memory_order_relaxed);
  g_compiled_matmul_add_groups.store(0, std::memory_order_relaxed);
  g_compiled_matmul_add_relu_groups.store(0, std::memory_order_relaxed);
  g_compiled_add_relu_groups.store(0, std::memory_order_relaxed);
  g_create_state_calls.store(0, std::memory_order_relaxed);
  g_compute_calls.store(0, std::memory_order_relaxed);
  g_compute_identity_calls.store(0, std::memory_order_relaxed);
  g_compute_add_calls.store(0, std::memory_order_relaxed);
  g_compute_relu_calls.store(0, std::memory_order_relaxed);
  g_compute_sigmoid_calls.store(0, std::memory_order_relaxed);
  g_compute_tanh_calls.store(0, std::memory_order_relaxed);
  g_compute_gelu_calls.store(0, std::memory_order_relaxed);
  g_compute_matmul_calls.store(0, std::memory_order_relaxed);
  g_compute_gemm_calls.store(0, std::memory_order_relaxed);
  g_compute_gemm_relu_gemm_calls.store(0, std::memory_order_relaxed);
  g_compute_matmul_add_calls.store(0, std::memory_order_relaxed);
  g_compute_matmul_add_relu_calls.store(0, std::memory_order_relaxed);
  g_compute_add_relu_calls.store(0, std::memory_order_relaxed);
  g_release_state_calls.store(0, std::memory_order_relaxed);
}

DoeOrtEpDebugCounters SnapshotDebugCounters() NO_EXCEPTION {
  return DoeOrtEpDebugCounters{
      .get_capability_calls = g_get_capability_calls.load(std::memory_order_relaxed),
      .claimed_nodes = g_claimed_nodes.load(std::memory_order_relaxed),
      .claimed_identity_nodes = g_claimed_identity_nodes.load(std::memory_order_relaxed),
      .claimed_add_nodes = g_claimed_add_nodes.load(std::memory_order_relaxed),
      .claimed_relu_nodes = g_claimed_relu_nodes.load(std::memory_order_relaxed),
      .claimed_sigmoid_nodes = g_claimed_sigmoid_nodes.load(std::memory_order_relaxed),
      .claimed_tanh_nodes = g_claimed_tanh_nodes.load(std::memory_order_relaxed),
      .claimed_gelu_nodes = g_claimed_gelu_nodes.load(std::memory_order_relaxed),
      .claimed_matmul_nodes = g_claimed_matmul_nodes.load(std::memory_order_relaxed),
      .claimed_gemm_nodes = g_claimed_gemm_nodes.load(std::memory_order_relaxed),
      .compile_calls = g_compile_calls.load(std::memory_order_relaxed),
      .compiled_identity_groups = g_compiled_identity_groups.load(std::memory_order_relaxed),
      .compiled_add_groups = g_compiled_add_groups.load(std::memory_order_relaxed),
      .compiled_relu_groups = g_compiled_relu_groups.load(std::memory_order_relaxed),
      .compiled_sigmoid_groups = g_compiled_sigmoid_groups.load(std::memory_order_relaxed),
      .compiled_tanh_groups = g_compiled_tanh_groups.load(std::memory_order_relaxed),
      .compiled_gelu_groups = g_compiled_gelu_groups.load(std::memory_order_relaxed),
      .compiled_matmul_groups = g_compiled_matmul_groups.load(std::memory_order_relaxed),
      .compiled_gemm_groups = g_compiled_gemm_groups.load(std::memory_order_relaxed),
      .compiled_gemm_relu_gemm_groups = g_compiled_gemm_relu_gemm_groups.load(std::memory_order_relaxed),
      .compiled_matmul_add_groups = g_compiled_matmul_add_groups.load(std::memory_order_relaxed),
      .compiled_matmul_add_relu_groups = g_compiled_matmul_add_relu_groups.load(std::memory_order_relaxed),
      .compiled_add_relu_groups = g_compiled_add_relu_groups.load(std::memory_order_relaxed),
      .create_state_calls = g_create_state_calls.load(std::memory_order_relaxed),
      .compute_calls = g_compute_calls.load(std::memory_order_relaxed),
      .compute_identity_calls = g_compute_identity_calls.load(std::memory_order_relaxed),
      .compute_add_calls = g_compute_add_calls.load(std::memory_order_relaxed),
      .compute_relu_calls = g_compute_relu_calls.load(std::memory_order_relaxed),
      .compute_sigmoid_calls = g_compute_sigmoid_calls.load(std::memory_order_relaxed),
      .compute_tanh_calls = g_compute_tanh_calls.load(std::memory_order_relaxed),
      .compute_gelu_calls = g_compute_gelu_calls.load(std::memory_order_relaxed),
      .compute_matmul_calls = g_compute_matmul_calls.load(std::memory_order_relaxed),
      .compute_gemm_calls = g_compute_gemm_calls.load(std::memory_order_relaxed),
      .compute_gemm_relu_gemm_calls = g_compute_gemm_relu_gemm_calls.load(std::memory_order_relaxed),
      .compute_matmul_add_calls = g_compute_matmul_add_calls.load(std::memory_order_relaxed),
      .compute_matmul_add_relu_calls = g_compute_matmul_add_relu_calls.load(std::memory_order_relaxed),
      .compute_add_relu_calls = g_compute_add_relu_calls.load(std::memory_order_relaxed),
      .release_state_calls = g_release_state_calls.load(std::memory_order_relaxed),
  };
}

OrtStatus* ORT_API_CALL DoeOrtEp::GetCapabilityImpl(
    OrtEp* this_ptr,
    const OrtGraph* graph,
    OrtEpGraphSupportInfo* graph_support_info) NO_EXCEPTION {
  auto& self = Self(this_ptr);
  if (graph == nullptr || graph_support_info == nullptr) {
    return MakeStatus(
        self.bindings_.api,
        ORT_INVALID_ARGUMENT,
        "Doe ORT plugin EP requires non-null graph and graph_support_info inputs.");
  }
  if (self.bindings_.ep_api == nullptr) {
    return MakeStatus(self.bindings_.api, ORT_NOT_IMPLEMENTED, "Doe ORT plugin EP requires OrtEpApi to report graph support.");
  }

  g_get_capability_calls.fetch_add(1, std::memory_order_relaxed);

  std::vector<const OrtNode*> nodes;
  OrtStatus* status = GetGraphNodes(self.bindings_.api, graph, &nodes);
  if (status != nullptr) return status;

  std::unordered_set<const OrtNode*> claimed_nodes;
  for (const OrtNode* node : nodes) {
    if (node == nullptr || claimed_nodes.find(node) != claimed_nodes.end()) {
      continue;
    }

    SupportedNodeSpec node_spec;
    bool node_supported = false;
    status = GetSupportedNodeSpec(self.bindings_.api, node, &node_spec, &node_supported);
    if (status != nullptr) return status;
    if (!node_supported) {
      continue;
    }

    SupportedGraphSpec graph_spec;
    graph_spec.kind = node_spec.kind;
    graph_spec.default_node_name = node_spec.node_name.empty() ? CompiledOpKindName(node_spec.kind) : node_spec.node_name;
    graph_spec.fused_nodes = {node};

    if (node_spec.kind == CompiledOpKind::kMatMul) {
      SupportedNodeSpec add_spec;
      size_t matmul_output_input_index = 0;
      bool found_add = false;
      status = FindSupportedAddConsumer(
          self.bindings_.api,
          node_spec,
          claimed_nodes,
          &add_spec,
          &matmul_output_input_index,
          &found_add);
      if (status != nullptr) return status;
      if (found_add) {
        SupportedNodeSpec relu_spec;
        bool found_relu = false;
        status = FindSupportedReluConsumer(self.bindings_.api, add_spec, claimed_nodes, &relu_spec, &found_relu);
        if (status != nullptr) return status;
        if (found_relu) {
          graph_spec = BuildMatMulAddReluGraphSpec(node_spec, add_spec, matmul_output_input_index, relu_spec);
        } else {
          graph_spec = BuildMatMulAddGraphSpec(node_spec, add_spec, matmul_output_input_index);
        }
      }
    } else if (node_spec.kind == CompiledOpKind::kGemm) {
      SupportedNodeSpec relu_spec;
      bool found_relu = false;
      status = FindSupportedReluConsumer(self.bindings_.api, node_spec, claimed_nodes, &relu_spec, &found_relu);
      if (status != nullptr) return status;
      if (found_relu) {
        SupportedNodeSpec second_gemm_spec;
        bool found_second_gemm = false;
        status =
            FindSupportedGemmConsumer(self.bindings_.api, relu_spec, claimed_nodes, &second_gemm_spec, &found_second_gemm);
        if (status != nullptr) return status;
        if (found_second_gemm) {
          graph_spec = BuildGemmReluGemmGraphSpec(node_spec, relu_spec, second_gemm_spec);
        }
      }
    } else if (node_spec.kind == CompiledOpKind::kAdd) {
      SupportedNodeSpec relu_spec;
      bool found_relu = false;
      status = FindSupportedReluConsumer(self.bindings_.api, node_spec, claimed_nodes, &relu_spec, &found_relu);
      if (status != nullptr) return status;
      if (found_relu) {
        graph_spec = BuildAddReluGraphSpec(node_spec, relu_spec);
      }
    }

    status = self.bindings_.ep_api->EpGraphSupportInfo_AddNodesToFuse(
        graph_support_info,
        graph_spec.fused_nodes.data(),
        graph_spec.fused_nodes.size(),
        nullptr);
    if (status != nullptr) return status;

    for (const OrtNode* claimed_node : graph_spec.fused_nodes) {
      claimed_nodes.insert(claimed_node);
    }
    IncrementClaimCounters(graph_spec.kind);
  }

  return nullptr;
}

OrtStatus* ORT_API_CALL DoeOrtEp::CompileImpl(
    OrtEp* this_ptr,
    const OrtGraph** graphs,
    const OrtNode** fused_nodes,
    const size_t count,
    OrtNodeComputeInfo** node_compute_infos,
    OrtNode** ep_context_nodes) NO_EXCEPTION {
  auto& self = Self(this_ptr);
  g_compile_calls.fetch_add(1, std::memory_order_relaxed);

  if (count != 0 && graphs == nullptr) {
    return MakeStatus(self.bindings_.api, ORT_INVALID_ARGUMENT, "Doe ORT plugin EP requires graphs when compiling assigned nodes.");
  }
  if (count != 0 && node_compute_infos == nullptr) {
    return MakeStatus(
        self.bindings_.api,
        ORT_INVALID_ARGUMENT,
        "Doe ORT plugin EP requires node_compute_infos when compiling graphs.");
  }
  if (node_compute_infos != nullptr) {
    for (size_t index = 0; index < count; ++index) {
      node_compute_infos[index] = nullptr;
    }
  }
  if (ep_context_nodes != nullptr) {
    for (size_t index = 0; index < count; ++index) {
      ep_context_nodes[index] = nullptr;
    }
  }

  for (size_t index = 0; index < count; ++index) {
    SupportedGraphSpec graph_spec;
    bool graph_supported = false;
    OrtStatus* status = AnalyzeSupportedGraph(self.bindings_.api, graphs[index], &graph_spec, &graph_supported);
    if (status != nullptr) {
      ReleaseNodeComputeInfosImpl(this_ptr, node_compute_infos, index);
      return status;
    }
    if (!graph_supported) {
      ReleaseNodeComputeInfosImpl(this_ptr, node_compute_infos, index);
      return MakeStatus(
          self.bindings_.api,
          ORT_NOT_IMPLEMENTED,
          "Doe ORT plugin EP was asked to compile a graph outside its narrow float32 Identity/Add/Relu/MatMul/Gemm/Gemm->Relu->Gemm/MatMul->Add/MatMul->Add->Relu/Add->Relu slice.");
    }

    auto info = std::make_unique<CompiledNodeComputeInfo>();
    info->base.ort_version_supported = ORT_API_VERSION;
    info->base.CreateState = &CreateStateImpl;
    info->base.Compute = &ComputeImpl;
    info->base.ReleaseState = &ReleaseStateImpl;
    info->bindings = self.bindings_;
    info->op_kind = graph_spec.kind;
    status = ResolveGraphInputBindings(
        self.bindings_.api,
        graphs[index],
        graph_spec,
        &info->input_binding_indices,
        &info->input_binding_count);
    if (status != nullptr) {
      ReleaseNodeComputeInfosImpl(this_ptr, node_compute_infos, index);
      return status;
    }

    const OrtNode* name_source =
        fused_nodes != nullptr && fused_nodes[index] != nullptr ? fused_nodes[index] : graph_spec.fused_nodes.front();
    const char* node_name = nullptr;
    status = self.bindings_.api->Node_GetName(name_source, &node_name);
    if (status != nullptr) {
      ReleaseNodeComputeInfosImpl(this_ptr, node_compute_infos, index);
      return status;
    }
    info->node_name = node_name != nullptr && node_name[0] != '\0' ? node_name : graph_spec.default_node_name;

    IncrementCompiledGroupCounters(info->op_kind);
    node_compute_infos[index] = &info.release()->base;
  }

  return nullptr;
}

void ORT_API_CALL DoeOrtEp::ReleaseNodeComputeInfosImpl(
    OrtEp* this_ptr,
    OrtNodeComputeInfo** node_compute_infos,
    const size_t num_node_compute_infos) NO_EXCEPTION {
  (void)this_ptr;
  if (node_compute_infos == nullptr) {
    return;
  }
  for (size_t index = 0; index < num_node_compute_infos; ++index) {
    if (node_compute_infos[index] == nullptr) {
      continue;
    }
    delete &ComputeInfoSelf(node_compute_infos[index]);
    node_compute_infos[index] = nullptr;
  }
}

OrtStatus* ORT_API_CALL DoeOrtEp::GetPreferredDataLayoutImpl(
    OrtEp* this_ptr,
    OrtEpDataLayout* preferred_data_layout) NO_EXCEPTION {
  if (preferred_data_layout == nullptr) {
    return MakeStatus(
        Self(this_ptr).bindings_.api,
        ORT_INVALID_ARGUMENT,
        "Doe ORT plugin EP requires a preferred_data_layout output pointer.");
  }
  *preferred_data_layout = OrtEpDataLayout_NCHW;
  return nullptr;
}

OrtStatus* ORT_API_CALL DoeOrtEp::OnRunStartImpl(
    OrtEp* this_ptr,
    const OrtRunOptions* run_options) NO_EXCEPTION {
  (void)this_ptr;
  (void)run_options;
  return nullptr;
}

OrtStatus* ORT_API_CALL DoeOrtEp::OnRunEndImpl(
    OrtEp* this_ptr,
    const OrtRunOptions* run_options,
    const bool sync_stream) NO_EXCEPTION {
  (void)this_ptr;
  (void)run_options;
  (void)sync_stream;
  return nullptr;
}

const char* ORT_API_CALL DoeOrtEp::GetCompiledModelCompatibilityInfoImpl(
    OrtEp* this_ptr,
    const OrtGraph* graph) NO_EXCEPTION {
  (void)this_ptr;
  (void)graph;
  return kCompatibilityInfo;
}

}  // namespace doe::ort_ep
