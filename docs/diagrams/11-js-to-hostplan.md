# 11 - Doppler JS -> HostPlan

## Purpose

Show where Doppler identity enters Doe. The source contract is raw JS plus raw
WGSL, not a Doe-specific model description.

## Slide content

- Left: Doppler `model.js` excerpt: embed -> layer block -> lm head -> sample.
- Middle: raw WGSL module list with digests.
- Right: Doe HostPlan launch list with stable symbols and compile targets.
- Label: **static lowering from source contract, not eager graph tracing.**

## Visual spec

- Three panes connected left to right.
- Doppler JS/WGSL uses `doppler.red`.
- Doe HostPlan uses `doe.blue`; hash badges use `accent.gold`.
- Add a small "refresh evidence" note: new Doppler contract -> rerun lowering
  -> new receipts.

## Scope guard

- Do not claim JS is inherently better than Python.
- Do not claim Doppler covers every model.
- Do not inline private Doppler details beyond raw JS/WGSL contract shape.

## Evidence sources

- `/home/x/deco/doppler/`
- `docs/doppler-ingest.md`
- `bench/tools/run_doe_csl_int4ple_transcript.py`
