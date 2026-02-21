#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: fetch_gerrit_changes.sh [options]

Required arguments:
  --output PATH            Directory to write raw data and index into.

Optional:
  --project NAME           Gerrit project (default: dawn)
  --status NAME            Gerrit status filter (default: merged)
  --since DATE             Lower date bound, e.g. 2025-01-01
  --until DATE             Upper date bound, e.g. 2026-01-16
  --query "TEXT"           Extra Gerrit query terms
  --host HOSTNAME          Gerrit review host (default: dawn-review.googlesource.com)
  --limit N                Page size (default: 200, max in Gerrit varies)
  --max-pages N            Safety cap for paging (default: 20)
  --shard-size N           Rows per raw JSONL shard (default: 300)
  --max-shard-mb N         Max shard file size in MB (default: 32)
  --resume                 Resume into existing raw output and dedupe
  --help                   Show this message

Example:
  ./fetch_gerrit_changes.sh --status merged --since 2025-01-01 --until 2026-01-16 --output out
EOF
}

PROJECT="${DREAM_GERRIT_PROJECT:-dawn}"
STATUS="${DREAM_GERRIT_STATUS:-merged}"
SINCE="${DREAM_GERRIT_SINCE:-}"
UNTIL="${DREAM_GERRIT_UNTIL:-}"
QUERY="${DREAM_GERRIT_QUERY:-}"
HOST="${DREAM_GERRIT_HOST:-dawn-review.googlesource.com}"
LIMIT="${DREAM_GERRIT_LIMIT:-200}"
MAX_PAGES="${DREAM_GERRIT_MAX_PAGES:-20}"
SHARD_SIZE="${DREAM_GERRIT_SHARD_SIZE:-300}"
MAX_SHARD_BYTES="${DREAM_GERRIT_MAX_SHARD_BYTES:-33554432}"
RESUME="${DREAM_GERRIT_RESUME:-0}"
OUTPUT_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT="$2"
      shift 2
      ;;
    --status)
      STATUS="$2"
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
    --query)
      QUERY="$2"
      shift 2
      ;;
    --host)
      HOST="$2"
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
    --shard-size)
      SHARD_SIZE="$2"
      shift 2
      ;;
    --max-shard-mb)
      MAX_SHARD_BYTES=$(awk -v mb="$2" 'BEGIN { printf "%d", mb * 1024 * 1024 }')
      shift 2
      ;;
    --resume)
      RESUME="1"
      shift 1
      ;;
    --output)
      OUTPUT_DIR="$2"
      shift 2
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

if [[ -z "$OUTPUT_DIR" ]]; then
  echo "Error: --output is required." >&2
  usage
  exit 1
fi

if (( SHARD_SIZE < 1 )); then
  echo "Error: --shard-size must be >= 1" >&2
  exit 1
fi
if (( MAX_SHARD_BYTES < 1 )); then
  echo "Error: --max-shard-mb must be >= 1" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/raw_changes"
RAW_FILE="$OUTPUT_DIR/raw_changes.ndjson"
RAW_SHARD_DIR="$OUTPUT_DIR/raw_changes"
INDEX_FILE="$OUTPUT_DIR/review_index.json"

existing_raw_change_count=0
if [[ -f "$RAW_FILE" ]]; then
  existing_raw_change_count="$(wc -l < "$RAW_FILE")"
fi

if [[ "$RESUME" == "1" ]]; then
  : >> "$RAW_FILE"
else
  : > "$RAW_FILE"
  rm -f "$RAW_SHARD_DIR"/changes-*.jsonl
fi

existing_shard_count=0
if [[ -d "$RAW_SHARD_DIR" ]]; then
  existing_shard_count="$(find "$RAW_SHARD_DIR" -maxdepth 1 -name 'changes-*.jsonl' -type f | wc -l | tr -d ' ')"
fi
if (( existing_shard_count < 0 )); then
  existing_shard_count=0
fi

existing_keys_file="$(mktemp)"
if [[ "$RESUME" == "1" && -f "$RAW_FILE" ]]; then
  jq -r '.changeId // .id // .number // empty' "$RAW_FILE" | sort -u > "$existing_keys_file"
else
  : > "$existing_keys_file"
fi

last_updated_min=""
last_updated_max=""

shard_counter=$((existing_shard_count + 1))
if (( shard_counter < 1 )); then
  shard_counter=1
fi
if (( RESUME == 0 )); then
  shard_counter=1
fi
shard_row_count=0
shard_bytes=0
shard_file=""
total_new_rows=0
request_count=0

open_shard() {
  shard_file="$RAW_SHARD_DIR/changes-$(printf '%06d' "$shard_counter").jsonl"
  : > "$shard_file"
}

