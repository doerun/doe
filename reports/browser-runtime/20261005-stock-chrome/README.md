# Stock Chrome native-boundary investigation

Disposition: diagnostic investigation. The user's accepted scope is a webpage
and downloaded WASM only. No launcher, extension, native host, modified Chrome,
or Fawn installation is permitted for that product. No page-only native provider
replacement was established. No production runtime or demo selector changed.

## What executed

An isolated stock Chrome process executed an integer compute shader and copied
its result back through ordinary page WebGPU. A launcher-loaded native probe
intercepted the GPU server's native Dawn submission wrapper while forwarding
the original call. Separately, the same GPU process executed the same operation
through a private Doe native context and validated its readback before cleanup.
Both observations used the physical AMD adapter. The browser launch retained
sandboxing; the probe did not independently inventory every sandbox restriction.

This is native interception and independent Doe execution within a stock browser
process. **The page's request still executed through Dawn.** It does not establish
native provider selection, hot swapping, canvas compatibility, performance,
clean installation, or a webpage-only mechanism. Loading the probe required a
local native launcher dependency, excluded by the user's subsequent scope.

The raw observations and exact trial source snapshots are retained in
[raw-evidence.tar.gz](raw-evidence.tar.gz), with
[SHA256SUMS](SHA256SUMS). Native libraries and the installed browser remain in
local custody and are not redistributed here. The snapshot is diagnostic source,
not a supported launcher or a browser patch distribution.

## Identities and controls

- Repository input: `239aea4dc`; runtime qualification remains the separately
  closed [ONNX integration](../../benchmarks/amd-vulkan/20261005-onnx-proc-adapter/README.md).
- Stock Chrome: `146.0.7680.177`, executable SHA-256
  `163bebf7c62e813523c35b12f8cc59f158b2c428c539ec4a3b5142a6b3c65010`.
- Doe library SHA-256:
  `1c59e7ec261f69c2e12e41530e3a135e57656b8ff448188cff275863ed5294ee`.
- Chrome's DEPS pins Dawn to `10fb89e3179bb7443e66911eb3c795c7aaf022e5`.
  Its generated common C layouts and signatures passed the existing adapter's
  audit. This does not qualify its private descriptor chains or browser policy.
- Chrome GPU identity: AMD, RDNA 3, device `0x1586`, RADV STRIX_HALO.
  Doe independently reported Vulkan, vendor `4098`, device `5510`.
- Inputs: `[1, 2, 3, 4]`; one increment per element, four workgroups of size one;
  independent integer oracle: `[2, 3, 4, 5]`.
- Browser flags enabled WebGPU developer/unsafe features, ignored the blocklist,
  selected Vulkan, and disabled Vulkan surfaces. These are not default settings.
  The successful paired diagnostic also pinned `VK_DRIVER_FILES` to RADV.
- No screenshots, unrelated browser sessions, servers, or workspace processes
  were used. Each trial owned and closed its browser and localhost server.

## Failures and corrected attribution

The evidence archive retains these distinct observations:

| Trial | Observation | Interpretation |
|---|---|---|
| Initial forwarding and controls | Some adapter requests failed with and without a hook | Hook causation was not established; bounded retries were recorded |
| Initial proc-table slot | Probe loaded; no intercepted submission | Library loading alone was insufficient |
| Initial body hook | Submission forwarded; page output passed | Later pinned-source inspection identified **wire-client code in the renderer**, correcting the initial GPU-server attribution |
| Doe loaded globally | Doe failed adapter acquisition after sandbox setup; page used SwiftShader | Neither physical browser evidence nor successful Doe execution |
| Global loader-only control | Page selected SwiftShader | Loader preload itself interfered with Chrome selection |
| Sandbox-disabled diagnostic | Private Doe output passed; page used SwiftShader | Retained failure, excluded from product acceptance |
| Separate loader namespace, unpinned drivers | GPU process crashed | This candidate failed; no successful substitution claim |
| Separate namespace, pinned RADV, client hook | Page physical output passed; private context unavailable in the hooked renderer | Confirmed that the two hooked processes differed |
| Separate namespace, pinned RADV, **server** hook | Page physical output and private Doe physical output passed in the GPU process | Bounded native admission, with Dawn still executing the page |
| Foreign pointer in native proc table | GPU process exited with signal-derived code `132`; no forwarding callback observed | Table replacement failed; CFI is a hypothesis, not a captured cause |

