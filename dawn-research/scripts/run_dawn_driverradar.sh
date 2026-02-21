#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run_dawn_driverradar.sh [options]

Collects Gerrit data and runs workaround analysis.

Options:
  --out PATH                      Output directory (default: data)
  --since DATE                    Lower date bound, e.g. 2025-01-01
  --until DATE                    Upper date bound, e.g. 2026-01-16
  --status NAME                   merged|open|abandoned|all (default: merged)
  --query "TEXT"                  Extra Gerrit query terms
  --limit N                       Page size passed to Gerrit
  --max-pages N                   Safety cap
  --skip-fetch                    Skip Gerrit fetch step
  --raw-input PATH                Analyze an existing raw_changes directory/file instead of fetching
  --resume-fetch                  Resume into existing raw output with dedupe (default: on)
  --no-resume-fetch               Do a fresh fetch write (discard cache in out/raw_changes)
  --use-manifest                  Use manifest to infer missing --since (default: on)
  --no-manifest                   Skip manifest inference
  --manifest PATH                 Manifest file path (default: out/dawn_research_manifest.json)
  --shard-size N                  Rows per raw shard file
  --max-shard-mb N                Max raw shard size in MB (default: 32)
  --row-shard-size N              Rows per review-row shard
  --workaround-shard-size N       Rows per workaround row shard
  --signal-shard-size N           Rows per signal row shard
  --trend-row-shard-size N        Rows per trend row shard (from trends)
  --trend-month-shard-size N      Rows per trend month shard
  --hotspot-row-shard-size N      Rows per file hotspot shard
  --candidate-row-shard-size N    Rows per candidate row shard
  --candidate-min-signal-rows N   Minimum workaround rows per candidate
  --candidate-min-change-count N  Minimum change-count per candidate
  --skip-workarounds             Skip workaround extraction
  --skip-trends                   Skip trend matrix generation
  --skip-hotspots                 Skip file hotspot generation
  --skip-candidates               Skip Fawn-ready candidate pack generation
  --help
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OUT_DIR="data"
STATUS="merged"
LIMIT="200"
MAX_PAGES="20"
SINCE=""
UNTIL=""
QUERY=""
SKIP_FETCH="0"
RAW_INPUT=""
RESUME_FETCH="1"
RAW_SHARD_SIZE="300"
RAW_SHARD_MB="32"
ROW_SHARD_SIZE="1500"
WORKAROUND_SHARD_SIZE="500"
SIGNAL_SHARD_SIZE="500"
TREND_ROW_SHARD_SIZE="500"
TREND_MONTH_SHARD_SIZE="500"
HOTSPOT_ROW_SHARD_SIZE="500"
CANDIDATE_ROW_SHARD_SIZE="500"
MIN_SIGNAL_ROWS="3"
MIN_CHANGE_COUNT="2"
USE_MANIFEST="1"
MANIFEST_PATH="dawn_research_manifest.json"
SKIP_WORKAROUNDS="0"
SKIP_TRENDS="0"
SKIP_HOTSPOTS="0"
SKIP_CANDIDATES="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --out)
      OUT_DIR="$2"
      shift 2
      ;;
    --since)
      SINCE="$2"
      shift 2
      ;;
    --until)
      UNTIL="$2"
      shift 2
      ;;
    --status)
      STATUS="$2"
      shift 2
      ;;
    --query)
      QUERY="$2"
      shift 2
      ;;
    --limit)
      LIMIT="$2"
      shift 2
      ;;
    --max-pages)
      MAX_PAGES="$2"
      shift 2
      ;;
    --skip-fetch)
      SKIP_FETCH="1"
      shift 1
      ;;
    --raw-input)
      RAW_INPUT="$2"
      SKIP_FETCH="1"
      shift 2
      ;;
    --resume-fetch)
      RESUME_FETCH="1"
      shift 1
      ;;
    --no-resume-fetch)
      RESUME_FETCH="0"
      shift 1
      ;;
    --use-manifest)
      USE_MANIFEST="1"
      shift 1
      ;;
    --no-manifest)
      USE_MANIFEST="0"
      shift 1
      ;;
    --manifest)
      MANIFEST_PATH="$2"
      shift 2
      ;;
    --shard-size)
      RAW_SHARD_SIZE="$2"
      shift 2
      ;;
    --max-shard-mb)
      RAW_SHARD_MB="$2"
      shift 2
      ;;
    --row-shard-size)
      ROW_SHARD_SIZE="$2"
      shift 2
      ;;
    --workaround-shard-size)
      WORKAROUND_SHARD_SIZE="$2"
      shift 2
      ;;
    --signal-shard-size)
      SIGNAL_SHARD_SIZE="$2"
      shift 2
      ;;
    --trend-row-shard-size)
      TREND_ROW_SHARD_SIZE="$2"
      shift 2
      ;;
    --trend-month-shard-size)
      TREND_MONTH_SHARD_SIZE="$2"
      shift 2
      ;;
    --hotspot-row-shard-size)
      HOTSPOT_ROW_SHARD_SIZE="$2"
      shift 2
      ;;
    --candidate-row-shard-size)
      CANDIDATE_ROW_SHARD_SIZE="$2"
      shift 2
      ;;
    --candidate-min-signal-rows)
      MIN_SIGNAL_ROWS="$2"
      shift 2
      ;;
    --candidate-min-change-count)
      MIN_CHANGE_COUNT="$2"
      shift 2
      ;;
    --skip-workarounds)
      SKIP_WORKAROUNDS="1"
      shift 1
      ;;
    --skip-trends)
      SKIP_TRENDS="1"
      shift 1
      ;;
    --skip-hotspots)
      SKIP_HOTSPOTS="1"
      shift 1
      ;;
    --skip-candidates)
      SKIP_CANDIDATES="1"
      shift 1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

