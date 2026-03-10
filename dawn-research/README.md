# Dawn Research Pipeline (Fawn)

`dawn-research` is a reusable research pipeline for mining Dawn Gerrit history, normalizing workaround signals, and producing human-review packets for Fawn quirk work.  
It is designed for repeated use without re-downloading the same data.

## Goals

- Keep source data cacheable and append-only.
- Keep analysis artifacts sharded (`.jsonl`) and deterministic.
- Support incremental updates from previous runs.
- Keep raw data and derived data in clearly separated stages.
- Generate only evidence artifacts for human review (no automatic Fawn code generation).

## Folder layout

- `scripts/fetch_gerrit_changes.sh` — fetch raw Dawn Gerrit changes and persist raw shards.
- `scripts/analyze_dawn_workarounds.py` — extract workaround signals and base structured rows.
- `scripts/analyze_dawn_trends.py` — compute vendor/backend/failure-class trend buckets.
- `scripts/analyze_dawn_hotspots.py` — compute file-level hotspots from workaround rows.
- `scripts/build_fawn_candidate_pack.py` — build review-ready candidate queue from signals.
- `scripts/run_dawn_driverradar.sh` — one-command orchestrator (fetch -> workaround -> trend -> hotspots -> candidates).
- `config/patterns.json` — regexp rule source for extraction.
- `data/` — generated artifacts (created at runtime).
- `docs/README.md` — operational runbook and cache/manifest maintenance.

## Runtime guarantees

This folder is built as a reusable pipeline:

- Raw fetch can be resumed (`--resume`) and deduplicated via `changeId / id / number`.
- Raw outputs are not mutated by default.
- Existing output shards are reused across runs.
- `raw_changes.ndjson` and `raw_changes/*.jsonl` shards are append-only during resume mode.
- Shard size cap defaults to 32MB:
  - `--max-shard-mb` (default `32`)
  - enforced in `fetch_gerrit_changes.sh` as `maxShardBytes`.
- `run_dawn_driverradar.sh` can reuse prior manifest state by default.

## Quick start

### 1) One-time bootstrap fetch

```bash
cd dawn-research
./scripts/run_dawn_driverradar.sh \
  --status merged \
  --since 2025-01-01 \
  --until 2026-01-16 \
  --limit 300 \
  --output data
```

### 2) Continuous incremental update (no duplicate fetches)

```bash
./scripts/run_dawn_driverradar.sh \
  --status merged \
  --limit 300 \
  --output data \
  --use-manifest
```

With manifest enabled, the script reads `manifest.lastMaxUpdated` and uses it as `--since` for the next pass.

### 3) Fast analysis against cached raw data only

```bash
./scripts/run_dawn_driverradar.sh \
  --skip-fetch \
  --raw-input data/raw_changes \
  --skip-workarounds \
  --skip-trends \
  --skip-hotspots \
  --skip-candidates
```

### 4) Full pipeline with manual stage skips

```bash
./scripts/run_dawn_driverradar.sh \
  --status merged \
  --since 2025-01-01 \
  --until 2026-01-16 \
  --skip-hotspots \
  --skip-candidates
```

## Stage-only controls

- `--skip-workarounds`
- `--skip-trends`
- `--skip-hotspots`
- `--skip-candidates`
- `--skip-fetch`
- `--raw-input PATH` to force using existing raw rows and bypass network fetch.

## Cache controls

- `--resume-fetch` (default): resume into existing raw output and dedupe.
- `--no-resume-fetch`: rewrite raw output from scratch and drop existing `raw_changes/` shards.
- `--max-shard-mb N`: change raw shard byte cap.
- `--shard-size N`: change raw rows per raw shard.

## Manifest controls

- `--manifest PATH` location for execution manifest (default: `out/dawn_research_manifest.json`).
- `--use-manifest` (default on): when `--since` is omitted, derive it from prior manifest state.
- `--no-manifest`: disable manifest inference and skip manifest writes for this run.

