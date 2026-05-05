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
| regenerated at | `2026-05-05T19:13:10Z` |
| archive | `bench/out/doe-cerebras-evidence-20260505-1513-f29552efb6ed.tar.gz` |
| archive sha256 | `89669ae0cc6d663a67984acbef55a14c13c673991b18c6fb694bc709e99afdd0` |
| MANIFEST.txt sha256 | `f75071e803801a0408df2c8f51493196cbc51f9787004ef16c3c9a4fb2c38c76` |
| BUNDLE_META.json sha256 | `3f1348daa60f8777ee72da569ee5043b8fce49d7e66405f2b16a2dbf0457dd07` |
| archive size (bytes) | `749785` |
| git commit | `f29552efb6eda92feb417b3d6085d28344751492` |
| git dirty | `clean` |
| evidence bundle verdict | `passed` (27/27 steps) |

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
