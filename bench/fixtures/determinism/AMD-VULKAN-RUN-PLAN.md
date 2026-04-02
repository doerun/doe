# AMD Vulkan

```bash
export B=amd-vulkan
```

See [RUN-PLAN.md](RUN-PLAN.md) for the full procedure.

## Hardware

- AMD GPU with Vulkan support (tested: Radeon GFX1151, RADV, Mesa 25.0.7)
- Chromium with WebGPU + Vulkan ANGLE
- Zig 0.15.2 (for doe-zig-runtime)

## Prerequisites

```bash
# 1. Build doe-zig-runtime
cd runtime/zig && zig build doe-runtime && cd ../..

# 2. Verify Vulkan
python3 bench/runners/preflight_vulkan_host.py

# 3. Verify models exist
ls ../doppler/models/local/gemma-3-270m-it-q4k-ehf16-af32/manifest.json
ls ../doppler/models/local/gemma-3-1b-it-q4k-ehf16-af32/manifest.json
ls ../doppler/models/local/qwen-3.5-0.6b-q4k-ehf16-af32/manifest.json
```

## Runs on this machine

- **2b** Gemma 270M / Doe
- **2d** Gemma 1B / Doe
- **2f** Qwen 3.5 0.6B / Doe
- **6c** Gemma 270M / Dawn (requires Dawn Vulkan build)
- **6f** Qwen 3.5 0.6B / Dawn

## Notes

- Layer 0: attention-slice and rmsnorm-slice diverge on AMD Vulkan. Dot product does not (8-term reduction too small to trigger non-associativity on this hardware).
- Batch splits recommended due to longer per-prompt inference time.
