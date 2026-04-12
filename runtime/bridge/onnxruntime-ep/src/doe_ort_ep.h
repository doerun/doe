#pragma once

#include "doe_ort_ep_api_version.h"
#include "doe_ort_ep_factory.h"

#include <string>

namespace doe::ort_ep {

class DoeOrtEp final : public OrtEp {
 public:
  DoeOrtEp(std::string registration_name, ApiBindings bindings);

 private:
  static DoeOrtEp& Self(OrtEp* this_ptr);
  static const DoeOrtEp& Self(const OrtEp* this_ptr);

  static const char* ORT_API_CALL GetNameImpl(const OrtEp* this_ptr) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL GetCapabilityImpl(
      OrtEp* this_ptr,
      const OrtGraph* graph,
      OrtEpGraphSupportInfo* graph_support_info) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL CompileImpl(
      OrtEp* this_ptr,
      const OrtGraph** graphs,
      const OrtNode** fused_nodes,
      size_t count,
      OrtNodeComputeInfo** node_compute_infos,
      OrtNode** ep_context_nodes) NO_EXCEPTION;
  static void ORT_API_CALL ReleaseNodeComputeInfosImpl(
      OrtEp* this_ptr,
      OrtNodeComputeInfo** node_compute_infos,
      size_t num_node_compute_infos) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL GetPreferredDataLayoutImpl(
      OrtEp* this_ptr,
      OrtEpDataLayout* preferred_data_layout) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL OnRunStartImpl(
      OrtEp* this_ptr,
      const OrtRunOptions* run_options) NO_EXCEPTION;
  static OrtStatus* ORT_API_CALL OnRunEndImpl(
      OrtEp* this_ptr,
      const OrtRunOptions* run_options,
      bool sync_stream) NO_EXCEPTION;
  static const char* ORT_API_CALL GetCompiledModelCompatibilityInfoImpl(
      OrtEp* this_ptr,
      const OrtGraph* graph) NO_EXCEPTION;

  std::string registration_name_;
  ApiBindings bindings_;
};

}  // namespace doe::ort_ep
