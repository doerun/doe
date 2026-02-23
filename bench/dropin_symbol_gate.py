#!/usr/bin/env python3
"""Drop-in ABI symbol gate against config/dropin_abi.symbols.txt."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import output_paths


SYMBOL_PATTERN = re.compile(r"\b(wgpu[A-Za-z0-9_]+)\b")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact",
        required=True,
        help="Path to the candidate drop-in shared library artifact.",
    )
    parser.add_argument(
        "--symbols",
        default="config/dropin_abi.symbols.txt",
        help="Required symbol list (one symbol per line).",
    )
    parser.add_argument(
        "--report",
        default="bench/out/dropin_symbol_report.json",
        help="JSON report output path.",
    )
    parser.add_argument(
        "--timestamp",
        default="",
        help=(
            "UTC suffix for output artifact path (YYYYMMDDTHHMMSSZ). "
            "Defaults to current UTC time when --timestamp-output is enabled."
        ),
    )
    parser.add_argument(
        "--timestamp-output",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Stamp the report path with a UTC timestamp suffix.",
    )
    return parser.parse_args()


def read_required_symbols(path: Path) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(f"missing required symbol list: {path}")

    symbols: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not stripped.startswith("wgpu"):
            raise ValueError(f"invalid symbol entry (must start with 'wgpu'): {stripped}")
        if stripped in seen:
            continue
        seen.add(stripped)
        symbols.append(stripped)
    if not symbols:
        raise ValueError(f"required symbol list is empty: {path}")
    return sorted(symbols)


def run_symbol_tool(command: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return completed.returncode, completed.stdout, completed.stderr


def extract_symbols_from_output(output: str) -> set[str]:
    return {match.group(1) for match in SYMBOL_PATTERN.finditer(output)}


def export_symbols_from_artifact(artifact: Path) -> tuple[list[str], set[str], str]:
    tool_candidates: list[list[str]] = [
        ["nm", "-D", "--defined-only", str(artifact)],
        ["llvm-nm", "-D", "--defined-only", str(artifact)],
        ["objdump", "-T", str(artifact)],
        ["readelf", "-Ws", str(artifact)],
    ]

    attempted_commands: list[str] = []
    for command in tool_candidates:
        tool = command[0]
        if shutil.which(tool) is None:
            attempted_commands.append(f"{tool}:not-found")
            continue

        attempted_commands.append(" ".join(command))
        return_code, stdout, stderr = run_symbol_tool(command)
        if return_code != 0:
            attempted_commands.append(f"{tool}:rc={return_code}:{stderr.strip()}")
            continue

        symbols = extract_symbols_from_output(stdout)
        if symbols:
            return attempted_commands, symbols, " ".join(command)

    raise RuntimeError(
        "unable to read exported symbols; attempted: " + "; ".join(attempted_commands)
    )


def write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    artifact_path = Path(args.artifact)
    symbols_path = Path(args.symbols)
    output_timestamp = (
        output_paths.resolve_timestamp(args.timestamp)
        if args.timestamp_output
        else ""
    )
    report_path = output_paths.with_timestamp(
        args.report,
        output_timestamp,
        enabled=args.timestamp_output,
    )

    report: dict[str, Any] = {
        "schemaVersion": 1,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "outputTimestamp": output_timestamp,
        "artifact": str(artifact_path),
        "symbolsPath": str(symbols_path),
        "pass": False,
    }

    exit_code = 1
    try:
        if not artifact_path.exists():
            raise FileNotFoundError(f"missing artifact: {artifact_path}")

        required_symbols = read_required_symbols(symbols_path)
        attempted, exported_symbols, command_used = export_symbols_from_artifact(artifact_path)

        required_set = set(required_symbols)
        missing = sorted(required_set - exported_symbols)
        extras = sorted(exported_symbols - required_set)

        report.update(
            {
                "requiredSymbolCount": len(required_symbols),
                "exportedSymbolCount": len(exported_symbols),
                "missingSymbolCount": len(missing),
                "missingSymbols": missing,
                "extraSymbolCount": len(extras),
                "toolCommandUsed": command_used,
                "toolAttempts": attempted,
            }
        )

        if missing:
            report["error"] = "missing required symbols"
            exit_code = 1
        else:
            report["pass"] = True
            exit_code = 0
    except Exception as exc:  # noqa: BLE001
        report["error"] = str(exc)
        exit_code = 1
    finally:
        write_report(report_path, report)

    if report.get("pass"):
        print(f"PASS: drop-in symbol gate ({report.get('requiredSymbolCount')} required)")
    else:
        print(f"FAIL: drop-in symbol gate: {report.get('error', 'unknown failure')}")
        missing = report.get("missingSymbols")
        if isinstance(missing, list) and missing:
            preview = ", ".join(str(item) for item in missing[:8])
            print(f"  missing symbols ({len(missing)}): {preview}")
    print(f"report: {report_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
