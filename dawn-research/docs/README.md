# Dawn Research Operations Guide

This folder documents practical operating procedures for `dawn-research` so the pipeline can be reused safely and repeatedly without reprocessing unchanged history.

## 1) Setup and initialization

- Ensure scripts are executable:
  - `chmod +x ./scripts/fetch_gerrit_changes.sh ./scripts/run_dawn_driverradar.sh`
- Run from repository root of this folder or pass absolute paths.
- Required tools: `bash`, `curl`, `jq`, `python3`.
- Baseline directory is `data/` by default.

## 2) Baseline ingest plan (first-time)

Use one larger window for a clean baseline:

```bash
cd dawn-research
./scripts/run_dawn_driverradar.sh \
  --status merged \
  --since 2024-01-01 \
  --until 2026-01-16 \
  --limit 300 \
  --out data
```

Expected output:

- `data/raw_changes.ndjson`
- `data/raw_changes/changes-000001.jsonl` ...
- `data/review_index.json`
- `data/analysis/...`
- `data/dawn_research_manifest.json`

## 3) Reusable incremental updates

For repeated updates, keep one stable output directory and re-run with manifest inference:

```bash
./scripts/run_dawn_driverradar.sh \
  --status merged \
  --out data \
  --limit 300 \
  --use-manifest
```

How it works:

- If `--since` is missing and manifest exists, `--since` is inferred from `raw.lastMaxUpdated`.
- New fetches are deduped by `changeId / id / number`.
- Existing raw ndjson and raw shards are append-only in resume mode.
- Added rows are tracked in manifest under `raw.addedRows`.

## 4) Fast local analysis without network

If fetch is not needed:

```bash
./scripts/run_dawn_driverradar.sh \
  --skip-fetch \
  --out data \
  --raw-input data/raw_changes \
  --skip-workarounds \
  --skip-trends \
  --skip-hotspots \
  --skip-candidates
```

This regenerates no network data and uses cached `data/raw_changes`.

## 5) Stage-by-stage reruns

Use these switches for partial runs:

- `--skip-workarounds` (reuse existing `analysis/workarounds`)
- `--skip-trends` (reuse existing `analysis/trends`)
- `--skip-hotspots` (reuse existing `analysis/hotspots`)
- `--skip-candidates` (reuse existing `analysis/candidate_pack`)

Common use:

```bash
./scripts/run_dawn_driverradar.sh \
  --skip-fetch \
  --skip-workarounds \
  --out data
```

This is useful when patterns/hotspot logic changed in scripts but raw data is unchanged.

## 6) Backfill and re-shape workflows

For historical repair windows:

```bash
./scripts/run_dawn_driverradar.sh \
  --status merged \
  --since 2025-03-01 \
  --until 2025-03-31 \
  --no-resume-fetch \
  --out data
```

Notes:

- `--no-resume-fetch` rewrites raw artifacts.
- Use for bounded backfills where you want a strict replace.
- Pair with `--skip-*` stages as needed to avoid redoing derivations.

## 7) Shard and manifest policy

- Raw shard target defaults:
  - `--max-shard-mb 32`
  - `--shard-size 300`
- `--resume-fetch` dedupes and appends new rows.
- Manifest default path: `data/dawn_research_manifest.json`.
- Manifest fields of interest:
  - `raw.lastUpdatedMin`, `raw.lastUpdatedMax`, `raw.lastMaxUpdated`
  - `raw.existingRows`, `raw.addedRows`, `raw.rawRows`
  - `stageControls` and each stage `summary` block.

## 8) Data retention guidance (shared cache discipline)

- Keep `data/` as long-lived cache for local analysis, not source of truth.
- Archive old windows by copying/moving dated `data/` snapshots if needed.
- Never mutate committed raw artifacts in place during normal workflow.
- Run a scheduled refresh cadence:
  - Long baseline window monthly/quarterly.
  - Short incrementals daily/weekly.

## 9) Safety defaults

- No stage produces Fawn runtime code or modifies non-research folders.
- Candidate outputs are human review artifacts only.
- If cache corruption is suspected, delete `data/raw_changes*` and rerun explicit full bootstrap.
