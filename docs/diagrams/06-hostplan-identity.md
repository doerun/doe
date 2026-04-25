# 06 - HostPlan: "Identity through execution"

## Purpose

Explain where identity is needed: not for every internal compiler pass, but for
the evidence chain that proves the same Doppler program reached Cerebras.

## Slide content

- Ordered launch list: `embed`, `rmsnorm_prefill`, `tiled`, `rope`,
  `attention`, `gelu`, `residual`, `lm_head`, `sample`.
- Bind-by-symbol arrows between launches.
- Hash chain beside the list:
  - `manifestSha256`
  - `executionGraphSha256`
  - `hostplanSha256`
  - `compileTargetHashes`
  - `runnerVersion`

## Visual spec

- Vertical HostPlan strip in `doe.blue`.
- Hash badges in `accent.gold`.
- Cerebras launch/PE boundary markers in `cerebras.orange`.
- Highlight one output-to-input symbol binding with a thick line.

## Scope guard

- HostPlan identity is not a substitute for numeric parity.
- HostPlans are not portable across different manifests or weights.
- Runner behavior changes must be represented by version/receipt metadata.

## Evidence sources

- `bench/runners/csl-runners/int4ple_hostplan_execution_plan.py`
- `bench/tools/run_doe_csl_int4ple_transcript.py`
- `config/doe-csl-reference-parity.schema.json`
