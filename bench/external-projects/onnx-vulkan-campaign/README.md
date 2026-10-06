# Source-matched ONNX Vulkan campaign

This bounded campaign hardens the existing proc-table substitution, qualifies
Microsoft's pinned SqueezeNet console application, and retains a completed
negative performance decision. The model, original ramp input, operators and
winning-class behavior remain unchanged. MatMul/Add remains recovery/regression
coverage. [The report](../../../reports/benchmarks/amd-vulkan/20261005-onnx-vulkan-campaign/README.md)
contains raw independent-process observations and local custody identities.

## Contracts

Read [the contract and migration](../../../docs/onnx-vulkan-campaign-contract.md)
and [frozen policy](../../../config/onnx-vulkan-campaign.json). A request for full
validation is common to both arms; general callback/extension conformance remains
open. In particular, descriptor-return null/status recovery does not imply a
recoverable contract for every future or void call.

The common ONNX core is the pinned published binary paired with its matching
C++ headers. The WebGPU provider is built from the pinned consumer source, with
the existing explicit default-context patch. Source-built Dawn uses that same
source build, headers, Release configuration and Vulkan backend. Both backends
use the same context selection and instrumented bridge. An earlier direct Dawn
control is retained as a separate diagnostic lane. Native preparation and
synchronization remain owned by each implementation.

`reference.py` uses ONNX's reference evaluator. Its Softmax override follows the
[legacy opset specification](https://onnx.ai/onnx/operators/onnx__Softmax.html),
flattening from the axis, rather than applying newer semantics to the older
model. Full-output agreement with a separately executed CPU session validates
this oracle; application arms prohibit CPU fallback. Corrupted-oracle execution
controls demonstrate sensitivity beyond the application's original assertions.

The new unchanged-Conv WGSL reproduction exposed missing integer `dot` lowering
in Doe's SPIR-V emitter. The general typed integer multiply/add correction follows
[WGSL dot semantics](https://www.w3.org/TR/WGSL/#dot). Physical signed/unsigned
wraparound checks and unchanged full-shader compilation qualify the correction
before timing. This does not reopen browser shader transformations.

## Preparation and execution

All output directories must be new. The existing source-build preparation and
pinned ABI generator live in
[the proc-adapter harness](../onnx-webgpu-substitution/README.md). After preparing
that exact consumer, build the control and bridge:

```sh
python3 bench/external-projects/onnx-vulkan-campaign/build_control.py --consumer-root "$CONSUMER" --out "$CONTROL"
python3 bench/external-projects/onnx-webgpu-substitution/build_adapter.py --help
python3 bench/external-projects/onnx-vulkan-campaign/prepare.py --help
python3 bench/external-projects/onnx-vulkan-campaign/reference.py --help
python3 bench/external-projects/onnx-vulkan-campaign/safety.py --help
python3 bench/external-projects/onnx-vulkan-campaign/run_application.py --help
```

The report retains exact compilation commands for the context/recovery helpers,
application and source control. Use the pinned consumer's Python environment for
ONNX/reference/safety scripts. Build Doe's native library with the declared
ReleaseFast drop-in target; bind its actual bytes and build metadata. `safety.py`
requires explicit native, bridge, context, recovery and provider paths for each
arm. `run_application.py` accepts only those exact safety-qualified bytes and the
prepared application's identity. Its `--disable-native` control must fail.

Only after both positive and negative controls and Doppler retirement qualification
pass, collect balanced independent processes:

```sh
python3 bench/external-projects/onnx-vulkan-campaign/measure.py --doe "$DOE_QUALIFIED" --dawn "$DAWN_QUALIFIED" --doppler "$DOPPLER_SAFETY" --out "$MEASUREMENTS"
```

The performance process exits unsuccessfully when the frozen acceptance rule is
not met; it retains complete observations and a decision rather than hiding the
result. A/A failure stops the comparison. Cold and warm populations are separate. The corrected measurement scopes HOME
as well as XDG/Mesa cache roots and records actual persistent cache inventories;
the earlier cohort remains diagnostic after its HOME-based cache-path mismatch.
Warm profiles are diagnostic and cannot replace the primary metric. The original
harness bytes used for the retained run are included under `raw/execution-harness`;
subsequent type annotations, formatting and failure-record retention are explicit
source revisions, not a benchmark rerun.

## Deployment and replay

```sh
python3 bench/external-projects/onnx-vulkan-campaign/bundle.py --doe "$DOE_QUALIFIED" --dawn "$DAWN_QUALIFIED" --bundle "$BUNDLE" --out "$REPLAY"
python3 bench/external-projects/onnx-vulkan-campaign/bundle.py --replay-only --bundle "$BUNDLE" --out "$FRESH_REPLAY"
python3 bench/external-projects/onnx-vulkan-campaign/deliver_doppler.py --source "$DOPPLER_SNAPSHOT" --native "$DOE_LIBRARY" --metadata "$DOE_METADATA" --populate-cache --out "$DOPPLER_DELIVERY"
```

Application replay requires Linux bubblewrap and the tested host's Vulkan driver,
system libraries and GPU. It runs both native arms, library-disabling controls,
and corrupted-oracle controls with no checkout/network exposure. It is a local
integration bundle, not a published installer.

Doppler reconstruction places the corrected native and matching metadata into an
explicit derived copy of the retained provider archive. It keeps the exact
Doppler package; archive identities and changed members are recorded. Cache
population during preparation may access the network. Execution reconstructs
locked dependencies with isolated offline `npm ci`, verifies every installed
archive member and inventory, and checks generation/reopening plus named failures.
The earlier manually installed native-overlay controls remain retained separately.

Retain and verify evidence without changing its claim class:

```sh
python3 bench/external-projects/onnx-vulkan-campaign/retain.py --run "$RUN" --report "$REPORT" --custody "$CUSTODY_ARCHIVE"
python3 bench/external-projects/onnx-vulkan-campaign/verify.py --report "$REPORT" --with-custody
python3 -m unittest bench.tests.test_onnx_vulkan_campaign
```

The semantic verifier recomputes estimates from raw observations, validates work
placement and native ownership, and rejects promotion of the unfavorable result.
Local custody preserves executable bytes and the offline Doppler consumer. The
historical proc-adapter manifest stays untouched; its original verifier passes
against the retained original-source snapshot.
