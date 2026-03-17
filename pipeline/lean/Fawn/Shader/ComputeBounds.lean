-- Shader compute bounds safety theorems.
-- Mirrors: runtime/zig/src/doe_wgsl/ir_transform_robustness.zig
--
-- Proves that global_invocation_id components are strictly less than
-- array_length when the dispatch dimensions fit. This lets the robustness
-- pass skip the min() clamp for index patterns that match proven conditions.
--
-- Layer 1 (Zig): clamp ALL indices unconditionally (ir_transform_robustness.zig).
-- Layer 2 (Lean → Zig): this module proves conditions under which the clamp is
-- provably unnecessary, allowing the Zig runtime to elide it.
--
-- Integration: build.zig reads proven-conditions.json (-Dlean-verified=true),
-- lean_proof.zig validates at comptime, ir_transform_robustness.zig consults
-- the proof status to skip clamping for matched patterns.

/-- Global invocation ID for a single dimension.
    Mirrors WGSL: global_invocation_id.x = workgroup_id.x * workgroup_size.x + local_invocation_id.x -/
def globalInvocationId (workgroup_id local_id workgroup_size : Nat) : Nat :=
  workgroup_id * workgroup_size + local_id

/-- Core single-dimension bound: if the dispatch grid fits in the array,
    every global invocation ID is strictly less than the array length.

    Preconditions (enforced at dispatch time by host-side check):
    - workgroup_id < num_workgroups  (GPU hardware guarantee)
    - local_id < workgroup_size      (GPU hardware guarantee)
    - workgroup_size * num_workgroups ≤ array_length  (host-side precondition)

    This is `lean_verified`: it quantifies over arbitrary Nat values and
    cannot be replicated by comptime enumeration. -/
theorem gid_component_lt_total
    (workgroup_id local_id workgroup_size num_workgroups array_length : Nat)
    (h_wid : workgroup_id < num_workgroups)
    (h_lid : local_id < workgroup_size)
    (h_fit : workgroup_size * num_workgroups ≤ array_length) :
    globalInvocationId workgroup_id local_id workgroup_size < array_length := by
  unfold globalInvocationId
  -- workgroup_id * workgroup_size + local_id
  --   < workgroup_id * workgroup_size + workgroup_size   (from h_lid)
  --   = (workgroup_id + 1) * workgroup_size
  --   ≤ num_workgroups * workgroup_size                  (from h_wid + 1 ≤ num_workgroups)
  --   = workgroup_size * num_workgroups                  (commutativity)
  --   ≤ array_length                                     (from h_fit)
  omega

/-- 1D dispatch convenience wrapper. When a compute shader accesses
    buf[global_invocation_id.x] and the host ensures
    workgroup_size.x * num_workgroups.x ≤ buf.length,
    the access is proven in-bounds and the min() clamp can be elided.

    This is the theorem that ir_transform_robustness.zig pattern-matches
    against. The pattern recognizer checks:
    1. Index expression uses global_invocation_id.x
    2. Base is a storage buffer with known binding
    3. Dispatch precondition is registered for that binding -/
theorem gid_inbounds_when_dispatch_fits
    (workgroup_id_x local_id_x workgroup_size_x num_workgroups_x array_length : Nat)
    (h_wid : workgroup_id_x < num_workgroups_x)
    (h_lid : local_id_x < workgroup_size_x)
    (h_fit : workgroup_size_x * num_workgroups_x ≤ array_length) :
    globalInvocationId workgroup_id_x local_id_x workgroup_size_x < array_length :=
  gid_component_lt_total workgroup_id_x local_id_x workgroup_size_x num_workgroups_x array_length
    h_wid h_lid h_fit

/-- The clamp min(gid, len-1) is a no-op when gid < len.
    This connects the proof to the transform: if the condition holds,
    min(gid, len-1) = gid, so the injected code has no runtime effect
    and can be elided entirely. -/
theorem clamp_noop_when_inbounds
    (gid len : Nat)
    (h_pos : 0 < len)
    (h_bound : gid < len) :
    min gid (len - 1) = gid := by
  omega

/-- Two-dimensional extension. For 2D compute dispatches accessing
    a 2D array flattened as buf[gid.y * width + gid.x], both components
    must be independently bounded. -/
theorem gid_2d_inbounds
    (wid_x lid_x ws_x nwg_x width : Nat)
    (wid_y lid_y ws_y nwg_y height : Nat)
    (h_wid_x : wid_x < nwg_x) (h_lid_x : lid_x < ws_x)
    (h_wid_y : wid_y < nwg_y) (h_lid_y : lid_y < ws_y)
    (h_fit_x : ws_x * nwg_x ≤ width)
    (h_fit_y : ws_y * nwg_y ≤ height) :
    globalInvocationId wid_x lid_x ws_x < width ∧
    globalInvocationId wid_y lid_y ws_y < height :=
  ⟨gid_component_lt_total wid_x lid_x ws_x nwg_x width h_wid_x h_lid_x h_fit_x,
   gid_component_lt_total wid_y lid_y ws_y nwg_y height h_wid_y h_lid_y h_fit_y⟩

/-- Flat index from 2D global invocation ID. Common pattern:
    buf[gid.y * width + gid.x] where buf has width * height elements. -/
def flatIndex2D (gid_x gid_y width : Nat) : Nat :=
  gid_y * width + gid_x

/-- Flat 2D index is in bounds when both components are bounded and
    the total size is width * height. -/
theorem flat_index_2d_inbounds
    (gid_x gid_y width height : Nat)
    (h_x : gid_x < width)
    (h_y : gid_y < height)
    (h_pos : 0 < width) :
    flatIndex2D gid_x gid_y width < width * height := by
  unfold flatIndex2D
  -- gid_y * width + gid_x < height * width
  -- because gid_y < height and gid_x < width
  omega
