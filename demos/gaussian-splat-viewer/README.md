# Doe gaussian splat viewer demo

Browser-hosted [3D Gaussian splatting](https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/) viewer rendered through Doe's WebGPU runtime. Demo-only; not a public package contract.

## What it does

Loads a `.splat` binary (the community format from
[antimatter15/splat](https://github.com/antimatter15/splat)) and renders up to a
few million 3D Gaussians per frame as alpha-composited 2D ellipses using a
single instanced draw on the WebGPU `doe-gpu` package.

- each splat: 3D position, anisotropic 3D scale, unit quaternion rotation, RGB + opacity
- CPU-side depth sort in a worker thread; main thread renders back-to-front with premultiplied alpha blending
- camera: orbit (mouse drag), dolly (wheel), pan (shift-drag)
- optional webcam overlay toggle composites a live `MediaStream` video as a 2D quad on top of the splat scene

Works with Luma AI / Polycam web exports, Kerbl et al. reference captures
(`garden`, `train`, `bicycle`, etc.), and any other `.splat` file from the
community.

## Run

```
cd demos/gaussian-splat-viewer
npm install
npx vite
```

Then open the reported URL in a browser with WebGPU enabled (Chrome 113+,
Safari 18.4+, Firefox with `dom.webgpu.enabled` set).

### Test data

The demo defaults to no scene loaded; drop a `.splat` file onto the canvas, or
paste a public URL into the URL input. Recommended small-scene downloads:

- `https://huggingface.co/cakewalk/splat-data/resolve/main/nike.splat` (~1M splats, ~32 MB)
- `https://huggingface.co/cakewalk/splat-data/resolve/main/plush.splat` (~0.5M splats)

Any `.splat` file that follows the 32-byte-per-point community layout works.

## Implementation notes

- vertex shader projects each splat's 3D Gaussian to a 2D conic using the EWA-splatting projection, computes a 3-sigma billboard bound, and emits a quad instanced from `@builtin(instance_index)`
- fragment shader evaluates `alpha = opacity * exp(-0.5 * d^T * Σ'⁻¹ * d)` in screen-space offset coordinates and discards below a small alpha floor
- depth sort runs on a web worker against the camera's view matrix; sorts are debounced to not fire more than once per frame
- video overlay is a separate draw pass using a fullscreen-aligned textured quad fed from a `HTMLVideoElement` as an external texture

Follow the Doe WGSL sema constraints inline-documented in `splat-render.wgsl`:
scalar broadcast via `vec3f(x)`, loop increments as `i = i + 1` (not `i++`),
inline any helper that closes over module-scope uniforms.

## Status

Demo-only. This tree is not a public package contract and is not covered by the
Doe runtime support matrix. If it becomes an actively supported surface,
promote it in `config/tool-surfaces.json` per the policy in `../README.md`.

### WGSL-emitter note

Both shader entry points (`vs_main`, `fs_main`) pass Tint compilation and
`spirv-val` on their emitted SPIR-V. Doe's own `doe-emit-spirv` tool today
fails on this shader because it does not yet support every construct the
demo uses — specifically matrix column indexing (`frame.view[0][0]`) and
multi-entry-point module emission. When Chrome or Firefox runs this demo,
the browser compiles the shader through Dawn+Tint, so the demo works end-to-end
on stock WebGPU today. Running the same shader through Doe's native emitter
(a "Chromium + Doe substitute" path) is a separate follow-up on Doe's WGSL
surface.

## Follow-ups

- GPU-side bitonic sort so scenes above ~5M splats stay smooth
- spherical-harmonics color (SH order 3) for view-dependent appearance; today's renderer treats colour as a fixed RGB (SH order 0 only)
- progressive loading for large `.splat` streams
- splat-from-video training loop is explicitly out of scope for this demo; that is multi-day SfM + optimization work, not a browser demo
