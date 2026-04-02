# Apple Metal

```bash
export B=apple-metal
```

See [RUN-PLAN.md](RUN-PLAN.md) for the full procedure.

## Hardware

- Apple Silicon Mac (tested: M-series)
- Chromium with WebGPU

## Prerequisites

```bash
ls ../doppler/models/local/gemma-3-270m-it-q4k-ehf16-af32/manifest.json
ls ../doppler/models/local/gemma-3-1b-it-q4k-ehf16-af32/manifest.json
ls ../doppler/models/local/qwen-3-5-0-8b-q4k-ehaf16/manifest.json
```

## Runs on this machine

- **2a** Gemma 270M / Doe
- **2c** Gemma 1B / Doe
- **2e** Qwen 3.5 0.8B / Doe
- **6a** Gemma 270M / Dawn (requires Dawn build)
- **6b** Gemma 270M / WebKit (requires WebKit shim)
- **6d** Qwen 3.5 0.8B / Dawn
- **6e** Qwen 3.5 0.8B / WebKit

## Notes

- All four Layer 0 operator counterexamples diverge on Apple Metal.
- Dawn and WebKit runs use the same fixtures with `backendLane` overrides.
