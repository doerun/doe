structure ChoiceCandidate where
  token : Nat
  priority : Nat
  deriving Repr, DecidableEq

def stableTokenChoose : List Nat → Option Nat
  | [] => none
  | token :: rest =>
      match stableTokenChoose rest with
      | none => some token
      | some chosen => if token <= chosen then some token else some chosen

theorem stableTokenChoose_mem_tiedMaxIndices :
    ∀ indices chosen, stableTokenChoose indices = some chosen → chosen ∈ indices := by
  intro indices
  induction indices with
  | nil =>
      intro chosen h
      simp [stableTokenChoose] at h
  | cons token rest ih =>
      intro chosen h
      cases hrest : stableTokenChoose rest with
      | none =>
          simp [stableTokenChoose, hrest] at h
          cases h
          simp
      | some restChosen =>
          by_cases hle : token <= restChosen
          · simp [stableTokenChoose, hrest, hle] at h
            cases h
            simp
          · simp [stableTokenChoose, hrest, hle] at h
            have hmem : restChosen ∈ rest := ih restChosen hrest
            cases h
            simp [hmem]

theorem stableTokenChoose_le_all_tiedMaxIndices :
    ∀ indices chosen,
      stableTokenChoose indices = some chosen →
      ∀ other, other ∈ indices → chosen <= other := by
  intro indices
  induction indices with
  | nil =>
      intro chosen h
      simp [stableTokenChoose] at h
  | cons token rest ih =>
      intro chosen h other hmem
      cases hrest : stableTokenChoose rest with
      | none =>
          simp [stableTokenChoose, hrest] at h
          cases h
          cases rest with
          | nil =>
              simp at hmem
              simp [hmem]
          | cons restHead restTail =>
              have hImpossible : False := by
                cases htail : stableTokenChoose restTail with
                | none =>
                    simp [stableTokenChoose, htail] at hrest
                | some val =>
                    by_cases hcmp : restHead <= val
                    · simp [stableTokenChoose, htail, hcmp] at hrest
                    · simp [stableTokenChoose, htail, hcmp] at hrest
              exact False.elim hImpossible
      | some restChosen =>
          by_cases hle : token <= restChosen
          · simp [stableTokenChoose, hrest, hle] at h
            cases h
            simp at hmem
            cases hmem with
            | inl hEq =>
                simp [hEq]
            | inr hInRest =>
                have hrestLe : restChosen <= other := ih restChosen hrest other hInRest
                exact Nat.le_trans hle hrestLe
          · simp [stableTokenChoose, hrest, hle] at h
            cases h
            simp at hmem
            cases hmem with
            | inl hEq =>
                simpa [hEq] using Nat.le_of_lt (Nat.lt_of_not_ge hle)
            | inr hInRest =>
                exact ih _ hrest other hInRest

def exactMaxTieTriggered (ambiguousCandidateCount : Nat) : Bool :=
  decide (2 <= ambiguousCandidateCount)

theorem exactMaxTieTriggered_iff_two_or_more_candidates (ambiguousCandidateCount : Nat) :
    exactMaxTieTriggered ambiguousCandidateCount = true ↔ 2 <= ambiguousCandidateCount := by
  simp [exactMaxTieTriggered]

def candidateMarginBandTriggered (gap epsilon : Nat) : Bool :=
  decide (gap <= epsilon)

theorem candidateMarginBandTriggered_iff_gap_within_epsilon (gap epsilon : Nat) :
    candidateMarginBandTriggered gap epsilon = true ↔ gap <= epsilon := by
  simp [candidateMarginBandTriggered]

def fixedPriorityLexPreferred (lhs rhs : ChoiceCandidate) : Prop :=
  lhs.priority < rhs.priority ∨ (lhs.priority = rhs.priority ∧ lhs.token <= rhs.token)

def fixedPriorityBetter (lhs rhs : ChoiceCandidate) : Bool :=
  if lhs.priority < rhs.priority then
    true
  else if rhs.priority < lhs.priority then
    false
  else
    decide (lhs.token <= rhs.token)

theorem fixedPriorityBetter_true_implies_lexicographic_preference
    (lhs rhs : ChoiceCandidate)
    (h : fixedPriorityBetter lhs rhs = true) :
    fixedPriorityLexPreferred lhs rhs := by
  by_cases hprio : lhs.priority < rhs.priority
  · simp [fixedPriorityBetter, hprio] at h
    exact Or.inl hprio
  · by_cases hrev : rhs.priority < lhs.priority
    · simp [fixedPriorityBetter, hprio, hrev] at h
    · have hTokenLe : lhs.token <= rhs.token := by
        have : decide (lhs.token <= rhs.token) = true := by
          simpa [fixedPriorityBetter, hprio, hrev] using h
        simpa using this
      have hEq : lhs.priority = rhs.priority := by
        exact Nat.le_antisymm (Nat.le_of_not_gt hrev) (Nat.le_of_not_gt hprio)
      exact Or.inr ⟨hEq, hTokenLe⟩

def reviewedChoiceSelect (fallback reviewToken : Nat) (ambiguousTokens : List Nat) : Nat :=
  if reviewToken ∈ ambiguousTokens then reviewToken else fallback

theorem reviewedChoiceSelect_uses_review_token_when_present
    (fallback reviewToken : Nat)
    (ambiguousTokens : List Nat)
    (h : reviewToken ∈ ambiguousTokens) :
    reviewedChoiceSelect fallback reviewToken ambiguousTokens = reviewToken := by
  simp [reviewedChoiceSelect, h]
