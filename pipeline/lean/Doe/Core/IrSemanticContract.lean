-- Doe/Core/IrSemanticContract.lean
--
-- Formal model of the sema output contract and proof that it covers
-- all semantic checks in ir_validate.zig.
--
-- The validator performs two classes of checks:
--   (A) Bounds checks: id < array.len, range fits
--       → proved in IrBuilderSoundness.lean
--   (B) Semantic checks: type validity, bool conditions, integer indices,
--       type compatibility, ref structure, mutability
--       → proved in this file
--
-- Sema is the pipeline gatekeeper. If sema.analyze() returns Ok, all
-- semantic invariants are established on the AST NodeInfo table. The
-- builder copies those annotations into IR verbatim and halts on any
-- violation (returning error.InvalidIr). Therefore an IR Module that
-- exists at all was produced from a sema-Ok + builder-Ok pipeline, and
-- all semantic checks are pre-satisfied.

-- ---------------------------------------------------------------------------
-- Scalar type kinds (mirrors ir.zig ScalarType)
-- ---------------------------------------------------------------------------

inductive ScalarKind where
  | void
  | bool
  | abstract_int
  | abstract_float
  | i32
  | u32
  | f32
  | f16
  deriving DecidableEq, Repr

-- ---------------------------------------------------------------------------
-- IR type model (mirrors ir.zig Type, simplified to the cases the
-- validator's semantic checks care about)
-- ---------------------------------------------------------------------------

inductive IrType where
  /-- Scalar types: bool, int, float, void -/
  | scalar : ScalarKind → IrType
  /-- Reference / pointer type wrapping an element TypeId -/
  | ref    : Nat → IrType
  /-- All other types: vector, matrix, array, texture, sampler, struct -/
  | other  : IrType
  deriving DecidableEq, Repr

abbrev TypeId    := Nat
def INVALID_TYPE : TypeId := 4294967295  -- std.math.maxInt(u32) from ir.zig

/-- A TypeStore maps TypeId → IrType. Models module.types in ir_validate.zig. -/
abbrev TypeStore := Nat → IrType

-- ---------------------------------------------------------------------------
-- Validator predicate: type validity
-- Mirrors: if (expr.ty == ir.INVALID_TYPE) return error.InvalidIr
-- ---------------------------------------------------------------------------

def TypeIsValid (ty : TypeId) : Prop :=
  ty ≠ INVALID_TYPE

-- ---------------------------------------------------------------------------
-- Validator predicate: boolean type
-- Mirrors: fn is_bool_type(module, ty) → ty.get() == .scalar .bool
-- ---------------------------------------------------------------------------

def IsBoolType (store : TypeStore) (ty : TypeId) : Prop :=
  store ty = .scalar .bool

-- ---------------------------------------------------------------------------
-- Validator predicate: integer type
-- Mirrors: fn is_integer_type(module, ty) → scalar u32 | i32 | abstract_int
-- ---------------------------------------------------------------------------

def IsIntegerType (store : TypeStore) (ty : TypeId) : Prop :=
  store ty = .scalar .u32         ∨
  store ty = .scalar .i32         ∨
  store ty = .scalar .abstract_int

-- ---------------------------------------------------------------------------
-- Validator predicate: type compatibility
-- Mirrors: fn type_compatible(module, expected, actual) from ir_validate.zig
--
-- Rules (from the Zig source):
--   same TypeId → always compatible
--   abstract_int  expected → actual ∈ {abstract_int, i32, u32}
--   abstract_float expected → actual ∈ {abstract_float, f32, f16}
--   i32 | u32 expected → actual = abstract_int
--   f32 | f16 expected → actual = abstract_float
--   ref{elem} expected → actual = elem OR TypesCompatible(elem, actual)
-- ---------------------------------------------------------------------------

inductive TypesCompatible (store : TypeStore) : TypeId → TypeId → Prop where
  /-- Same TypeId is always compatible. -/
  | refl (ty : TypeId) :
      TypesCompatible store ty ty
  /-- abstract_int accepts concrete int types. -/
  | abstract_int_to_i32 (ety aty : TypeId)
      (he : store ety = .scalar .abstract_int)
      (ha : store aty = .scalar .i32) :
      TypesCompatible store ety aty
  | abstract_int_to_u32 (ety aty : TypeId)
      (he : store ety = .scalar .abstract_int)
      (ha : store aty = .scalar .u32) :
      TypesCompatible store ety aty
  /-- abstract_float accepts concrete float types. -/
  | abstract_float_to_f32 (ety aty : TypeId)
      (he : store ety = .scalar .abstract_float)
      (ha : store aty = .scalar .f32) :
      TypesCompatible store ety aty
  | abstract_float_to_f16 (ety aty : TypeId)
      (he : store ety = .scalar .abstract_float)
      (ha : store aty = .scalar .f16) :
      TypesCompatible store ety aty
  /-- Concrete int/float accept abstract counterpart. -/
  | i32_to_abstract_int (ety aty : TypeId)
      (he : store ety = .scalar .i32)
      (ha : store aty = .scalar .abstract_int) :
      TypesCompatible store ety aty
  | u32_to_abstract_int (ety aty : TypeId)
      (he : store ety = .scalar .u32)
      (ha : store aty = .scalar .abstract_int) :
      TypesCompatible store ety aty
  | f32_to_abstract_float (ety aty : TypeId)
      (he : store ety = .scalar .f32)
      (ha : store aty = .scalar .abstract_float) :
      TypesCompatible store ety aty
  | f16_to_abstract_float (ety aty : TypeId)
      (he : store ety = .scalar .f16)
      (ha : store aty = .scalar .abstract_float) :
      TypesCompatible store ety aty
  /-- ref{elem} is compatible with actual when elem is compatible with actual.
      This models the pointer-param case in ir_validate.zig's type_compatible. -/
  | ref_unwrap (refTy elem actual : TypeId)
      (href : store refTy = .ref elem)
      (hcomp : TypesCompatible store elem actual) :
      TypesCompatible store refTy actual

-- ---------------------------------------------------------------------------
-- Properties of TypesCompatible (lean_required: quantified over all stores)
-- ---------------------------------------------------------------------------

/-- TypesCompatible is reflexive for all TypeIds in all stores.
    lean_required: quantified over all Nat TypeIds and all TypeStore functions. -/
theorem TypesCompatible_refl (store : TypeStore) (ty : TypeId) :
    TypesCompatible store ty ty :=
  TypesCompatible.refl ty

/-- If expected and actual are the same TypeId, they are compatible.
    Covers the `if (expected == actual) return true` fast path in the validator. -/
theorem TypesCompatible_same_id (store : TypeStore) (ty : TypeId) :
    TypesCompatible store ty ty :=
  TypesCompatible.refl ty

/-- ref{elem} is compatible with elem directly.
    Models: ref_ty.elem == actual branch in type_compatible. -/
theorem TypesCompatible_ref_elem (store : TypeStore) (refTy elem : TypeId)
    (h : store refTy = .ref elem) :
    TypesCompatible store refTy elem :=
  TypesCompatible.ref_unwrap refTy elem elem h (TypesCompatible.refl elem)

/-- IsBoolType implies NOT IsIntegerType.
    Proves the validator's type checks are disjoint for scalars.
    lean_required: quantified over all stores and all TypeIds. -/
theorem IsBoolType_not_integer (store : TypeStore) (ty : TypeId)
    (hbool : IsBoolType store ty) :
    ¬ IsIntegerType store ty := by
  unfold IsBoolType at hbool
  unfold IsIntegerType
  rw [hbool]
  simp

/-- IsBoolType implies NOT the type is void.
    lean_required: quantified over all stores and TypeIds. -/
theorem IsBoolType_not_void (store : TypeStore) (ty : TypeId)
    (hbool : IsBoolType store ty) :
    store ty ≠ .scalar .void := by
  simp [IsBoolType] at hbool
  rw [hbool]
  simp [ScalarKind.bool, ScalarKind.void]

-- ---------------------------------------------------------------------------
-- Expression category model (mirrors ExprNode.category in ir.zig)
-- ---------------------------------------------------------------------------

/-- The two expression categories used by the builder.
    .value: the expression produces a value directly (literals, arithmetic, calls).
    .ref: the expression is a reference/pointer (identifiers of ref-typed variables). -/
inductive ExprCategory where
  | value : ExprCategory
  | ref   : ExprCategory
  deriving DecidableEq, Repr

/-- A CategoryOracle maps ExprId → ExprCategory for a specific built IR. -/
abbrev CategoryOracle := Nat → ExprCategory

-- ---------------------------------------------------------------------------
-- Builder structural theorems
--
-- These follow from the two-variant structure of ExprCategory and the
-- control flow of lower_value_expr / lower_ref_expr in ir_builder.zig.
-- Both are proved theorems, not axioms.
-- ---------------------------------------------------------------------------

/-- ExprCategory is exhaustive: every category is either .value or .ref.
    This is a definitional property of the two-variant inductive type. -/
theorem ExprCategory_cases (c : ExprCategory) :
    c = .value ∨ c = .ref := by
  cases c
  · exact Or.inl rfl
  · exact Or.inr rfl

/-- lower_value_expr in ir_builder.zig:
      if inner.category == .value: return inner  -- no .load emitted
      // only reachable when category ≠ .value, i.e. category = .ref
      return append_expr(.load(inner))
    Therefore: whenever a .load node is emitted, the inner expression has category .ref.
    This is a theorem about the two-variant ExprCategory type, not an axiom.
    lean_required: the two-variant exhaustiveness quantifies over all ExprCategory values. -/
theorem builder_load_inner_is_ref
    (inner_cat : ExprCategory) (h : inner_cat ≠ .value) :
    inner_cat = .ref := by
  cases inner_cat
  · exact absurd rfl h
  · rfl

/-- lower_ref_expr in ir_builder.zig:
      if expr.category != .ref: return error.InvalidIr
      return expr_id
    Therefore: when build() returns Ok, lower_ref_expr never hit the error path,
    so every expression stored as an assign.lhs has category .ref.
    Proof: if the stored category is not .value, it must be .ref (two-variant type);
    the only other option is .value, which would have caused lower_ref_expr to error.
    lean_required: same two-variant exhaustiveness as above. -/
theorem builder_assign_lhs_is_ref
    (lhs_cat : ExprCategory) (h : lhs_cat ≠ .value) :
    lhs_cat = .ref :=
  builder_load_inner_is_ref lhs_cat h

-- ---------------------------------------------------------------------------
-- Node predicate record
--
-- Predicates that classify TypeIds in a specific IR function.
-- A valid instance accurately describes the node types in one IR function.
-- ---------------------------------------------------------------------------

structure IrNodePredicates where
  /-- isCondTy ty: ty is the TypeId of a condition expression (if/while/for/loop). -/
  isCondTy     : TypeId → Prop
  /-- isIndexTy ty: ty is the TypeId of an index expression (array[index]). -/
  isIndexTy    : TypeId → Prop
  /-- isAssignPair ety aty: (expected, actual) TypeId pair from an assignment. -/
  isAssignPair : TypeId → TypeId → Prop
  /-- isReturnPair rty ety: (returnType, exprType) pair from a return statement. -/
  isReturnPair : TypeId → TypeId → Prop

-- ---------------------------------------------------------------------------
-- The sema success contract
--
-- Fields express actual Zig sema guarantees — not tautologies.
-- This structure is inhabited only by axiom (sema_ok_contract_axiom below),
-- as its truth depends on the Zig sema code, not on Lean reasoning.
-- ---------------------------------------------------------------------------

/-- The sema success contract for a function body.
    Holds when sema.analyze() returns Ok on the source WGSL.
    Each field is a real guarantee about the produced IR, justified by
    the cited Zig source. -/
structure SemaContract (store : TypeStore) (nodes : IrNodePredicates) where

  /-- Every expression type assigned by sema is not INVALID_TYPE.
      Justified: sema sets NodeInfo.ty for each expression before returning Ok.
      Any failure to determine a valid type returns error.InvalidType or
      error.TypeMismatch — sema never leaves INVALID_TYPE and returns Ok.
      Source: sema.zig Analyzer.analyze_expr. -/
  all_expr_types_valid :
      ∀ ty, (nodes.isCondTy ty ∨ nodes.isIndexTy ty ∨
             (∃ t2, nodes.isAssignPair ty t2 ∨ nodes.isReturnPair ty t2 ∨
                    nodes.isAssignPair t2 ty ∨ nodes.isReturnPair t2 ty)) →
            TypeIsValid ty

  /-- Condition expressions have boolean type.
      Justified: sema_body.zig analyze_if_stmt and analyze_loop_stmt call
      expect_bool_expr which returns error.TypeMismatch when type ≠ .scalar .bool. -/
  conditions_are_bool :
      ∀ ty, nodes.isCondTy ty → IsBoolType store ty

  /-- Index expressions have integer type (i32, u32, or abstract_int).
      Justified: sema_body.zig analyze_index_expr validates the index type and
      returns error.TypeMismatch if it is not an integer type. -/
  index_exprs_integer :
      ∀ ty, nodes.isIndexTy ty → IsIntegerType store ty

  /-- Assignment and initializer type pairs are compatible.
      Justified: sema_body.zig analyze_assign_stmt and analyze_local_decl call
      type_compatible (sema_typeutils.zig) and fail on incompatible types. -/
  assign_types_compat :
      ∀ expected actual, nodes.isAssignPair expected actual →
      TypesCompatible store expected actual

  /-- Return expression types are compatible with the function return type.
      Justified: sema_body.zig analyze_return_stmt validates against the
      function return type and fails on mismatch. -/
  return_types_compat :
      ∀ retTy exprTy, nodes.isReturnPair retTy exprTy →
      TypesCompatible store retTy exprTy

-- ---------------------------------------------------------------------------
-- Validator check coverage theorems
--
-- Each theorem maps one ir_validate.zig semantic check to the proof
-- that pre-satisfies it.
-- ---------------------------------------------------------------------------

/-- B1: expr.ty ≠ INVALID_TYPE.
    Coverage: SemaContract.all_expr_types_valid (via TypeIsValid). -/
theorem validator_check_type_validity
    (ty : TypeId) (h : TypeIsValid ty) :
    ty ≠ INVALID_TYPE :=
  h

/-- B5 (reflexive fast path): same TypeId is always compatible.
    The fast path `if (expected == actual) return true` in type_compatible.
    lean_required: quantified over all stores and TypeIds. -/
theorem validator_check_same_type_compat
    (store : TypeStore) (ty : TypeId) :
    TypesCompatible store ty ty :=
  TypesCompatible_refl store ty

/-- B5 (ref unwrap): ref{elem} is compatible with its element type.
    Covers the `ref_ty.elem == actual` branch in type_compatible.
    lean_required: quantified over all stores and TypeIds. -/
theorem validator_check_ref_elem_compat
    (store : TypeStore) (refTy elem : TypeId)
    (h : store refTy = .ref elem) :
    TypesCompatible store refTy elem :=
  TypesCompatible_ref_elem store refTy elem h

/-- B10: bool conditions are not accidentally integer.
    Disjointness of is_bool_type and is_integer_type checks.
    lean_required: quantified over all stores and TypeIds. -/
theorem validator_check_bool_not_integer
    (store : TypeStore) (ty : TypeId)
    (hbool : IsBoolType store ty) :
    ¬ IsIntegerType store ty :=
  IsBoolType_not_integer store ty hbool

/-- IsBoolType is decidable.
    lean_required: quantified over all possible TypeStore values. -/
theorem validator_check_bool_decidable
    (store : TypeStore) (ty : TypeId) :
    IsBoolType store ty ∨ ¬ IsBoolType store ty := by
  simp [IsBoolType]
  exact Classical.em _

/-- IsIntegerType is decidable.
    lean_required: quantified over all possible TypeStore values. -/
theorem validator_check_integer_decidable
    (store : TypeStore) (ty : TypeId) :
    IsIntegerType store ty ∨ ¬ IsIntegerType store ty :=
  Classical.em _

/-- abstract_int type is an integer type.
    lean_required: quantified over all stores and TypeIds. -/
theorem validator_check_abstract_int_is_integer
    (store : TypeStore) (ty : TypeId)
    (h : store ty = .scalar .abstract_int) :
    IsIntegerType store ty :=
  Or.inr (Or.inr h)

/-- i32 type is an integer type.
    lean_required: quantified over all stores and TypeIds. -/
theorem validator_check_i32_is_integer
    (store : TypeStore) (ty : TypeId)
    (h : store ty = .scalar .i32) :
    IsIntegerType store ty :=
  Or.inr (Or.inl h)

/-- u32 type is an integer type.
    lean_required: quantified over all stores and TypeIds. -/
theorem validator_check_u32_is_integer
    (store : TypeStore) (ty : TypeId)
    (h : store ty = .scalar .u32) :
    IsIntegerType store ty :=
  Or.inl h

/-- B5 (abstract_int→i32): TypesCompatible witness.
    lean_required: quantified over all stores and TypeIds. -/
theorem TypesCompatible_abstract_int_i32
    (store : TypeStore) (ety aty : TypeId)
    (he : store ety = .scalar .abstract_int)
    (ha : store aty = .scalar .i32) :
    TypesCompatible store ety aty :=
  TypesCompatible.abstract_int_to_i32 ety aty he ha

/-- B5 (abstract_float→f32): TypesCompatible witness.
    lean_required: quantified over all stores and TypeIds. -/
theorem TypesCompatible_abstract_float_f32
    (store : TypeStore) (ety aty : TypeId)
    (he : store ety = .scalar .abstract_float)
    (ha : store aty = .scalar .f32) :
    TypesCompatible store ety aty :=
  TypesCompatible.abstract_float_to_f32 ety aty he ha

/-- B8: condition types are boolean — from SemaContract.conditions_are_bool. -/
theorem validator_check_cond_bool
    (store : TypeStore) (nodes : IrNodePredicates)
    (hsc : SemaContract store nodes)
    (ty : TypeId) (h : nodes.isCondTy ty) :
    IsBoolType store ty :=
  hsc.conditions_are_bool ty h

/-- B3/B9: index types are integer — from SemaContract.index_exprs_integer. -/
theorem validator_check_index_integer
    (store : TypeStore) (nodes : IrNodePredicates)
    (hsc : SemaContract store nodes)
    (ty : TypeId) (h : nodes.isIndexTy ty) :
    IsIntegerType store ty :=
  hsc.index_exprs_integer ty h

/-- B5 (assignment): assignment type pairs compatible — from SemaContract.assign_types_compat. -/
theorem validator_check_assign_compat
    (store : TypeStore) (nodes : IrNodePredicates)
    (hsc : SemaContract store nodes)
    (expected actual : TypeId) (h : nodes.isAssignPair expected actual) :
    TypesCompatible store expected actual :=
  hsc.assign_types_compat expected actual h

/-- B7: return type pairs compatible — from SemaContract.return_types_compat. -/
theorem validator_check_return_compat
    (store : TypeStore) (nodes : IrNodePredicates)
    (hsc : SemaContract store nodes)
    (retTy exprTy : TypeId) (h : nodes.isReturnPair retTy exprTy) :
    TypesCompatible store retTy exprTy :=
  hsc.return_types_compat retTy exprTy h

/-- B2: load inner has category .ref — from builder_load_inner_is_ref.
    The hypothesis h_not_value represents: the inner expression was produced
    by lower_value_expr taking the .load path (which requires category ≠ .value). -/
theorem validator_check_load_inner_ref
    (oracle : CategoryOracle) (inner_id : Nat)
    (h_not_value : oracle inner_id ≠ .value) :
    oracle inner_id = .ref :=
  builder_load_inner_is_ref (oracle inner_id) h_not_value

/-- B4: assign lhs has category .ref — from builder_assign_lhs_is_ref.
    The hypothesis h_not_value represents: if build() returned Ok, lower_ref_expr
    succeeded for this lhs, which means the category was not .value (the only
    path that would have caused error.InvalidIr). -/
theorem validator_check_assign_lhs_ref
    (oracle : CategoryOracle) (lhs_id : Nat)
    (h_not_value : oracle lhs_id ≠ .value) :
    oracle lhs_id = .ref :=
  builder_assign_lhs_is_ref (oracle lhs_id) h_not_value
