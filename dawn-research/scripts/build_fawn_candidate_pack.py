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


def normalize_backend_values(value: Any) -> List[str]:
    values = normalize_list(value)
    normalized: List[str] = []
    for backend in values:
        if backend.lower() == "d3d":
            normalized.append("d3d12")
        else:
            normalized.append(backend.lower())
    return normalized


def parse_iso8601(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


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


def write_csv_rows(path: Path, rows: Iterable[dict], fields: List[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


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
        current_path = self.output_path = self.output_dir / f"{self.prefix}-{self.shard_index:05d}.jsonl"
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


def classify_priority(score: int) -> str:
    if score >= 50:
        return "high"
    if score >= 30:
        return "medium"
    if score >= 15:
        return "low"
    return "backlog"


def compute_fawn_api(backend: str) -> str:
    if backend in {"d3d", "d3d12"}:
        return "d3d12"
    return backend if backend in {"vulkan", "metal", "webgpu"} else "unknown"


def load_trends(path: Path) -> dict[Tuple[str, str, str], dict]:
    trend_map: dict[Tuple[str, str, str], dict] = {}
    if path is None:
        return trend_map
    if not path.is_file():
        return trend_map
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                continue
            vendor = str(payload.get("vendor", "unknown")).lower()
            backend = str(payload.get("backend", "unknown")).lower()
            failure_class = str(payload.get("failureClass", "unknown")).lower()
            trend_map[(vendor, backend, failure_class)] = payload
    return trend_map


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Fawn research candidate pack from workaround rows.")
    parser.add_argument("--workarounds", required=True, help="Workaround row directory or file")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--trends", default="", help="Optional trend bucket JSONL path")
    parser.add_argument("--row-shard-size", type=int, default=500, help="Rows per candidate shard")
    parser.add_argument("--min-signal-rows", type=int, default=3, help="Min workaround rows for a candidate")
    parser.add_argument("--min-change-count", type=int, default=2, help="Min unique change count for a candidate")
    parser.add_argument("--max-samples", type=int, default=6, help="Max samples per candidate")
    parser.add_argument("--max-top-files", type=int, default=6, help="Max top files to keep per candidate")
    args = parser.parse_args()

    workaround_paths = resolve_input_paths(Path(args.workarounds))
    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)
    trend_map = load_trends(Path(args.trends)) if args.trends else {}

    writer = NDJSONShardedWriter(output_path / "candidates", "candidate", args.row_shard_size)
    candidate_rows: list[dict] = []
    aggregate: dict[Tuple[str, str, str], dict] = {}

    for row in row_stream(workaround_paths):
        vendors = normalize_list(row.get("vendors")) or ["unknown"]
        backends = normalize_backend_values(row.get("backends")) or ["unknown"]
        severities = normalize_list(row.get("severity")) or ["unknown"]
        change_id = str(row.get("change_id", ""))
        updated = parse_iso8601(row.get("updated"))
        updated_text = updated.isoformat() if updated else ""
        url = str(row.get("url", "")).strip()
        snippet = str(row.get("snippet", "")).strip()
        files = normalize_list(row.get("files"))

        for vendor in vendors:
            for backend in backends:
                for failure_class in severities:
                    key = (vendor.lower(), backend.lower(), failure_class.lower())
                    bucket = aggregate.setdefault(
                        key,
                        {
                            "vendor": vendor.lower(),
                            "backend": backend.lower(),
                            "failureClass": failure_class.lower(),
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
                    if updated_text:
                        if bucket["firstSeen"] is None or updated_text < bucket["firstSeen"]:
                            bucket["firstSeen"] = updated_text
                        if bucket["lastSeen"] is None or updated_text > bucket["lastSeen"]:
                            bucket["lastSeen"] = updated_text

                    for file_name in files:
                        bucket["files"][file_name] += 1

                    if len(bucket["samples"]) < args.max_samples and (url or snippet):
                        bucket["samples"].append({
                            "change_id": change_id,
                            "url": url,
                            "snippet": snippet[:220],
                        })

    for (vendor, backend, failure_class), bucket in aggregate.items():
        change_count = len(bucket["changeIds"])
        if bucket["signalRows"] < args.min_signal_rows or change_count < args.min_change_count:
            continue

        top_files = [f for f, _ in bucket["files"].most_common(args.max_top_files)]
        trend = trend_map.get((vendor, backend, failure_class), {})
        recency = 0
        if bucket["lastSeen"]:
            try:
                last_seen = datetime.fromisoformat(bucket["lastSeen"])
                age = (datetime.utcnow() - last_seen).days
                if age <= 90:
                    recency = 10
                elif age <= 180:
                    recency = 6
                elif age <= 365:
                    recency = 3
            except ValueError:
                recency = 0
        trend_signal_bonus = min(10, int(trend.get("signalRows", 0) / 5))
        score = (bucket["signalRows"] * 4) + (change_count * 7) + recency + trend_signal_bonus + min(10, len(top_files))
        priority = classify_priority(score)
        candidate_id = f"{vendor}__{backend}__{failure_class}"

        change_samples = sorted(bucket["changeIds"])[: args.max_samples]

        candidate = {
            "candidateId": candidate_id,
            "priority": priority,
            "priorityScore": score,
            "vendor": vendor,
            "backend": backend,
            "failureClass": failure_class,
            "fawnApiHint": compute_fawn_api(backend),
            "supportingSignals": {
                "signalRows": bucket["signalRows"],
                "changeCount": change_count,
                "firstSeen": bucket["firstSeen"] or "",
                "lastSeen": bucket["lastSeen"] or "",
                "topFiles": top_files,
                "sampleSignals": bucket["samples"][: args.max_samples],
            },
            "trendContext": {
                "trendSignalRows": trend.get("signalRows", 0),
                "trendChangeCount": trend.get("changeCount", 0),
                "trendLastSeen": trend.get("lastSeen", ""),
            },
            "decision": {
                "state": "human_review_pending",
                "evidence": {
                    "sampleChangeIds": change_samples,
                    "reason": "Repeated workaround signal cluster across vendor/backend/failure-class with code-touch evidence.",
                },
            },
        }
        candidate_rows.append(candidate)

    candidate_rows.sort(key=lambda row: row["priorityScore"], reverse=True)

    for candidate in candidate_rows:
        writer.write(candidate)

    fields = [
        "candidateId",
        "priority",
        "priorityScore",
        "vendor",
        "backend",
        "failureClass",
        "fawnApiHint",
        "supportingSignals_signalRows",
        "supportingSignals_changeCount",
        "supportingSignals_firstSeen",
        "supportingSignals_lastSeen",
        "supportingSignals_topFiles",
        "trendContext_trendSignalRows",
        "trendContext_trendChangeCount",
        "decision_state",
    ]
    csv_rows = []
    for candidate in candidate_rows:
        csv_rows.append({
            "candidateId": candidate["candidateId"],
            "priority": candidate["priority"],
            "priorityScore": candidate["priorityScore"],
            "vendor": candidate["vendor"],
            "backend": candidate["backend"],
            "failureClass": candidate["failureClass"],
            "fawnApiHint": candidate["fawnApiHint"],
            "supportingSignals_signalRows": candidate["supportingSignals"]["signalRows"],
            "supportingSignals_changeCount": candidate["supportingSignals"]["changeCount"],
            "supportingSignals_firstSeen": candidate["supportingSignals"]["firstSeen"],
            "supportingSignals_lastSeen": candidate["supportingSignals"]["lastSeen"],
            "supportingSignals_topFiles": ",".join(candidate["supportingSignals"]["topFiles"]),
            "trendContext_trendSignalRows": candidate["trendContext"]["trendSignalRows"],
            "trendContext_trendChangeCount": candidate["trendContext"]["trendChangeCount"],
            "decision_state": candidate["decision"]["state"],
        })
    with (output_path / "candidate_list.csv").open("w", encoding="utf-8", newline="") as handle:
        writer_csv = csv.DictWriter(handle, fieldnames=fields)
        writer_csv.writeheader()
        writer_csv.writerows(csv_rows)

    summary_payload = {
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "input": {
            "workarounds": [str(p) for p in workaround_paths],
            "trends": str(Path(args.trends)) if args.trends else "",
        },
        "candidateCount": len(candidate_rows),
        "thresholds": {
            "minSignalRows": args.min_signal_rows,
            "minChangeCount": args.min_change_count,
            "maxSamples": args.max_samples,
            "maxTopFiles": args.max_top_files,
        },
        "candidateShard": {
            "prefix": "candidate",
            "shardSize": args.row_shard_size,
            "files": writer.files,
            "totalRows": writer.total_rows,
        },
    }
    with (output_path / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary_payload, handle, indent=2, sort_keys=True)

    writer.close()

    print(f"Wrote {writer.total_rows} candidate rows to {output_path / 'candidates'}")
    print(f"Candidate summary written to {output_path / 'summary.json'}")


if __name__ == "__main__":
    main()
