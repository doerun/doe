#!/usr/bin/env python3
"""Check invalid WGSL diagnostic fixture contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", required=True, help="WGSL diagnostic fixture JSON path.")
    parser.add_argument("--manifest", required=True, help="WGSL corpus manifest JSON path.")
    parser.add_argument("--taxonomy", required=True, help="Shader error taxonomy JSON path.")
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def safe_repo_path(path_text: str) -> bool:
    path = PurePosixPath(path_text)
    return bool(path_text) and not path.is_absolute() and ".." not in path.parts


def check_fixtures(
    fixtures: dict[str, Any],
    manifest: dict[str, Any],
    taxonomy: dict[str, Any],
) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    manifest_by_shader = {
        row.get("shaderId"): row
        for row in manifest.get("rows", [])
        if isinstance(row, dict)
    }
    invalid_shader_ids = {
        row.get("shaderId")
        for row in manifest.get("rows", [])
        if isinstance(row, dict) and row.get("expectedValidity") == "invalid"
    }
    fixture_shader_ids: set[str] = set()
    taxonomy_codes = {
        code.get("code"): code
        for code in taxonomy.get("codes", [])
        if isinstance(code, dict)
    }

    for row_index, row in enumerate(fixtures.get("rows", [])):
        if not isinstance(row, dict):
            continue
        row_path = f"rows[{row_index}]"
        shader_id = row.get("shaderId")
        fixture_shader_ids.add(shader_id)
        source_path = row.get("sourcePath")
        if isinstance(source_path, str) and source_path and not safe_repo_path(source_path):
            failures.append(
                failure(
                    "unsafe_source_path",
                    f"{row_path}.sourcePath",
                    "sourcePath must be repo-relative",
                )
            )
        manifest_row = manifest_by_shader.get(shader_id)
        if not isinstance(manifest_row, dict) or manifest_row.get("expectedValidity") != "invalid":
            failures.append(
                failure(
                    "missing_invalid_manifest_row",
                    f"{row_path}.shaderId",
                    f"fixture shader {shader_id!r} does not map to an invalid manifest row",
                )
            )
            continue
        for field in ("sourcePath", "normalizedSourceSha256", "expectedDiagnosticCategory"):
            if row.get(field) != manifest_row.get(field):
                failures.append(
                    failure(
                        "manifest_fixture_mismatch",
                        f"{row_path}.{field}",
                        f"fixture {field} does not match manifest row",
                    )
                )

        expected = row.get("expected", {})
        doe_expected = expected.get("doe", {}) if isinstance(expected, dict) else {}
        taxonomy_code = doe_expected.get("taxonomyCode") if isinstance(doe_expected, dict) else None
        taxonomy_entry = taxonomy_codes.get(taxonomy_code)
        if not isinstance(taxonomy_entry, dict):
            failures.append(
                failure(
                    "unknown_taxonomy_code",
                    f"{row_path}.expected.doe.taxonomyCode",
                    f"unknown shader taxonomy code {taxonomy_code!r}",
                )
            )
        elif taxonomy_entry.get("stage") != doe_expected.get("stage"):
            failures.append(
                failure(
                    "taxonomy_stage_mismatch",
                    f"{row_path}.expected.doe.stage",
                    f"taxonomy stage for {taxonomy_code} is {taxonomy_entry.get('stage')!r}",
                )
            )

        evidence_policy = row.get("evidencePolicy", {})
        if not isinstance(evidence_policy, dict) or evidence_policy.get("freeFormTextCompared") is not False:
            failures.append(
                failure(
                    "free_form_text_comparison",
                    f"{row_path}.evidencePolicy.freeFormTextCompared",
                    "diagnostic fixtures must compare typed categories, not free-form text",
                )
            )

    for shader_id in sorted(invalid_shader_ids - fixture_shader_ids):
        failures.append(
            failure(
                "missing_invalid_fixture",
                "rows",
                f"missing diagnostic fixture for invalid shader {shader_id}",
            )
        )

    return failures


def main() -> int:
    args = parse_args()
    failures = check_fixtures(
        load_json(Path(args.fixtures)),
        load_json(Path(args.manifest)),
        load_json(Path(args.taxonomy)),
    )
    report = {
        "schemaVersion": 1,
        "artifactKind": "wgsl_diagnostic_fixtures_check",
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: WGSL diagnostic fixtures")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: WGSL diagnostic fixtures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