The successful server hook preserved the original CFI thunk and forwarded from
the native wrapper body at relative address `0x7423d80`, after admitting its
exact instruction prefix. The earlier client body was `0x73fe210`. Duplicate
proc-name records caused the initial mapping ambiguity; pinned native and wire
queue source separated them. The browser executable on disk remained unchanged.
Its process memory was deliberately patched by the launcher probe.

## Why this does not solve the accepted scope

The existing browser WASM artifact,
`packages/doe-gpu/assets/doe-wgsl-cff0e5502ab99769.wasm`, has no imports and exports
only compiler memory/job functions. Its SHA-256 is
`cff0e5502ab9976943936150e29ee521d4da590295bfcc7b1fbeca55136168af`.
Its Worker returns WGSL to a browser-owned `GPUDevice`; it has no native loader,
native proc-table access, driver entrypoints, or browser-process patch capability.
That inspection is retained in `wasm-interface.txt` inside the archive.

WebAssembly's host supplies its external capabilities. WASM memory and dynamic
linking do not supply access to Chrome's native functions or process memory.
Emscripten's browser dynamic linker links WASM side modules; it cannot load the
qualified ELF Vulkan runtime into Chrome's GPU server from a webpage.
[WebAssembly portability](https://webassembly.org/docs/portability/),
[WebAssembly security](https://webassembly.org/docs/security/),
[Emscripten dynamic linking](https://emscripten.org/docs/compiling/Dynamic-Linking.html).

The web WebGPU API exposes adapter/device requests, WGSL, resources and commands;
it has no native-provider installation interface. Chrome's documented web C API
binding uses the JavaScript WebGPU API, while native builds use Dawn directly.
[WebGPU specification](https://gpuweb.github.io/gpuweb/),
[Chrome's web and native integration](https://developer.chrome.com/docs/web-platform/webgpu/build-app).

Inspection of pinned Chromium source also found that its GPU decoder overrides
adapter/device creation and injects a Dawn-owned instance into the wire server.
Device construction carries feature restrictions, security toggles and an origin
cache-isolation descriptor. A generic native table replacement would therefore
need more than matching common C signatures. Stripping those descriptors or
passing Dawn-owned handles into Doe was not attempted.
[Pinned Chromium decoder](https://chromium.googlesource.com/chromium/src/+/146.0.7680.177/gpu/command_buffer/service/webgpu_decoder_impl.cc),
[pinned DEPS](https://chromium.googlesource.com/chromium/src/+/146.0.7680.177/DEPS).

## Remaining possibilities under webpage-only delivery

- Doe can own shader processing and application-level runtime logic, submitting
  through Chrome WebGPU. Native compilation and driver submission remain
  browser-owned. The existing compiler-delivery prototype supports this boundary;
  its closed optimization experiments do not establish an acceleration advantage.
- A separately implemented WebGL-backed subset could expose an application-owned
  WebGPU-like interface through browser WebGL. That needs new lowering and
  emulation qualification; it would not replace Chrome's native WebGPU backend.
- A WASM software executor could own execution on the CPU. It would not provide
  Doe's native GPU acceleration.

These are distinct alternatives, not completed implementations or changes to the
user's requested native replacement. A browser-exposed provider interface is
missing for the accepted webpage-only native-swap objective. No such supported
mechanism was found in the inspected build, implementation, or documented APIs.

Component: `doe.bench.external-projects`, `doe.reports`, `doe.docs.status`.
Intent: preserved. Acceptance evidence: archived physical controls, exact source
and binary hashes, common-ABI audit, documentation link validation.
Boundary effects: diagnostic native process interception only; no production
runtime, package, Chrome executable, Fawn demo, or provider-selection contract changed.
