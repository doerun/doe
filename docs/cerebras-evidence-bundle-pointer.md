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
| regenerated at | `2026-05-05T17:13:25Z` |
| archive | `bench/out/doe-cerebras-evidence-20260505-1313-1430485da2a7.tar.gz` |
| archive sha256 | `adb080857a2d1c5f38469b993acaf22648ecb3250e83f8e0b4194f22e59a63ef` |
| MANIFEST.txt sha256 | `a9acf24917fc8195c698c700dc42093d76ad5cb2a5d2f1358919ce8a0fbaf34a` |
| BUNDLE_META.json sha256 | `ad014c9ecbaf9e1bc62948875f9f93c4d475fac54df8b1d4906eaaca51e443f4` |
| archive size (bytes) | `731036` |
| git commit | `1430485da2a74b9508c9572cb44b120679a08220` |
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
