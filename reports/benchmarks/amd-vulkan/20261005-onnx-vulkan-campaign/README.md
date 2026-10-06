# ONNX Vulkan campaign decision

Safety and compatibility qualify for the bounded integration on the tested AMD
Vulkan host. The unchanged upstream SqueezeNet application executes through Doe
and source-built Dawn with all observed operators placed on WebGPU, full-output
agreement with an independent oracle, and native disabling controls. The frozen
application advantage rule is rejected: primary gain falls below the material
threshold and CPU cost exceeds the regression bound. No performance correction
or speed claim is promoted.

[Measurement](measurement-summary.json) retains independent-process warm
and cold populations, balanced arm order, A/A controls, every complete `Session.Run`
observation and process controls. The [complete corrected raw cohort](raw/measurement-qualified/measurement.json.gz)
includes actual cache inventories. [Policy](policy.json) was frozen before timing.
The raw logs and observation files remain alongside their derived statistics.
[The cache audit](cache-audit.json) invalidates the first cohort’s cold-control
interpretation: Doe resolves its shader cache through HOME, so XDG isolation
alone was insufficient. The first cohort remains diagnostic and unaltered.
The corrected cohort scopes cache homes, proves empty cold caches and separately
preconditioned warm caches, and drives the final decision. Cold/tail improvements
cannot override failed primary and CPU criteria.
[Warm profiles](raw/warm-profile/profile-disposition.json) are diagnostic.
[The native CPU profiling attempt](raw/warm-profile/native-cpu-permission.json)
failed under host perf permissions; operator-inclusive profiles do not justify a
measured-owner correction. This does not establish that no optimization exists.

## Qualified ownership and recovery

[Doe safety](raw/safety/doe-matched.json) and
[Dawn safety](raw/safety/dawn-matched.json) retain failed initialization, invalid
descriptor recovery, failed session initialization and successful MatMul/Add reuse.
Cancellation is before execution; interruption of submitted work is unqualified.
The bridge permits null/status rejection where the consumer contract supports it.
The common matched safety fixtures cover failed session initialization and
pre-execution cancellation; the [additional Dawn bridge controls](raw/safety/dawn-additional-controls.json)
replay initialization/descriptor rejection against unchanged qualified libraries
after measurement. No timing or native bytes change.
Void/future paths without a qualified recovery contract remain explicit failures;
general callback and extension conformance are still open.

[Doe application](raw/doe-matched.json) and
[Dawn application](raw/dawn-matched.json) share application/core/provider/bridge/
context/model/input/oracle bytes, full validation requests and CPU-fallback
prohibition. Each backend keeps its own preparation and synchronization.
The source-built provider/control pins come from the original consumer source
receipt and retained build flags. The common core is the pinned published binary
with matching headers, not a source-built core. Actual operation sequences and
bridge calls include shader creation, submission, mapped readback and destruction.
This is bounded application/resource qualification, not universal safety equivalence.

The original input, model and console application remain unchanged apart from
provider plumbing, observation/oracle checks and recoverable top-level errors.
[The retained patch and preparation](raw/application-matched/preparation.json)
bind that boundary. The reference evaluator uses legacy opset Softmax semantics;
[a separate CPU crosscheck](raw/reference/cpu-crosscheck.json) checks full output.
CPU evaluation belongs only to the oracle; application fallback is disabled.

## Concrete correctness repairs

The unchanged [Conv shader](raw/compiler-reproduction/04-Conv2dMM.wgsl) supplied
an integer-dot SPIR-V reproduction. Original failure/debug logs and corrected
compilation/validation remain retained. Intermediate failed attempts, including
the earlier `corrected-compile.log`, stay visible; [the final full-shader receipt](raw/compiler-reproduction/full-shader-final.json)
and its SPIR-V outputs are the authoritative successful compiler controls.
Doe now emits typed integer multiply/add
without rewriting the application shader, with single argument evaluation.
[Physical integer-dot results](raw/compiler-reproduction/integer-dot-physical.json)
check signed/unsigned wraparound. Compiler and runtime gate logs remain in that
directory. The repair precedes timing and does not reopen browser transformations.

[Physical buffer retirement](raw/safety/physical-retirement-final.json) traces
separate completion boundaries and exactly-once release through device loss.
The original installed generation warning, corrected package/reopening observations
and [safety admission](raw/safety/doppler-safety-final.json) are retained. Unknown
completion retains ownership; confirmed loss permits retirement without consulting
a destroyed queue. Failed destruction remains owned for explicit retry.

## Deployment and custody

[Application replay](raw/deployment-final/results/replay.json) runs the retained
bundle with checkouts and external networking inaccessible. Both backends pass;
selected-native disabling and corrupted-oracle controls fail at their intended
boundaries. Declared system roots, drivers, GPU devices and writable results/scratch
remain host dependencies. This is local deployment qualification, not adoption or
another host's reproduction.

The earlier installed safety runs used a declared native overlay and are preserved
as executed, including their inherited installation metadata. The subsequent
[offline delivery reconstruction](raw/doppler-offline-final/delivery.json) fixes
archive/lock/installation identities and embeds the exact corrected native plus
matching metadata in an explicit derived provider archive. The exact Doppler
package remains bound to the safety result. Network access is allowed for cache
population during preparation; [isolated offline reconstruction and controls](raw/doppler-offline-final/results/summary.json)
pass with complete installed-member and dependency-inventory verification.

[Manifest](manifest.json) binds raw files, current source and local binary custody.
The ignored custody archive contains the application bundle and offline Doppler
consumer; every member can be rehashed with `--with-custody`. Raw execution harness
snapshots preserve pre-formatting/pre-annotation source. Later source revisions
retain cleanup failures as structured evidence and do not change the measured work.
[Trace metadata](trace-meta.json) binds complete application timing to its frozen
policy and raw measurements without inventing native timing phases.

The original proc-adapter report/native/source identities remain untouched. Its
verifier passes against the retained original-source snapshot and original custody.
The Chrome native-loader evidence is likewise preserved: it establishes native
computation inside the GPU process, while webpage work still uses Dawn. Browser
switching, Metal and D3D12 remain deferred.

Reproduce using [the harness](../../../../bench/external-projects/onnx-vulkan-campaign/README.md)
and [versioned contract](../../../../docs/onnx-vulkan-campaign-contract.md). Run:

```sh
python3 bench/external-projects/onnx-vulkan-campaign/verify.py --report reports/benchmarks/amd-vulkan/20261005-onnx-vulkan-campaign --with-custody
python3 -m unittest bench.tests.test_onnx_vulkan_campaign
```
