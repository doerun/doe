#!/usr/bin/env python3
"""Check browser-facing WGSL robustness fixture coverage."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_PATTERN_CLASSES = {"bounds", "aliasing", "texture_dimension", "guard"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", required=True, help="WGSL robustness fixture JSON path.")
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def normalize_source(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.endswith("\n"):
        normalized += "\n"
    return normalized


def normalized_sha256(path: Path) -> str:
    return hashlib.sha256(normalize_source(path.read_text(encoding="utf-8")).encode("utf-8")).hexdigest()


def failure(code: str, path: str, message: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message}


def safe_repo_path(path_text: str) -> bool:
    path = PurePosixPath(path_text)
    return bool(path_text) and not path.is_absolute() and ".." not in path.parts


def resolve_repo_path(repo_root: Path, path_text: str) -> Path:
    return repo_root.joinpath(*PurePosixPath(path_text).parts)


def check_fixtures(payload: dict[str, Any], *, repo_root: Path = REPO_ROOT) -> list[dict[str, str]]:
    failures: list[dict[str, str]] = []
    rows = [row for row in payload.get("rows", []) if isinstance(row, dict)]
    pattern_classes = {str(row.get("patternClass")) for row in rows}
    for pattern_class in sorted(REQUIRED_PATTERN_CLASSES - pattern_classes):
        failures.append(failure("missing_pattern_class", "rows", f"missing robustness fixture class {pattern_class}"))

    seen_fixture_ids: set[str] = set()
    for row_index, row in enumerate(rows):
        row_path = f"rows[{row_index}]"
        fixture_id = str(row.get("fixtureId", ""))
        if fixture_id in seen_fixture_ids:
            failures.append(failure("duplicate_fixture_id", f"{row_path}.fixtureId", f"duplicate fixture id {fixture_id!r}"))
        seen_fixture_ids.add(fixture_id)

        source_path_text = str(row.get("sourcePath", ""))
        if not safe_repo_path(source_path_text):
            failures.append(
                failure(
                    "unsafe_source_path",
                    f"{row_path}.sourcePath",
                    "sourcePath must be repo-relative",
                )
            )
            continue
        source_path = resolve_repo_path(repo_root, source_path_text)
        if not source_path.is_file():
            failures.append(failure("source_not_found", f"{row_path}.sourcePath", f"source path not found: {source_path}"))
            continue
        source_text = normalize_source(source_path.read_text(encoding="utf-8"))
        actual_hash = normalized_sha256(source_path)
        if actual_hash != row.get("normalizedSourceSha256"):
            failures.append(
                failure(
                    "source_hash_mismatch",
                    f"{row_path}.normalizedSourceSha256",
                    f"expected {row.get('normalizedSourceSha256')}, got {actual_hash}",
                )
            )
        for needle in row.get("requiredNeedles", []):
            if isinstance(needle, str) and needle not in source_text:
                failures.append(
                    failure(
                        "missing_required_needle",
                        f"{row_path}.requiredNeedles",
                        f"fixture source does not contain {needle!r}",
                    )
                )

    return failures


def main() -> int:
    args = parse_args()
    failures = check_fixtures(load_json(Path(args.fixtures)))
    report = {
        "schemaVersion": 1,
        "artifactKind": "wgsl_robustness_fixtures_check",
        "status": "fail" if failures else "pass",
        "failures": failures,
    }
    if args.emit_json:
        print(json.dumps(report, indent=2))
    elif failures:
        print("FAIL: WGSL robustness fixtures")
        for item in failures:
            print(f"- {item['code']}: {item['path']}: {item['message']}")
    else:
        print("PASS: WGSL robustness fixtures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
