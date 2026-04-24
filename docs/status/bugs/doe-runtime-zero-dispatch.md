# Doe runtime zero-dispatch bug

**Status:** open, non-critical.
**Lane:** bug follow-up from Track 1 (Doe WebGPU execution trace).
**Does not block:** browser→CSL parity receipt (Track 2 + Track 3 are
the critical path to the north-star receipt; Track 1 is a portability
lane).

## Minimum repro

`bench/repros/doe-runtime-zero-dispatch/repro.mjs`

A 3-line WGSL compute kernel that writes `u32(42)` to index 0 of a
storage buffer:

```wgsl
@group(0) @binding(0) var<storage, read_write> out: array<u32>;
@compute @workgroup_size(1) fn main() { out[0] = 42u; }
```

Through `doe-gpu`'s compute facade in Node, every intermediate call
succeeds without error (createShaderModule, createComputePipeline,
createBuffer, createBindGroup, dispatchWorkgroups, queue.submit,
copyBufferToBuffer, mapAsync). Readback returns `0` instead of `42`,
deterministically.

Run:
```
node bench/repros/doe-runtime-zero-dispatch/repro.mjs
```

Exit 0 when the bug is fixed; exit 1 while it persists.

## Already fixed in this lane

- `packages/doe-gpu/src/vendor/webgpu/compute.js:wrapAdapter` now
  exposes `info` by delegating to the raw Doe Adapter. Previously
  Doppler's `src/config/platforms/loader.js:102` threw
  `Cannot read properties of undefined (reading 'vendor')` and the
  error was swallowed by Doppler's try/catch. Fix was necessary but
  not sufficient — the zero-dispatch persists after it.

## Still failing

Trivial WGSL writes `42u`; readback returns `0`.

## Candidate surfaces to investigate

Ordered by likelihood of root cause:

1. **`queue.submit` flush** — is the command buffer actually reaching
   the Vulkan device? Probe by logging command-buffer handle validity
   at submit time, or by checking whether any Vulkan-side command
   execution counter moves.
2. **Device-visible memory backing** — is `storageBuf` allocated on
   device-local memory, or only CPU-visible? If `read_write` storage
   buffers land in host-visible memory, the GPU compute dispatch
   might write to a staging buffer that's never flushed back.
3. **`copyBufferToBuffer` source synchronization** — is there a
   memory barrier between the compute dispatch's write and the
   buffer-to-buffer copy? Without one, the copy might read stale
   zero-initialized bytes.
4. **`mapAsync(GPUMapMode.READ)` on device-side-written buffers** —
   does `mapAsync` correctly synchronize against pending device
   writes? If it maps before the GPU finishes writing, we see
   zero-initialized memory.

## What the fix unblocks

Once fixed, Track 1's "execution green" exit condition (realKvCache
non-zero, real tokens for Gemma 3 1B) becomes reachable. This is a
portability-path win — browser already works, this makes Node/Doe
work too. It is NOT on the critical path to the browser→CSL parity
receipt; Track 2's CSL simfabric and Track 3's comparator/binding
work proceed independently.

## Related signals (separate issues, not fixes yet)

- `device.adapterInfo` is `undefined` — same class of bug as
  `wrapAdapter.info` was. Fix would be analogous:
  `get adapterInfo() { return raw.adapterInfo; }` on `wrapDevice`.
- `device.features` exposes `depth-clip-control`,
  `depth32float-stencil8`, three texture-compression features —
  graphics features on a compute-only facade — and `shader-f16` /
  `subgroups` are missing. For Doppler's capability-aware kernel
  path policy, f16 and subgroup kernels get remapped to f32 /
  non-subgroup fallbacks. Not a zero-dispatch cause (the repro uses
  neither), but worth cleaning up.

## Handoff artifacts

- Repro: `bench/repros/doe-runtime-zero-dispatch/repro.mjs`
- Prior stderr evidence: `/tmp/ws-c-gate-postfix1-transcript.json`
  (post-adapter.info-fix Gemma 3 1B transcript showing `[1]` +
  zero KV / zero logits)
- Track 1 diagnostic shard entry:
  `docs/status/compiler-and-webgpu.md` (2026-04-24 entry at top)
