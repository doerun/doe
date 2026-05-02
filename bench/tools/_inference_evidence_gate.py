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
  - complete session transcript evidence may supersede per-kernel evidence
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
REASON_SESSION_TRANSCRIPT_NOT_OUTPUT_READY = "session_transcript_not_output_ready"
REASON_SESSION_TRANSCRIPT_DECODE_COUNT_MISMATCH = (
    "session_transcript_decode_count_mismatch"
)
REASON_SESSION_TRANSCRIPT_TOKENS_INCOMPLETE = (
    "session_transcript_generated_tokens_incomplete"
)
REASON_SESSION_TRANSCRIPT_LOGITS_MISSING = (
    "session_transcript_logits_digests_missing"
)
REASON_SESSION_TRANSCRIPT_LM_HEAD_MISSING = (
    "session_transcript_lm_head_dispatch_missing"
)
REASON_SESSION_TRANSCRIPT_KV_CACHE_MISSING = (
    "session_transcript_kv_cache_missing"
)


_LM_HEAD_PREFIX = "lm_head"
_SAMPLE_NAME = "sample"
_BOUND_VERDICT = "bound"
_DIRECT_DISPATCH_MODE = "monolithic_full_fabric"
_DIRECT_LM_HEAD_SCOPE = "manifest_shape_direct_dispatch"
_WIDTH_TILED_DISPATCH_MODE = "dense_gemv_width_tiled"
_WIDTH_TILED_LM_HEAD_SCOPE = "full_vocab_host_reduced_width_row_tiles"
_OUTPUT_READY_STATUS = "output_ready"


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


def _as_mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def _as_sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return []


def _session_transcript(
    real_session_runtime: Mapping[str, object],
) -> Mapping[str, object]:
    transcript = real_session_runtime.get("runtimeTranscript")
    if isinstance(transcript, Mapping):
        return transcript
    return real_session_runtime


def _session_claims_output_ready(
    real_session_runtime: Mapping[str, object],
) -> bool:
    transcript = _session_transcript(real_session_runtime)
    runtime_status = str(real_session_runtime.get("status") or "")
    transcript_status = str(transcript.get("status") or runtime_status)
    return (
        runtime_status == _OUTPUT_READY_STATUS
        or transcript_status == _OUTPUT_READY_STATUS
    )


