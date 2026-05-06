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
| regenerated at | `2026-05-06T17:18:26Z` |
| archive | `bench/out/doe-cerebras-evidence-20260506-1318-2dd569878f30.tar.gz` |
| archive sha256 | `aa3c5a07d2af552d1638f9844aa0821abd551c1ceaf962ac45463cd6053a462f` |
| MANIFEST.txt sha256 | `ad1c9b08161782303133c0e4125cc65306a36064f15000cd7a9c2b6d292ecc78` |
| BUNDLE_META.json sha256 | `ce902546df945233a9e7f82bd47ed872dc3b5fcc312aa8cd2a388ee7ec69dda2` |
| archive size (bytes) | `1075127` |
| git commit | `2dd569878f3009875186ff5a55c2b5352ab8a544` |
| git dirty | `clean` |
| evidence bundle verdict | `passed` (28/28 steps) |

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
