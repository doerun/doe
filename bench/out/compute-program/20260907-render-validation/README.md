# Native rendering validation

`baseline.txt`, `source.patch`, and `SHA256SUMS` bind this correction and its
evidence. `rendering.log` retains the preceding package's physical rendering
result with Khronos synchronization validation enabled. Direct and bundled
indexed draws produced accepted pixels while Vulkan reported missing vertex
and index buffer usage flags. That successful process exit was insufficient
evidence of valid native execution.

The shared Vulkan buffer allocator now includes the vertex/index usages consumed
by rendering, also preserving them through device-local storage promotion.
Public WebGPU descriptors, native signatures, and report schemas are unchanged.
The existing render fixture, shaders, inputs, and pixel/depth acceptance tests
are unchanged.

`accepted-rendering.log` retains the corrected physical run from a fresh install
of the archives in `../20260907-render-validation-qualified/`. The same retained
package passes Node, Bun, and Electron main-process qualification. The earlier
failing run used archives from `../20260907-texture-transfers-qualified/`.
Install logs and `installed-library.sha256` identify the accepted installed
library; its hash must match `native-library.sha256` and every qualified host.
The validation layer is bound by
`../20260907-texture-transfers/validation-tool.sha256`.

Package qualification now rejects Vulkan validation errors and synchronization
hazards in either output stream, including when process exit is successful.
The captured streams remain retained before rejection. `baseline-admission-check.log`
shows rejection of the observed pre-fix zero-exit rendering result.
`package-tests.log` covers this admission rule. Runs without an enabled Vulkan
layer do not gain validation evidence from this guard.

`debug.log` and `release-fast.log` retain canonical runtime/compiler tests and
native build tiers. `accepted-transfers.log` rechecks the preceding checkpoint's
direct C transfer and lifetime fixture against the corrected library.

Reproduce the native build from `runtime/zig`:

```bash
zig build test test-wgsl --summary all
zig build test test-wgsl dropin dropin-compute dropin-full -Doptimize=ReleaseFast --summary all
```

Use `program qualify-package` and the disk-backed temporary-directory recipe in
`../20260907-texture-transfers/README.md`, with a fresh output directory. Install
its retained wrapper/platform archives into a fresh private npm project using
`npm install --offline --omit=optional --no-audit --no-fund`. Copy the qualified
`node-rendering.mjs` to `rendering.mjs` in that project, together with the retained
`native-addon-test-helper.js`. Run `node rendering.mjs` with the extracted layer:

```text
VK_LAYER_PATH=<layer-root>/usr/share/vulkan/explicit_layer.d
LD_LIBRARY_PATH=<layer-root>/usr/lib/x86_64-linux-gnu
VK_INSTANCE_LAYERS=VK_LAYER_KHRONOS_validation
VK_LAYER_VALIDATE_SYNC=1
VK_LOADER_DEBUG=layer
```

Reject `Validation Error` and `SYNC-HAZARD` diagnostics independently of exit
status, and require every pixel/depth assertion to complete. The loader output
identifies the active layer. The corrected fixture covers direct and bundled
indexed rendering, attachment load behavior, depth preservation/read-only use,
explicit depth clear, and caller reference release.

This is targeted AMD Vulkan correctness evidence. It does not establish full
render conformance, untested resource usages, physical Metal/D3D12, driver-loss
recovery, peak device memory, publication, or a measured application advantage.