write_record() {
  local line="$1"
  local line_bytes=0
  local dedupe_key=""
  dedupe_key="$(printf '%s' "$line" | jq -r '.changeId // .id // .number // empty')"
  if [[ -n "$dedupe_key" ]] && grep -Fxq "$dedupe_key" "$existing_keys_file"; then
    return
  fi

  if [[ -z "$shard_file" ]]; then
    open_shard
  fi
  line_bytes="$(printf '%s\n' "$line" | wc -c | tr -d ' ')"
  if (( shard_row_count >= SHARD_SIZE )) || (( shard_bytes + line_bytes >= MAX_SHARD_BYTES )); then
    shard_counter=$((shard_counter + 1))
    shard_row_count=0
    shard_bytes=0
    open_shard
  fi

  printf '%s\n' "$line" >> "$shard_file"
  printf '%s\n' "$line" >> "$RAW_FILE"
  shard_row_count=$((shard_row_count + 1))
  shard_bytes=$((shard_bytes + line_bytes))
  total_new_rows=$((total_new_rows + 1))
  if [[ -n "$dedupe_key" ]]; then
    echo "$dedupe_key" >> "$existing_keys_file"
  fi

  updated_value="$(printf '%s' "$line" | jq -r '.lastUpdated // .updated // empty')"
  if [[ -n "$updated_value" ]]; then
    if [[ -z "$last_updated_min" || "$updated_value" < "$last_updated_min" ]]; then
      last_updated_min="$updated_value"
    fi
    if [[ -z "$last_updated_max" || "$updated_value" > "$last_updated_max" ]]; then
      last_updated_max="$updated_value"
    fi
  fi
}

query_parts=("project:$PROJECT")
if [[ -n "$STATUS" && "$STATUS" != "all" ]]; then
  query_parts+=("status:$STATUS")
fi
if [[ -n "$SINCE" ]]; then
  query_parts+=("after:$SINCE")
fi
if [[ -n "$UNTIL" ]]; then
  query_parts+=("before:$UNTIL")
fi
if [[ -n "$QUERY" ]]; then
  query_parts+=("$QUERY")
fi

query="${query_parts[*]}"
query_encoded="$(python3 - "$query" <<'PY'
import urllib.parse
import sys
print(urllib.parse.quote(sys.argv[1], safe=''))
PY
)"

start=0
page=0

while (( page < MAX_PAGES )); do
  page=$((page + 1))
  url="https://$HOST/changes/?q=$query_encoded&n=$LIMIT&start=$start&o=ALL_REVISIONS&o=ALL_COMMITS&o=ALL_FILES&o=MESSAGES"

  response="$(curl -fsSL "$url")"
  response="$(printf '%s' "$response" | sed -e "1s/^)]}'//")"
  tmp_batch_file="$(mktemp)"
  echo "$response" | jq -c '.[] | select(has("project"))' > "$tmp_batch_file"
  batch_count=0
  while IFS= read -r line; do
    if [[ -n "$line" ]]; then
      write_record "$line"
      batch_count=$((batch_count + 1))
    fi
  done < "$tmp_batch_file"
  request_count=$((request_count + 1))

  rm -f "$tmp_batch_file"
  echo "Fetched page $page: $batch_count changes (start=$start)" >&2

  if [[ "$batch_count" -lt "$LIMIT" ]]; then
    break
  fi
  start=$((start + LIMIT))
done

rm -f "$existing_keys_file"

raw_shard_count="$(find "$RAW_SHARD_DIR" -maxdepth 1 -name 'changes-*.jsonl' -type f | wc -l | tr -d ' ')"

query_metadata="$query"
cat > "$INDEX_FILE" <<EOF
{
  "project": "$PROJECT",
  "status": "$STATUS",
  "shardSize": $SHARD_SIZE,
  "maxShardBytes": $MAX_SHARD_BYTES,
  "since": "$SINCE",
  "until": "$UNTIL",
  "query": "$query_metadata",
  "host": "$HOST",
  "limit": $LIMIT,
  "maxPages": $MAX_PAGES,
  "requests": $request_count,
  "existingRows": $existing_raw_change_count,
  "addedRows": $total_new_rows,
  "rawRows": $((existing_raw_change_count + total_new_rows)),
  "rawShardCount": $raw_shard_count,
  "rawShardDir": "$(basename "$RAW_SHARD_DIR")",
  "totalChanges": $total_new_rows,
  "lastUpdatedMin": "$last_updated_min",
  "lastUpdatedMax": "$last_updated_max",
  "resume": "$RESUME",
  "output": "$(basename "$RAW_FILE")"
}
EOF

echo "Wrote $total_new_rows new rows to $RAW_FILE"
echo "Wrote $total_new_rows rows across $raw_shard_count shard files in $RAW_SHARD_DIR"
echo "Index written to $INDEX_FILE"
