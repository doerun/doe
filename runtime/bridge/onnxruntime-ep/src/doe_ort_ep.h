#pragma once

#include "doe_ort_ep_api_version.h"
#include "doe_ort_ep_factory.h"

#include <cstdint>
#include <string>

namespace doe::ort_ep {

struct DoeOrtEpDebugCounters {
  uint64_t get_capability_calls = 0;
  uint64_t claimed_nodes = 0;
  uint64_t claimed_identity_nodes = 0;
  uint64_t claimed_add_nodes = 0;
  uint64_t claimed_relu_nodes = 0;
  uint64_t claimed_matmul_nodes = 0;
  uint64_t claimed_gemm_nodes = 0;
  uint64_t compile_calls = 0;
  uint64_t compiled_identity_groups = 0;
  uint64_t compiled_add_groups = 0;
  uint64_t compiled_relu_groups = 0;
  uint64_t compiled_matmul_groups = 0;
  uint64_t compiled_gemm_groups = 0;
  uint64_t compiled_gemm_relu_gemm_groups = 0;
  uint64_t compiled_matmul_add_groups = 0;
  uint64_t compiled_matmul_add_relu_groups = 0;
  uint64_t compiled_add_relu_groups = 0;
  uint64_t create_state_calls = 0;
  uint64_t compute_calls = 0;
  uint64_t compute_identity_calls = 0;
  uint64_t compute_add_calls = 0;
  uint64_t compute_relu_calls = 0;
  uint64_t compute_matmul_calls = 0;
  uint64_t compute_gemm_calls = 0;
  uint64_t compute_gemm_relu_gemm_calls = 0;
  uint64_t compute_matmul_add_calls = 0;
  uint64_t compute_matmul_add_relu_calls = 0;
  uint64_t compute_add_relu_calls = 0;
  uint64_t release_state_calls = 0;
};

void ResetDebugCounters() NO_EXCEPTION;
DoeOrtEpDebugCounters SnapshotDebugCounters() NO_EXCEPTION;

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
