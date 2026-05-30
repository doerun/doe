#!/usr/bin/env python3
"""Validate browser unsupported/fallback reason taxonomy."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


REQUIRED_CODES = {
    "runtime_available",
    "webgpu_runtime_unavailable",
    "hidden_fallback_allowed",
    "fallback_applied",
    "global_disable_active",
    "profile_denylisted",
    "canvas_fusion_artifact_missing",
    "external_texture_artifact_missing",
    "media_path_probe_incomplete",
    "scheduler_artifact_missing",
    "webgpu_effect_artifact_missing",
    "local_ai_artifact_missing",
    "pipeline_cache_artifact_missing",
    "shader_link_artifact_missing",
    "hidden_fallback_applied",
    "diagnostic_sample",
}
REASON_CODE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
VALID_CATEGORIES = {
    "supported",
    "diagnostic",
    "unsupported",
    "fallback",
    "blocked",
    "policy",
    "failure",
}
VALID_CAPABILITIES = {
    "webgpu_runtime",
    "canvas_fusion",
    "external_texture",
    "local_ai",
    "scheduler",
    "webgpu_effect",
    "pipeline_cache",
    "shader_link",
    "capture_policy",
    "cts_subset",
    "recovery_parity",
}
VALID_STATUSES = {"supported", "unsupported", "fallback", "blocked", "diagnostic", "fail"}
CATEGORY_REQUIRED_STATUS = {
    "supported": "supported",
    "diagnostic": "diagnostic",
    "unsupported": "unsupported",
    "fallback": "fallback",
    "blocked": "blocked",
    "failure": "fail",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--taxonomy",
        default="config/browser-unsupported-reason-taxonomy.json",
        help="Browser unsupported reason taxonomy JSON.",
    )
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def check_taxonomy(payload: dict[str, Any]) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    if payload.get("schemaVersion") != 1:
        failures.append(failure("invalid_schema_version", "schemaVersion", "schemaVersion must be 1"))
    if payload.get("artifactKind") != "browser_unsupported_reason_taxonomy":
        failures.append(
            failure(
                "invalid_artifact_kind",
                "artifactKind",
                "artifactKind must be browser_unsupported_reason_taxonomy",
            )
        )
    codes = payload.get("codes")
    if not isinstance(codes, list) or not codes:
        return failures + [failure("missing_codes", "codes", "codes must be a non-empty array")]

    seen: set[str] = set()
    for index, row in enumerate(codes):
        row_path = f"codes[{index}]"
        if not isinstance(row, dict):
            failures.append(failure("invalid_code_row", row_path, "code row must be an object"))
            continue
        code = row.get("reasonCode")
        if not isinstance(code, str) or not code:
            failures.append(failure("missing_reason_code", f"{row_path}.reasonCode", "reasonCode is required"))
        elif not REASON_CODE_RE.fullmatch(code):
            failures.append(failure("invalid_reason_code", f"{row_path}.reasonCode", "reasonCode must use snake_case taxonomy form"))
        elif code in seen:
            failures.append(failure("duplicate_reason_code", f"{row_path}.reasonCode", f"duplicate reasonCode {code}"))
        else:
            seen.add(code)
        category = row.get("category")
        if category not in VALID_CATEGORIES:
            failures.append(failure("invalid_category", f"{row_path}.category", "category must use the browser unsupported reason taxonomy"))
        developer_visible = row.get("developerVisible")
        if not isinstance(developer_visible, bool):
            failures.append(failure("invalid_developer_visible", f"{row_path}.developerVisible", "developerVisible must be boolean"))
        elif developer_visible is False and category != "diagnostic":
            failures.append(failure("nonvisible_reason_not_diagnostic", f"{row_path}.developerVisible", "non-visible reason codes must remain diagnostic-only"))
        if not isinstance(row.get("notes"), str) or not row.get("notes", "").strip():
            failures.append(failure("missing_notes", f"{row_path}.notes", "developer-visible reason codes require notes"))
        capabilities = row.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities:
            failures.append(failure("missing_capabilities", f"{row_path}.capabilities", "capabilities must be non-empty"))
        else:
            for capability_index, capability in enumerate(capabilities):
                if capability not in VALID_CAPABILITIES:
                    failures.append(
                        failure(
                            "invalid_capability",
                            f"{row_path}.capabilities[{capability_index}]",
                            "capability must use the browser unsupported reason taxonomy",
                        )
                    )
            if len(capabilities) != len(set(capabilities)):
                failures.append(failure("duplicate_capability", f"{row_path}.capabilities", "capabilities must be unique"))
        statuses = row.get("statuses")
        if not isinstance(statuses, list) or not statuses:
            failures.append(failure("missing_statuses", f"{row_path}.statuses", "statuses must be non-empty"))
        else:
            for status_index, status in enumerate(statuses):
                if status not in VALID_STATUSES:
                    failures.append(
                        failure(
                            "invalid_status",
                            f"{row_path}.statuses[{status_index}]",
                            "status must use the browser unsupported reason taxonomy",
                        )
                    )
            if len(statuses) != len(set(statuses)):
                failures.append(failure("duplicate_status", f"{row_path}.statuses", "statuses must be unique"))
            required_status = CATEGORY_REQUIRED_STATUS.get(str(category))
            if required_status is not None and required_status not in statuses:
                failures.append(
                    failure(
                        "category_status_mismatch",
                        f"{row_path}.statuses",
                        f"category {category!r} requires status {required_status!r}",
                    )
                )

    for code in sorted(REQUIRED_CODES - seen):
        failures.append(failure("missing_required_reason_code", "codes", f"missing required reasonCode {code}"))
    return failures


def main() -> int:
    args = parse_args()
    failures = check_taxonomy(load_json(Path(args.taxonomy)))
    report = {
        "schemaVersion": 1,
        "artifactKind": "browser_unsupported_reason_taxonomy_check",
        "taxonomyPath": args.taxonomy,
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: browser unsupported reason taxonomy")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: browser unsupported reason taxonomy")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
