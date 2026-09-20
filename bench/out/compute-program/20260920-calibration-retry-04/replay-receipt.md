# Calibration replay receipt

Recorded UTC: 2026-09-20T14:28:59.318956+00:00
Checkpoint at replay completion: `94f84ed81d1f3ec83cc32ff00ef934694f939957`

Command:

```bash
python3 -m bench.gates.compute_program_calibration_gate --report bench/out/compute-program/20260920-command-storage-calibration-window-03/report.json
```

Exit code: `0`

Output: `Calibration observations are consistent; no candidate is promoted`

| Retained decision field | Value |
| --- | --- |
| `schemaVersion` | `3` |
| `status` | `"consistent"` |
| `claimStatus` | `"diagnostic"` |
| `candidateEvaluationAllowed` | `true` |
| `promotionResolutionPassed` | `false` |

The existing gate rehashed declared artifacts and frozen inputs, checked package
qualification, numerical outputs, work receipts, process order and GPU observation
admission, and recomputed the uncertainty assessment. Consistency and resolution
remain separate decisions. This result promotes no candidate or package.

Replay began from the working tree based on `8d647be84`; the separate Metal
repair was committed while this CPU-only replay ran. The evaluator and frozen
acceptance inputs were unchanged. The evaluator digest below binds the code
used for this replay.

## Bound bytes

| Input or output | SHA-256 |
| --- | --- |
| `bench/out/compute-program/20260920-command-storage-calibration-window-03/report.json` | `7ac7523ab0e21227f29ab024feb994b73b975a475e6358562d4b0aad6796ba42` |
| `bench/out/compute-program/20260920-command-storage-calibration-window-03/uncertainty.json` | `117a425446be69468d322a5e1c2bfbef86e426602e06e35e09203565dd48ad6a` |
| `bench/out/compute-program/20260920-command-storage-calibration-window-03/frozen-inputs.json` | `3a3c626e8568f99a18ebcd0a42d5b7efaaee4dfa555ea8b0ed80e77b2eb0e58d` |
| `bench/out/compute-program/20260920-command-storage-calibration-window-03/metrics.tsv` | `907fe4ba47733aa228c6aaf7d3bb49e5c96bed3f19a5e8665c62e247c991bdd1` |
| `bench/out/compute-program/20260912-warmup-calibration-v1/procedure/calibration.json` | `98246884ccd63fe43cb478cacbd25299fadf92c7caae8b1399113ff79447cefe` |
| `bench/out/compute-program/20260920-calibration-retry-04/admission.log` | `7f12f3a821f1492572edca5ccc2f9c7eb6b365547f9fee1b52bd8ee70ecaf225` |
| `bench/gates/compute_program_calibration_gate.py` | `87a087fa20bc2a94c73212ec8c09e8ef22826eb16d6b95239d0837c1b8d403d2` |
| `bench/out/compute-program/20260908-helper-cleanup/qualified-final/doe-gpu-0.5.0.tgz` | `62a9ccfbe470543b551f7c4a146dded389803984ab1acfcfb5470755fc176914` |
| `bench/out/compute-program/20260908-helper-cleanup/qualified-final/doe-gpu-linux-x64-0.5.0.tgz` | `060c53f6cf9c47578311acd32c2041230618994e9db4b87ddfec934e28c0925a` |

The raw report, process reports, numerical outputs and observation sidecars remain
in the local ignored cohort directory. Tracked summaries and hashes alone cannot
reproduce the replay. Preserve those bytes alongside the accepted archives.

The original `metrics.tsv` keeps its CSV-writer CRLF line endings to preserve
the recorded digest; the derived precision table uses LF.
