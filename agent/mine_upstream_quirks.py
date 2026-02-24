#!/usr/bin/env python3
"""Deterministic upstream quirk mining for toggle-style driver workarounds."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OBSERVED_AT = "1970-01-01T00:00:00Z"
DEFAULT_ALLOWED_SUFFIXES = {
    ".cc",
    ".cpp",
    ".c",
    ".h",
    ".hpp",
    ".mm",
    ".m",
    ".rs",
    ".zig",
}
TOGGLE_RE = re.compile(r"\bToggle::([A-Za-z0-9_]+)\b")
HASH_SEED = "0" * 64


@dataclass(frozen=True)
class ToggleHit:
    root: Path
    source_path: Path
    toggle: str
    line: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-root",
        action="append",
        default=[],
        help="Source root to scan recursively. May be repeated.",
    )
    parser.add_argument(
        "--source-repo",
        required=True,
        help="Upstream repo identifier stored in provenance (for example dawn/main).",
    )
    parser.add_argument(
        "--source-commit",
        required=True,
        help="Upstream source commit stored in provenance.",
    )
    parser.add_argument("--vendor", required=True, help="Quirk match.vendor value.")
    parser.add_argument(
        "--api",
        required=True,
        choices=["vulkan", "metal", "d3d12", "webgpu"],
        help="Quirk match.api value.",
    )
    parser.add_argument(
        "--device-family",
        default="",
        help="Optional quirk match.deviceFamily value.",
    )
    parser.add_argument(
        "--driver-range",
        default="",
        help="Optional quirk match.driverRange value.",
    )
    parser.add_argument(
        "--observed-at",
        default=DEFAULT_OBSERVED_AT,
        help=(
            "RFC3339 timestamp for provenance.observedAt. "
            "Default is deterministic for reproducible fixtures."
        ),
    )
    parser.add_argument(
        "--allow-suffix",
        action="append",
        default=[],
        help="Allowed file suffix (including dot). May be repeated.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output path for mined quirk JSON array (quirks.schema records).",
    )
    parser.add_argument(
        "--manifest-output",
        required=True,
        help="Output path for mining manifest JSON.",
    )
    return parser.parse_args()


def normalize_suffixes(raw: list[str]) -> set[str]:
    if raw:
        normalized: set[str] = set()
        for suffix in raw:
            token = suffix.strip()
            if not token:
                continue
            if not token.startswith("."):
                token = "." + token
            normalized.add(token.lower())
        if normalized:
            return normalized
    return set(DEFAULT_ALLOWED_SUFFIXES)


def rfc3339_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def short_path_hash(path_value: str) -> str:
    return hashlib.sha256(path_value.encode("utf-8")).hexdigest()[:10]


def candidate_quirk_id(
    *,
    vendor: str,
    api: str,
    toggle: str,
    source_path: str,
) -> str:
    path_token = short_path_hash(source_path)
    return (
        "auto."
        + vendor.lower().replace(" ", "_")
        + "."
        + api.lower()
        + ".toggle."
        + toggle.lower()
        + "."
        + path_token
    )


def build_match_object(
    *,
    vendor: str,
    api: str,
    device_family: str,
    driver_range: str,
) -> dict[str, str]:
    result: dict[str, str] = {"vendor": vendor, "api": api}
    if device_family:
        result["deviceFamily"] = device_family
    if driver_range:
        result["driverRange"] = driver_range
    return result


def build_candidate(
    *,
    toggle: str,
    source_repo: str,
    source_path: str,
    source_commit: str,
    vendor: str,
    api: str,
    device_family: str,
    driver_range: str,
    observed_at: str,
) -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "quirkId": candidate_quirk_id(
            vendor=vendor,
            api=api,
            toggle=toggle,
            source_path=source_path,
        ),
        "scope": "driver_toggle",
        "match": build_match_object(
            vendor=vendor,
            api=api,
            device_family=device_family,
            driver_range=driver_range,
        ),
        "action": {
            "kind": "toggle",
            "params": {
                "toggle": toggle,
            },
        },
        "safetyClass": "moderate",
        "verificationMode": "guard_only",
        "proofLevel": "guarded",
        "provenance": {
            "sourceRepo": source_repo,
            "sourcePath": source_path,
            "sourceCommit": source_commit,
            "observedAt": observed_at,
        },
    }


def iter_candidate_files(root: Path, allowed_suffixes: set[str]) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in allowed_suffixes:
            continue
        files.append(path)
    files.sort(key=lambda item: str(item))
    return files


def extract_toggle_hits(
    *,
    root: Path,
    candidate_files: list[Path],
) -> list[ToggleHit]:
    hits: list[ToggleHit] = []
    for path in candidate_files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for match in TOGGLE_RE.finditer(text):
            toggle = match.group(1)
            line = text.count("\n", 0, match.start()) + 1
            hits.append(
                ToggleHit(
                    root=root,
                    source_path=path,
                    toggle=toggle,
                    line=line,
                )
            )
    hits.sort(
        key=lambda item: (
            str(item.source_path),
            item.line,
            item.toggle.lower(),
        )
    )
    return hits


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_hash_chain(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    previous_hash = HASH_SEED
    for idx, candidate in enumerate(candidates):
        candidate_blob = canonical_json(candidate)
        row_hash = hashlib.sha256(
            (previous_hash + ":" + candidate_blob).encode("utf-8")
        ).hexdigest()
        rows.append(
            {
                "index": idx,
                "quirkId": str(candidate.get("quirkId", "")),
                "hash": row_hash,
                "previousHash": previous_hash,
            }
        )
        previous_hash = row_hash
    return {
        "algorithm": "sha256",
        "seedHash": HASH_SEED,
        "finalHash": previous_hash,
        "rowCount": len(rows),
        "rows": rows,
    }


def main() -> int:
    args = parse_args()
    if not args.source_root:
        print("FAIL: at least one --source-root is required")
        return 1

    roots: list[Path] = []
    for raw in args.source_root:
        root = Path(raw)
        if not root.exists() or not root.is_dir():
            print(f"FAIL: invalid --source-root (missing directory): {root}")
            return 1
        roots.append(root.resolve())
    roots.sort(key=lambda item: str(item))

    allowed_suffixes = normalize_suffixes(args.allow_suffix)
    all_hits: list[ToggleHit] = []
    scanned_files = 0
    for root in roots:
        files = iter_candidate_files(root, allowed_suffixes)
        scanned_files += len(files)
        all_hits.extend(
            extract_toggle_hits(
                root=root,
                candidate_files=files,
            )
        )

    candidates: list[dict[str, Any]] = []
    hit_rows: list[dict[str, Any]] = []
    for hit in all_hits:
        try:
            source_path = str(hit.source_path.relative_to(hit.root))
        except ValueError:
            source_path = str(hit.source_path)
        candidates.append(
            build_candidate(
                toggle=hit.toggle,
                source_repo=args.source_repo,
                source_path=source_path,
                source_commit=args.source_commit,
                vendor=args.vendor,
                api=args.api,
                device_family=args.device_family,
                driver_range=args.driver_range,
                observed_at=args.observed_at,
            )
        )
        hit_rows.append(
            {
                "toggle": hit.toggle,
                "sourcePath": source_path,
                "line": hit.line,
            }
        )

    # Deterministic candidate ordering for reproducible artifacts.
    candidates.sort(
        key=lambda item: (
            str(item.get("quirkId", "")),
            str(item.get("provenance", {}).get("sourcePath", "")),
        )
    )
    hit_rows.sort(
        key=lambda item: (
            str(item.get("sourcePath", "")),
            int(item.get("line", 0)),
            str(item.get("toggle", "")).lower(),
        )
    )

    write_json(Path(args.output), candidates)
    manifest_payload = {
        "schemaVersion": 1,
        "generatedAtUtc": rfc3339_now(),
        "sourceRepo": args.source_repo,
        "sourceCommit": args.source_commit,
        "sourceRoots": [str(root) for root in roots],
        "vendor": args.vendor,
        "api": args.api,
        "deviceFamily": args.device_family,
        "driverRange": args.driver_range,
        "observedAt": args.observed_at,
        "allowedSuffixes": sorted(allowed_suffixes),
        "scannedFileCount": scanned_files,
        "toggleHitCount": len(hit_rows),
        "candidateCount": len(candidates),
        "hashChain": build_hash_chain(candidates),
        "toggleHits": hit_rows,
        "candidateOutputPath": str(Path(args.output)),
    }
    write_json(Path(args.manifest_output), manifest_payload)

    print("PASS: mined upstream quirks")
    print(f"candidates: {Path(args.output)} ({len(candidates)})")
    print(f"manifest: {Path(args.manifest_output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
