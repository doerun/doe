#!/usr/bin/env python3
"""Run a configured WebGPU CTS subset and emit machine-readable trend artifacts."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="bench/cts_subset.webgpu-node.json",
        help="CTS subset config JSON.",
    )
    parser.add_argument(
        "--out-json",
        default="bench/out/cts_subset_report.json",
        help="JSON output path.",
    )
    parser.add_argument(
        "--out-md",
        default="bench/out/cts_subset_report.md",
        help="Markdown output path.",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=0,
        help="Optional max number of queries to execute (>0 limits execution).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not execute commands; emit planned runs only.",
    )
    parser.add_argument(
        "--stop-on-fail",
        action="store_true",
        help="Stop after first failing query.",
    )
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def ensure_string_list(value: Any, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"invalid {field}: expected string[]")
    out: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"invalid {field}[{index}]: expected non-empty string")
        out.append(item.strip())
    if not out:
        raise ValueError(f"invalid {field}: expected at least one query")
    return out


def markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# CTS Subset Report")
    lines.append("")
    lines.append(f"- Generated: `{payload.get('generatedAtUtc', '')}`")
    lines.append(f"- Config: `{payload.get('configPath', '')}`")
    lines.append(f"- Workdir: `{payload.get('workdir', '')}`")
    lines.append(f"- Command template: `{payload.get('commandTemplate', '')}`")
    lines.append("")
    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}
    lines.append(f"- Query count: `{summary.get('queryCount', 0)}`")
    lines.append(f"- Pass count: `{summary.get('passCount', 0)}`")
    lines.append(f"- Fail count: `{summary.get('failCount', 0)}`")
    lines.append("")
    lines.append("| Query | Exit | Wall ms | Pass |")
    lines.append("|---|---:|---:|---:|")
    rows = payload.get("rows", [])
    if not isinstance(rows, list):
        rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| `{row.get('query', '')}` | {row.get('exitCode', '')} | "
            f"{row.get('wallMs', '')} | {row.get('pass', False)} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def run_query(command: list[str], workdir: Path) -> dict[str, Any]:
    start = time.perf_counter()
    proc = subprocess.run(
        command,
        cwd=str(workdir),
        text=True,
        capture_output=True,
        check=False,
    )
    wall_ms = (time.perf_counter() - start) * 1000.0
    return {
        "exitCode": proc.returncode,
        "wallMs": wall_ms,
        "stdoutTail": (proc.stdout or "").splitlines()[-20:],
        "stderrTail": (proc.stderr or "").splitlines()[-20:],
    }


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"FAIL: missing CTS config: {config_path}")
        return 1

    try:
        config = load_json(config_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"FAIL: {exc}")
        return 1

    workdir_raw = config.get("workdir")
    command_template = config.get("commandTemplate")
    if not isinstance(workdir_raw, str) or not workdir_raw.strip():
        print("FAIL: invalid config workdir")
        return 1
    if not isinstance(command_template, str) or "{query}" not in command_template:
        print("FAIL: invalid config commandTemplate (must include {query})")
        return 1
    try:
        queries = ensure_string_list(config.get("queries"), field="queries")
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1

    if args.max_queries > 0:
        queries = queries[: args.max_queries]

    workdir = Path(workdir_raw)
    if not workdir.is_absolute():
        workdir = (Path(__file__).resolve().parent.parent / workdir).resolve()
    if not workdir.exists():
        print(f"FAIL: configured CTS workdir does not exist: {workdir}")
        return 1

    rows: list[dict[str, Any]] = []
    fail_count = 0
    pass_count = 0

    for query in queries:
        rendered = command_template.format(query=query)
        command = shlex.split(rendered)
        if args.dry_run:
            rows.append(
                {
                    "query": query,
                    "command": command,
                    "exitCode": None,
                    "wallMs": None,
                    "pass": None,
                    "stdoutTail": [],
                    "stderrTail": [],
                }
            )
            continue

        run = run_query(command, workdir)
        is_pass = run["exitCode"] == 0
        if is_pass:
            pass_count += 1
        else:
            fail_count += 1
        rows.append(
            {
                "query": query,
                "command": command,
                "exitCode": run["exitCode"],
                "wallMs": run["wallMs"],
                "pass": is_pass,
                "stdoutTail": run["stdoutTail"],
                "stderrTail": run["stderrTail"],
            }
        )
        if args.stop_on_fail and not is_pass:
            break

    summary = {
        "queryCount": len(rows),
        "passCount": pass_count,
        "failCount": fail_count,
        "dryRun": bool(args.dry_run),
    }
    payload = {
        "schemaVersion": 1,
        "generatedAtUtc": utc_now(),
        "configPath": str(config_path),
        "workdir": str(workdir),
        "commandTemplate": command_template,
        "summary": summary,
        "rows": rows,
    }

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    out_md.write_text(markdown(payload), encoding="utf-8")
    print(
        json.dumps(
            {
                "outJson": str(out_json),
                "outMd": str(out_md),
                "queryCount": summary["queryCount"],
                "passCount": summary["passCount"],
                "failCount": summary["failCount"],
                "dryRun": summary["dryRun"],
            },
            indent=2,
        )
    )
    if args.dry_run:
        return 0
    return 0 if fail_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

