#!/usr/bin/env python3
"""Triage directional workloads against the latest compare artifact.

For each workload in a backend's tracked catalog that is currently
``comparable: false`` with empty ``directionalReason``, this script pulls the
matching ``.compare.json`` from the latest ``explore`` (or similar) compare
run, reads the comparability obligations, and derives a concrete reason
string.

The triage produces three classifications:

- ``promotion_candidate``: every blocking/applicable obligation passes
  except ``workload_marked_comparable`` itself. The execution shapes, timing
  classes, timing phases, and hardware paths are all compatible; the workload
  is a candidate for ``comparable=true`` promotion pending a product-meaning
  audit (some "directionals" are intentional single-side coverage even when
  technically compatible).
- ``directional_with_derived_reason``: at least one other blocking obligation
  fails, so the workload is legitimately directional. The derived reason is
  constructed from the failed obligation ids plus any ``details.reason``
  field present.
- ``inconclusive``: no compare-artifact match or the artifact has no
  obligations field; the script cannot classify.

Usage:
    python3 bench/tools/audit_comparability_promotion.py \\
        --catalog bench/workloads/workloads.amd.vulkan.json \\
        --artifact-glob 'bench/out/amd-vulkan/explore/20260412T161500Z/*.compare.json' \\
        [--write-reasons]   # apply derived reasons to the catalog (directional rows only)
        [--dry-run]         # default; print the triage without touching the catalog

The script never promotes a workload to ``comparable=true``. Promotion remains
an explicit human decision; this script only reduces the empty-reason
backlog and lists the promotion candidates.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

OBLIGATION_REASON_HINTS: dict[str, str] = {
    "baseline_comparison_execution_shape_match": "execution shape (dispatch/row/success counts) differs",
    "baseline_comparison_timing_phase_match": "timing-phase coverage differs (zero-vs-material)",
    "baseline_comparison_timing_class_match": "timing classes differ between sides",
    "baseline_comparison_trace_meta_source_match": "timing sources differ between sides",
    "baseline_comparison_timing_selection_policy_match": "timing selection policies differ",
    "baseline_comparison_queue_sync_mode_match": "queue sync modes differ",
    "baseline_comparison_submit_scope_match": "submit scopes differ",
    "baseline_comparison_hardware_path_match": "hardware paths differ",
    "baseline_comparison_upload_buffer_usage_match": "upload buffer usage differs",
    "baseline_comparison_upload_submit_cadence_match": "upload submit cadence differs",
    "baseline_successful_execution_present": "baseline execution unsuccessful on some samples",
    "baseline_execution_errors_absent": "baseline execution reported errors",
    "comparison_execution_errors_absent": "comparison execution reported errors",
    "baseline_comparison_timing_plausibility": "timing values are implausible (near-zero or pathological)",
    "baseline_resource_probe_available": "baseline resource probe unavailable",
    "comparison_resource_probe_available": "comparison resource probe unavailable",
    "left_required_timing_class": "baseline missing required timing class",
    "right_required_timing_class": "comparison missing required timing class",
    "baseline_upload_ignore_first_scope_consistent": "baseline upload ignore-first scope inconsistent",
    "comparison_upload_ignore_first_scope_consistent": "comparison upload ignore-first scope inconsistent",
    "baseline_comparison_explicit_native_shader_artifact_match": "native shader artifacts differ",
    "baseline_native_operation_timing_for_webgpu_ffi": "native operation timing not available for webgpu-ffi path",
}


@dataclass(frozen=True)
class ArtifactMatch:
    artifact_path: Path
    obligations: tuple[dict[str, Any], ...]
    workload_path_asymmetry: bool
    exec_shape_reason: str


@dataclass(frozen=True)
class TriageDecision:
    classification: str
    derived_reason: str
    failed_obligation_ids: tuple[str, ...]
    exec_shape_reason: str
    artifact_path: str


@dataclass
class TriageSummary:
    promotion_candidates: list[tuple[str, TriageDecision]] = field(default_factory=list)
    directional_with_derived_reason: list[tuple[str, TriageDecision]] = field(default_factory=list)
    inconclusive: list[tuple[str, TriageDecision]] = field(default_factory=list)
    already_comparable: list[str] = field(default_factory=list)
    already_has_reason: list[str] = field(default_factory=list)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True, help="Workload catalog JSON path")
    parser.add_argument(
        "--artifact-glob",
        required=True,
        help="Glob matching compare artifact JSONs (quote in shell).",
    )
    parser.add_argument(
        "--write-reasons",
        action="store_true",
        help=(
            "Apply derived reasons to the catalog for directional rows with empty reason. "
            "Never promotes a workload; only fills directionalReason. Omit for dry-run."
        ),
    )
    parser.add_argument(
        "--canonical-catalog",
        type=Path,
        default=None,
        help=(
            "Canonical catalog JSON to update when --write-reasons is set. Required "
            "for persistent updates; per-backend files are generator output and will "
            "be regenerated from this catalog."
        ),
    )
    parser.add_argument(
        "--canonical-source-lane",
        default=None,
        help=(
            "Source lane id in the canonical catalog that produces --catalog "
            "(e.g. amd_vulkan_superset_native_supported, apple_metal_extended, "
            "local_d3d12_extended). Required with --canonical-catalog."
        ),
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=None,
        help="Optional JSON summary output path.",
    )
    return parser.parse_args()


def load_catalog(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "workloads" not in raw:
        raise ValueError(f"expected workload catalog dict with 'workloads' key: {path}")
    return raw


def load_artifact_index(glob_pattern: str) -> dict[str, ArtifactMatch]:
    from glob import glob

    index: dict[str, ArtifactMatch] = {}
    for artifact_path_str in glob(glob_pattern):
        artifact_path = Path(artifact_path_str)
        try:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        for w in payload.get("workloads", []) or []:
            if not isinstance(w, dict):
                continue
            workload_id = w.get("id")
            if not isinstance(workload_id, str):
                continue
            comparability = w.get("comparability") or {}
            obligations = tuple(
                o for o in (comparability.get("obligations") or []) if isinstance(o, dict)
            )
            exec_shape_reason = ""
            for o in obligations:
                if o.get("id") == "baseline_comparison_execution_shape_match":
                    details = o.get("details") or {}
                    if isinstance(details, dict):
                        reason = details.get("comparisonReason") or details.get("reason") or ""
                        if isinstance(reason, str):
                            exec_shape_reason = reason
                    break
            index[workload_id] = ArtifactMatch(
                artifact_path=artifact_path,
                obligations=obligations,
                workload_path_asymmetry=bool(w.get("pathAsymmetry")),
                exec_shape_reason=exec_shape_reason,
            )
    return index


def classify(
    workload_id: str,
    artifact: ArtifactMatch,
) -> TriageDecision:
    failed_ids: list[str] = []
    reason_parts: list[str] = []
    for o in artifact.obligations:
        obligation_id = o.get("id")
        if not isinstance(obligation_id, str):
            continue
        if o.get("blocking") is not True or o.get("applicable") is not True:
            continue
        if o.get("passes") is True:
            continue
        if obligation_id == "workload_marked_comparable":
            # This is the reason we are looking at the row; not a real failure.
            continue
        failed_ids.append(obligation_id)
        hint = OBLIGATION_REASON_HINTS.get(obligation_id)
        if hint:
            reason_parts.append(hint)
        else:
            reason_parts.append(f"obligation {obligation_id} failed")

    if artifact.workload_path_asymmetry and "hardware path asymmetry" not in " ".join(reason_parts):
        reason_parts.append("hardware path asymmetry declared on the workload")

    if not failed_ids and not artifact.workload_path_asymmetry:
        return TriageDecision(
            classification="promotion_candidate",
            derived_reason="",
            failed_obligation_ids=(),
            exec_shape_reason=artifact.exec_shape_reason,
            artifact_path=str(artifact.artifact_path),
        )

    seen: set[str] = set()
    unique_parts: list[str] = []
    for part in reason_parts:
        if part not in seen:
            seen.add(part)
            unique_parts.append(part)

    derived = "; ".join(unique_parts)
    if artifact.exec_shape_reason and artifact.exec_shape_reason not in derived:
        derived = f"{derived}; {artifact.exec_shape_reason}" if derived else artifact.exec_shape_reason

    return TriageDecision(
        classification="directional_with_derived_reason",
        derived_reason=derived,
        failed_obligation_ids=tuple(failed_ids),
        exec_shape_reason=artifact.exec_shape_reason,
        artifact_path=str(artifact.artifact_path),
    )


def run_triage(catalog: dict[str, Any], artifact_index: dict[str, ArtifactMatch]) -> TriageSummary:
    summary = TriageSummary()
    for workload in catalog.get("workloads", []) or []:
        if not isinstance(workload, dict):
            continue
        workload_id = workload.get("id")
        if not isinstance(workload_id, str):
            continue
        if workload.get("comparable"):
            summary.already_comparable.append(workload_id)
            continue
        existing_reason = str(workload.get("directionalReason") or "").strip()
        if existing_reason:
            summary.already_has_reason.append(workload_id)
            continue
        artifact = artifact_index.get(workload_id)
        if artifact is None:
            summary.inconclusive.append(
                (
                    workload_id,
                    TriageDecision(
                        classification="inconclusive",
                        derived_reason="no matching compare artifact in the glob",
                        failed_obligation_ids=(),
                        exec_shape_reason="",
                        artifact_path="",
                    ),
                )
            )
            continue
        decision = classify(workload_id, artifact)
        if decision.classification == "promotion_candidate":
            summary.promotion_candidates.append((workload_id, decision))
        elif decision.classification == "directional_with_derived_reason":
            summary.directional_with_derived_reason.append((workload_id, decision))
        else:
            summary.inconclusive.append((workload_id, decision))
    return summary


def derive_reason_for_promotion_candidate(artifact_path: str) -> str:
    return (
        "promotion candidate: every blocking comparability obligation passes "
        f"against {artifact_path}; pending product-meaning audit before flipping "
        "comparable=true"
    )


def derive_reason_for_inconclusive(artifact_glob: str) -> str:
    return (
        "coverage gap: no matching compare artifact in the latest triaged corpus "
        f"({artifact_glob}); re-run the explore preset to produce an artifact "
        "before triage"
    )


def _effective_lane_field(item: dict[str, Any], lane_id: str, key: str, default: Any) -> Any:
    lane_override = (item.get("lanes") or {}).get(lane_id) or {}
    if isinstance(lane_override, dict) and key in lane_override:
        return lane_override[key]
    shared = item.get("shared") or {}
    if isinstance(shared, dict) and key in shared:
        return shared[key]
    return default


def apply_reasons_canonical(
    canonical_catalog: dict[str, Any],
    lane_id: str,
    directional_decisions: list[tuple[str, TriageDecision]],
    promotion_candidates: list[tuple[str, TriageDecision]],
    inconclusive_decisions: list[tuple[str, TriageDecision]],
    artifact_glob: str,
) -> int:
    by_id: dict[str, str] = {}
    for wid, dec in directional_decisions:
        if dec.derived_reason:
            by_id[wid] = dec.derived_reason
    for wid, dec in promotion_candidates:
        by_id[wid] = derive_reason_for_promotion_candidate(dec.artifact_path)
    for wid, dec in inconclusive_decisions:
        by_id.setdefault(wid, derive_reason_for_inconclusive(artifact_glob))

    applied = 0
    for item in canonical_catalog.get("workloads", []) or []:
        if not isinstance(item, dict):
            continue
        workload_id = item.get("id")
        if not isinstance(workload_id, str):
            continue
        if workload_id not in by_id:
            continue
        if lane_id not in (item.get("lanes") or {}):
            continue
        effective_comparable = bool(_effective_lane_field(item, lane_id, "comparable", False))
        if effective_comparable:
            continue
        effective_reason = str(_effective_lane_field(item, lane_id, "directionalReason", "") or "").strip()
        if effective_reason:
            continue
        lane_override = (item["lanes"][lane_id] or {})
        if not isinstance(lane_override, dict):
            continue
        lane_override["directionalReason"] = by_id[workload_id]
        item["lanes"][lane_id] = lane_override

        field_order = item.get("fieldOrder")
        if isinstance(field_order, list) and "directionalReason" not in field_order:
            insert_at = len(field_order)
            for anchor in ("benchmarkClass", "comparable"):
                if anchor in field_order:
                    insert_at = field_order.index(anchor) + 1
                    break
            field_order.insert(insert_at, "directionalReason")

        applied += 1
    return applied


def apply_reasons(
    catalog: dict[str, Any],
    directional_decisions: list[tuple[str, TriageDecision]],
    promotion_candidates: list[tuple[str, TriageDecision]] | None = None,
    inconclusive_decisions: list[tuple[str, TriageDecision]] | None = None,
    artifact_glob: str = "",
) -> int:
    applied = 0
    directional_by_id = {wid: dec for wid, dec in directional_decisions}
    candidate_by_id = {wid: dec for wid, dec in (promotion_candidates or [])}
    inconclusive_by_id = {wid: dec for wid, dec in (inconclusive_decisions or [])}
    for workload in catalog.get("workloads", []) or []:
        if not isinstance(workload, dict):
            continue
        workload_id = workload.get("id")
        if not isinstance(workload_id, str):
            continue
        if workload.get("comparable"):
            continue
        if str(workload.get("directionalReason") or "").strip():
            continue
        decision = directional_by_id.get(workload_id)
        if decision is not None and decision.derived_reason:
            workload["directionalReason"] = decision.derived_reason
            applied += 1
            continue
        candidate = candidate_by_id.get(workload_id)
        if candidate is not None:
            workload["directionalReason"] = derive_reason_for_promotion_candidate(
                candidate.artifact_path
            )
            applied += 1
            continue
        inconclusive = inconclusive_by_id.get(workload_id)
        if inconclusive is not None and artifact_glob:
            workload["directionalReason"] = derive_reason_for_inconclusive(artifact_glob)
            applied += 1
    return applied


def format_summary(summary: TriageSummary) -> str:
    lines: list[str] = []
    lines.append(f"promotion_candidates: {len(summary.promotion_candidates)}")
    for wid, dec in summary.promotion_candidates:
        lines.append(f"  + {wid}  ({dec.artifact_path})")
    lines.append("")
    lines.append(f"directional_with_derived_reason: {len(summary.directional_with_derived_reason)}")
    for wid, dec in summary.directional_with_derived_reason:
        lines.append(f"  ~ {wid}")
        lines.append(f"      reason: {dec.derived_reason}")
    lines.append("")
    lines.append(f"inconclusive: {len(summary.inconclusive)}")
    for wid, dec in summary.inconclusive:
        lines.append(f"  ? {wid}  ({dec.derived_reason or dec.classification})")
    lines.append("")
    lines.append(f"already_comparable (skipped): {len(summary.already_comparable)}")
    lines.append(f"already_has_reason (skipped): {len(summary.already_has_reason)}")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    catalog_path: Path = args.catalog
    if not catalog_path.exists():
        sys.stderr.write(f"catalog not found: {catalog_path}\n")
        return 1
    catalog = load_catalog(catalog_path)
    artifact_index = load_artifact_index(args.artifact_glob)
    summary = run_triage(catalog, artifact_index)

    sys.stdout.write(format_summary(summary))
    sys.stdout.write("\n")

    if args.write_reasons:
        if args.canonical_catalog is None:
            sys.stderr.write(
                "--write-reasons requires --canonical-catalog (per-backend files "
                "are generator output). Aborting without changes.\n"
            )
            return 3
        if args.canonical_source_lane is None:
            sys.stderr.write(
                "--canonical-catalog requires --canonical-source-lane to name which "
                "lane in the canonical catalog emits this per-backend file.\n"
            )
            return 3
        canonical_path: Path = args.canonical_catalog
        canonical_catalog = json.loads(canonical_path.read_text(encoding="utf-8"))
        applied = apply_reasons_canonical(
            canonical_catalog,
            args.canonical_source_lane,
            summary.directional_with_derived_reason,
            summary.promotion_candidates,
            summary.inconclusive,
            args.artifact_glob,
        )
        canonical_path.write_text(
            json.dumps(canonical_catalog, indent=2) + "\n", encoding="utf-8"
        )
        sys.stdout.write(
            f"applied directionalReason to {applied} workload(s) on lane "
            f"{args.canonical_source_lane} in {canonical_path}\n"
        )

    if args.summary_out:
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "promotionCandidates": [wid for wid, _ in summary.promotion_candidates],
            "directionalWithDerivedReason": [
                {"id": wid, "reason": dec.derived_reason} for wid, dec in summary.directional_with_derived_reason
            ],
            "inconclusive": [
                {"id": wid, "reason": dec.derived_reason} for wid, dec in summary.inconclusive
            ],
            "alreadyComparable": summary.already_comparable,
            "alreadyHasReason": summary.already_has_reason,
        }
        args.summary_out.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
