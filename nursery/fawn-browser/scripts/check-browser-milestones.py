#!/usr/bin/env python3
"""Validate browser milestone manifest and report local evidence coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
VALID_STATUSES = {
    "planned",
    "in_progress",
    "local_evidence",
    "ready_for_promotion",
    "promoted",
    "blocked",
}
VALID_TRACKS = {"track_a", "track_b", "promotion"}
VALID_KINDS = {"doc", "contract", "script", "schema", "manifest", "artifact", "report", "note"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        default=str(REPO_ROOT / "nursery/fawn-browser/bench/workflows/browser-milestones.json"),
        help="Path to browser milestone manifest JSON.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="emit_json",
        help="Emit JSON summary instead of text.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing non-empty string: {label}")
    return value


def require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"missing bool: {label}")
    return value


def require_string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"missing list: {label}")
    items: list[str] = []
    for index, item in enumerate(value):
        items.append(require_string(item, f"{label}[{index}]"))
    return items


def resolve_repo_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    return (REPO_ROOT / candidate).resolve()


def validate_manifest(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []

    schema_version = payload.get("schemaVersion")
    if schema_version != 1:
        errors.append(f"invalid schemaVersion: expected 1, got {schema_version}")

    statuses = payload.get("statuses")
    if not isinstance(statuses, list) or not statuses:
        errors.append("missing non-empty statuses[]")
    else:
        seen_statuses: set[str] = set()
        for index, status in enumerate(statuses):
            try:
                status_value = require_string(status, f"statuses[{index}]")
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if status_value not in VALID_STATUSES:
                errors.append(f"invalid status in statuses[]: {status_value}")
            if status_value in seen_statuses:
                errors.append(f"duplicate status in statuses[]: {status_value}")
            seen_statuses.add(status_value)

    milestones_raw = payload.get("milestones")
    if not isinstance(milestones_raw, list) or not milestones_raw:
        errors.append("missing non-empty milestones[]")
        return [], errors

    milestones: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, milestone_raw in enumerate(milestones_raw):
        if not isinstance(milestone_raw, dict):
            errors.append(f"invalid milestones[{index}] object")
            continue

        try:
            milestone_id = require_string(milestone_raw.get("id"), f"milestones[{index}].id")
            title = require_string(milestone_raw.get("title"), f"milestones[{index}].title")
            track = require_string(milestone_raw.get("track"), f"milestones[{index}].track")
            status = require_string(milestone_raw.get("status"), f"milestones[{index}].status")
            summary = require_string(milestone_raw.get("summary"), f"milestones[{index}].summary")
            dependencies = require_string_list(
                milestone_raw.get("dependencies"), f"milestones[{index}].dependencies"
            )
            exit_criteria = require_string_list(
                milestone_raw.get("exitCriteria"), f"milestones[{index}].exitCriteria"
            )
            blockers = require_string_list(
                milestone_raw.get("blockers"), f"milestones[{index}].blockers"
            )
            next_actions = require_string_list(
                milestone_raw.get("nextActions"), f"milestones[{index}].nextActions"
            )
        except ValueError as exc:
            errors.append(str(exc))
            continue

        if milestone_id in seen_ids:
            errors.append(f"duplicate milestone id: {milestone_id}")
        seen_ids.add(milestone_id)

        if milestone_id not in {f"M{value}" for value in range(7)}:
            errors.append(f"invalid milestone id: {milestone_id}")
        if track not in VALID_TRACKS:
            errors.append(f"invalid track for {milestone_id}: {track}")
        if status not in VALID_STATUSES:
            errors.append(f"invalid status for {milestone_id}: {status}")

        evidence_rows: list[dict[str, Any]] = []
        evidence_raw = milestone_raw.get("evidence")
        if not isinstance(evidence_raw, list):
            errors.append(f"missing list: milestones[{index}].evidence")
            evidence_raw = []

        seen_evidence_ids: set[str] = set()
        for evidence_index, evidence_item in enumerate(evidence_raw):
            if not isinstance(evidence_item, dict):
                errors.append(
                    f"invalid evidence object: milestones[{index}].evidence[{evidence_index}]"
                )
                continue
            try:
                evidence_id = require_string(
                    evidence_item.get("id"),
                    f"milestones[{index}].evidence[{evidence_index}].id",
                )
                kind = require_string(
                    evidence_item.get("kind"),
                    f"milestones[{index}].evidence[{evidence_index}].kind",
                )
                path = require_string(
                    evidence_item.get("path"),
                    f"milestones[{index}].evidence[{evidence_index}].path",
                )
                description = require_string(
                    evidence_item.get("description"),
                    f"milestones[{index}].evidence[{evidence_index}].description",
                )
                required = require_bool(
                    evidence_item.get("required"),
                    f"milestones[{index}].evidence[{evidence_index}].required",
                )
                must_exist = require_bool(
                    evidence_item.get("mustExist"),
                    f"milestones[{index}].evidence[{evidence_index}].mustExist",
                )
            except ValueError as exc:
                errors.append(str(exc))
                continue

            if evidence_id in seen_evidence_ids:
                errors.append(f"duplicate evidence id in {milestone_id}: {evidence_id}")
            seen_evidence_ids.add(evidence_id)

            if kind not in VALID_KINDS:
                errors.append(f"invalid evidence kind in {milestone_id}: {kind}")

            evidence_rows.append(
                {
                    "id": evidence_id,
                    "kind": kind,
                    "path": path,
                    "description": description,
                    "required": required,
                    "mustExist": must_exist,
                }
            )

        milestones.append(
            {
                "id": milestone_id,
                "title": title,
                "track": track,
                "status": status,
                "summary": summary,
                "dependencies": dependencies,
                "evidence": evidence_rows,
                "exitCriteria": exit_criteria,
                "blockers": blockers,
                "nextActions": next_actions,
            }
        )

    milestone_ids = {row["id"] for row in milestones}
    for milestone in milestones:
        for dependency in milestone["dependencies"]:
            if dependency not in milestone_ids:
                errors.append(f"{milestone['id']} references unknown dependency: {dependency}")

    return milestones, errors


def build_summary(milestones: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    status_counts = {status: 0 for status in VALID_STATUSES}
    track_counts = {track: 0 for track in VALID_TRACKS}
    missing_required_paths: list[str] = []
    missing_optional_paths: list[str] = []
    milestone_rows: list[dict[str, Any]] = []

    for milestone in milestones:
        status_counts[milestone["status"]] += 1
        track_counts[milestone["track"]] += 1

        evidence_rows: list[dict[str, Any]] = []
        present_count = 0
        required_count = 0
        for evidence in milestone["evidence"]:
            resolved = resolve_repo_path(evidence["path"])
            exists = resolved.exists()
            if exists:
                present_count += 1
            if evidence["required"]:
                required_count += 1
            if evidence["mustExist"] and not exists:
                message = f"{milestone['id']} missing required local evidence: {evidence['path']}"
                errors.append(message)
                missing_required_paths.append(evidence["path"])
            elif not exists:
                missing_optional_paths.append(evidence["path"])

            evidence_rows.append(
                {
                    "id": evidence["id"],
                    "kind": evidence["kind"],
                    "path": evidence["path"],
                    "exists": exists,
                    "required": evidence["required"],
                    "mustExist": evidence["mustExist"],
                }
            )

        milestone_rows.append(
            {
                "id": milestone["id"],
                "title": milestone["title"],
                "track": milestone["track"],
                "status": milestone["status"],
                "dependencyCount": len(milestone["dependencies"]),
                "blockerCount": len(milestone["blockers"]),
                "evidencePresentCount": present_count,
                "evidenceCount": len(milestone["evidence"]),
                "requiredEvidenceCount": required_count,
                "evidence": evidence_rows,
            }
        )

    return {
        "ok": not errors,
        "errorCount": len(errors),
        "errors": errors,
        "statusCounts": status_counts,
        "trackCounts": track_counts,
        "missingRequiredEvidencePaths": sorted(set(missing_required_paths)),
        "missingOptionalEvidencePaths": sorted(set(missing_optional_paths)),
        "milestones": milestone_rows,
    }


def emit_text(summary: dict[str, Any]) -> None:
    print(f"ok: {summary['ok']}")
    print(f"errors: {summary['errorCount']}")
    print("status counts:")
    for status, count in sorted(summary["statusCounts"].items()):
        print(f"  {status}: {count}")
    print("track counts:")
    for track, count in sorted(summary["trackCounts"].items()):
        print(f"  {track}: {count}")
    if summary["missingRequiredEvidencePaths"]:
        print("missing required local evidence:")
        for path in summary["missingRequiredEvidencePaths"]:
            print(f"  {path}")
    if summary["errors"]:
        print("errors:")
        for error in summary["errors"]:
            print(f"  {error}")


def main() -> int:
    args = parse_args()
    payload = load_json(Path(args.manifest).resolve())
    milestones, errors = validate_manifest(payload)
    summary = build_summary(milestones, errors)

    if args.emit_json:
      print(json.dumps(summary, indent=2))
    else:
      emit_text(summary)

    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
