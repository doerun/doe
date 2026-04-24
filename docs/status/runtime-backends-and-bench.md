# Doe status: runtime backends and benchmark lanes

This is a live topical status shard.

- Add new entries at the top.
- Keep this file under 1200 lines.
- Split by subdomain before it exceeds the cap.
- Dated history lives under `docs/status/archive/`.

## Current state

- Apple Metal native Doe-vs-Dawn fair-cold compare defaults are in place.
- AMD Vulkan now has Doe-side `VkPipelineCache` support and renewed strict
  compare evidence.
- Apple Metal package lanes and AMD Vulkan package lanes both have current
  narrow claimable surfaces.
- Benchmark reporting is artifact-first; JSON receipts under `bench/out/` are
  the canonical output surface.

## Active blockers

- Backend-wide claim language is still narrower than the existence of isolated
  claimable rows.
- D3D12 claim evidence still requires a suitable Windows host.
- Broader Metal and ORT/WebGPU package claims remain mixed or narrow.

## Landed infrastructure

- Fair-cold compare defaults on Metal
- Vulkan pipeline-cache implementation and optional persistence
- Artifact-first compare/claim/report flows
- Bench output viewer as the single tracked local HTML surface

## Ground truth

- Backend benchmark status is no longer the main source of status-log volume.
- This shard exists so backend and benchmark updates stop crowding compiler and
  Cerebras work into a single giant dated file.

## Use this shard for

- Native backend compare status
- Package-lane status
- Benchmark methodology / claim updates
- Backend-specific performance evidence
