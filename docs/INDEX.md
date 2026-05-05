# Doe docs index

Grouped pointer to every doc under `docs/`. Files stay flat by intent
(see commit history if curious about why) — this index is the table of
contents.

For dated, append-only history, see [`docs/status.md`](status.md) and
the shards under [`docs/status/`](status/).

## Project front doors

- [`thesis.md`](thesis.md) — what Doe is and why it exists
- [`architecture.md`](architecture.md) — high-level shape of the runtime + compiler + bench surfaces
- [`process.md`](process.md) — gate modes, blocking vs advisory, release rules
- [`status.md`](status.md) — concise status front door; dated history under `docs/status/`
- [`problems-addressed.md`](problems-addressed.md) — practitioner pain points the runtime targets
- [`glossary.md`](glossary.md) — terminology used across docs
- [`repo-taxonomy.md`](repo-taxonomy.md) — what lives where; tenant boundaries
- [`internal-tooling.md`](internal-tooling.md) — public vs repo-only tooling boundary
- [`licensing.md`](licensing.md) — license surface and third-party
- [`upgrade-policy.md`](upgrade-policy.md) — version compatibility and deprecation rules

## Cerebras lane (Doppler → Doe → Cerebras)

Front door: [`cerebras.md`](cerebras.md). Bundle packer + claim-discipline
gate depend on the bundle and appendix files; do not rename.

- [`cerebras.md`](cerebras.md) — single front door (progress, source code, reproduce, hardware)
- [`cerebras-hardware-runbook.md`](cerebras-hardware-runbook.md) — operator how-to for hardware receipts
- [`cerebras-evidence-bundle.md`](cerebras-evidence-bundle.md) — bundle source (parsed by the prep script)
- [`cerebras-evidence-bundle-pointer.md`](cerebras-evidence-bundle-pointer.md) — auto-generated archive pointer
- [`cerebras-evidence-ledger-gemma.md`](cerebras-evidence-ledger-gemma.md) — Gemma 4 31B evidence ledger
- [`cerebras-evidence-ledger-qwen.md`](cerebras-evidence-ledger-qwen.md) — Qwen 3.6 27B evidence ledger
- [`hardware-validation-appendix.md`](hardware-validation-appendix.md) — governance + claim scope

## CSL (Cerebras shader language) layer

- [`csl-architecture.md`](csl-architecture.md) — CSL abstraction stack
- [`csl-quickstart.md`](csl-quickstart.md) — getting started with CSL emit
- [`csl-layer-block-self-check.md`](csl-layer-block-self-check.md) — layer-block self-check protocol

## Compiler / TSIR

- [`tsir-lowering-plan.md`](tsir-lowering-plan.md) — TSIR architecture and lowering plan
- [`shader-compiler-architecture.md`](shader-compiler-architecture.md) — WGSL → backend pipeline
- [`lean-bounds-elimination-design.md`](lean-bounds-elimination-design.md) — Lean-driven proof elimination of runtime branches
- [`doppler-ingest.md`](doppler-ingest.md) — Doppler ingest contract
- [`loop-protocol.md`](loop-protocol.md) — TSIR iteration discipline

## Runtime / packaging

- [`doe-gpu-node-runtime-scope.md`](doe-gpu-node-runtime-scope.md) — Node runtime scope
- [`package-model.md`](package-model.md) — npm package contract
- [`apple-metal-runtime-release.md`](apple-metal-runtime-release.md) — Apple Metal runtime bundle
- [`metal-macos-proof-bundle-runbook.md`](metal-macos-proof-bundle-runbook.md) — Metal macOS proof bundle runbook
- [`fawn-fork-maintenance-policy.md`](fawn-fork-maintenance-policy.md) — Fawn (Chromium fork) policy
- [`concurrency-strategy.md`](concurrency-strategy.md) — runtime concurrency model

## Performance + benchmarks

- [`benchmark-taxonomy.md`](benchmark-taxonomy.md) — canonical compare taxonomy
- [`performance-strategy.md`](performance-strategy.md) — performance work approach
- [`doe-support-matrix.md`](doe-support-matrix.md) — platform × surface × runtime support
- [`browser-lane.md`](browser-lane.md) — browser benchmarking lane
- [`numeric-stability.md`](numeric-stability.md) — determinism + numeric stability
- [`claim-discipline.md`](claim-discipline.md) — claim-language rules over benchmark output
