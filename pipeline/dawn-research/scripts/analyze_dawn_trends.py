#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Tuple


def resolve_input_paths(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise ValueError(f"Input path does not exist: {path}")
    paths = sorted(
        p for p in path.iterdir() if p.is_file() and p.suffix in {".jsonl", ".ndjson"}
    )
    if not paths:
        raise ValueError(f"No JSONL files in {path}")
    return paths


def normalize_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def safe_list_str(value: Any) -> str:
    items = normalize_list(value)
    return ",".join(items) if items else "unknown"


def parse_iso8601(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        # Fallback: stripped date-only
        try:
            return datetime.fromisoformat(text[:10])
        except ValueError:
            return None


def month_bucket(timestamp: datetime | None) -> str:
    if timestamp is None:
        return "unknown"
    return f"{timestamp.year:04d}-{timestamp.month:02d}"


class NDJSONShardedWriter:
    def __init__(self, output_dir: Path, prefix: str, shard_size: int):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.prefix = prefix
        self.shard_size = max(1, shard_size)
        self.shard_index = 0
        self.rows_in_shard = 0
        self.total_rows = 0
        self.files: List[str] = []
        self.handle = None
        self._open_next()

    def _open_next(self) -> None:
        if self.handle is not None:
            self.handle.close()
        self.shard_index += 1
        self.rows_in_shard = 0
        path = self.output_dir / f"{self.prefix}-{self.shard_index:05d}.jsonl"
        self.handle = path.open("w", encoding="utf-8")
        self.files.append(path.name)

    def write(self, row: dict) -> None:
        if self.rows_in_shard >= self.shard_size:
            self._open_next()
        line = json.dumps(row, ensure_ascii=False)
        self.handle.write(line + "\n")
        self.rows_in_shard += 1
        self.total_rows += 1

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()


def row_stream(paths: Iterable[Path]) -> Iterator[dict]:
    for input_path in paths:
        with input_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if isinstance(row, dict):
                    yield row


def write_csv_rows(path: Path, rows: Iterable[dict], fields: List[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Workaround row shard file or directory")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--row-shard-size", type=int, default=500, help="Rows per trend shard")
    parser.add_argument("--monthly-shard-size", type=int, default=500, help="Rows per monthly shard")
    parser.add_argument("--allowed-api", nargs="*", default=["vulkan", "metal", "d3d12", "webgpu"], help="API values to include in matrix")
    args = parser.parse_args()

    input_paths = resolve_input_paths(Path(args.input))
    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    allowed_api = set(args.allowed_api)
    bucket_rows: dict[Tuple[str, str, str], dict] = {}
    monthly_rows: defaultdict[str, dict] = defaultdict(lambda: {"signals": 0, "changeIds": set()})

    for row in row_stream(input_paths):
        updated = parse_iso8601(row.get("updated"))
        month = month_bucket(updated)
        change_id = row.get("change_id", "")
        vendors = normalize_list(row.get("vendors"))
        backends = normalize_list(row.get("backends"))
        severities = normalize_list(row.get("severity"))
        files = normalize_list(row.get("files"))

        if not vendors:
            vendors = ["unknown"]
        if not backends:
            backends = ["unknown"]
        if not severities:
            severities = ["unknown"]

        normalized_backends = []
        for backend in backends:
            if backend == "d3d":
                normalized_backends.append("d3d12")
            else:
                normalized_backends.append(backend)
        backends = normalized_backends

        for vendor in vendors:
            for backend in backends:
                bucket_api = backend
                if allowed_api and bucket_api not in allowed_api:
                    continue
                for severity in severities:
                    key = (vendor, bucket_api, severity)
                    bucket = bucket_rows.setdefault(
                        key,
                        {
                            "vendor": vendor,
                            "backend": bucket_api,
                            "failureClass": severity,
                            "signalRows": 0,
                            "changeIds": set(),
                            "firstSeen": None,
                            "lastSeen": None,
                            "files": Counter(),
                            "samples": [],
                        },
                    )
                    bucket["signalRows"] += 1
                    if change_id:
                        bucket["changeIds"].add(change_id)
                    if updated is not None:
                        iso = updated.isoformat()
                        if bucket["firstSeen"] is None or iso < bucket["firstSeen"]:
                            bucket["firstSeen"] = iso
                        if bucket["lastSeen"] is None or iso > bucket["lastSeen"]:
                            bucket["lastSeen"] = iso
                    for file in files:
                        bucket["files"][file] += 1
                    if row.get("snippet"):
                        bucket["samples"].append({
                            "change_id": change_id,
                            "snippet": row.get("snippet"),
                            "url": row.get("url", ""),
                        })

                    monthly_key = f"{month}|{vendor}|{bucket_api}|{severity}"
                    monthly_rows[monthly_key]["signals"] += 1
                    if change_id:
                        monthly_rows[monthly_key]["changeIds"].add(change_id)

    trend_rows = []
    for key, bucket in bucket_rows.items():
        change_count = len(bucket["changeIds"])
        top_files = [k for k, _ in bucket["files"].most_common(5)]
        trend_rows.append({
            "vendor": key[0],
            "backend": key[1],
            "failureClass": key[2],
            "signalRows": bucket["signalRows"],
            "changeCount": change_count,
            "firstSeen": bucket["firstSeen"] or "",
            "lastSeen": bucket["lastSeen"] or "",
            "topFiles": top_files,
            "sampleCount": len(bucket["samples"]),
            "samples": bucket["samples"][:4],
        })

    trend_rows.sort(
        key=lambda r: (r["signalRows"], r["changeCount"]),
        reverse=True,
    )

    trend_writer = NDJSONShardedWriter(
        output_path / "matrix",
        "trend_bucket",
        args.row_shard_size,
    )
    for row in trend_rows:
        if row["sampleCount"] > 0:
            del row["sampleCount"]
        trend_writer.write(row)

    with (output_path / "trend_buckets.jsonl").open("w", encoding="utf-8") as handle:
        for row in trend_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    matrix_csv_fields = [
        "vendor",
        "backend",
        "failureClass",
        "signalRows",
        "changeCount",
        "firstSeen",
        "lastSeen",
        "topFiles",
    ]
    write_csv_rows(
        output_path / "trend_matrix.csv",
        (
            {
                "vendor": row["vendor"],
                "backend": row["backend"],
                "failureClass": row["failureClass"],
                "signalRows": row["signalRows"],
                "changeCount": row["changeCount"],
                "firstSeen": row["firstSeen"],
                "lastSeen": row["lastSeen"],
                "topFiles": "|".join(row["topFiles"]),
            }
            for row in trend_rows
        ),
        matrix_csv_fields,
    )

    monthly_output = []
    for month_key, counts in sorted(monthly_rows.items()):
        month, vendor, backend, failure_class = month_key.split("|", 3)
        monthly_output.append({
            "month": month,
            "vendor": vendor,
            "backend": backend,
            "failureClass": failure_class,
            "signalRows": counts.get("signals", 0),
            "changeCount": len(counts.get("changeIds", set())),
        })

    monthly_writer = NDJSONShardedWriter(
        output_path / "time_series",
        "trend_month",
        args.monthly_shard_size,
    )
    for item in monthly_output:
        monthly_writer.write(item)

    with (output_path / "trend_timeseries.json").open("w", encoding="utf-8") as handle:
        json.dump({
            "generatedAt": datetime.utcnow().isoformat() + "Z",
            "input": [str(p) for p in input_paths],
            "months": monthly_output,
        }, handle, indent=2, sort_keys=True)

    trend_writer.close()
    monthly_writer.close()

    summary = {
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "input": str(Path(args.input)),
        "totalBuckets": len(trend_rows),
        "totalMonthlyRecords": len(monthly_output),
        "rowShards": {
            "trendBuckets": {
                "files": trend_writer.files,
                "shardSize": args.row_shard_size,
                "totalRows": trend_writer.total_rows,
            },
            "monthly": {
                "files": monthly_writer.files,
                "shardSize": args.monthly_shard_size,
                "totalRows": monthly_writer.total_rows,
            },
        },
    }
    with (output_path / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)

    print(f"Wrote trend matrix rows: {len(trend_rows)} to {output_path / 'matrix'}")
    print(f"Wrote monthly rows: {len(monthly_output)} to {output_path / 'time_series'}")
    print(f"Summary written: {output_path / 'summary.json'}")


if __name__ == "__main__":
    main()
