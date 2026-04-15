-- Doe/Full/WorkloadGeometry.lean
--
-- Structural equivalence of workload geometry (dispatch extent and buffer bytes).
-- Feeds the comparability execution-shape obligation via withExecutionShapeGeometry.

import Doe.Full.Comparability

structure DispatchGeometry where
  x : Nat
  y : Nat
  z : Nat
  deriving Repr, DecidableEq

structure WorkloadGeometry where
  bufferBytes : Nat
  dispatch : DispatchGeometry
  deriving Repr, DecidableEq

def structurallyEquivalentGeometry (left right : WorkloadGeometry) : Bool :=
  left.bufferBytes == right.bufferBytes &&
    left.dispatch.x == right.dispatch.x &&
    left.dispatch.y == right.dispatch.y &&
    left.dispatch.z == right.dispatch.z

def withExecutionShapeGeometry
    (facts : ComparabilityFacts)
    (left right : WorkloadGeometry)
    : ComparabilityFacts :=
  { facts with
    executionShapeMatchApplies := true
    baselineComparisonExecutionShapeMatch := structurallyEquivalentGeometry left right
  }

-- Classification: lean_verified (quantified over unbounded Nat record fields).
theorem structurallyEquivalentGeometry_refl (geometry : WorkloadGeometry) :
    structurallyEquivalentGeometry geometry geometry = true := by
  cases geometry with
  | mk bufferBytes dispatch =>
      cases dispatch with
      | mk x y z =>
          simp [structurallyEquivalentGeometry]

-- Classification: lean_verified (quantified over unbounded Nat component values).
theorem structurallyEquivalentGeometry_forall_components
    (bufferBytes dispatchX dispatchY dispatchZ : Nat) :
    let geometry : WorkloadGeometry :=
      { bufferBytes := bufferBytes
        dispatch := { x := dispatchX, y := dispatchY, z := dispatchZ } }
    structurallyEquivalentGeometry geometry geometry = true := by
  simp [structurallyEquivalentGeometry]

-- Classification: lean_verified (quantified over unbounded ComparabilityFacts + Nat fields).
theorem equalGeometrySetsExecutionShapeFacts
    (facts : ComparabilityFacts)
    (bufferBytes dispatchX dispatchY dispatchZ : Nat) :
    let geometry : WorkloadGeometry :=
      { bufferBytes := bufferBytes
        dispatch := { x := dispatchX, y := dispatchY, z := dispatchZ } }
    (withExecutionShapeGeometry facts geometry geometry).executionShapeMatchApplies = true ∧
      (withExecutionShapeGeometry facts geometry geometry).baselineComparisonExecutionShapeMatch = true := by
  simp [withExecutionShapeGeometry, structurallyEquivalentGeometry]