def session_runtime_evidence_reasons(
    real_session_runtime: Mapping[str, object] | None,
    *,
    requested_decode_steps: int | None = None,
) -> tuple[GateReason, ...]:
    if real_session_runtime is None:
        return (
            GateReason(
                REASON_SESSION_TRANSCRIPT_NOT_OUTPUT_READY,
                "no real-session runtime evidence was supplied.",
            ),
        )

    transcript = _session_transcript(real_session_runtime)
    runtime_status = str(real_session_runtime.get("status") or "")
    transcript_status = str(transcript.get("status") or runtime_status)
    reasons: list[GateReason] = []

    if runtime_status != _OUTPUT_READY_STATUS:
        reasons.append(GateReason(
            REASON_SESSION_TRANSCRIPT_NOT_OUTPUT_READY,
            "real-session runtime status is "
            f"'{runtime_status or '<missing>'}'; required: "
            f"'{_OUTPUT_READY_STATUS}'.",
        ))
    elif transcript_status != _OUTPUT_READY_STATUS:
        reasons.append(GateReason(
            REASON_SESSION_TRANSCRIPT_NOT_OUTPUT_READY,
            "real-session transcript status is "
            f"'{transcript_status or '<missing>'}'; required: "
            f"'{_OUTPUT_READY_STATUS}'.",
        ))

    requested = requested_decode_steps
    if requested is None:
        try:
            requested = int(transcript.get("requestedDecodeSteps") or 0)
        except (TypeError, ValueError):
            requested = 0
    try:
        actual = int(transcript.get("actualDecodeSteps") or 0)
    except (TypeError, ValueError):
        actual = 0
    if requested is None or requested <= 0 or actual != requested:
        reasons.append(GateReason(
            REASON_SESSION_TRANSCRIPT_DECODE_COUNT_MISMATCH,
            "real-session transcript decode count mismatch; "
            f"requested={requested or 0}; actual={actual}.",
        ))

    generated_tokens = _as_sequence(transcript.get("generatedTokenIds"))
    if (
        actual <= 0
        or len(generated_tokens) != actual
        or any(not isinstance(token, int) for token in generated_tokens)
    ):
        reasons.append(GateReason(
            REASON_SESSION_TRANSCRIPT_TOKENS_INCOMPLETE,
            "real-session transcript generatedTokenIds must contain one "
            "integer token ID per decoded output step.",
        ))

    logits_digests = _as_sequence(transcript.get("logitsDigests"))
    if len(logits_digests) < actual or actual <= 0:
        reasons.append(GateReason(
            REASON_SESSION_TRANSCRIPT_LOGITS_MISSING,
            "real-session transcript must include at least one logits digest "
            "record per decoded output step.",
        ))
    else:
        for index, digest in enumerate(logits_digests[:actual]):
            item = _as_mapping(digest)
            if item is None:
                reasons.append(GateReason(
                    REASON_SESSION_TRANSCRIPT_LOGITS_MISSING,
                    f"logits digest record {index} is not an object.",
                ))
                break
            if not str(item.get("sha256") or ""):
                reasons.append(GateReason(
                    REASON_SESSION_TRANSCRIPT_LOGITS_MISSING,
                    f"logits digest record {index} has no sha256.",
                ))
                break

    lm_head_dispatches = _as_sequence(transcript.get("lmHeadDispatches"))
    if len(lm_head_dispatches) < actual or actual <= 0:
        reasons.append(GateReason(
            REASON_SESSION_TRANSCRIPT_LM_HEAD_MISSING,
            "real-session transcript must include at least one lm-head "
            "dispatch record per decoded output step.",
        ))
    else:
        for index, dispatch in enumerate(lm_head_dispatches[:actual]):
            item = _as_mapping(dispatch)
            if item is None:
                reasons.append(GateReason(
                    REASON_SESSION_TRANSCRIPT_LM_HEAD_MISSING,
                    f"lm-head dispatch record {index} is not an object.",
                ))
                break
            if not str(item.get("dispatchMode") or ""):
                reasons.append(GateReason(
                    REASON_SESSION_TRANSCRIPT_LM_HEAD_MISSING,
                    f"lm-head dispatch record {index} has no dispatchMode.",
                ))
                break

    kv_cache = _as_mapping(transcript.get("kvCache"))
    digest_count = 0
    if kv_cache is not None:
        try:
            digest_count = int(kv_cache.get("digestCount") or 0)
        except (TypeError, ValueError):
            digest_count = 0
    if (
        kv_cache is None
        or str(kv_cache.get("mode") or "") != "runtime_captured"
        or digest_count <= 0
    ):
        reasons.append(GateReason(
            REASON_SESSION_TRANSCRIPT_KV_CACHE_MISSING,
            "real-session transcript must include runtime_captured KV-cache "
            "digests.",
        ))

    return tuple(reasons)


def session_runtime_evidence_is_complete(
    real_session_runtime: Mapping[str, object] | None,
    *,
    requested_decode_steps: int | None = None,
) -> bool:
    return not session_runtime_evidence_reasons(
        real_session_runtime,
        requested_decode_steps=requested_decode_steps,
    )


def evaluate_inference_evidence_gate(
    *,
    host_plan: Mapping[str, object],
    per_kernel_summary: Mapping[str, object] | None = None,
    require_dispatch_evidence: bool = True,
    source_graph_kernels: Sequence[str] | None = None,
    real_session_runtime: Mapping[str, object] | None = None,
    requested_decode_steps: int | None = None,
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

    session_reasons: tuple[GateReason, ...] = ()
    session_evidence_complete = False
    session_output_ready_claim = False
    if real_session_runtime is not None:
        session_reasons = session_runtime_evidence_reasons(
            real_session_runtime,
            requested_decode_steps=requested_decode_steps,
        )
        session_evidence_complete = not session_reasons
        session_output_ready_claim = _session_claims_output_ready(
            real_session_runtime
        )

    if sample_in_any_phase and session_evidence_complete:
        pass
    elif sample_in_any_phase and session_output_ready_claim:
        reasons.extend(session_reasons)
    elif per_kernel_summary is None:
        if require_dispatch_evidence and sample_in_any_phase:
            if real_session_runtime is not None:
                reasons.extend(session_reasons)
            else:
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
