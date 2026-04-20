# Cerebras evidence-bundle tools

Narrow index of the six tools that together prepare, verify, and
summarize a Cerebras hardware-validation evidence bundle. Not
exhaustive of `bench/tools/` — this file only covers the bundle
pipeline so a contributor or reviewer can find the right tool
without `grep`ping 75+ scripts.

See `bench/README.md` § "Cerebras hardware-validation evidence
bundle" for the prose workflow; this file is the tool-reference.

## One-command driver

- **`prepare_cerebras_validation_bundle.sh`** — the everyday
  entry point. Chains gates → pack → verify and fails fast on
  any step. Produces the git-sha-stamped archive and prints its
  path + size + commit. Use before external circulation.

## Underlying tools (called by the prep script, usable standalone)

- **`run_cerebras_evidence_bundle.py`** — runs 5 local gates in
  order (truth-table test, self-check, claim-discipline, SdkLayout
  streaming hardening, receipt link integrity) and writes
  `bench/out/cerebras-evidence-bundle/summary.json` with per-step
  `step / status / returnCode / elapsedMs / stdoutTail / stderrTail`
  plus an aggregate verdict.
- **`pack_cerebras_validation_archive.py`** — builds the tarball
  at `bench/out/doe-cerebras-evidence-<UTC>-<gitShortSha>[-dirty].tar.gz`.
  Allow-list + deny-list construction excludes SDK binaries
  (`.elf`/`.lst`/`.map`/`.symbols`/`.viz`), weight bytes (`.f32`),
  simulator logs, and scratch dirs. Top-level files: `README.md`,
  `CLAIM_SCOPE.md`, `CEREBRAS_ASK.md`, `LOCAL_INSPECTION.md`,
  `BUNDLE_META.json`, `MANIFEST.txt`. Every file in MANIFEST has
  a sha256 + claim-role.
- **`verify_cerebras_validation_archive.py`** — extracts the
  archive to a temp dir, re-hashes every manifest entry, validates
  BUNDLE_META required fields + claim-role taxonomy, runs the
  live claim-discipline rules over every text file inside. Use
  after `pack` and on any received archive.

## Quick-read helpers

- **`summarize_cerebras_evidence_archive.sh <archive>`** — prints
  E2B / 31B / MoE status + bundle verdict + emulator verdicts
  entirely from inside the tarball via `tar -xzO | jq`. No unpack
  needed.
- **`summarize_doe_run_lanes.py --num-layers 1`** — refreshes
  `bench/out/doe-run/all-lanes-summary-L1.json` (the 5-lane
  rollup that the E2B cockpit consumes and that the bundle
  includes). Also invoked automatically by the self-check's STEP 4b.

## Artifact trail

```
bench/tools/prepare_cerebras_validation_bundle.sh
  ├── run_cerebras_evidence_bundle.py
  │     └── bench/out/cerebras-evidence-bundle/summary.json     (rollup)
  ├── pack_cerebras_validation_archive.py
  │     └── bench/out/doe-cerebras-evidence-<stamp>.tar.gz       (archive)
  │           ├── BUNDLE_META.json
  │           ├── MANIFEST.txt
  │           ├── README.md, CLAIM_SCOPE.md, CEREBRAS_ASK.md, LOCAL_INSPECTION.md
  │           ├── docs/hardware-validation-appendix.md
  │           ├── docs/claim-discipline.md
  │           ├── config/gemma-4-e2b-real-weight-fixture.json
  │           ├── config/gemma-4-31b-real-weight-fixture.json
  │           ├── bench/out/{e2b,31b}-full-graph/gemma-4-*-runtime-receipt.{json,md}
  │           ├── bench/out/streaming-executor/*-cross-runtime-parity-check.json
  │           ├── bench/out/doppler-reference/csl-emulator-*-verdict-*.json
  │           ├── bench/out/gemma-4-*-real-weight-parity-L1.json
  │           ├── bench/out/26b-moe-lane/*.json                  (7 files)
  │           ├── bench/out/doe-run/all-lanes-summary-L1.json
  │           └── bench/out/cerebras-evidence-bundle/summary.json
  └── verify_cerebras_validation_archive.py
        └── (exit 0 on pass — no output artifact)
```

## Regression surface

The self-check at `bench/tools/e2b_layer_block_self_check.py`
locks most of this pipeline via numbered contracts:

| Contract | What it catches |
| --- | --- |
| C16 | pack + verify round-trip integrity |
| C17 | viewer `/api` routes (positive + negative paths + bundle-summary shape + evidence-commands) |
| C18 | demo HTML structural sanity + cross-links + command-copy controls |
| C19 | evidence-bundle summary shape + verdict/steps consistency + numeric elapsedMs |
| C20 | lane-label consistency across E2B / 31B / MoE |
| C21 | MoE TODO artifactKind stays `_todo`, never `_receipt` |
| C22 | packager `INCLUDE_FILES` ↔ `CLAIM_ROLE` in sync |
| C23 | packer deny-list extensions ↔ verifier `FORBIDDEN_EXTENSIONS` in sync |
| C24 | `bash -n` parse check on bundle shell scripts |
| C25 | every `data-copy-for` in SDK-GUI viewer HTML resolves to real element id |
| C26 | `summarize_cerebras_evidence_archive.sh` runs cleanly on the newest archive |
| C27 | emulator lane soft-fails CSL contract check structurally (WGSL-before-try + unchecked branch + `cslContract` field) |
| C28 | bundle-doc skip-lists in sync across packer `INCLUDE_FILES` ↔ gate `SKIP_PREFIXES` ↔ verifier `CLAIM_SCAN_SKIP_ARCHIVE_PATHS` (AST-based) |
| C29 | `docs/cerebras-evidence-bundle-pointer.md` is NOT in packer `INCLUDE_FILES` (stale-lag guard) |
| C30 | prep-script stage ordering: gates → pack → verify → pointer-write |
| C31 | `cerebras-evidence-bundle-tools.md` lists every on-disk `bench/tools/*cerebras*` tool |
| C32 | packer path-substring deny-list ↔ verifier `FORBIDDEN_PATH_SUBSTRINGS` in sync (non-extension deny-list defense-in-depth) |
| C33 | E2B demo error-to-preview paths all pipe through `stripAnsi()` (no ANSI leak into browser preview panes) |
| C34 | four governance docs (ASK, README, CLAIM_SCOPE, appendix) all name both hardware-validation paths (A endpoint access / B Cerebras-assisted bundle run) |

## What this pipeline does NOT do

- Run the CSL simulator or hardware — see
  `bench/runners/csl-runners/e2b_layer_block_smoke.py` or
  `bench/runners/run_csl_governed_lane.py` for those.
- Produce a Cerebras hardware receipt — that requires a reachable
  CS / WSC endpoint; see `docs/hardware-validation-appendix.md`.
- Replace real-weight parity — that's the external checkpoint
  extractor's job; the bundle only ships the fixture contracts +
  blocked parity verdicts today.
