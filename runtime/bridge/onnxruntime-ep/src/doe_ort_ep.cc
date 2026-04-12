#include "doe_ort_ep.h"

#include <cstddef>
#include <string>
#include <utility>

namespace doe::ort_ep {

namespace {

constexpr const char* kCompatibilityInfo = "doe-ort-noop-ep-v0";

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

OrtStatus* ORT_API_CALL DoeOrtEp::GetCapabilityImpl(
    OrtEp* this_ptr,
    const OrtGraph* graph,
    OrtEpGraphSupportInfo* graph_support_info) NO_EXCEPTION {
  (void)this_ptr;
  (void)graph;
  (void)graph_support_info;
  return nullptr;
}

OrtStatus* ORT_API_CALL DoeOrtEp::CompileImpl(
    OrtEp* this_ptr,
    const OrtGraph** graphs,
    const OrtNode** fused_nodes,
    const size_t count,
    OrtNodeComputeInfo** node_compute_infos,
    OrtNode** ep_context_nodes) NO_EXCEPTION {
  (void)graphs;
  (void)fused_nodes;
  if (count != 0) {
    return MakeStatus(
        Self(this_ptr).bindings_.api,
        ORT_NOT_IMPLEMENTED,
        "Doe ORT plugin EP currently creates a real OrtEp instance but does not compile or claim graph nodes yet.");
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
  return nullptr;
}

void ORT_API_CALL DoeOrtEp::ReleaseNodeComputeInfosImpl(
    OrtEp* this_ptr,
    OrtNodeComputeInfo** node_compute_infos,
    const size_t num_node_compute_infos) NO_EXCEPTION {
  (void)this_ptr;
  (void)node_compute_infos;
  (void)num_node_compute_infos;
}

OrtStatus* ORT_API_CALL DoeOrtEp::GetPreferredDataLayoutImpl(
    OrtEp* this_ptr,
    OrtEpDataLayout* preferred_data_layout) NO_EXCEPTION {
  if (preferred_data_layout == nullptr) {
    return MakeStatus(Self(this_ptr).bindings_.api, ORT_INVALID_ARGUMENT, "Doe ORT plugin EP requires a preferred_data_layout output pointer.");
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
