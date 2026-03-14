-- Re-export from Fawn.Core.Model for backward compatibility.
-- Canonical source: Fawn/Core/Model.lean
import Fawn.Core.Model
export Api (vulkan metal d3d12 webgpu)
export Scope (alignment barrier layout driver_toggle memory)
export SafetyClass (low moderate high critical)
export VerificationMode (guard_only lean_preferred lean_required)
export ProofLevel (proven guarded rejected)
export CommandKind (
  upload
  copyBufferToTexture
  barrier
  dispatch
  dispatchIndirect
  kernelDispatch
  renderDraw
  drawIndirect
  drawIndexedIndirect
  renderPass
  samplerCreate
  samplerDestroy
  textureWrite
  textureQuery
  textureDestroy
  surfaceCreate
  surfaceCapabilities
  surfaceConfigure
  surfaceAcquire
  surfacePresent
  surfaceUnconfigure
  surfaceRelease
  asyncDiagnostics
  mapAsync
)
export ToggleEffect (behavioral informational unhandled)
export ActionKind (use_temporary_buffer use_temporary_render_texture toggle no_op)
