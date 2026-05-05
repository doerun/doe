# Cerebras evidence-bundle tools

Narrow index of the tools that together prepare, verify, and
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

- **`run_cerebras_evidence_bundle.py`** — runs the local gate sequence
  in order (truth-table test, Doppler Gemma-4 WebGPU capture graph,
  manifest-shape probe, manifest-shape CPU execution oracle,
  Doppler RDRR/int4ple structural probe,
  Doppler RDRR Q4_K_M L1 smoke-contract parity,
  declared-depth BF16/RDRR diagnostics, self-check,
  E2B model receipt refresh after those diagnostics, manifest-shape
  attention-core SdkLayout diagnostic, Doppler capture-to-CSL
  attention-core lowering, manifest-shape Doe/CSL runtime-path
  contract after a second receipt refresh, claim-discipline,
  SdkLayout streaming hardening, receipt link integrity) and writes
  `bench/out/cerebras-evidence-bundle/summary.json` with per-step
  `step / status / returnCode / elapsedMs / stdoutTail / stderrTail`
  plus an aggregate verdict. The INT4 PLE manifest compile-param promotion
  gate is available through
  `--require-int4ple-manifest-compile-params`; default bundle runs skip it
  so blocked metadata evidence can still pass before manifest-shaped CSL
  targets are available.
- **`pack_cerebras_validation_archive.py`** — builds the tarball
  at `bench/out/doe-cerebras-evidence-<UTC>-<gitShortSha>[-dirty].tar.gz`.
  Allow-list + deny-list construction excludes SDK binaries
  (`.elf`/`.lst`/`.map`/`.symbols`/`.viz`), weight bytes (`.f32`),
  simulator logs, and scratch dirs. Top-level files: `README.md`,
  `CLAIM_SCOPE.md`, `MODEL_ACCESS.md`, `CEREBRAS_ASK.md`,
  `LOCAL_INSPECTION.md`, `BUNDLE_META.json`, `MANIFEST.txt`. The
  archive-root governance files are extracted from marked sections in
  `docs/cerebras-evidence-bundle.md`. Every file in MANIFEST has a
  sha256 + claim-role.
- **`verify_cerebras_validation_archive.py`** — extracts the
  archive to a temp dir, re-hashes every manifest entry, validates
  BUNDLE_META required fields + claim-role taxonomy, runs the
  live claim-discipline rules over every text file inside. Use
  after `pack` and on any received archive.
- **`cerebras_status_snapshot.py`** — refreshes
  `bench/out/r3-cerebras-status/snapshot.{json,md}` from the current
  Cerebras receipt set so docs can point at a generated status table
  instead of copying verdicts into prose.

## Quick-read helpers

