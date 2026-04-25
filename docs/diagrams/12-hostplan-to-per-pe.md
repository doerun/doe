# 12 - HostPlan -> per-PE execution

## Purpose

Show what actually runs: every launch stages inputs, dispatches a per-PE
program, captures outputs, and feeds later launches by symbol.

## Slide content

- HostPlan launch selected from the vertical list.
- Expansion: `h2d -> dispatch -> d2h -> next launch input`.
- Checkpoint marker after `hostplan_launch_complete status=succeeded`.
- Receipt marker captures element counts, symbols, target, phase, and status.

## Visual spec

- Left: HostPlan strip in `doe.blue`.
- Right: PE-grid dispatch in `cerebras.orange`.
- h2d/d2h boxes use `doe.purple`; receipt/checkpoint badges use
  `accent.gold`.
- Draw one symbol path, e.g. `output -> input`.

## Scope guard

- Do not imply the diagnostic runner is performance-optimized.
- Do not imply every production-grid launch is tractable on simfabric.
- Do not imply checkpoint/resume proves numerical correctness.

## Evidence sources

- `bench/runners/csl-runners/int4ple_compile_target_sim_runner.py`
- `bench/runners/csl-runners/int4ple_checkpoint.py`
- `docs/status/cerebras-csl.md`
