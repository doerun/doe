# Independent Three.js graphics screen

## Disposition

Close the graphics screen without a transformation or performance promotion.
The particle candidate stays closed. Preserve the delivered browser compiler;
activate only the existing native Vulkan Doppler generation contract batch.
The [summary](summary.json) owns observations, exclusions and disposition.

## Application and observation boundary

The pinned [Three.js fog-scattering application](https://github.com/mrdoob/three.js/blob/3d3a92e467aafd6749eb06f732a5f42e6d117fe4/examples/webgpu_custom_fog_scattering.html)
renders a procedural forest, compositing blurred scene depth with fog.
[Original](application-original.html) and [observed](application-observed.html)
application sources are retained. The observation patch exposes the existing
renderer, render pipeline, camera and scattering uniform. It changes no scene,
shader graph, resource layout or dispatch. The animation loop is stopped for
fixed-camera manual frames; this is an execution-condition deviation from
ordinary interactive use, not an unchanged interactive performance claim.
The [screenshot](application.png) confirms the real application rendered.

The upstream Gaussian implementation already uses directional passes and
setup-computed coefficients. [Dependency identities](dependencies.json) bind
acquired upstream files by Git blob identity and content digest. The mirror
checks against the pinned Git tree. [License](THREE-LICENSE.txt) is retained.
The [frozen plan](frozen-plan.json) binds the executed runner. Generated shader
captures are in [the profile receipt](profile-0.json), with standalone WGSL files.
The compiler's output preserves each captured blur fragment byte for byte:
[horizontal](shader-16.wgsl), [vertical](shader-17.wgsl),
[admission receipt](doe-admission.json). No altered shader was executed.

## Actual execution and attribution limits

The profile uses the engine's existing timestamp pool with driver shader
capture enabled. Its asynchronous pool sometimes supplies incomplete or cached
pass records. The analyzer excludes incomplete sets and repeated timestamp
identities. Remaining unique complete sets are diagnostic observations, not a
qualified per-frame latency decomposition. Material contribution to ordinary
application latency remains unqualified. Host completion and GPU observations
are separate; their durations are not added or subtracted.

[Matching Gaussian-family driver captures](driver-findings.json) contain NIR,
ACO and final native assembly. Identification uses the Gaussian coefficient
signature and fragment texture-sample count; it is not an exact per-pipeline
execution receipt. Raw [driver capture](driver-capture.log.gz) and selected
programs retain the evidence. Native texture samples survive compilation;
repeated source-level uniform reads do not establish repeated native loads,
and source private temporaries do not establish scratch traffic. Register
allocation and whole-application superiority are not established.

The [first](aa-0.json) and [second](aa-1.json) independent uninstrumented browser
processes execute identical shader captures with balanced label order. Paired
complete-frame differences reverse between processes. This blocks performance
attribution; no further calibration or outcome-selected cohorts were run.
There is no independent image oracle, transformed-shader comparison, or accepted
application benefit.

## Automatic optimization versus specialization

No provably redundant native work was identified. Removing texture samples
would need a separate sampler, spacing and numerical-equivalence contract;
linear-filter pairing is not justified by this application's dynamically
adjustable scattering and downsampled passes. Freezing the runtime uniform
would change the accepted input contract. A future explicit specialization
experiment would need a competent pipeline-overrides baseline. This screen
implements neither specialization nor application scheduling.

## Failure and reproduction

The [initial observer failure](failed-setup.json) attempted to read an adapter
field that the engine did not retain. Its [log](failed-setup.log.gz) is preserved.
The corrected observer captures identity at `GPUAdapter.requestDevice`, forwards
the call unchanged, and leaves engine source intact. The failure occurred before
completed profiling evidence; it was not a rejected timing cohort.

From the Doe root, use a headful display environment and a Playwright module:

```bash
DEBUG=pw:browser DOE_PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs node bench/external-projects/three-webgpu-screen/run-screen.mjs > screen.log 2>&1
node bench/external-projects/three-webgpu-screen/analyze-screen.mjs reports/browser-compiler/20261004/three-screen
runtime/zig/zig-out/bin/doe-emit-wgsl reports/browser-compiler/20261004/three-screen/shader-16.wgsl
```

The first command runs the pinned screen, acquiring only its observed
application dependencies. The second recomputes the retained disposition and
checks selected native instruction counts and emitted byte parity. The emitter
writes WGSL to standard output; its build identity is in [manifest](manifest.json).
The runner uses the plan's browser flags and capture environment. Raw generated
receipts are engine-owned snapshots, retained unchanged and hash-bound; only
the screen plan and derived summary introduce schema contracts. These are
repo-only diagnostics and do not amend runtime or public package APIs.

Component: `Benchmark and evidence system`, `External application portfolio`,
`Published reports`, and compiler emit/runtime relationship review.

Intent: preserved.

Acceptance evidence: [summary](summary.json), [manifest](manifest.json),
[validation](validation.txt).

Boundary effects: observation-only upstream application adapter; no runtime,
compiler, package or application semantic change. Compiler relationship review
remains in progress. Native Vulkan generation is a separate active campaign.
