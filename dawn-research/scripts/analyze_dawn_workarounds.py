#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterator, List, Optional, Tuple


def load_patterns(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def default_patterns() -> dict:
    return {
        "workaround_patterns": [
            {"id": "workaround", "pattern": r"\bworkaround\b"},
            {"id": "driver_workaround", "pattern": r"\bdriver(?:-|\s+)workaround\b"},
            {"id": "workaround_for", "pattern": r"\bworkaround\s+for\b"},
            {"id": "driver_bug", "pattern": r"\bdriver\s+bug\b"},
            {"id": "backend_workaround", "pattern": r"\bbackend[_-]specific\b"},
            {"id": "adreno_workaround", "pattern": r"\badreno\s+workaround\b"},
            {"id": "intel_workaround", "pattern": r"\bintel\s+workaround\b"},
        ],
        "vendor_patterns": [
            {"id": "amd", "pattern": r"\bamd\b|\bradeon\b|\bgfx\b"},
            {"id": "intel", "pattern": r"\bintel\b|\bxe\b|\badln\b|\barc\b|\bultra\b"},
            {"id": "nvidia", "pattern": r"\bnvidia\b|\bgeforce\b|\bturing\b|\bampere\b"},
            {"id": "qualcomm", "pattern": r"\bqualcomm\b|\badreno\b|\bsnapdragon\b"},
            {"id": "apple", "pattern": r"\bapple\b|\bmgpu\b|\barm\.?"},
            {"id": "arm", "pattern": r"\barm\b|\bmali\b"},
        ],
        "backend_patterns": [
            {"id": "vulkan", "pattern": r"\bvulkan\b"},
            {"id": "metal", "pattern": r"\bmetal\b"},
            {"id": "d3d", "pattern": r"\bd3d|direct3d|dx12|d3d12\b"},
            {"id": "opengl", "pattern": r"\bogl\b|\bopengl\b"},
            {"id": "webgpu", "pattern": r"\bwebgpu\b"},
            {"id": "dawn", "pattern": r"\bdawn\b"},
        ],
        "severity_patterns": [
            {"id": "crash", "pattern": r"\bcrash\b|\bcrashed\b|\bcrashing\b"},
            {"id": "hang", "pattern": r"\bhang\b|\bhangs\b|\bhanging\b"},
            {"id": "artifact", "pattern": r"\bartifact\b|\bvisual\b|\brendering\b"},
            {"id": "incorrect", "pattern": r"\bincorrect\b|\bwrong\b|\bregression\b"},
            {"id": "stability", "pattern": r"\bstability\b|\bflaky\b|\bsporadic\b|\bintermittent\b"},
            {"id": "performance", "pattern": r"\bperf\b|\bperformance\b|\bslowdown\b|\bspike\b"},
        ],
    }


class NDJSONShardedWriter:
    def __init__(self, output_dir: Path, prefix: str, shard_size: int, fallback_file: Optional[Path] = None):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.prefix = prefix
        self.shard_size = max(1, shard_size)
        self.shard_index = 0
        self.rows_in_shard = 0
        self.total_rows = 0
        self.files: List[str] = []
        self.handle = None
        self.current_path: Optional[Path] = None
        self._open_next()
        self.fallback_handle = fallback_file.open("w", encoding="utf-8") if fallback_file else None

    def _open_next(self) -> None:
        if self.handle is not None:
            self.handle.close()
        self.shard_index += 1
        self.rows_in_shard = 0
        self.current_path = self.output_dir / f"{self.prefix}-{self.shard_index:05d}.jsonl"
        self.handle = self.current_path.open("w", encoding="utf-8")
        self.files.append(self.current_path.name)

    def write(self, row: dict) -> None:
        if self.rows_in_shard >= self.shard_size:
            self._open_next()

        line = json.dumps(row, ensure_ascii=False)
        self.handle.write(line)
        self.handle.write("\n")
        self.rows_in_shard += 1
        self.total_rows += 1
        if self.fallback_handle is not None:
            self.fallback_handle.write(line + "\n")

    def close(self) -> None:
        if self.handle is not None:
            self.handle.close()
        if self.fallback_handle is not None:
            self.fallback_handle.close()


def compile_patterns(pattern_items: List[dict]) -> List[Tuple[str, re.Pattern]]:
    compiled = []
    for entry in pattern_items:
        rid = entry["id"]
        regex = re.compile(entry["pattern"], re.IGNORECASE)
        compiled.append((rid, regex))
    return compiled


def get_text_entries(change: dict) -> Iterator[Tuple[str, str]]:
    for key in ("subject", "commitMessage", "message", "description"):
        value = change.get(key)
        if isinstance(value, str) and value.strip():
            yield key, value

    messages = change.get("messages", [])
    for idx, msg in enumerate(messages):
        if isinstance(msg, dict):
            text = msg.get("message", "").strip()
            if text:
                yield (f"messages[{idx}]", text)

    all_comments = change.get("comments", {})
    if isinstance(all_comments, dict):
        for file_name, file_comments in all_comments.items():
            for comment in file_comments if isinstance(file_comments, list) else []:
                if isinstance(comment, dict):
                    body = comment.get("message") or comment.get("comment")
                    if isinstance(body, str) and body.strip():
                        yield (f"comments[{file_name}]", body)

    patch_sets = change.get("patchSets") or change.get("patch_sets") or []
    for i, patch in enumerate(patch_sets):
        if not isinstance(patch, dict):
            continue
        for comment in patch.get("comments", []):
            if isinstance(comment, dict):
                body = comment.get("message") or comment.get("comment")
                if isinstance(body, str) and body.strip():
                    yield (f"patchSets[{i}].comments", body)

    for key in ("author", "currentPatchSet", "revisions"):
        value = change.get(key)
        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                if isinstance(nested_value, str) and nested_key.lower() in {"message", "description", "commitMessage"}:
                    yield (f"{key}.{nested_key}", nested_value)


def find_matches(text: str, compiled_patterns: List[Tuple[str, re.Pattern]]) -> List[str]:
    matches = []
    for rid, regex in compiled_patterns:
        if regex.search(text):
            matches.append(rid)
    return matches


def find_urls(change: dict) -> str:
    project = change.get("project", "dawn")
    change_id = change.get("changeId") or change.get("change_id") or change.get("id", "")
    number = change.get("number") or change.get("number_")
    if number:
        return f"https://dawn-review.googlesource.com/c/{project}/+/{number}"
    if change_id:
        return f"https://dawn-review.googlesource.com/c/{project}/+/{change_id}"
    return ""


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()


def write_rows_from_inputs(paths: List[Path]) -> Iterator[Tuple[str, dict]]:
    for input_path in paths:
        with input_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if line:
                    yield input_path.name, json.loads(line)


def normalize_snippet(text: str, limit: int = 240) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= limit:
        return one_line
    return f"{one_line[:limit]}..."


def write_csv_rows(output_path: Path):
    fields = [
        "change_id",
        "change_number",
        "status",
        "updated",
        "subject",
        "author",
        "source",
        "match",
        "vendors",
        "backends",
        "severity",
        "snippet",
        "files",
        "url",
        "project",
    ]
    handle = output_path.open("w", encoding="utf-8", newline="")
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    return handle, writer


def resolve_input_paths(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise ValueError(f"Input path does not exist: {path}")
    paths = sorted([p for p in path.iterdir() if p.is_file() and p.suffix in {".jsonl", ".ndjson"}])
    if not paths:
        raise ValueError(f"No JSONL files in {path}")
    return paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to raw_changes.ndjson or raw_changes/ directory of shards")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument(
        "--patterns",
        default=str(Path(__file__).resolve().parent.parent / "config" / "patterns.json"),
        help="Path to pattern JSON config",
    )
    parser.add_argument("--row-shard-size", type=int, default=1500, help="Rows per review-row JSONL shard")
    parser.add_argument("--workaround-shard-size", type=int, default=500, help="Rows per workaround JSONL shard")
    parser.add_argument("--signal-shard-size", type=int, default=500, help="Rows per signal JSONL shard")
    args = parser.parse_args()

    input_path = Path(args.input)
    input_paths = resolve_input_paths(input_path)
    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    patterns_path = Path(args.patterns)
    if patterns_path.exists():
        cfg = load_patterns(patterns_path)
    else:
        cfg = default_patterns()

    workaround_patterns = compile_patterns(cfg.get("workaround_patterns", []))
    vendor_patterns = compile_patterns(cfg.get("vendor_patterns", []))
    backend_patterns = compile_patterns(cfg.get("backend_patterns", []))
    severity_patterns = compile_patterns(cfg.get("severity_patterns", []))

    review_writer = NDJSONShardedWriter(
        output_path / "rows",
        "review_rows",
        args.row_shard_size,
    )
    workaround_writer = NDJSONShardedWriter(
        output_path / "workarounds",
        "workaround_rows",
        args.workaround_shard_size,
        fallback_file=output_path / "workarounds.jsonl",
    )
    signal_writer = NDJSONShardedWriter(
        output_path / "signals",
        "signals",
        args.signal_shard_size,
        fallback_file=output_path / "pattern_signals.jsonl",
    )

    summary = defaultdict(Counter)
    total_changes = 0
    total_review_rows = 0
    total_workaround_rows = 0
    total_signal_rows = 0

    csv_handle, csv_writer = write_csv_rows(output_path / "workarounds.csv")

    for source_file, change in write_rows_from_inputs(input_paths):
        total_changes += 1
        change_id = change.get("changeId", change.get("id", ""))
        change_number = change.get("number", "")
        subject = change.get("subject", "")
        project = change.get("project", "")
        status = change.get("status", "")
        updated = change.get("lastUpdated", change.get("updated", ""))
        author = ""
        if isinstance(change.get("owner"), dict):
            owner = change["owner"]
            author = owner.get("name", "") or owner.get("username", "") or owner.get("email", "")
        url = find_urls(change)
        files = []
        if isinstance(change.get("files"), list):
            files = [f.get("file", f) if isinstance(f, dict) else str(f) for f in change["files"]]

        touched = False
        text_index = 0
        for source, text in get_text_entries(change):
            text_index += 1
            total_review_rows += 1
            review_payload = {
                "row_id": f"{change_id}:{text_index}:{sha1_text(text)[:14]}",
                "source_file": source_file,
                "change_id": change_id,
                "change_number": change_number,
                "status": status,
                "updated": updated,
                "project": project,
                "subject": subject,
                "author": author,
                "source": source,
                "text": text,
                "text_sha1": sha1_text(text),
                "url": url,
            }
            review_writer.write(review_payload)

            workaround_matches = find_matches(text, workaround_patterns)
            if not workaround_matches:
                continue

            vendor_matches = find_matches(text, vendor_patterns)
            backend_matches = find_matches(text, backend_patterns)
            severity_matches = find_matches(text, severity_patterns)

            if not backend_matches:
                signal_tags = vendor_matches + severity_matches
            else:
                signal_tags = backend_matches + vendor_matches + severity_matches
            if not signal_tags:
                continue

            touched = True
            total_workaround_rows += 1
            workaround_row = {
                "change_id": change_id,
                "change_number": change_number,
                "status": status,
                "updated": updated,
                "subject": subject,
                "author": author,
                "source": source,
                "match": "|".join(sorted(set(workaround_matches))),
                "vendors": sorted(set(vendor_matches)),
                "backends": sorted(set(backend_matches)),
                "severity": sorted(set(severity_matches)),
                "snippet": normalize_snippet(text),
                "files": sorted(set(files)),
                "url": url,
                "project": project,
                "source_file": source_file,
            }
            workaround_writer.write(workaround_row)
            csv_writer.writerow({
                "change_id": workaround_row["change_id"],
                "change_number": workaround_row.get("change_number", ""),
                "status": workaround_row.get("status", ""),
                "updated": workaround_row.get("updated", ""),
                "subject": workaround_row.get("subject", ""),
                "author": workaround_row.get("author", ""),
                "source": workaround_row.get("source", ""),
                "match": workaround_row["match"],
                "vendors": ",".join(workaround_row["vendors"]),
                "backends": ",".join(workaround_row["backends"]),
                "severity": ",".join(workaround_row["severity"]),
                "snippet": workaround_row["snippet"],
                "files": ",".join(workaround_row["files"]),
                "url": workaround_row["url"],
                "project": workaround_row["project"],
            })

            for match_id in workaround_matches:
                summary["pattern"].update([match_id])
            for vendor in vendor_matches:
                summary["vendor"].update([vendor])
            for backend in backend_matches:
                summary["backend"].update([backend])
            for sev in severity_matches:
                summary["severity"].update([sev])

            for signal in signal_tags:
                total_signal_rows += 1
                signal_writer.write({
                    "change_id": change_id,
                    "signal": signal,
                    "source": source,
                    "source_file": source_file,
                    "source_text": normalize_snippet(text, 400),
                    "url": url,
                    "match": "|".join(sorted(set(workaround_matches))),
                    "vendors": sorted(set(vendor_matches)),
                    "backends": sorted(set(backend_matches)),
                    "severity": sorted(set(severity_matches)),
                })

        if not touched:
            summary["unmatched"]["no_signal"] += 1

    csv_handle.close()

    review_writer.close()
    workaround_writer.close()
    signal_writer.close()

    summary_payload = {
        "generatedAt": datetime.utcnow().isoformat() + "Z",
        "input": str(input_path),
        "inputFiles": [str(p) for p in input_paths],
        "totalChanges": total_changes,
        "totalReviewRows": total_review_rows,
        "totalWorkaroundRows": total_workaround_rows,
        "totalSignalRows": total_signal_rows,
        "patternCounts": dict(summary["pattern"]),
        "vendorCounts": dict(summary["vendor"]),
        "backendCounts": dict(summary["backend"]),
        "severityCounts": dict(summary["severity"]),
        "unmatchedChangesWithoutSignal": summary["unmatched"]["no_signal"],
        "shards": {
            "reviewRows": {
                "prefix": "review_rows",
                "shardSize": args.row_shard_size,
                "files": review_writer.files,
                "totalRows": review_writer.total_rows,
            },
            "workaroundRows": {
                "prefix": "workaround_rows",
                "shardSize": args.workaround_shard_size,
                "files": workaround_writer.files,
                "totalRows": workaround_writer.total_rows,
            },
            "signals": {
                "prefix": "signals",
                "shardSize": args.signal_shard_size,
                "files": signal_writer.files,
                "totalRows": signal_writer.total_rows,
            },
        },
    }

    with (output_path / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary_payload, handle, indent=2, sort_keys=True)

    print(f"Wrote {review_writer.total_rows} review rows to {output_path / 'rows'}")
    print(f"Wrote {workaround_writer.total_rows} workaround rows to {output_path / 'workarounds'}")
    print(f"Wrote {signal_writer.total_rows} signal rows to {output_path / 'signals'}")
    print(f"Summary: {summary_payload['totalWorkaroundRows']} workaround rows from {summary_payload['totalChanges']} changes")


if __name__ == "__main__":
    main()
