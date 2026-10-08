# ONNX Vulkan callback qualification

The bounded callback campaign passes on the tested AMD Radeon Vulkan host.
The retained pre-correction Doe binary fails 35 observations in each of three
independent processes. Pinned source-built Dawn and corrected Doe pass all
observations in three processes each. This establishes the named callback paths;
it does not establish general WebGPU conformance or a performance advantage.

The [contract](../../../../config/native-callback-contract.json) pins ONNX
`d2ede0adeb300958cfb5a256c09d27c66c3a6d71` and Dawn
`ec7b457e5bb1fcec6f59733c4f3dd84d2f885a38`. The same bridge, generated Dawn headers,
fixture and compiler flags serve both implementations. Each implementation retains
its normal preparation and GPU synchronization. This campaign collects correctness
observations, with no application timing samples or performance candidate.

The corrected native library is
`af66973e3b8fde7d8f9977cd4c94493bab4b92449e82eb56fd9428f7f3c386a5`.
The [manifest](manifest.json) binds executed sources, native/control binaries,
headers, build command, raw observations, application receipts and local binary
custody. Source base `5a917a0c5bae7df8809f76ea73eda103feb65046` plus retained source
snapshots describes the correction before its publishing commit.

## Qualified behavior

- RequestAdapter, RequestDevice, compute pipeline creation, buffer mapping,
  error-scope popping, queue completion and shader compilation information respect
  WaitAnyOnly, AllowProcessEvents and AllowSpontaneous.
- WaitAnyOnly callbacks execute inside matching WaitAny; an unrelated instance
  pump cannot deliver them. AllowProcessEvents callbacks execute in their owning
  pump or matching WaitAny. Spontaneous callbacks retain arbitrary-thread permission.
- Unique instance-owned future identities survive repeated waits without repeated
  delivery. Waiting on one pending future leaves another callback pending.
- Submitted buffer copying returns the exact independent CPU pattern through mapped
  readback. Pending mapping cannot expose a mapped range. Unmap and buffer destruction
  abort undelivered mapping success with the actual ABI status; subsequent mapping
  succeeds. Alignment errors reach the validation scope.
- Failed descriptor snapshots deliver an explicit pipeline validation failure in
  the requested callback mode and permit successful reuse. Empty error-scope pops
  return Error/NoError instead of false success. The invalid pipeline control contains
  an unsupported constant-entry chain and an unknown override name: Doe rejects the
  snapshot, while Dawn diagnoses the override; identical backend error internals
  are not required.
- Callback resource leases survive caller releases and foreign callbacks. Pipeline
  producer leases and request-owned shader/layout/device leases retire before future
  settlement. A live instance drains pending obligations; DRM descriptors return
  to their initial count before process exit. The existing async render-pipeline
  fixture also passes caller teardown, independent result leases and DRM cleanup.

Allocator failure, reentrant pumping, instance release inside a callback and
concurrent completion/wait tests accompany the physical fixture. Core, full and WGSL
Zig suites, format, import fence, source layout and line limits pass. A prior allocation
failure test leaked its successful adapter probe; it now releases that probe.
The old WaitAny test invented identities; it now creates and settles real obligations,
with a separate unknown-identity rejection test.

## Unchanged applications

The same prepared upstream SqueezeNet binary, model, ramp input, pinned ONNX provider,
full validation, independent reference and numerical requirements pass on both native
arms. Each profile contains 123 operators, all placed on WebGpuExecutionProvider;
CPU fallback is disabled. MatMul/Add, failed initialization, failed session creation,
descriptor recovery and subsequent reuse pass on both arms. Pre-execution cancellation
remains cancellation before submission, not interruption of submitted GPU work.

Disabling each selected native library fails the application's actual operation.
Changing the independent oracle makes Doe's application fail at class zero. The
application preparation and native call logs remain retained; a side computation
cannot substitute for the application's execution ownership.

## Retained failures and limits

The [exploratory records](exploratory/) preserve early mismatches, fixture defects,
bridge descriptor-chain aborts and the intermediate teardown failure. One intermediate
cohort overlapped a native rebuild and lacks per-process immutable-byte custody;
it grants no final qualification credit. The final producer records identical native
hashes before and after every process. The request cleanup ordering was corrected
before the final cohort.

Last caller-held instance release is not a qualified abandonment/cancellation
mechanism. The pinned Dawn abandonment probe did not deliver its pending adapter
callback on that release boundary. The accepted teardown keeps an instance available
to pump or wait until obligations settle; it does not claim abandoned-instance cleanup.
Device-lost descriptor callbacks and DeviceDestroy semantics remain open: the current
native device-lost descriptor is not wired, and the drop-in destroy function remains
a no-op. Observing the application's DeviceDestroy call is not evidence of those
semantics. Unknown legacy lost futures reject an unwakeable blocking wait.

Real device loss, submitted-work interruption, arbitrary API/thread combinations,
other hosts, Metal, D3D12, browser switching, deployment and upstream adoption remain
unqualified. The shared callback owner preserves Metal's spontaneous worker delivery,
but no Metal hardware qualification is promoted here. Browser transformations remain
closed; a separate compiler campaign still requires a concrete reproduction.

Earlier [application/performance](../20261005-onnx-vulkan-campaign/README.md) and
[CPU attribution](../20261008-onnx-vulkan-cpu-attribution/README.md) reports remain
byte-for-byte unchanged. Their original verifiers, including local custody checks,
pass against source base `5a917a0c5`; their rejected advantage/no-candidate decisions
are unchanged. Current native sources are a new qualification, not a rewrite of
those historical binaries.

## Verification

From the Doe repository:

```bash
python3 bench/external-projects/onnx-vulkan-callbacks/verify.py --report reports/benchmarks/amd-vulkan/20261008-onnx-vulkan-callbacks
python3 bench/external-projects/onnx-vulkan-callbacks/verify.py --report reports/benchmarks/amd-vulkan/20261008-onnx-vulkan-callbacks --check-current --with-custody
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_native_callback_evidence
```

The portable verifier replays callback placement, unique identities, status meanings,
selected-future delivery, exact readback, mapping state, teardown, native call counts,
operator placement and application identity joins. The custody option authenticates
the ignored local binary archive named by the manifest. Its availability is distinct
from the retained source/log report. Tamper controls reject changed callback phase,
wrong mapped status and altered readback after the outer hashes are recomputed.
