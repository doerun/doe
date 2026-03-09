#!/usr/bin/env python3
"""Validate module prototype fixtures and determinism."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from module_prototype import (
    MODULE_INCUBATION_ROOT,
    POLICY_PATH,
    RUNNERS,
    load_json,
    stable_hash,
    validate_payload,
)


DEFAULT_FIXTURES_DIR = MODULE_INCUBATION_ROOT / "fixtures"
DEFAULT_ARTIFACTS_DIR = MODULE_INCUBATION_ROOT.parent / "artifacts"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures-dir", default=str(DEFAULT_FIXTURES_DIR))
    parser.add_argument("--policy", default=str(POLICY_PATH))
    parser.add_argument("--out", default="", help="Optional report path.")
    parser.add_argument("--json", action="store_true", dest="emit_json")
    return parser.parse_args()


def timestamp_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def default_out_path() -> Path:
    return DEFAULT_ARTIFACTS_DIR / timestamp_id() / "module-prototype-check.json"


def main() -> int:
    args = parse_args()
    fixtures_dir = Path(args.fixtures_dir).resolve()
    policy_payload = load_json(Path(args.policy).resolve())
    fixture_paths = sorted(fixtures_dir.glob("*.request.json"))
    rows: list[dict[str, object]] = []
    errors: list[str] = []

    for fixture_path in fixture_paths:
        request_payload = load_json(fixture_path)
        module_id = request_payload.get("moduleId")
        if module_id not in RUNNERS:
            errors.append(f"unsupported module in fixture: {fixture_path.name}")
            continue
        try:
            validate_payload(module_id, request_payload)
            request_hash = stable_hash(request_payload)
            policy_hash = stable_hash(policy_payload)
            first = RUNNERS[module_id](request_payload, policy_payload, request_hash, policy_hash)
            second = RUNNERS[module_id](request_payload, policy_payload, request_hash, policy_hash)
            validate_payload(module_id, first)
            deterministic = stable_hash(first) == stable_hash(second)
            if not deterministic:
                errors.append(f"non-deterministic prototype output: {fixture_path.name}")
            fallback_stats = first.get("qualityStats") or first.get("fallbackStats") or {}
            fallback_count = fallback_stats.get("fallbackCount", 0)
            rows.append(
                {
                    "fixture": fixture_path.name,
                    "moduleId": module_id,
                    "deterministic": deterministic,
                    "resultHash": stable_hash(first),
                    "fallbackCount": fallback_count,
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{fixture_path.name}: {exc}")

    report = {
        "ok": not errors,
        "errorCount": len(errors),
        "errors": errors,
        "fixtureCount": len(rows),
        "rows": rows,
    }

    out_path = Path(args.out).resolve() if args.out else default_out_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.emit_json or not args.out:
        print(json.dumps(report, indent=2))

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