Manifest is intentionally small and meant to be the cache anchor for incremental updates. A typical path is:

- `data/dawn_research_manifest.json`

Useful manifest fields:

- `raw.project`, `raw.status`, `raw.since`, `raw.until`, `raw.query`
- `raw.lastUpdatedMin`, `raw.lastUpdatedMax`
- `raw.existingRows`, `raw.addedRows`, `raw.rawRows`
- `raw.lastMaxUpdated` (same value as `raw.lastUpdatedMax`, convenient for increment seed)
- `stageControls` (`skipFetch`, `skipWorkarounds`, `skipTrends`, `skipHotspots`, `skipCandidates`, `resumeFetch`, `useManifest`)
- Stage summary blocks for analysis/trends/hotspots/candidate outputs.

## Script inputs and outputs

- `fetch_gerrit_changes.sh`
  - Input: `--project`, `--status`, `--since`, `--until`, `--query`
  - Output:
    - `data/raw_changes.ndjson`
    - `data/raw_changes/changes-000001.jsonl` ... (raw shards)
    - `data/review_index.json`
- `analyze_dawn_workarounds.py` (`--input data/raw_changes`)
  - Output:
    - `data/analysis/rows/review_rows-00001.jsonl`
    - `data/analysis/workarounds/workaround_rows-00001.jsonl`
    - `data/analysis/signals/signals-00001.jsonl`
    - `data/analysis/workarounds.csv`
    - `data/analysis/workarounds.jsonl` (flattened fallback)
    - `data/analysis/pattern_signals.jsonl`
    - `data/analysis/summary.json`
- `analyze_dawn_trends.py`
  - Output:
    - `data/analysis/trends/matrix/trend_bucket-00001.jsonl`
    - `data/analysis/trends/trend_buckets.jsonl` (flattened)
    - `data/analysis/trends/trend_matrix.csv`
    - `data/analysis/trends/time_series/trend_month-00001.jsonl`
    - `data/analysis/trends/trend_timeseries.json`
    - `data/analysis/trends/summary.json`
- `analyze_dawn_hotspots.py`
  - Output:
    - `data/analysis/hotspots/files/file_hotspot-00001.jsonl`
    - `data/analysis/hotspots/file_hotspots.csv`
    - `data/analysis/hotspots/summary.json`
- `build_fawn_candidate_pack.py`
  - Output:
    - `data/analysis/candidate_pack/candidates/candidate-00001.jsonl`
    - `data/analysis/candidate_pack/candidate_list.csv`
    - `data/analysis/candidate_pack/summary.json`
- `run_dawn_driverradar.sh`
  - Output:
    - `data/dawn_research_manifest.json`

## Why shard-first data layout

Each row-based artifact is split into fixed-width shards:

- Faster reruns because downstream stages can target a subset of files.
- Deterministic replay order and easy resumption.
- Storage and transfer safety for large windows (default raw shards capped near 32MB).
- Easy archival and pruning for history windows without losing schema history.

## Data refresh strategy

- Run a long window periodically (e.g., quarterly) to establish baseline.
- Then run short incremental windows daily/weekly with `--use-manifest`.
- If backfill is needed for an old range, set `--since` and `--until`, and optionally `--no-resume-fetch` if you want strict rewrites.
- Keep `data/` checked in only if needed; otherwise, treat as cache and re-generateable in CI/local environment.

## Non-functional notes

- No script in this folder emits or mutates Fawn runtime files.
- Candidate output is evidence for human review only; no automatic code generation is performed.
- Raw data retention and retention policies are controlled by caller policy (not implicit script behavior).

## Known extension points

- `config/patterns.json` adds/changes signal coverage.
- Use separate analysis scripts for custom aggregations by consuming:
  - `raw_changes.ndjson`, `data/analysis/workarounds/workaround_rows-*.jsonl`, and
  - `data/analysis/summary.json`.
- Add new scripts in this folder using the same sharded `.jsonl` + summary output contract.
