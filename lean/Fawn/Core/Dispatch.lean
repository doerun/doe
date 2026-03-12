import Fawn.Core.Runtime

-- Dispatch-level theorems proven against the Runtime model.
-- These operate on the same CommandKind, Quirk, and supportsScope
-- used by Bridge.lean and the Zig runtime.

theorem toggleAlwaysSupported (q : Quirk) :
    q.scope = .driver_toggle → ∀ cmd : CommandKind, supportsQuirk q cmd := by
  intro h cmd
  simp [supportsQuirk, supportsScope, h]

theorem strongerSafetyRaisesProofDemand :
    ∀ q : Quirk, q.safetyClass = .critical → requiredProofClass q.safetyClass = ProofLevel.proven := by
  intro q h
  simp [h, requiredProofClass]

theorem noOpActionIdentity : ActionKind.no_op.isIdentity = true := by
  rfl

theorem informationalToggleIdentity : (ActionKind.toggle .informational).isIdentity = true := by
  rfl

theorem unhandledToggleIdentity : (ActionKind.toggle .unhandled).isIdentity = true := by
  rfl

theorem behavioralToggleNotIdentity : (ActionKind.toggle .behavioral).isIdentity = false := by
  rfl

theorem identityActionComplete :
    ∀ a : ActionKind, a.isIdentity = true ↔
      (a = .no_op ∨ a = .toggle .informational ∨ a = .toggle .unhandled) := by
  intro a
  cases a with
  | use_temporary_buffer => simp [ActionKind.isIdentity]
  | use_temporary_render_texture => simp [ActionKind.isIdentity]
  | toggle e => cases e <;> simp [ActionKind.isIdentity]
  | no_op => simp [ActionKind.isIdentity]
