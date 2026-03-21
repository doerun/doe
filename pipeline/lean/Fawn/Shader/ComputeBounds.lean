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
  have h_local :
      workgroup_id * workgroup_size + local_id <
      workgroup_id * workgroup_size + workgroup_size := by
    exact Nat.add_lt_add_left h_lid (workgroup_id * workgroup_size)
  have h_step :
      workgroup_id * workgroup_size + workgroup_size =
      (workgroup_id + 1) * workgroup_size := by
    simpa using (Nat.succ_mul workgroup_id workgroup_size).symm
  have h_wid_mul :
      (workgroup_id + 1) * workgroup_size ≤
      num_workgroups * workgroup_size := by
    exact Nat.mul_le_mul_right workgroup_size (Nat.succ_le_of_lt h_wid)
  have h_fit_comm :
      num_workgroups * workgroup_size ≤ array_length := by
    simpa [Nat.mul_comm] using h_fit
  calc
    workgroup_id * workgroup_size + local_id <
        workgroup_id * workgroup_size + workgroup_size := h_local
    _ = (workgroup_id + 1) * workgroup_size := h_step
    _ ≤ num_workgroups * workgroup_size := h_wid_mul
    _ ≤ array_length := h_fit_comm

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

/-- Texture coordinate analogue of `gid_2d_inbounds`. When the dispatched 2D
    grid fits the texture extents, `global_invocation_id.xy` is already
    componentwise in bounds and texture coordinate clamping is redundant. -/
theorem gid_texture_coords_2d_inbounds_when_dispatch_fits
    (wid_x lid_x ws_x nwg_x width : Nat)
    (wid_y lid_y ws_y nwg_y height : Nat)
    (h_wid_x : wid_x < nwg_x) (h_lid_x : lid_x < ws_x)
    (h_wid_y : wid_y < nwg_y) (h_lid_y : lid_y < ws_y)
    (h_fit_x : ws_x * nwg_x ≤ width)
    (h_fit_y : ws_y * nwg_y ≤ height) :
    globalInvocationId wid_x lid_x ws_x < width ∧
    globalInvocationId wid_y lid_y ws_y < height :=
  gid_2d_inbounds wid_x lid_x ws_x nwg_x width wid_y lid_y ws_y nwg_y height
    h_wid_x h_lid_x h_wid_y h_lid_y h_fit_x h_fit_y

/-- Flat index from 2D global invocation ID. Common pattern:
    buf[gid.y * width + gid.x] where buf has width * height elements. -/
def flatIndex2D (gid_x gid_y width : Nat) : Nat :=
  gid_y * width + gid_x

/-- Flat 2D index is in bounds when both components are bounded and
    the total size is width * height. -/
theorem flat_index_2d_inbounds
    (gid_x gid_y width height : Nat)
    (h_x : gid_x < width)
    (h_y : gid_y < height) :
    flatIndex2D gid_x gid_y width < width * height := by
  unfold flatIndex2D
  have h_row :
      gid_y * width + gid_x < gid_y * width + width := by
    exact Nat.add_lt_add_left h_x (gid_y * width)
  have h_step :
      gid_y * width + width = (gid_y + 1) * width := by
    simpa using (Nat.succ_mul gid_y width).symm
  have h_height :
      (gid_y + 1) * width ≤ height * width := by
    exact Nat.mul_le_mul_right width (Nat.succ_le_of_lt h_y)
  calc
    gid_y * width + gid_x < gid_y * width + width := h_row
    _ = (gid_y + 1) * width := h_step
    _ ≤ height * width := h_height
    _ = width * height := by simp [Nat.mul_comm]

/-- Early-return texture guard for 2D gid coordinates. If the shader exits when
    either coordinate is out of range, any surviving execution has both
    coordinates strictly below the texture dimensions. This is the proof-backed
    bridge for eliding texture coordinate clamp insertion. -/
theorem guarded_gid_texture_coords_2d_inbounds
    (gid_x gid_y width height : Nat)
    (h_guard : ¬ (gid_x ≥ width ∨ gid_y ≥ height)) :
    gid_x < width ∧ gid_y < height := by
  omega

/-- 3D extension of the early-return texture guard theorem. -/
theorem guarded_gid_texture_coords_3d_inbounds
    (gid_x gid_y gid_z width height depth : Nat)
    (h_guard : ¬ (gid_x ≥ width ∨ gid_y ≥ height ∨ gid_z ≥ depth)) :
    gid_x < width ∧ gid_y < height ∧ gid_z < depth := by
  omega

/-- 3D dispatch-fit version of the texture coordinate proof. -/
theorem gid_texture_coords_3d_inbounds_when_dispatch_fits
    (wid_x lid_x ws_x nwg_x width : Nat)
    (wid_y lid_y ws_y nwg_y height : Nat)
    (wid_z lid_z ws_z nwg_z depth : Nat)
    (h_wid_x : wid_x < nwg_x) (h_lid_x : lid_x < ws_x)
    (h_wid_y : wid_y < nwg_y) (h_lid_y : lid_y < ws_y)
    (h_wid_z : wid_z < nwg_z) (h_lid_z : lid_z < ws_z)
    (h_fit_x : ws_x * nwg_x ≤ width)
    (h_fit_y : ws_y * nwg_y ≤ height)
    (h_fit_z : ws_z * nwg_z ≤ depth) :
    globalInvocationId wid_x lid_x ws_x < width ∧
    globalInvocationId wid_y lid_y ws_y < height ∧
    globalInvocationId wid_z lid_z ws_z < depth := by
  refine ⟨?_, ?_, ?_⟩
  exact gid_component_lt_total wid_x lid_x ws_x nwg_x width h_wid_x h_lid_x h_fit_x
  exact gid_component_lt_total wid_y lid_y ws_y nwg_y height h_wid_y h_lid_y h_fit_y
  exact gid_component_lt_total wid_z lid_z ws_z nwg_z depth h_wid_z h_lid_z h_fit_z
