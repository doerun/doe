import Fawn.Generated.ComparabilityContract

theorem comparableFromObligations_eq_noFailed (items : List ComparabilityObligation) :
    comparableFromObligations items = (failedBlockingObligations items).isEmpty := by
  rfl

theorem comparableFromFacts_eq_noFailed (facts : ComparabilityFacts) :
    comparableFromFacts facts = (failedBlockingObligations (obligationsFromFacts facts)).isEmpty := by
  rfl

theorem comparableFromObligations_true_iff_failedBlockingNil
    (items : List ComparabilityObligation) :
    comparableFromObligations items = true ↔ failedBlockingObligations items = [] := by
  constructor
  · intro h
    have hEmpty : (failedBlockingObligations items).isEmpty = true := by
      simpa [comparableFromObligations] using h
    simpa [List.isEmpty_eq_true] using hEmpty
  · intro h
    have hEmpty : (failedBlockingObligations items).isEmpty = true := by
      simpa [List.isEmpty_eq_true] using h
    simpa [comparableFromObligations] using hEmpty

theorem comparableFromObligations_false_iff_failedBlockingNonEmpty
    (items : List ComparabilityObligation) :
    comparableFromObligations items = false ↔ failedBlockingObligations items ≠ [] := by
  constructor
  · intro h
    have hEmpty : (failedBlockingObligations items).isEmpty = false := by
      simpa [comparableFromObligations] using h
    simpa [List.isEmpty_eq_false] using hEmpty
  · intro h
    have hEmpty : (failedBlockingObligations items).isEmpty = false := by
      simpa [List.isEmpty_eq_false] using h
    simpa [comparableFromObligations] using hEmpty

theorem comparableFromFacts_true_iff_failedBlockingNil
    (facts : ComparabilityFacts) :
    comparableFromFacts facts = true ↔
      failedBlockingObligations (obligationsFromFacts facts) = [] := by
  simpa [comparableFromFacts] using
    comparableFromObligations_true_iff_failedBlockingNil (obligationsFromFacts facts)

theorem comparableFromFacts_false_iff_failedBlockingNonEmpty
    (facts : ComparabilityFacts) :
    comparableFromFacts facts = false ↔
      failedBlockingObligations (obligationsFromFacts facts) ≠ [] := by
  simpa [comparableFromFacts] using
    comparableFromObligations_false_iff_failedBlockingNonEmpty (obligationsFromFacts facts)
