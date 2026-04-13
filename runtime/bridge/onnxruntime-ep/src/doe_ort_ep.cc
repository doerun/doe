#include "doe_ort_ep.h"

#include <atomic>
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

constexpr const char* kCompatibilityInfo = "doe-ort-basic-ops-ep-v2";
constexpr const char* kIdentityOperatorType = "Identity";
constexpr const char* kAddOperatorType = "Add";
constexpr const char* kReluOperatorType = "Relu";
constexpr const char* kMatMulOperatorType = "MatMul";
constexpr const char* kOnnxDomain = "";
constexpr const char* kOnnxAiDomain = "ai.onnx";
constexpr ONNXTensorElementDataType kSupportedElementType = ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;
constexpr size_t kUnaryInputCount = 1;
constexpr size_t kBinaryInputCount = 2;
constexpr size_t kSingleOutputCount = 1;
constexpr size_t kMatrixRank = 2;

enum class CompiledOpKind : uint8_t {
  kIdentity,
  kAdd,
  kRelu,
  kMatMul,
  kAddRelu,
};

std::atomic<uint64_t> g_get_capability_calls{0};
std::atomic<uint64_t> g_claimed_nodes{0};
std::atomic<uint64_t> g_claimed_identity_nodes{0};
std::atomic<uint64_t> g_claimed_add_nodes{0};
std::atomic<uint64_t> g_claimed_relu_nodes{0};
std::atomic<uint64_t> g_claimed_matmul_nodes{0};
std::atomic<uint64_t> g_compile_calls{0};
std::atomic<uint64_t> g_compiled_identity_groups{0};
std::atomic<uint64_t> g_compiled_add_groups{0};
std::atomic<uint64_t> g_compiled_relu_groups{0};
std::atomic<uint64_t> g_compiled_matmul_groups{0};
std::atomic<uint64_t> g_compiled_add_relu_groups{0};
std::atomic<uint64_t> g_create_state_calls{0};
std::atomic<uint64_t> g_compute_calls{0};
std::atomic<uint64_t> g_compute_identity_calls{0};
std::atomic<uint64_t> g_compute_add_calls{0};
std::atomic<uint64_t> g_compute_relu_calls{0};
std::atomic<uint64_t> g_compute_matmul_calls{0};
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
    case CompiledOpKind::kMatMul:
      return kMatMulOperatorType;
    case CompiledOpKind::kAddRelu:
      return "Add->Relu";
  }
  return "unknown";
}

size_t ClaimedNodeCountForKind(const CompiledOpKind kind) {
  return kind == CompiledOpKind::kAddRelu ? 2 : 1;
}

size_t ExpectedInputCountForKind(const CompiledOpKind kind) {
  switch (kind) {
    case CompiledOpKind::kIdentity:
    case CompiledOpKind::kRelu:
      return kUnaryInputCount;
    case CompiledOpKind::kAdd:
    case CompiledOpKind::kMatMul:
    case CompiledOpKind::kAddRelu:
      return kBinaryInputCount;
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
    case CompiledOpKind::kMatMul:
      g_claimed_matmul_nodes.fetch_add(1, std::memory_order_relaxed);
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
    case CompiledOpKind::kMatMul:
      g_compiled_matmul_groups.fetch_add(1, std::memory_order_relaxed);
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
    case CompiledOpKind::kMatMul:
      g_compute_matmul_calls.fetch_add(1, std::memory_order_relaxed);
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
  const char* value_name = nullptr;
  OrtStatus* status = api->GetValueInfoName(value_info, &value_name);
  if (status != nullptr) return status;
  descriptor_out->name = value_name != nullptr ? value_name : "";

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
  } else if (std::string_view(operator_type) == kMatMulOperatorType) {
    spec_out->kind = CompiledOpKind::kMatMul;
    expected_inputs = kBinaryInputCount;
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
      return nullptr;
    }
    spec_out->outputs.push_back(std::move(descriptor));
  }

  switch (spec_out->kind) {
    case CompiledOpKind::kIdentity:
    case CompiledOpKind::kRelu:
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
      if (!IsStaticMatMulShape(spec_out->inputs[0], spec_out->inputs[1], spec_out->outputs[0])) {
        return nullptr;
      }
      break;
    case CompiledOpKind::kAddRelu:
      return MakeInvalidArgumentStatus(api, "Doe ORT plugin EP does not validate Add->Relu as a single OrtNode.");
  }

  *is_supported = true;
  return nullptr;
}

