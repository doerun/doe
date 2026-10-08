# ONNX Vulkan device lifecycle qualification

This correctness campaign repairs Doe's descriptor loss callback, no-op device
destruction and untracked loss future. Last external release now triggers logical
loss while internal resource references preserve native cleanup. Explicit destroy
blocks new GPU admission and drains accepted work through the existing completion
policy. Unknown completion never authorizes release or successful output.

The [manifest](manifest.json) binds the pinned ONNX consumer, source-built Dawn,
preceding Doe and immutable repaired native library. [Lifecycle controls](controls/receipt.json)
retain requested modes, borrowed callback handles, stable pending/completed future
identity, failed creation and valid reuse. Repeated destruction and legal release
inside WaitAny callbacks preserve exactly-once delivery and cleanup.

Async pipelines delivered after loss return Success with inert error objects,
matching pinned Dawn. They retain cleanup leases and fail native submission
validation. The [callback regressions](callback-controls/receipt.json) and native
async render fixture preserve descriptor snapshots, joined requests and eventual
DRM cleanup. This success status does not establish compiled or executed GPU work.
The copy/readback oracle and submitted completion controls establish the bounded
actual work separately; destruction does not imply kernel interruption.

[Unchanged SqueezeNet](application/doe.json) and [MatMul/Add recovery](safety/doe.json)
retain the original source, model, inputs, independent numerical requirements,
source provider and Vulkan context plumbing. CPU fallback stays disabled, raw
profiles substantiate operator placement and equivalent Dawn arms retain their
normal preparation and synchronization. [Native disabling](application/doe-disabled.json)
and [oracle sensitivity](application/oracle-negative.json) fail the application as
expected. This is qualification without application timing samples.

Rejected prior attempts remain under `exploratory/prior-attempts/`. They include
missing multiple-device context selection, prohibited spontaneous reentry, the
initial public-AddRef migration error and the async pipeline gap. Earlier fixture
source and overwritten intermediate binaries are not fully retained; those
attempts are diagnostic and supply no qualification custody. Final processes bind
exact source and immutable binary identities. Prior published callback, application
and CPU-attribution reports retain their original bytes and decisions.

[Contract and migration](../../../../docs/native-device-lifecycle-contract.md) and
[execution/replay commands](../../../../bench/external-projects/onnx-vulkan-device-lifecycle/README.md)
define the bounded acceptance. Failed-creation WaitAnyOnly delivery, abandoned
instances, real driver loss, arbitrary concurrent API use and other backends remain
unqualified. No general WebGPU conformance, performance advantage or adoption is
claimed. Metal, D3D12, browser switching and closed browser transformations remain
deferred.
