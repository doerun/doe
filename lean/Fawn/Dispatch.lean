import Fawn.Model

inductive CommandKind where
  | upload
  | copyBuffer
  | barrier
  | dispatch
  | kernelDispatch
  deriving Repr, DecidableEq

structure Quirk where
  id : String
  scope : Scope
  vendor : String
  api : Api
  verificationMode : VerificationMode
  safetyClass : SafetyClass

def supportsScope (scope : Scope) (command : CommandKind) : Bool :=
  match scope with
  | .alignment => command = CommandKind.upload ∨ command = CommandKind.copyBuffer
  | .layout => command = CommandKind.dispatch ∨ command = CommandKind.copyBuffer ∨ command = CommandKind.kernelDispatch
  | .barrier => command = CommandKind.barrier ∨ command = CommandKind.dispatch ∨ command = CommandKind.kernelDispatch
  | .driver_toggle => True
  | .memory => command = CommandKind.copyBuffer ∨ command = CommandKind.upload

def supports : Quirk → CommandKind → Bool
  | q, cmd => supportsScope q.scope cmd

def requiresObligation (q : Quirk) : Bool :=
  match q.verificationMode with
  | .lean_required => true
  | _ => false

theorem toggleAlwaysSupported (q : Quirk) :
    q.scope = .driver_toggle → ∀ cmd : CommandKind, supports q cmd := by
  intro h cmd
  simp [supports, supportsScope, h]

theorem strongerSafetyRaisesProofDemand :
    ∀ q : Quirk, q.safetyClass = .critical → requiredProofClass q.safetyClass = ProofLevel.proven := by
  intro q h
  simp [h, requiredProofClass]
