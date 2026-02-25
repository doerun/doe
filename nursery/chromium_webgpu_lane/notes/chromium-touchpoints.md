# Chromium Touchpoints for Fawn Runtime Lane

## Status

`draft`

## Context

Local Chromium checkout exists under:

1. `nursery/chromium_webgpu_lane/src`
2. current `src` revision: `5ffed8f84d` (local checkout HEAD at scan time)

## Primary Track A Touchpoints

These are the most relevant files for seam-only runtime selection and fallback control.

## Runtime Initialization and Dawn Procs

1. `src/gpu/ipc/service/gpu_init.cc`
   - Dawn proc initialization and context-provider creation.
   - Graphite backend-specific handling and adapter validation logic.

## WebGPU Command Buffer Entry

1. `src/gpu/ipc/service/webgpu_command_buffer_stub.cc`
2. `src/gpu/ipc/service/webgpu_command_buffer_stub.h`
3. `src/gpu/ipc/service/gpu_channel.cc`
4. `src/gpu/ipc/in_process_command_buffer.cc`
5. `src/gpu/ipc/webgpu_in_process_context.cc`

These files define core WebGPU stub/decoder wiring in GPU process and in-process paths.

## GPU Preferences and Switch Surfaces

1. `src/gpu/ipc/common/gpu_preferences.mojom`
2. `src/gpu/config/gpu_switches.h`
3. `src/gpu/config/gpu_switches.cc`
4. `src/gpu/ipc/common/gpu_preferences_mojom_traits.h`

These are candidate surfaces for explicit `dawn|doe|auto` selector controls and telemetry fields.

## Blocklist and Adapter Policy

1. `src/gpu/config/webgpu_blocklist_impl.cc`
2. `src/gpu/config/software_rendering_list.json`

These are candidate surfaces for deterministic denylist/fallback integration.

## Disk Cache and Shared Runtime Artifacts

1. `src/gpu/ipc/host/gpu_disk_cache.cc`
2. `src/gpu/ipc/common/gpu_disk_cache_type.*`
3. `src/gpu/ipc/service/gpu_channel_manager.cc`

Relevant for cache handles and runtime artifact integration behavior.

## Graphite-Related Files (Reference Only for Track A)

1. `src/gpu/config/gpu_switches.cc` (`skia-graphite-dawn-backend`)
2. `src/gpu/ipc/service/gpu_init.cc` (Graphite Dawn selection)
3. `src/skia/features.gni`

Track A should avoid coupling to Graphite behavior changes unless explicitly required.

## Initial Integration Sequence (Code-Facing)

1. Add selector enum/control surface (`dawn|doe|auto`) in GPU preference flow.
2. Add kill switch and denylist checks at runtime selection point.
3. Add typed fallback reason telemetry in run/session reporting surfaces.
4. Keep Dawn path default and fallback-ready.
5. Add negative tests for all fallback reason codes.

## Non-Goals for First Integration Pass

1. No compositor/layout/media architecture changes.
2. No Skia Graphite refactoring.
3. No internal module Track B code in first pass.

## Immediate Follow-Up

1. Identify exact call site where `dawnProcSetProcs(&dawn::native::GetProcs())` can be abstracted behind a selector bridge.
2. Draft candidate Chromium-side selector switch names and prefs mapping.
3. Define fallback reason telemetry schema that can map into Fawn trace/meta style reporting.
