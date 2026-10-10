#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, List, Optional, Tuple


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
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        text = value.strip()
        if text:
            return [text]
    return []


def normalize_file(value: Any) -> str:
    text = str(value).strip()
    return text


def parse_iso8601(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def normalize_backend_values(value: Any) -> List[str]:
    values = normalize_list(value)
    normalized: List[str] = []
    for backend in values:
        if backend.lower() == "d3d":
            normalized.append("d3d12")
        else:
            normalized.append(backend.lower())
    return normalized


def row_stream(paths: Iterable[Path]) -> Iterator[dict]:
    for input_path in paths:
        with input_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                if isinstance(payload, dict):
                    yield payload


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
        current_path = self.output_dir / f"{self.prefix}-{self.shard_index:05d}.jsonl"
        self.handle = current_path.open("w", encoding="utf-8")
        self.files.append(current_path.name)

    def write(self, row: dict) -> None:
        if self.rows_in_shard >= self.shard_size:
            self._open_next()
        line = json.dumps(row, ensure_ascii=False)
        self.handle.write(line)
        self.handle.write("\n")
        self.rows_in_shard += 1
        self.total_rows += 1

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()


def write_csv_rows(path: Path, rows: Iterable[dict], fields: List[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Workaround rows directory or file")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--row-shard-size", type=int, default=500, help="Rows per file hotspot shard")
    parser.add_argument(
        "--top-count",
        type=int,
        default=25,
        help="Number of top hotspots to include in summary",
    )
    args = parser.parse_args()

    input_paths = resolve_input_paths(Path(args.input))
    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    hotspot_writer = NDJSONShardedWriter(output_path / "files", "file_hotspot", args.row_shard_size)

    file_buckets: dict[Tuple[str, str, str, str], dict] = {}
    file_totals: dict[str, dict] = defaultdict(lambda: {"signals": 0, "changeIds": set(), "backendVendor": Counter()})

    for row in row_stream(input_paths):
        change_id = row.get("change_id", "")
        updated = parse_iso8601(row.get("updated"))
        updated_text = updated.isoformat() if updated else ""
        vendors = normalize_list(row.get("vendors")) or ["unknown"]
        backends = normalize_backend_values(row.get("backends"))
        if not backends:
            backends = ["unknown"]
        severities = normalize_list(row.get("severity")) or ["unknown"]
        files = normalize_list(row.get("files")) or ["unknown_file"]
        snippet = str(row.get("snippet", "")).strip()
        url = str(row.get("url", "")).strip()

        for file_name in [normalize_file(f) for f in files]:
            for vendor in vendors:
                for backend in backends:
                    for failure_class in severities:
                        key = (file_name, vendor.lower(), backend.lower(), failure_class.lower())
                        bucket = file_buckets.setdefault(
                            key,
                            {
                                "file": file_name,
                                "vendor": vendor.lower(),
                                "backend": backend.lower(),
                                "failureClass": failure_class.lower(),
                                "signalRows": 0,
                                "changeIds": set(),
                                "firstSeen": None,
                                "lastSeen": None,
                                "samples": [],
                            },
                        )
                        bucket["signalRows"] += 1
                        if change_id:
                            bucket["changeIds"].add(str(change_id))
                        if updated_text:
                            if bucket["firstSeen"] is None or updated_text < bucket["firstSeen"]:
                                bucket["firstSeen"] = updated_text
                            if bucket["lastSeen"] is None or updated_text > bucket["lastSeen"]:
                                bucket["lastSeen"] = updated_text
                        if url and len(bucket["samples"]) < 4:
                            bucket["samples"].append({"change_id": str(change_id), "url": url, "snippet": snippet[:200]})

                        totals = file_totals[file_name]
                        totals["signals"] += 1
                        totals["backendVendor"][(vendor.lower(), backend.lower())] += 1
                        if change_id:
                            totals["changeIds"].add(str(change_id))

    hotspot_rows: list[dict] = []
    for key, bucket in file_buckets.items():
        file_name, _, _, _ = key
        change_count = len(bucket["changeIds"])
        hotspot_rows.append({
            "file": file_name,
            "vendor": bucket["vendor"],
            "backend": bucket["backend"],
            "failureClass": bucket["failureClass"],
            "signalRows": bucket["signalRows"],
            "changeCount": change_count,
            "firstSeen": bucket["firstSeen"] or "",
            "lastSeen": bucket["lastSeen"] or "",
            "samples": bucket["samples"],
        })

    hotspot_rows.sort(key=lambda row: (row["signalRows"], row["changeCount"]), reverse=True)

    for row in hotspot_rows:
        if isinstance(row.get("samples"), list):
            row["sampleCount"] = len(row["samples"])
        if row["sampleCount"] > 0:
            row["sampleUrls"] = "|".join(
                [s.get("url", "") for s in row["samples"] if isinstance(s, dict)]
            )
        else:
            row["sampleUrls"] = ""
        hotspot_writer.write(row)

    hotspot_fields = [
        "file",
        "vendor",
        "backend",
        "failureClass",
        "signalRows",
        "changeCount",
        "firstSeen",
        "lastSeen",
        "sampleCount",
        "sampleUrls",
    ]
    write_csv_rows(
        output_path / "file_hotspots.csv",
        ({
            "file": row["file"],
            "vendor": row["vendor"],
            "backend": row["backend"],
            "failureClass": row["failureClass"],
            "signalRows": row["signalRows"],
            "changeCount": row["changeCount"],
            "firstSeen": row["firstSeen"],
            "lastSeen": row["lastSeen"],
            "sampleCount": row["sampleCount"],
            "sampleUrls": row["sampleUrls"],
        } for row in hotspot_rows),
        hotspot_fields,
    )

    sorted_top_files = sorted(
        ((name, data) for name, data in file_totals.items()),
        key=lambda item: item[1]["signals"],
        reverse=True,
    )
    top_file_summary = []
    for file_name, totals in sorted_top_files[: args.top_count]:
        top_file_summary.append({
            "file": file_name,
            "signalRows": totals["signals"],
            "changeCount": len(totals["changeIds"]),
        })

    pair_counts = Counter()
    for totals in file_totals.values():
        for pair, count in totals["backendVendor"].items():
            pair_counts[pair] += count

    top_pair_summary = []
    for (vendor, backend), count in pair_counts.most_common(args.top_count):
        top_pair_summary.append({
            "vendor": vendor,
            "backend": backend,
            "signalRows": count,
        })

    summary_payload = {
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "input": [str(p) for p in input_paths],
        "totalFiles": len(file_totals),
        "totalHotspotRows": len(hotspot_rows),
        "topFiles": top_file_summary,
        "topVendorBackendPairs": top_pair_summary,
        "rowShards": {
            "files": {
                "prefix": "file_hotspot",
                "shardSize": args.row_shard_size,
                "files": hotspot_writer.files,
                "totalRows": hotspot_writer.total_rows,
            },
            "rowInputDirectory": str((output_path / "files").resolve().as_posix()),
        },
    }

    with (output_path / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary_payload, handle, indent=2, sort_keys=True)

    hotspot_writer.close()

    print(f"Wrote {hotspot_writer.total_rows} hotspot rows to {output_path / 'files'}")
    print(f"Hotspot summary written to {output_path / 'summary.json'}")


if __name__ == "__main__":
    main()