- **`summarize_cerebras_evidence_archive.sh <archive>`** — prints
  E2B / 31B / MoE status + bundle verdict + claimable-depth coverage
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
  │           ├── README.md, CLAIM_SCOPE.md, MODEL_ACCESS.md, CEREBRAS_ASK.md, LOCAL_INSPECTION.md
  │           ├── docs/hardware-validation-appendix.md
  │           ├── docs/claim-discipline.md
  │           ├── config/gemma-4-e2b-real-weight-fixture.json
  │           ├── config/gemma-4-31b-real-weight-fixture.json
  │           ├── config/gemma-4-e2b-doppler-rdrr-int4ple-fixture.json
  │           ├── bench/out/{e2b,31b}-full-graph/gemma-4-*-runtime-receipt.{json,md}
  │           ├── bench/out/streaming-executor/*-cross-runtime-parity-check.json
  │           ├── bench/out/doppler-reference/csl-emulator-speed-verdict-L1.json
  │           ├── bench/out/gemma-4-*-real-weight-parity-L1.json
  │           ├── bench/out/gemma-4-e2b-real-weight-parity-L{2,4,8,35}.json
  │           ├── bench/out/manifest-shape/gemma-4-e2b-manifest-shape-probe.json
  │           ├── bench/out/manifest-shape/gemma-4-e2b-manifest-shape-execution.json
  │           ├── bench/out/manifest-shape/gemma-4-e2b-manifest-shape-attention-core.json
  │           ├── bench/out/manifest-shape/gemma-4-e2b-manifest-shape-runtime-path.json
  │           ├── bench/out/doppler-capture/gemma-4-e2b-doe-webgpu-capture-graph.json
  │           ├── bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-probe.json
  │           ├── bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-*.json
  │           ├── bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-l{1,2,4,8,35}-parity.json
  │           ├── bench/out/weights-audit/gemma-4-e2b-rdrr-int4ple-weights-audit.json
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
| C28 | bundle-doc section skip-lists in sync across packer `INCLUDE_FILES` ↔ gate `SKIP_PREFIXES` ↔ verifier `CLAIM_SCAN_SKIP_ARCHIVE_PATHS` (AST-based) |
| C29 | `docs/cerebras-evidence-bundle-pointer.md` is NOT in packer `INCLUDE_FILES` (stale-lag guard) |
| C30 | prep-script stage ordering: gates → pack → verify → pointer-write |
| C31 | `cerebras-evidence-bundle-tools.md` lists every on-disk `bench/tools/*cerebras*` tool |
| C32 | packer path-substring deny-list ↔ verifier `FORBIDDEN_PATH_SUBSTRINGS` in sync (non-extension deny-list defense-in-depth) |
| C33 | E2B demo error-to-preview paths all pipe through `stripAnsi()` (no ANSI leak into browser preview panes) |
| C34 | bundle governance doc + appendix both name both hardware-validation paths (A endpoint access / B Cerebras-assisted bundle run) |
| C35 | declared depth list stays synchronized between the depth matrix generator and E2B cockpit |
| C36 | Doppler RDRR/int4ple structural probe validates manifest, selected shard hash, target spans, and keeps Q4 dequant explicitly blocked |
| C37 | Doppler RDRR Q4_K_M L1 smoke parity verdict stays scoped to smoke-contract parity and blocks full-model / hardware claims |
| C38 | optional E2B BF16/RDRR diagnostic verdicts pass exactly their requested smoke depth and remain non-full-model / non-hardware evidence |
| C39 | manifest-shape probe records the upstream E2B tensor-shape contract and accepts Doe manifest fields only when they match the source metadata |
| C40 | manifest-shape CPU oracle executes the raw BF16 E2B text stack through 35 layers and tied lm-head top-k while Doe/CSL runtime claims remain blocked |
| C41 | CSL emitters target the SDK 2.10 parameter surface and use queue-bound fabric DSDs without `fabric_color` metadata |
| C42 | model receipt promotes the generated E2B SdkLayout layer-block smoke with stream graph, telemetry, `rt.stop()`, non-stub kernel, and parity evidence |
| C43 | model receipt binds BF16 + RDRR declared-depth smoke diagnostics as non-claimable evidence with manifest-shape/runtime/hardware blockers intact |
| C44 | model receipt binds the partial manifest-shape attention-core SdkLayout slice with local/global heads, grouped KV, and CPU-oracle parity while full claims stay blocked |
| C45 | model receipt binds the Doppler Gemma-4 WebGPU capture graph as shared JS/WGSL input while full-graph HostPlan/SdkLayout/CSL lowering claims remain blocked |
| C46 | model receipt binds the captured WebGPU graph to the first attention-core SdkLayout/CSL lowering receipt with CPU-oracle parity and full-inference blockers intact |

## What this pipeline does NOT do

- Run the CSL simulator or hardware — see
  `bench/runners/csl-runners/e2b_layer_block_smoke.py` or
  `bench/runners/run_csl_governed_lane.py` for those.
- Produce a Cerebras hardware receipt — that requires a reachable
  CS / WSC endpoint; see `docs/hardware-validation-appendix.md`.
- Replace full real-weight parity — the bundle now includes E2B L1
  BF16-derived and RDRR-derived smoke-contract parity plus bundled
  declared-depth diagnostics, but those diagnostics are not
  Doe/CSL manifest-shape runtime, 31B, MoE, or hardware receipts.
- Promote manifest-shape runtime — the runtime-path artifact is still a
  blocked checklist for embed, decoder stack, unembed/logits, and parity
  receipts. The attention-core receipt covers only the local/global
  head-dim plus grouped-KV diagnostic rung, not full attention or model
  execution.
- Promote captured Doppler WebGPU graphs to full inference — the capture
  graph proves the shared input surface can be recorded through Doppler's
  Node provider bootstrap, and the lowering receipt now binds that graph to
  the first attention-core SdkLayout/CSL slice. Full captured-graph
  HostPlan lowering and Doppler production-inference parity remain blocked.
