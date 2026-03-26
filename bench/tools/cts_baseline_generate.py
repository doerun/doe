#!/usr/bin/env python3
"""Generate a CTS baseline snapshot by running WebGPU CTS queries against Doe.

Reads a CTS subset config (same format as run_cts_subset.py), executes each
query, and writes a structured baseline JSON artifact to bench/out/cts-baseline/.

Usage:
    python3 bench/tools/cts_baseline_generate.py \
        --config bench/fixtures/cts_subset.fawn-node.json \
        --backend doe_metal \
        --host "macbook-m2" \
        --os "darwin-25.3"
"""

from __future__ import annotations

import argparse
import json
import platform
import shlex
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def utc_timestamp_compact() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a CTS baseline snapshot for Doe."
    )
    parser.add_argument(
        "--config",
        default="bench/fixtures/cts_subset.fawn-node.json",
        help="CTS subset config JSON (same format as run_cts_subset.py).",
    )
    parser.add_argument(
        "--backend",
        default="doe_metal",
        help="Runtime backend identifier (e.g. doe_metal, doe_vulkan).",
    )
    parser.add_argument(
        "--host",
        default="",
        help="Host machine identifier. Auto-detected when omitted.",
    )
    parser.add_argument(
        "--os",
        default="",
        help="OS identifier. Auto-detected when omitted.",
    )
    parser.add_argument(
        "--cts-revision",
        default="untracked",
        help="CTS revision string for traceability.",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Output path. Defaults to bench/out/cts-baseline/<timestamp>.json.",
    )
    parser.add_argument(
        "--max-queries",
        type=int,
        default=0,
        help="Limit the number of queries executed (0 = unlimited).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not execute queries; emit planned run skeleton.",
    )
    parser.add_argument(
        "--stop-on-fail",
        action="store_true",
        help="Stop after first failing query.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid JSON object: {path}")
    return payload


def normalize_label(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_") or "query"


def load_query_entries(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise ValueError("invalid queries: expected list")
    out: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            query = item.strip()
            if not query:
                raise ValueError(f"invalid queries[{index}]: empty string")
            out.append({"id": normalize_label(query), "query": query, "bucket": "", "notes": ""})
            continue
        if not isinstance(item, dict):
            raise ValueError(f"invalid queries[{index}]: expected string or object")
        query = item.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"invalid queries[{index}].query: expected non-empty string")
        raw_id = item.get("id")
        entry_id = raw_id.strip() if isinstance(raw_id, str) and raw_id.strip() else normalize_label(query)
        bucket = item.get("bucket", "")
        bucket = bucket.strip() if isinstance(bucket, str) else ""
        notes = item.get("notes", "")
        notes = notes.strip() if isinstance(notes, str) else ""
        out.append({"id": entry_id, "query": query.strip(), "bucket": bucket, "notes": notes})
    if not out:
        raise ValueError("invalid queries: expected at least one entry")
    return out


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
        "stdoutTail": (proc.stdout or "").splitlines()[-10:],
        "stderrTail": (proc.stderr or "").splitlines()[-10:],
    }


def summarize_buckets(results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for row in results:
        bucket = row.get("bucket") or "unbucketed"
        item = summary.setdefault(bucket, {"queryCount": 0, "passCount": 0, "failCount": 0, "skipCount": 0})
        item["queryCount"] += 1
        status = row.get("status", "skip")
        if status == "pass":
            item["passCount"] += 1
        elif status == "fail":
            item["failCount"] += 1
        else:
            item["skipCount"] += 1
    return summary


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
        queries = load_query_entries(config.get("queries"))
    except ValueError as exc:
        print(f"FAIL: {exc}")
        return 1

    if args.max_queries > 0:
        queries = queries[: args.max_queries]

    workdir = Path(workdir_raw)
    if not workdir.is_absolute():
        workdir = (REPO_ROOT / workdir).resolve()

    host = args.host.strip() or socket.gethostname()
    os_id = args.os.strip() or f"{platform.system().lower()}-{platform.release()}"
    cts_source = config.get("ctsSource", str(config_path))
    if not isinstance(cts_source, str) or not cts_source.strip():
        cts_source = str(config_path)

    results: list[dict[str, Any]] = []
    pass_count = 0
    fail_count = 0
    skip_count = 0

    for entry in queries:
        rendered = command_template.format(
            query=entry["query"],
            id=entry["id"],
            bucket=entry.get("bucket", ""),
            notes=entry.get("notes", ""),
        )
        command = shlex.split(rendered)

        if args.dry_run:
            results.append({
                "id": entry["id"],
                "query": entry["query"],
                "bucket": entry.get("bucket", ""),
                "status": "skip",
                "exitCode": None,
                "wallMs": None,
                "notes": entry.get("notes", ""),
            })
            skip_count += 1
            continue

        if not workdir.exists():
            print(f"SKIP: workdir does not exist: {workdir}")
            results.append({
                "id": entry["id"],
                "query": entry["query"],
                "bucket": entry.get("bucket", ""),
                "status": "skip",
                "exitCode": None,
                "wallMs": None,
                "notes": f"workdir missing: {workdir}",
            })
            skip_count += 1
            continue

        run = run_query(command, workdir)
        if run["exitCode"] == 0:
            status = "pass"
            pass_count += 1
        else:
            status = "fail"
            fail_count += 1

        results.append({
            "id": entry["id"],
            "query": entry["query"],
            "bucket": entry.get("bucket", ""),
            "status": status,
            "exitCode": run["exitCode"],
            "wallMs": run["wallMs"],
            "notes": entry.get("notes", ""),
        })

        if args.stop_on_fail and status == "fail":
            break

    query_count = len(results)
    pass_rate = (pass_count / query_count * 100.0) if query_count > 0 else 0.0

    payload: dict[str, Any] = {
        "schemaVersion": 1,
        "generatedAtUtc": utc_now(),
        "backend": args.backend,
        "host": host,
        "os": os_id,
        "ctsSource": cts_source,
        "ctsRevision": args.cts_revision,
        "configPath": str(config_path),
        "summary": {
            "queryCount": query_count,
            "passCount": pass_count,
            "failCount": fail_count,
            "skipCount": skip_count,
            "passRate": round(pass_rate, 2),
            "bucketSummary": summarize_buckets(results),
        },
        "results": results,
    }

    if args.out:
        out_path = Path(args.out)
    else:
        timestamp = utc_timestamp_compact()
        out_path = Path("bench/out/cts-baseline") / f"{timestamp}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(json.dumps({
        "status": "ok",
        "outPath": str(out_path),
        "queryCount": query_count,
        "passCount": pass_count,
        "failCount": fail_count,
        "skipCount": skip_count,
        "passRate": round(pass_rate, 2),
        "dryRun": args.dry_run,
    }, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
