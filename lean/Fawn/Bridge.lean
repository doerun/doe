import Fawn.Model
import Fawn.Runtime

-- A single-source Lean gate check for a selected quirk.
def SafetyProofOverride := SafetyClass → Option ProofLevel

def defaultSafetyProofOverride : SafetyProofOverride := fun _ => Option.none

def proofRank : ProofLevel → Nat
  | .proven => 3
  | .guarded => 2
  | .rejected => 1

def maxProofLevel (lhs : ProofLevel) (rhs : ProofLevel) : ProofLevel :=
  if proofRank lhs >= proofRank rhs then lhs else rhs

def requiredProofFromVerificationMode (mode : VerificationMode) : Option ProofLevel :=
  match mode with
  | .lean_required => some .proven
  | _ => none

def requiredProofFromSafetyClass (safety : SafetyClass) (override : SafetyProofOverride) : Option ProofLevel :=
  override safety

def requiredProofFromPolicy
    (mode : VerificationMode)
    (safety : SafetyClass)
    (safetyOverride : SafetyProofOverride := defaultSafetyProofOverride)
    : Option ProofLevel :=
  match requiredProofFromVerificationMode mode, requiredProofFromSafetyClass safety safetyOverride with
  | none, none => none
  | some level, none => some level
  | none, some level => some level
  | some left, some right => some (maxProofLevel left right)

def proofMeetsRequirement (actual : ProofLevel) (required : Option ProofLevel) : Bool :=
  match required with
  | none => true
  | some required_level => proofRank actual >= proofRank required_level

def isBlocking (actual : ProofLevel) (required : Option ProofLevel) : Bool :=
  match required with
  | none => false
  | some required_level => !proofMeetsRequirement actual (some required_level)

structure QuirkLeanObligation where
  quirkId : String
  requiresLean : Bool
  requiredProofLevel : Option ProofLevel
  actualProofLevel : ProofLevel
  isBlocking : Bool
  isAdvisory : Bool
  requiredByVerificationMode : Bool
  requiredBySafetyOverride : Bool
  deriving Repr

def fromQuirk
    (quirk : Runtime.Quirk)
    (safetyOverride : SafetyProofOverride := defaultSafetyProofOverride)
    : QuirkLeanObligation :=
  let required_level := requiredProofFromPolicy
    quirk.verificationMode
    quirk.safetyClass
    safetyOverride
  let required_by_verification_mode := requiredProofFromVerificationMode quirk.verificationMode |> Option.isSome
  let required_by_safety_override := requiredProofFromSafetyClass quirk.safetyClass safetyOverride |> Option.isSome
  let blocked := isBlocking quirk.proofLevel required_level
  let requires_lean := Option.isSome required_level
  let advisory :=
    requires_lean &&
    !blocked &&
    !required_by_verification_mode &&
    required_by_safety_override

  { quirkId := quirk.id
    requiresLean := requires_lean
    requiredProofLevel := required_level
    actualProofLevel := quirk.proofLevel
    isBlocking := blocked
    isAdvisory := advisory
    requiredByVerificationMode := required_by_verification_mode
    requiredBySafetyOverride := required_by_safety_override
  }

def fromDispatchResult
    (result : Runtime.DispatchResult)
    (safetyOverride : SafetyProofOverride := defaultSafetyProofOverride)
    : Option QuirkLeanObligation :=
  match result.quirk with
  | none => none
  | some quirk => some (fromQuirk quirk safetyOverride)

def fromDispatchDecision
    (result : Runtime.DispatchDecision)
    (safetyOverride : SafetyProofOverride := defaultSafetyProofOverride)
    : Option QuirkLeanObligation :=
  match result.quirk with
  | none => none
  | some quirk => some (fromQuirk quirk safetyOverride)

def obligationsFromDispatches
    (results : List Runtime.DispatchResult)
    (safetyOverride : SafetyProofOverride := defaultSafetyProofOverride)
    : List QuirkLeanObligation :=
  match results with
  | [] => []
  | head :: tail =>
    match fromDispatchResult head safetyOverride with
    | none => obligationsFromDispatches tail safetyOverride
    | some obligation => obligation :: obligationsFromDispatches tail safetyOverride

def obligationsFromDispatchDecisions
    (results : List Runtime.DispatchDecision)
    (safetyOverride : SafetyProofOverride := defaultSafetyProofOverride)
    : List QuirkLeanObligation :=
  match results with
  | [] => []
  | head :: tail =>
    match fromDispatchDecision head safetyOverride with
    | none => obligationsFromDispatchDecisions tail safetyOverride
    | some obligation => obligation :: obligationsFromDispatchDecisions tail safetyOverride

def blockingObligations
    (results : List Runtime.DispatchResult)
    (safetyOverride : SafetyProofOverride := defaultSafetyProofOverride)
    : List QuirkLeanObligation :=
  obligationsFromDispatches results safetyOverride |>.filter (fun item => item.isBlocking)

def blockingObligationsFromDecisions
    (results : List Runtime.DispatchDecision)
    (safetyOverride : SafetyProofOverride := defaultSafetyProofOverride)
    : List QuirkLeanObligation :=
  obligationsFromDispatchDecisions results safetyOverride |>.filter (fun item => item.isBlocking)