OrtStatus* FindSupportedReluConsumer(
    const OrtApi* api,
    const SupportedNodeSpec& add_spec,
    const std::unordered_set<const OrtNode*>& already_claimed,
    SupportedNodeSpec* relu_spec_out,
    bool* found) {
  if (relu_spec_out == nullptr || found == nullptr) {
    return MakeInvalidArgumentStatus(
        api,
        "Doe ORT plugin EP requires relu_spec_out and found output pointers when searching for Add->Relu fusion.");
  }
  *relu_spec_out = SupportedNodeSpec{};
  *found = false;

  if (add_spec.kind != CompiledOpKind::kAdd || add_spec.outputs.size() != 1 || add_spec.outputs[0].value_info == nullptr) {
    return nullptr;
  }

  bool is_graph_output = false;
  OrtStatus* status = api->ValueInfo_IsGraphOutput(add_spec.outputs[0].value_info, &is_graph_output);
  if (status != nullptr) return status;
  if (is_graph_output) {
    return nullptr;
  }

  size_t num_consumers = 0;
  status = api->ValueInfo_GetValueNumConsumers(add_spec.outputs[0].value_info, &num_consumers);
  if (status != nullptr) return status;
  if (num_consumers != 1) {
    return nullptr;
  }

  std::vector<const OrtNode*> consumer_nodes(num_consumers, nullptr);
  std::vector<int64_t> consumer_input_indices(num_consumers, -1);
  status = api->ValueInfo_GetValueConsumers(
      add_spec.outputs[0].value_info,
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
    } else {
      return nullptr;
    }

    SupportedNodeSpec fused_relu_spec;
    bool fused = false;
    status = FindSupportedReluConsumer(api, *add_spec, {}, &fused_relu_spec, &fused);
    if (status != nullptr) return status;
    if (!fused || fused_relu_spec.node != relu_spec->node) {
      return nullptr;
    }

    spec_out->kind = CompiledOpKind::kAddRelu;
    spec_out->default_node_name = "doe_add_relu";
    spec_out->fused_nodes = {add_spec->node, relu_spec->node};
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
    const size_t input_index,
    RuntimeTensorDescriptor* descriptor_out,
    const float** data_out) {
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

OrtStatus* ExecuteIdentity(const CompiledNodeComputeInfo& info, OrtKernelContext* kernel_context) {
  RuntimeTensorDescriptor input_descriptor;
  const float* input_data = nullptr;
  OrtStatus* status = GetKernelInputData(info, kernel_context, 0, &input_descriptor, &input_data);
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
  OrtStatus* status = GetKernelInputData(info, kernel_context, 0, &lhs_descriptor, &lhs_data);
  if (status != nullptr) return status;
  status = GetKernelInputData(info, kernel_context, 1, &rhs_descriptor, &rhs_data);
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
  OrtStatus* status = GetKernelInputData(info, kernel_context, 0, &input_descriptor, &input_data);
  if (status != nullptr) return status;

  float* output_data = nullptr;
  status = CreateKernelOutput(info, kernel_context, input_descriptor, &output_data);
  if (status != nullptr) return status;

  for (size_t index = 0; index < input_descriptor.element_count; ++index) {
    const float value = input_data[index];
    output_data[index] = value < 0.0f ? 0.0f : value;
  }
  return nullptr;
}

OrtStatus* ExecuteMatMul(const CompiledNodeComputeInfo& info, OrtKernelContext* kernel_context) {
  RuntimeTensorDescriptor lhs_descriptor;
  RuntimeTensorDescriptor rhs_descriptor;
  RuntimeTensorDescriptor output_descriptor;
  const float* lhs_data = nullptr;
  const float* rhs_data = nullptr;
  OrtStatus* status = GetKernelInputData(info, kernel_context, 0, &lhs_descriptor, &lhs_data);
  if (status != nullptr) return status;
  status = GetKernelInputData(info, kernel_context, 1, &rhs_descriptor, &rhs_data);
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

OrtStatus* ExecuteAddRelu(const CompiledNodeComputeInfo& info, OrtKernelContext* kernel_context) {
  RuntimeTensorDescriptor lhs_descriptor;
  RuntimeTensorDescriptor rhs_descriptor;
  const float* lhs_data = nullptr;
  const float* rhs_data = nullptr;
  OrtStatus* status = GetKernelInputData(info, kernel_context, 0, &lhs_descriptor, &lhs_data);
  if (status != nullptr) return status;
  status = GetKernelInputData(info, kernel_context, 1, &rhs_descriptor, &rhs_data);
  if (status != nullptr) return status;
  status = ValidateSameRuntimeShape(info, "input0", lhs_descriptor, "input1", rhs_descriptor);
  if (status != nullptr) return status;

  float* output_data = nullptr;
  status = CreateKernelOutput(info, kernel_context, lhs_descriptor, &output_data);
  if (status != nullptr) return status;

  for (size_t index = 0; index < lhs_descriptor.element_count; ++index) {
    const float sum = lhs_data[index] + rhs_data[index];
    output_data[index] = sum < 0.0f ? 0.0f : sum;
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
    case CompiledOpKind::kMatMul:
      return ExecuteMatMul(info, kernel_context);
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
  g_claimed_matmul_nodes.store(0, std::memory_order_relaxed);
  g_compile_calls.store(0, std::memory_order_relaxed);
  g_compiled_identity_groups.store(0, std::memory_order_relaxed);
  g_compiled_add_groups.store(0, std::memory_order_relaxed);
  g_compiled_relu_groups.store(0, std::memory_order_relaxed);
  g_compiled_matmul_groups.store(0, std::memory_order_relaxed);
  g_compiled_add_relu_groups.store(0, std::memory_order_relaxed);
  g_create_state_calls.store(0, std::memory_order_relaxed);
  g_compute_calls.store(0, std::memory_order_relaxed);
  g_compute_identity_calls.store(0, std::memory_order_relaxed);
  g_compute_add_calls.store(0, std::memory_order_relaxed);
  g_compute_relu_calls.store(0, std::memory_order_relaxed);
  g_compute_matmul_calls.store(0, std::memory_order_relaxed);
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
      .claimed_matmul_nodes = g_claimed_matmul_nodes.load(std::memory_order_relaxed),
      .compile_calls = g_compile_calls.load(std::memory_order_relaxed),
      .compiled_identity_groups = g_compiled_identity_groups.load(std::memory_order_relaxed),
      .compiled_add_groups = g_compiled_add_groups.load(std::memory_order_relaxed),
      .compiled_relu_groups = g_compiled_relu_groups.load(std::memory_order_relaxed),
      .compiled_matmul_groups = g_compiled_matmul_groups.load(std::memory_order_relaxed),
      .compiled_add_relu_groups = g_compiled_add_relu_groups.load(std::memory_order_relaxed),
      .create_state_calls = g_create_state_calls.load(std::memory_order_relaxed),
      .compute_calls = g_compute_calls.load(std::memory_order_relaxed),
      .compute_identity_calls = g_compute_identity_calls.load(std::memory_order_relaxed),
      .compute_add_calls = g_compute_add_calls.load(std::memory_order_relaxed),
      .compute_relu_calls = g_compute_relu_calls.load(std::memory_order_relaxed),
      .compute_matmul_calls = g_compute_matmul_calls.load(std::memory_order_relaxed),
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

    if (node_spec.kind == CompiledOpKind::kAdd) {
      SupportedNodeSpec relu_spec;
      bool found_relu = false;
      status = FindSupportedReluConsumer(self.bindings_.api, node_spec, claimed_nodes, &relu_spec, &found_relu);
      if (status != nullptr) return status;
      if (found_relu) {
        graph_spec.kind = CompiledOpKind::kAddRelu;
        graph_spec.default_node_name = "doe_add_relu";
        graph_spec.fused_nodes = {node, relu_spec.node};
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
          "Doe ORT plugin EP was asked to compile a graph outside its narrow float32 Identity/Add/Relu/MatMul slice.");
    }

    auto info = std::make_unique<CompiledNodeComputeInfo>();
    info->base.ort_version_supported = ORT_API_VERSION;
    info->base.CreateState = &CreateStateImpl;
    info->base.Compute = &ComputeImpl;
    info->base.ReleaseState = &ReleaseStateImpl;
    info->bindings = self.bindings_;
    info->op_kind = graph_spec.kind;

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