mkdir -p "$OUT_DIR"
if [[ "$MANIFEST_PATH" == /* ]]; then
  MANIFEST_FILE="$MANIFEST_PATH"
else
  MANIFEST_FILE="$OUT_DIR/$MANIFEST_PATH"
fi

RAW_INPUT_DIR="$OUT_DIR/raw_changes"
if [[ -n "$RAW_INPUT" ]]; then
  RAW_INPUT_DIR="$RAW_INPUT"
fi

if [[ "$SINCE" == "" && "$SKIP_FETCH" == "0" && "$RESUME_FETCH" == "1" && "$USE_MANIFEST" == "1" ]]; then
  if [[ -f "$MANIFEST_FILE" ]]; then
    since_from_manifest="$(python3 - "$MANIFEST_FILE" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as handle:
    manifest = json.load(handle)
run_metadata = manifest.get("raw", {})
value = run_metadata.get("lastMaxUpdated") or ""
print(value)
PY
)"
    if [[ -n "$since_from_manifest" ]]; then
      SINCE="$since_from_manifest"
    fi
  fi
fi

if [[ "$SKIP_FETCH" == "0" ]]; then
  fetch_args=(
    --project dawn
    --status "$STATUS"
    --limit "$LIMIT"
    --max-pages "$MAX_PAGES"
    --shard-size "$RAW_SHARD_SIZE"
    --max-shard-mb "$RAW_SHARD_MB"
    --output "$OUT_DIR"
  )
  if [[ "$RESUME_FETCH" == "1" ]]; then
    fetch_args+=(--resume)
  fi
  if [[ -n "$SINCE" ]]; then
    fetch_args+=(--since "$SINCE")
  fi
  if [[ -n "$UNTIL" ]]; then
    fetch_args+=(--until "$UNTIL")
  fi
  if [[ -n "$QUERY" ]]; then
    fetch_args+=(--query "$QUERY")
  fi

  "$SCRIPT_DIR/fetch_gerrit_changes.sh" "${fetch_args[@]}"
else
  if [[ -z "$RAW_INPUT" ]]; then
    if [[ ! -d "$RAW_INPUT_DIR" && ! -f "$RAW_INPUT_DIR" ]]; then
      echo "Error: --skip-fetch requires existing input at: $RAW_INPUT_DIR" >&2
      exit 1
    fi
  elif [[ ! -d "$RAW_INPUT_DIR" && ! -f "$RAW_INPUT_DIR" ]]; then
    echo "Error: --raw-input path does not exist: $RAW_INPUT_DIR" >&2
    exit 1
  fi
fi

ANALYSIS_OUTPUT="$OUT_DIR/analysis"
if [[ "$SKIP_WORKAROUNDS" == "0" ]]; then
  python3 "$SCRIPT_DIR/analyze_dawn_workarounds.py" \
    --input "$RAW_INPUT_DIR" \
    --row-shard-size "$ROW_SHARD_SIZE" \
    --workaround-shard-size "$WORKAROUND_SHARD_SIZE" \
    --signal-shard-size "$SIGNAL_SHARD_SIZE" \
    --output "$ANALYSIS_OUTPUT"
elif [[ ! -d "$ANALYSIS_OUTPUT/workarounds" && ! -f "$ANALYSIS_OUTPUT/workarounds/workaround_rows-000001.jsonl" ]]; then
  echo "Error: --skip-workarounds requires existing analysis workaround rows at: $ANALYSIS_OUTPUT/workarounds" >&2
  exit 1
fi

trend_output="$ANALYSIS_OUTPUT/trends"
hotspot_output="$ANALYSIS_OUTPUT/hotspots"
candidate_output="$ANALYSIS_OUTPUT/candidate_pack"

if [[ "$SKIP_TRENDS" == "0" ]]; then
  python3 "$SCRIPT_DIR/analyze_dawn_trends.py" \
    --input "$ANALYSIS_OUTPUT/workarounds" \
    --output "$trend_output" \
    --row-shard-size "$TREND_ROW_SHARD_SIZE" \
    --monthly-shard-size "$TREND_MONTH_SHARD_SIZE"
fi

if [[ "$SKIP_HOTSPOTS" == "0" ]]; then
  python3 "$SCRIPT_DIR/analyze_dawn_hotspots.py" \
    --input "$ANALYSIS_OUTPUT/workarounds" \
    --output "$hotspot_output" \
    --row-shard-size "$HOTSPOT_ROW_SHARD_SIZE"
fi

if [[ "$SKIP_CANDIDATES" == "0" ]]; then
  trend_args=()
  if [[ "$SKIP_TRENDS" == "0" && -f "$trend_output/trend_buckets.jsonl" ]]; then
    trend_args+=(--trends "$trend_output/trend_buckets.jsonl")
  fi

  python3 "$SCRIPT_DIR/build_fawn_candidate_pack.py" \
    --workarounds "$ANALYSIS_OUTPUT/workarounds" \
    --output "$candidate_output" \
    --min-signal-rows "$MIN_SIGNAL_ROWS" \
    --min-change-count "$MIN_CHANGE_COUNT" \
    --row-shard-size "$CANDIDATE_ROW_SHARD_SIZE" \
    "${trend_args[@]}"
fi

echo "Run complete. Results in: $OUT_DIR/analysis"

if [[ "$USE_MANIFEST" == "1" ]]; then
python3 - "$OUT_DIR/review_index.json" "$ANALYSIS_OUTPUT/summary.json" \
  "$trend_output/summary.json" "$hotspot_output/summary.json" "$candidate_output/summary.json" \
  "$MANIFEST_FILE" \
  "$SKIP_FETCH" "$SKIP_WORKAROUNDS" "$SKIP_TRENDS" "$SKIP_HOTSPOTS" \
  "$SKIP_CANDIDATES" "$RESUME_FETCH" "$USE_MANIFEST" "$RAW_SHARD_MB" \
  "$RAW_SHARD_SIZE" "$QUERY" "$STATUS" "$SINCE" "$UNTIL" <<'PY'
import json
import os
import sys
from datetime import datetime


def _safe_load(path: str):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _as_bool(text: str) -> bool:
    return text == "1"


raw_index = _safe_load(sys.argv[1])
analysis = _safe_load(sys.argv[2])
trends = _safe_load(sys.argv[3])
hotspots = _safe_load(sys.argv[4])
candidate_pack = _safe_load(sys.argv[5])
manifest_path = sys.argv[6]
skip_fetch = _as_bool(sys.argv[7])
skip_workarounds = _as_bool(sys.argv[8])
skip_trends = _as_bool(sys.argv[9])
skip_hotspots = _as_bool(sys.argv[10])
skip_candidates = _as_bool(sys.argv[11])
resume_fetch = _as_bool(sys.argv[12])
use_manifest = _as_bool(sys.argv[13])
shard_mb = int(sys.argv[14])
shard_rows = int(sys.argv[15])
query = sys.argv[16]
status = sys.argv[17]
since = sys.argv[18]
until = sys.argv[19]

manifest = {
    "generatedAt": datetime.utcnow().isoformat() + "Z",
    "outDir": os.path.dirname(manifest_path),
    "raw": raw_index,
    "analysis": analysis,
    "trends": trends,
    "hotspots": hotspots,
    "candidatePack": candidate_pack,
    "stageControls": {
        "skipFetch": skip_fetch,
        "skipWorkarounds": skip_workarounds,
        "skipTrends": skip_trends,
        "skipHotspots": skip_hotspots,
        "skipCandidates": skip_candidates,
        "resumeFetch": resume_fetch,
        "useManifest": use_manifest,
        "shards": {
            "rawShardSizeMB": shard_mb,
            "rawShardRows": shard_rows,
        },
        "query": query,
        "status": status,
        "since": since,
        "until": until,
    },
}

raw_last_updated_max = raw_index.get("lastUpdatedMax", "")
if not isinstance(raw_last_updated_max, str) or not raw_last_updated_max:
    raw_last_updated_max = raw_index.get("maxUpdated", "")
if isinstance(raw_last_updated_max, str):
    manifest["raw"]["lastMaxUpdated"] = raw_last_updated_max
else:
    manifest["raw"]["lastMaxUpdated"] = ""

with open(manifest_path, "w", encoding="utf-8") as handle:
    json.dump(manifest, handle, indent=2, sort_keys=True)
PY
else
  echo "Manifest disabled (--no-manifest). Skipping manifest write."
fi
