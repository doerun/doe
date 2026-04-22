#!/usr/bin/env python3
"""Validate Doe CSL INT4 PLE hardware receipt readiness."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[2]
PENDING = {"", "pending", "<pending>"}
CMADDR_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d+\b")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    parser.add_argument(
        "--schema",
        default="config/doe-csl-int4ple-hardware-receipt.schema.json",
    )
    parser.add_argument("--require-hardware-success", action="store_true")
    return parser.parse_args()


def resolve(raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def schema_failures(data: Any, schema: Any) -> list[str]:
    return [
        f"{'.'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
        for e in sorted(
            jsonschema.Draft202012Validator(schema).iter_errors(data),
            key=lambda item: tuple(str(p) for p in item.absolute_path),
        )
    ]


def check_hash_link(
    label: str,
    link: dict[str, Any],
    failures: list[str],
) -> dict[str, Any] | None:
    path_text = link.get("path", "")
    expected = link.get("sha256", "")
    if path_text in PENDING or expected in PENDING:
        failures.append(f"{label}.path/hash pending")
        return None
    path = resolve(path_text)
    if not path.is_file():
        failures.append(f"{label}.path missing: {path_text}")
        return None
    actual = sha256_file(path)
    if actual != expected:
        failures.append(f"{label}.sha256={expected!r}, actual {actual!r}")
        return None
    try:
        return load_json(path)
    except json.JSONDecodeError as exc:
        failures.append(f"{label}.path invalid JSON: {exc}")
        return None


def walk_strings(value: Any, prefix: str = "") -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(prefix or "<root>", value)]
    if isinstance(value, list):
        out: list[tuple[str, str]] = []
        for index, item in enumerate(value):
            out.extend(walk_strings(item, f"{prefix}[{index}]"))
        return out
    if isinstance(value, dict):
        out: list[tuple[str, str]] = []
        for key, item in value.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            out.extend(walk_strings(item, child))
        return out
    return []


def source_subset(source: dict[str, Any]) -> dict[str, Any]:
    keys = {
        "manifestSha256",
        "graphSha256",
        "weightSetId",
        "weightSha256",
        "inputSetSha256",
        "programBundleId",
    }
    return {key: source.get(key) for key in keys}


def main() -> int:
    args = parse_args()
    failures: list[str] = []
    try:
        receipt = load_json(resolve(args.receipt))
        schema = load_json(resolve(args.schema))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: INT4 PLE hardware receipt gate: {exc}")
        return 1

    failures.extend(schema_failures(receipt, schema))
    parity = check_hash_link(
        "simulatorParityReceipt",
        receipt.get("simulatorParityReceipt") or {},
        failures,
    )
    transcript = check_hash_link(
        "simulatorTranscriptReceipt",
        receipt.get("simulatorTranscriptReceipt") or {},
        failures,
    )

    source = receipt.get("sourceProgram") or {}
    if parity:
        parity_source = parity.get("sourceProgram") or {}
        reference = parity.get("referenceRun") or {}
        if "inputSetSha256" not in parity_source:
            parity_source = dict(parity_source)
            parity_source["inputSetSha256"] = reference.get("inputSetSha256")
        if source_subset(source) != source_subset(parity_source):
            failures.append("sourceProgram does not match simulator parity receipt")
        if parity.get("comparison", {}).get("status") == "passed":
            if receipt.get("hardwareRun", {}).get("status") == "pending_simulator_parity":
                failures.append(
                    "hardwareRun.status is pending_simulator_parity but parity passed"
                )
    if transcript:
        transcript_source = transcript.get("sourceProgram") or {}
        for key in ("manifestSha256", "graphSha256", "weightSha256", "programBundleId"):
            if transcript_source.get(key) != source.get(key):
                failures.append(
                    f"sourceProgram.{key} does not match simulator transcript receipt"
                )

    for location, text in walk_strings(receipt):
        if CMADDR_RE.search(text) and "$DOE_CSL_CMADDR" not in text:
            failures.append(f"{location}: unredacted cmaddr-like endpoint")

    criteria = receipt.get("promotionCriteria") or {}
    hardware = receipt.get("hardwareRun") or {}
    if hardware.get("status") != "hardware_success":
        if criteria.get("hardwareSuccessClaimable") is not False:
            failures.append(
                "promotionCriteria.hardwareSuccessClaimable must be false "
                "without hardware_success"
            )
        if criteria.get("hardwareExecuted") is not False:
            failures.append(
                "promotionCriteria.hardwareExecuted must be false without hardware_success"
            )

    if args.require_hardware_success:
        required_true = [
            "sameSourceIdentity",
            "simulatorParityPassed",
            "hardwareExecuted",
            "hardwareTranscriptBound",
            "tokenIdsMatched",
            "perStepLogitsParityPassed",
            "realKvCacheUsed",
            "endpointRedacted",
            "stubStagesAbsent",
            "syntheticInputsAbsent",
            "syntheticWeightsAbsent",
            "hardwareSuccessClaimable",
        ]
        if hardware.get("status") != "hardware_success":
            failures.append(
                f"hardwareRun.status={hardware.get('status')!r}, "
                "expected 'hardware_success'"
            )
        for key in required_true:
            if criteria.get(key) is not True:
                failures.append(f"promotionCriteria.{key}={criteria.get(key)!r}")

    if failures:
        print("FAIL: INT4 PLE hardware receipt gate")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print(
        "PASS: INT4 PLE hardware receipt gate "
        f"(status={hardware.get('status', 'unknown')!r}, "
        f"target={hardware.get('executionTarget', 'unknown')!r})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
