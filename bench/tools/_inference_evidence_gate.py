"""Inference evidence gate.

Decides whether a HostPlan + dispatch evidence bundle is eligible to back a
token-output / inference receipt. Fail-closed: any gap in the
sample <- lm_head edge, or in the dispatch evidence for that edge,
rejects the claim.

Topology checks (HostPlan only):
  - sample with no lm-head upstream in the same phase
  - sample's immediate predecessor is not an lm-head kernel
  - lm-head present in a phase with no downstream sample
  - kernel registry has no lm-head entry while a phase references sample
  - no phase ends in sample (no token-output phase)
  - HostPlan kernel inventory diverges from a supplied source-graph inventory

Dispatch checks (per-kernel simfabric summary or equivalent):
  - sample missing from dispatch evidence
  - sample dispatch verdict is not 'bound'
  - lm-head missing from dispatch evidence
  - no lm-head dispatch verdict is 'bound'
  - dispatch evidence absent altogether while sample is in the plan
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence


REASON_SAMPLE_WITHOUT_LOGITS_PRODUCER = "sample_without_logits_producer"
REASON_SAMPLE_PREDECESSOR_NOT_LM_HEAD = "sample_predecessor_not_lm_head"
REASON_LM_HEAD_DANGLING = "lm_head_dangling"
REASON_NO_TOKEN_OUTPUT_PHASE = "no_token_output_phase"
REASON_KERNEL_REGISTRY_MISSING_LM_HEAD = "kernel_registry_missing_lm_head"
REASON_TARGET_INVENTORY_MISMATCH = "target_inventory_mismatch"
REASON_DISPATCH_EVIDENCE_ABSENT = "dispatch_evidence_absent"
REASON_DISPATCH_EVIDENCE_SAMPLE_UNBOUND = "dispatch_evidence_sample_unbound"
REASON_DISPATCH_EVIDENCE_LM_HEAD_MISSING = "dispatch_evidence_lm_head_missing"
REASON_DISPATCH_EVIDENCE_LM_HEAD_UNBOUND = "dispatch_evidence_lm_head_unbound"


_LM_HEAD_PREFIX = "lm_head"
_SAMPLE_NAME = "sample"
_BOUND_VERDICT = "bound"
_DIRECT_DISPATCH_MODE = "monolithic_full_fabric"
_DIRECT_LM_HEAD_SCOPE = "manifest_shape_direct_dispatch"
_WIDTH_TILED_DISPATCH_MODE = "dense_gemv_width_tiled"
_WIDTH_TILED_LM_HEAD_SCOPE = "full_vocab_host_reduced_width_row_tiles"


@dataclass(frozen=True)
class GateReason:
    code: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class GateResult:
    eligible: bool
    reasons: tuple[GateReason, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "eligible": self.eligible,
            "reasons": [r.to_dict() for r in self.reasons],
        }


class InferenceEvidenceGateError(RuntimeError):
    def __init__(self, result: GateResult) -> None:
        self.result = result
        codes = ", ".join(r.code for r in result.reasons) or "no_reason"
        super().__init__(f"inference evidence gate rejected: {codes}")


def _is_lm_head(name: object) -> bool:
    return isinstance(name, str) and name.startswith(_LM_HEAD_PREFIX)


def _phase_kernel_names(phase: Iterable[object]) -> list[str]:
    out: list[str] = []
    for step in phase:
        if not isinstance(step, Mapping):
            out.append("")
            continue
        out.append(str(step.get("kernelName") or ""))
    return out


def _resolve_plan_root(host_plan: Mapping[str, object]) -> Mapping[str, object]:
    inner = host_plan.get("hostPlan")
    if isinstance(inner, Mapping):
        return inner
    return host_plan


def _tile_dispatches_are_complete(entry: Mapping[str, object]) -> bool:
    dispatches = entry.get("tileDispatches")
    coverage = entry.get("tileCoverage")
    if not isinstance(dispatches, Mapping):
        return False
    if not isinstance(coverage, Mapping):
        return False
    shape_safety = coverage.get("tileShapeSafety")
    if not isinstance(shape_safety, Mapping):
        return False
    return (
        int(dispatches.get("blockedCount") or 0) == 0
        and int(dispatches.get("tileCount") or 0) > 0
        and bool(coverage.get("covered"))
        and bool(shape_safety.get("safe"))
    )


def _host_reduction_is_declared(entry: Mapping[str, object]) -> bool:
    reduction = entry.get("hostReduction")
    if not isinstance(reduction, Mapping):
        return False
    return str(reduction.get("kind") or "") == "sum_hidden_width_tiles"


def _lm_head_entry_promotes(entry: Mapping[str, object]) -> bool:
    if str(entry.get("verdict") or "") != _BOUND_VERDICT:
        return False
    mode = str(entry.get("dispatchMode") or "")
    scope = str(entry.get("lmHeadEvidenceScope") or "")
    if mode == _DIRECT_DISPATCH_MODE and scope == _DIRECT_LM_HEAD_SCOPE:
        return True
    if mode == _WIDTH_TILED_DISPATCH_MODE:
        return (
            scope == _WIDTH_TILED_LM_HEAD_SCOPE
            and _tile_dispatches_are_complete(entry)
            and _host_reduction_is_declared(entry)
        )
    return False


def evaluate_inference_evidence_gate(
    *,
    host_plan: Mapping[str, object],
    per_kernel_summary: Mapping[str, object] | None = None,
    require_dispatch_evidence: bool = True,
    source_graph_kernels: Sequence[str] | None = None,
) -> GateResult:
    reasons: list[GateReason] = []

    plan_root = _resolve_plan_root(host_plan)

    phases_obj = plan_root.get("phases") or {}
    phases: Mapping[str, object] = phases_obj if isinstance(phases_obj, Mapping) else {}

    kernels_obj = plan_root.get("kernels") or []
    kernels_registry: Sequence[object] = (
        kernels_obj if isinstance(kernels_obj, Sequence) and not isinstance(kernels_obj, (str, bytes)) else []
    )
    registry_names = {
        str(k.get("name") or "")
        for k in kernels_registry
        if isinstance(k, Mapping)
    }

    sample_in_any_phase = False
    token_output_phase_present = False

    for phase_name, phase in phases.items():
        if not isinstance(phase, Sequence) or isinstance(phase, (str, bytes)):
            continue
        names = _phase_kernel_names(phase)
        if _SAMPLE_NAME not in names:
            for kernel_name in names:
                if _is_lm_head(kernel_name):
                    reasons.append(GateReason(
                        REASON_LM_HEAD_DANGLING,
                        f"phase '{phase_name}' has lm-head kernel "
                        f"'{kernel_name}' with no downstream sample.",
                    ))
            continue
        sample_in_any_phase = True
        sample_idx = names.index(_SAMPLE_NAME)
        upstream = names[:sample_idx]
        if not any(_is_lm_head(n) for n in upstream):
            reasons.append(GateReason(
                REASON_SAMPLE_WITHOUT_LOGITS_PRODUCER,
                f"phase '{phase_name}' has 'sample' but no lm-head kernel "
                f"upstream of it.",
            ))
            continue
        predecessor = names[sample_idx - 1] if sample_idx > 0 else ""
        if not _is_lm_head(predecessor):
            reasons.append(GateReason(
                REASON_SAMPLE_PREDECESSOR_NOT_LM_HEAD,
                f"phase '{phase_name}' has 'sample' immediately preceded by "
                f"'{predecessor or '<none>'}' instead of an lm-head kernel.",
            ))
            continue
        if sample_idx == len(names) - 1:
            token_output_phase_present = True

    if sample_in_any_phase and not any(_is_lm_head(n) for n in registry_names):
        reasons.append(GateReason(
            REASON_KERNEL_REGISTRY_MISSING_LM_HEAD,
            "HostPlan kernels[] registry has no lm-head entry while a "
            "phase references sample.",
        ))

    if sample_in_any_phase and not token_output_phase_present:
        reasons.append(GateReason(
            REASON_NO_TOKEN_OUTPUT_PHASE,
            "no phase ends in 'sample'; HostPlan does not declare a "
            "terminal-token-output phase.",
        ))

    if source_graph_kernels is not None:
        plan_set = {n for n in registry_names if n}
        graph_set = {str(n) for n in source_graph_kernels if str(n)}
        if plan_set != graph_set:
            missing = sorted(graph_set - plan_set)
            extra = sorted(plan_set - graph_set)
            reasons.append(GateReason(
                REASON_TARGET_INVENTORY_MISMATCH,
                "HostPlan kernel inventory differs from source graph; "
                f"missing={missing}; extra={extra}.",
            ))

    if per_kernel_summary is None:
        if require_dispatch_evidence and sample_in_any_phase:
            reasons.append(GateReason(
                REASON_DISPATCH_EVIDENCE_ABSENT,
                "no per-kernel dispatch evidence supplied; cannot back an "
                "inference claim.",
            ))
    else:
        kernels_field = per_kernel_summary.get("kernels") or []
        kernel_entries: Sequence[object] = (
            kernels_field if isinstance(kernels_field, Sequence) and not isinstance(kernels_field, (str, bytes)) else []
        )
        evidence_by_kernel: dict[str, Mapping[str, object]] = {}
        for entry in kernel_entries:
            if not isinstance(entry, Mapping):
                continue
            kernel_name = str(entry.get("kernel") or "")
            if kernel_name:
                evidence_by_kernel[kernel_name] = entry

        if sample_in_any_phase:
            sample_entry = evidence_by_kernel.get(_SAMPLE_NAME)
            if sample_entry is None:
                reasons.append(GateReason(
                    REASON_DISPATCH_EVIDENCE_SAMPLE_UNBOUND,
                    "per-kernel summary has no entry for 'sample'.",
                ))
            else:
                verdict = str(sample_entry.get("verdict") or "")
                if verdict != _BOUND_VERDICT:
                    reasons.append(GateReason(
                        REASON_DISPATCH_EVIDENCE_SAMPLE_UNBOUND,
                        f"per-kernel verdict for 'sample' is '{verdict}'; "
                        f"required: '{_BOUND_VERDICT}'.",
                    ))

            lm_head_entries = [
                entry for kn, entry in evidence_by_kernel.items()
                if _is_lm_head(kn)
            ]
            if not lm_head_entries:
                reasons.append(GateReason(
                    REASON_DISPATCH_EVIDENCE_LM_HEAD_MISSING,
                    "per-kernel summary has no lm-head entry; sample's "
                    "logits have no dispatch evidence.",
                ))
            elif not any(_lm_head_entry_promotes(e) for e in lm_head_entries):
                observed = sorted({
                    (
                        f"{str(e.get('verdict') or '')}/"
                        f"{str(e.get('dispatchMode') or '<missing>')}/"
                        f"{str(e.get('lmHeadEvidenceScope') or '<missing>')}"
                    )
                    for e in lm_head_entries
                })
                reasons.append(GateReason(
                    REASON_DISPATCH_EVIDENCE_LM_HEAD_UNBOUND,
                    "no lm-head per-kernel entry has promotable token-output "
                    f"evidence; observed: {observed}.",
                ))

    return GateResult(eligible=not reasons, reasons=tuple(reasons))


def enforce_inference_evidence_gate(**kwargs: object) -> GateResult:
    result = evaluate_inference_evidence_gate(**kwargs)  # type: ignore[arg-type]
    if not result.eligible:
        raise InferenceEvidenceGateError(result)
    return result
