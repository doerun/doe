# Cerebras evidence bundle — current pointer

**Auto-generated** by
`bench/tools/prepare_cerebras_validation_bundle.sh` on each clean
run. Do not hand-edit; the prep script overwrites this file so it
always reflects the last successful pack.

> **Freshness check.** This pointer is a snapshot of the *last successful
> pack* — not a live status. Compare `regenerated at` against
> `git log -1 --format=%cI HEAD` before circulating the archive
> externally. Regenerate via the prep script if the repo has advanced
> beyond the pinned `git commit` below.

## Latest archive

| Field | Value |
| --- | --- |
| regenerated at | `2026-05-05T13:44:28Z` |
| archive | `bench/out/doe-cerebras-evidence-20260505-0944-7f56ff5821cb.tar.gz` |
| archive sha256 | `06d88a7f90e2cbd7b2dc9bb4d65976b011b7319aa2640ff60833c71c2f975702` |
| MANIFEST.txt sha256 | `b7c8b115579be59c73f30e24d448d5f61f7c3d16cfb51cf0a5a33306c899137c` |
| BUNDLE_META.json sha256 | `af6ddd48deeb2cf102bf1e3b34e3fb8a2eccd2c52a5d54a415f7339025a2b998` |
| archive size (bytes) | `220220` |
| git commit | `7f56ff5821cbc20161860d44c41c100efd76ffc9` |
| git dirty | `clean` |
| evidence bundle verdict | `passed` (24/24 steps) |

## Verify the bytes you received

```bash
python3 bench/tools/verify_cerebras_validation_archive.py \
    --archive <path-to-received-archive>
```

Expected: `PASS ... manifest sha integrity OK, claim-role taxonomy
clean, BUNDLE_META complete, claim-discipline scan clean`.

## Summarize without unpacking

```bash
bench/tools/summarize_cerebras_evidence_archive.sh <path-to-archive>
```

## Reproducibility note

The prep script refuses to pack from a dirty tree. The archive's own
`BUNDLE_META.json` is the authoritative source of truth for any bundle
in hand; this file just mirrors the values
from the last prep-script run on the repo.
