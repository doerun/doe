#!/usr/bin/env python3
"""Build a hardware x model capacity report for browserless AI/ML scope claims."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ALLOWED_STATUS = {"pass", "fail", "oom", "unsupported"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="bench/model_capacity_matrix.json",
        help="Input matrix JSON path.",
    )
    parser.add_argument(
        "--out-json",
        default="bench/out/model_capacity_matrix_report.json",
        help="Output JSON report path.",
    )
    parser.add_argument(
        "--out-md",
        default="bench/out/model_capacity_matrix_report.md",
        help="Output markdown report path.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def require_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"invalid entry.{field}: expected non-empty string")
    return value.strip()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def normalize_entry(index: int, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"invalid entries[{index}]: expected object")
    status = require_string(raw, "status")
    if status not in ALLOWED_STATUS:
        raise ValueError(
            f"invalid entries[{index}].status: expected one of {sorted(ALLOWED_STATUS)}"
        )
    params_b = parse_float(raw.get("paramsB"))
    ttft_ms = parse_float(raw.get("ttftMs"))
    decode_tokens_per_sec = parse_float(raw.get("decodeTokensPerSec"))
    prefill_tokens_per_sec = parse_float(raw.get("prefillTokensPerSec"))
    peak_vram_bytes = raw.get("peakVramBytes")
    if peak_vram_bytes is not None:
        if not isinstance(peak_vram_bytes, int) or peak_vram_bytes < 0:
            raise ValueError(
                f"invalid entries[{index}].peakVramBytes: expected non-negative integer"
            )
    artifact_path = raw.get("artifactPath")
    if artifact_path is not None and (
        not isinstance(artifact_path, str) or not artifact_path.strip()
    ):
        raise ValueError(f"invalid entries[{index}].artifactPath: expected non-empty string")
    return {
        "hardwareId": require_string(raw, "hardwareId"),
        "hardwareLabel": require_string(raw, "hardwareLabel"),
        "runtime": require_string(raw, "runtime"),
        "backend": require_string(raw, "backend"),
        "modelId": require_string(raw, "modelId"),
        "quantization": require_string(raw, "quantization"),
        "status": status,
        "paramsB": params_b,
        "ttftMs": ttft_ms,
        "decodeTokensPerSec": decode_tokens_per_sec,
        "prefillTokensPerSec": prefill_tokens_per_sec,
        "peakVramBytes": peak_vram_bytes,
        "artifactPath": artifact_path.strip() if isinstance(artifact_path, str) else "",
    }


def normalize_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_entries = payload.get("entries")
    if raw_entries is None:
        return []
    if not isinstance(raw_entries, list):
        raise ValueError("invalid entries: expected array")
    return [normalize_entry(index, raw) for index, raw in enumerate(raw_entries)]


def hardware_summary(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for entry in entries:
        hardware_id = entry["hardwareId"]
        bucket = grouped.get(hardware_id)
        if bucket is None:
            bucket = {
                "hardwareId": hardware_id,
                "hardwareLabel": entry["hardwareLabel"],
                "runtime": entry["runtime"],
                "backend": entry["backend"],
                "totalRows": 0,
                "passRows": 0,
                "failRows": 0,
                "oomRows": 0,
                "unsupportedRows": 0,
                "maxPassParamsB": None,
                "maxPassModelId": "",
                "maxPassQuantization": "",
                "maxPassArtifactPath": "",
            }
            grouped[hardware_id] = bucket

        bucket["totalRows"] += 1
        status = entry["status"]
        if status == "pass":
            bucket["passRows"] += 1
            params_b = entry.get("paramsB")
            current_max = bucket.get("maxPassParamsB")
            if params_b is not None and (
                current_max is None or float(params_b) > float(current_max)
            ):
                bucket["maxPassParamsB"] = float(params_b)
                bucket["maxPassModelId"] = entry["modelId"]
                bucket["maxPassQuantization"] = entry["quantization"]
                bucket["maxPassArtifactPath"] = entry.get("artifactPath", "")
        elif status == "fail":
            bucket["failRows"] += 1
        elif status == "oom":
            bucket["oomRows"] += 1
        elif status == "unsupported":
            bucket["unsupportedRows"] += 1

    rows = list(grouped.values())
    rows.sort(key=lambda row: row["hardwareId"])
    return rows


def report_summary(
    entries: list[dict[str, Any]], hardware_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    pass_rows = sum(1 for row in entries if row["status"] == "pass")
    fail_rows = sum(1 for row in entries if row["status"] == "fail")
    oom_rows = sum(1 for row in entries if row["status"] == "oom")
    unsupported_rows = sum(1 for row in entries if row["status"] == "unsupported")
    return {
        "entryCount": len(entries),
        "hardwareCount": len(hardware_rows),
        "passRows": pass_rows,
        "failRows": fail_rows,
        "oomRows": oom_rows,
        "unsupportedRows": unsupported_rows,
    }


def markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Model Capacity Matrix Report")
    lines.append("")
    lines.append(f"- Generated: `{payload.get('generatedAtUtc', '')}`")
    lines.append(f"- Input: `{payload.get('inputPath', '')}`")
    lines.append("")
    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    lines.append(f"- Entries: `{summary.get('entryCount', 0)}`")
    lines.append(f"- Hardware profiles: `{summary.get('hardwareCount', 0)}`")
    lines.append(
        "- Status rows: "
        f"pass=`{summary.get('passRows', 0)}`, "
        f"fail=`{summary.get('failRows', 0)}`, "
        f"oom=`{summary.get('oomRows', 0)}`, "
        f"unsupported=`{summary.get('unsupportedRows', 0)}`"
    )
    lines.append("")
    lines.append("## Per-hardware ceiling")
    lines.append("")
    lines.append("| Hardware | Runtime | Backend | Pass rows | Max pass params (B) | Model | Quantization |")
    lines.append("|---|---|---|---:|---:|---|---|")
    hardware_rows = payload.get("hardwareSummary", [])
    if not isinstance(hardware_rows, list):
        hardware_rows = []
    for row in hardware_rows:
        if not isinstance(row, dict):
            continue
        max_params = row.get("maxPassParamsB")
        max_params_text = f"{max_params:.2f}" if isinstance(max_params, float) else ""
        lines.append(
            "| "
            f"{row.get('hardwareLabel', '')} (`{row.get('hardwareId', '')}`) | "
            f"{row.get('runtime', '')} | "
            f"{row.get('backend', '')} | "
            f"{row.get('passRows', 0)} | "
            f"{max_params_text} | "
            f"{row.get('maxPassModelId', '')} | "
            f"{row.get('maxPassQuantization', '')} |"
        )
    lines.append("")
    lines.append("## Raw rows")
    lines.append("")
    lines.append("| Hardware | Model | Params (B) | Quantization | Status | TTFT ms | Decode tok/s | Prefill tok/s | Peak VRAM bytes | Artifact |")
    lines.append("|---|---|---:|---|---|---:|---:|---:|---:|---|")
    rows = payload.get("entries", [])
    if not isinstance(rows, list):
        rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        params_b = row.get("paramsB")
        params_text = f"{params_b:.2f}" if isinstance(params_b, float) else ""
        ttft_ms = row.get("ttftMs")
        ttft_text = f"{ttft_ms:.2f}" if isinstance(ttft_ms, float) else ""
        decode = row.get("decodeTokensPerSec")
        decode_text = f"{decode:.2f}" if isinstance(decode, float) else ""
        prefill = row.get("prefillTokensPerSec")
        prefill_text = f"{prefill:.2f}" if isinstance(prefill, float) else ""
        peak = row.get("peakVramBytes")
        peak_text = str(peak) if isinstance(peak, int) else ""
        lines.append(
            "| "
            f"{row.get('hardwareId', '')} | "
            f"{row.get('modelId', '')} | "
            f"{params_text} | "
            f"{row.get('quantization', '')} | "
            f"{row.get('status', '')} | "
            f"{ttft_text} | "
            f"{decode_text} | "
            f"{prefill_text} | "
            f"{peak_text} | "
            f"{row.get('artifactPath', '')} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"FAIL: missing input: {input_path}")
        return 1

    try:
        payload = load_json(input_path)
        entries = normalize_entries(payload)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1

    hardware_rows = hardware_summary(entries)
    summary = report_summary(entries, hardware_rows)
    report = {
        "schemaVersion": 1,
        "generatedAtUtc": utc_now(),
        "inputPath": str(input_path),
        "summary": summary,
        "hardwareSummary": hardware_rows,
        "entries": entries,
    }

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_md.write_text(markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "outJson": str(out_json),
                "outMd": str(out_md),
                "entryCount": summary["entryCount"],
                "hardwareCount": summary["hardwareCount"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
