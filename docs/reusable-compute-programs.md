# Reusable compute programs

`doe-gpu/compute-program` is the explicit fixed-shape interface for repeated
compute. Its declarations contain WGSL source, shader entry points, buffers,
ordered dispatches, bindings, and an output. The schema is
[`compute-program.schema.json`](../config/compute-program.schema.json).
It has no Doppler or browser dependency.
This is the initial declared DoePlan surface. Existing `doe-gpu/plan` capture
lowering remains a separate ingestion contract; no automatic capture is implied.

## Qualified scope

| Tuple or capability | Current boundary |
| --- | --- |
| Linux AMD Vulkan; Node, Bun, Electron main process | Local retained-package correctness and lifecycle evidence; see the [live status](status/reusable-compute-programs.md) |
| Apple Metal | Host recording requires physical requalification; GPU recording is unsupported |
| Windows D3D12 | No qualified package or plan lane in this change |
| Declared buffer compute in bind group zero | Fixed dimensions, ordered dispatches, changing exact-size input bytes |
| Texture plans, dynamic dimensions, automatic arbitrary capture | Outside this descriptor; unsupported declarations fail validation |

The image and heat examples are repository applications. The declared
HoloScript LIF fixture preserves an external shader and CPU twin while adapting
orchestration to a prepared program. These diagnostic cases do not complete the
external-application portfolio or general WebGPU conformance requirements.

## Application startup evidence

The isolated startup experiment uses
[`compute-program-startup-experiment.json`](../config/compute-program-startup-experiment.json)
and its schema. This additive repository-only contract inherits frozen workload,
sampling, and regression limits from the existing tail policy. It assesses
device readiness separately from warm execution and preserves original tail
comparisons. A passing startup experiment alone is not an ordinary-provider
advantage over Dawn. Run its assessment with
`python3 -m bench.runners.assess_compute_program_startup --input <cohort> --output <new-assessment> --policy config/compute-program-startup-experiment.json`.

Evaluation report version `6` defines `deviceStartupMs` from provider import
through a resolved device request, before benchmark evidence collection.
`deviceStartupTimingScope` names that boundary. `providerEvidenceMs` separately
records provider identity collection, hashing, and binary retention; it is not
runtime startup or an optimization acceptance cost. Application invocation
measurements and public runtime behavior are unchanged.

Earlier reports include provider-specific evidence work inside startup timing.
Their values and verdicts remain historical. New comparisons reject mixed
startup scopes, including legacy startup measurements from different provider
families. A shorter measurement after this correction is not a runtime speedup.
The [retained diagnosis](../bench/out/compute-program/20260908-startup-scope/README.md)
and [uninstrumented validation](../bench/out/compute-program/20260908-startup-scope/validation/outcome.json)
keep the original observations and corrected scope separate.

## Bounded candidate jobs

`python3 bench/cli.py program candidate --help` is the repository front door
for evaluating candidate WGSL. The acceptance job is independent of the candidate:
[`program-candidate.schema.json`](../config/program-candidate.schema.json) binds
the original descriptor, replaceable shader, trusted CPU reference, declared
dependencies, input bytes, float64 expected results, numerical tolerances,
process/resource limits, sampling, and required performance. Pin the job hash
before candidate development. Changing an acceptance file requires a new job;
changing the candidate cannot silently change its acceptance.

Reproduce the included search fixtures with
`python3 bench/fixtures/program-candidate/prepare.py`, then
`python3 bench/fixtures/program-candidate/prepare-batched.py`. Each prints its
job hash. The batch is a distinct useful operation; it does not overwrite the
single-query result or make a slower single query acceptable.

```bash
python3 bench/cli.py program candidate \
  --job bench/fixtures/program-candidate/batched-job.json \
  --job-sha256 <independently-pinned-job-hash> \
  --candidate bench/fixtures/program-candidate/batched-distance.wgsl \
  --package-qualification <retained-package-summary.json> \
  --output bench/out/compute-program/<new-run> \
  --node /usr/bin/node --backend vulkan --execution gpu-recorded \
  --render-node /dev/dri/renderD128
```

The runner installs the exact qualified packages, snapshots acceptance inputs,
and runs the trusted reference and candidate in separate processes inside one
Linux namespace and cgroup. `--render-node` explicitly selects the only exposed
GPU character device. The default
[`isolation policy`](../config/program-candidate-isolation.json) bounds charged
host memory, tasks, temporary storage, and individual output files. A different
`--isolation-policy` must satisfy the same schema; there is no unrestricted mode.
Bubblewrap and a working user systemd manager with cgroup v2 enforcement are
required. Missing isolation fails before candidate execution. The namespace has
no host networking, home directory, desktop sockets, or workspace mount. System
libraries and declared inputs are read-only; only numerical outputs, native
journals/SPIR-V, retained provider binaries, and the execution report are writable.
The kernel limits are checked before entering the namespace. It retains
every first, warmup, and timed output. Independent verification recomputes
numerical acceptance and timing summaries, then checks native shader identities,
dispatch geometry, submissions, and SPIR-V. Worker timing includes input cloning
through float32 output, including GPU upload, completion, and readback; parent
IPC time, process preparation, device initialization, CPU time, sampled process
RSS, and teardown are reported separately. The same prepared program survives
between cases; each case's first invocation is identified separately. Preparation
recovery includes process creation and the first-invocation difference.
Native journaling remains enabled and contributes to GPU
path cost. Acceptance requires correct outputs and the job's performance and
preparation-recovery criteria on every case. Results remain diagnostic; a CPU
reference comparison is neither incumbent-provider qualification nor production
promotion.

Use `--previous <summary.json>` to check environment changes. It verifies prior
artifact hashes and compares adapter/driver identity, OS/kernel, Node binary,
file-backed loaded runtime/driver hashes, and isolation policy/tool/implementation
identities. Kernel-provided virtual objects
are identified separately. Every invocation reruns acceptance regardless of
whether the environment changed; previous acceptance never substitutes for
fresh execution. Raw outputs, sources, inputs, package archives, and manifests
are retained under the output directory.

Migration: job inputs remain at their recorded version; acceptance rules and
fixture hashes are unchanged. Execution version `2` declares `nativeTracePath`
under the dedicated writable native directory. Report version `2` binds the
isolation invocation and checked kernel limits. The schemas still validate
historical version `1` evidence, which does not acquire isolation retroactively.
The current command requires an explicit render device and always uses the
versioned isolation policy. Public compute-program semantics and `run()`
completion are unchanged.

The executor accepts fixed invocation-lifetime buffer programs on Linux/Vulkan
and explicitly selected execution modes. Resident jobs, texture jobs, other
physical platforms, and automatic candidate generation remain outside this
executor. References remain trusted acceptance code. Host library mounts do not
establish complete dependency closure. The cgroup caps memory charged by the
kernel, including native host allocations; it does not guarantee a cap on all
GPU/driver allocations. Output-file limits are per file, not a total disk quota.
Deadlines and cancellation terminate the owned service and detached descendants;
they cannot preempt a GPU kernel or establish driver-loss recovery. The exposed
GPU still shares the host kernel and driver, so this boundary is not a guarantee
against hostile shader or driver exploits. Independent external applications
and physical platform acceptance remain necessary before broader claims.

## Execution and lifetime

The shipped Node example at
[`packages/doe-gpu/examples/live-simulation.js`](../packages/doe-gpu/examples/live-simulation.js)
provides a terminal workspace for resident heat diffusion. Generate editable
WGSL with `node packages/doe-gpu/examples/live-simulation.js --write-shader heat.wgsl`,
then start the workspace with `--backend vulkan --execution gpu-recorded`.
Enter `edit heat.wgsl` after changing the file, or `rate 0.1` to change the next
iteration's parameter. `format new-format` proposes an explicitly different
state interpretation; `approve id` and `decline id` resolve its reset decision.
`view` displays a snapshot of the checked GPU result with a relative intensity
scale, not the CPU oracle. `cancel`, `save path.wgsl`, and `status` manage edits.
`close` waits for worker cleanup; `reopen` explicitly initializes fresh state
using the last accepted shader, format, and rate. It is not completed-result
replay or unfinished-computation recovery. `quit` closes the terminal.

Candidates run in a separate bounded process against the unchanged independent
heat reference and configured adversarial inputs while the old simulation
continues. The active process pauses at an iteration boundary for assessment
and activation; destructive edits stay paused for the exact reset decision.
Activation prepares the replacement on the original device and reports its
pause and replacement preparation duration; initial preparation is also visible.
The compiler is not made asynchronous by this example. Numerical failure in an
active frame stops simulation and remains visible in the terminal, where the
operator can close and explicitly reopen. Already modified GPU state is not
assumed recoverable. Cancellation closes candidate processes or waits for
bounded active submissions; it does not preempt a kernel.

Migration: this is an additive Node example using the existing program API.
`config/live-simulation.json` owns its dimensions, reference tolerances, inputs,
and process limits, with matching shipped assets. Heap limits constrain the
JavaScript heap; reported worker RSS is host process memory, not GPU memory.
The application fixes its GPU buffer extents and has no automatic backend
fallback. Physical Metal and other hosts require separate application testing.

Pass a device and select `gpu-recorded`, `native-recorded`, or `webgpu`. The recorded modes accept
the registered Doe Node addon provider, also usable through Bun's Node addon
support. It requires a native contract version supporting the declaration, derived at
build time from the schema's `nativeContractVersion` definition. Native version
2 accepts descriptor versions 1, 2, and 3; version 3's additional state-update
policy runs in the package. Older libraries reject resident declarations before
allocation. The native command ABI has not changed.
`gpu-recorded` requires Vulkan support advertised by both the addon and library.
It owns a compiled GPU command buffer, retained pipelines, and descriptor pools.
Buffer identities and extents are checked before submission; mapping or changing
an allocation invalidates the recording. Programs own private descriptor state;
ordinary cache replacement cannot invalidate their commands.
Preparation does not dispatch the program; newly allocated resident state is
zeroed once and drained before preparation returns. Native pipeline creation costs are
included in preparation. Replacement records new GPU commands while retaining
unchanged public resources and compatible live native compute pipelines.

[`vulkan-compute-pipeline-policy.json`](../config/vulkan-compute-pipeline-policy.json)
selects `share-live-exact` at build time. The device registry checks complete
SPIR-V words, entry point, ordered descriptor layout definitions, and effective
required subgroup size before sharing a pipeline. Resource handles, buffer
extents, and dispatch counts remain private recording inputs; changing them
requires a new recording but can preserve its pipeline. Changed shader code,
layout, entry point, or subgroup requirement creates another pipeline. Another
device has another registry. The last active, cached, retired, or prepared owner
releases the pipeline; the registry does not retain unused pipeline history.
The shared owner also retains its creation layout for Vulkan implementations
without maintenance4 lifetime guarantees.
The `private` policy builds independent pipelines for controlled comparisons.
Local active and cached pipeline selection applies the same exact identity
checks. Hashes locate candidates; collisions retain distinct owning entries,
including pipelines already referenced by recorded commands. Effective subgroup
policy is resolved before lookup. Layout reuse also checks the layout definition.
Descriptor caches compare complete binding declarations, native resource handles,
allocation generations, buffer extents, and image layouts. New native resources
receive distinct generations even if a driver recycles a handle; image views
also require their original parent image. Collisions retain independent pools,
and failed preparation restores the previous descriptor owner. Buffer aliases
resolve their final allocation before descriptors capture handles. Prepared
programs validate retained resources before submission. These are internal
correctness checks; public descriptor, native ABI, and receipt versions remain
unchanged.
Program close releases owned bind groups, layouts, pipelines, shaders, and
buffers when their last program or output lease ends. Buffer destruction drains
submitted work and releases backing storage even while native handles remain
referenced. Ordinary Vulkan caches discard descriptors for destroyed buffers
while retaining compatible pipelines and unrelated live bindings. Device
teardown releases its queue reference; native resources retain the device they
need for subsequent cleanup. These lifecycle corrections preserve declaration,
options, and receipt schema versions. Checkpoint DRM allocation and residency
records in the [live status](status/reusable-compute-programs.md) are resource
retention diagnostics, not peak-memory or driver-loss evidence.
Linux package qualification runs the same native resource-retention regression
in Node, Bun, and Electron. It retains closed programs while checking DRM
allocation totals and device teardown, including timestamp scratch storage and
labeled queues. This adds acceptance evidence within qualification version 2;
it does not change its schema or establish another platform's resource behavior.
Native compute command recording owns pipelines, bind groups, indirect buffers,
copy resources, and query-resolution destinations until command buffer release.
Finishing transfers those references from the encoder; abandoning the encoder
releases them. Compute passes pin their encoder, and encoders and command
buffers retain their cleanup device. Fused compute/copy constructors follow the
same ownership rule, including failed preparation. This corrects caller-release
lifetimes without changing public declarations or receipts. Explicit resource
destruction still invalidates its backing storage. General JavaScript garbage
collection and rendering dependency ownership require separate qualification.
Native-direct JavaScript submission consumes command buffers and rejects reused
or duplicate buffers before submission. Finished encoders and ended compute
passes release their native handles. Native-direct mapped ranges use host-owned
ArrayBuffers on every host; writable mappings copy back before unmap, read
mappings do not, and unmap or destruction detaches the returned range. This
replaces external ArrayBuffers that Electron cannot create. The existing
mapped-range timing includes the host copy, so older native-direct measurements
do not establish the same readback cost. Package qualification checks command
consumption, mapped-at-creation writes, write remapping, and detachment in each
controlled host. These corrections add no public fields or fallback mode.
Compatible descriptor layouts permit sharing the compiled pipeline while
keeping descriptor sets independent, as specified by
[Vulkan layout compatibility](https://docs.vulkan.org/spec/latest/chapters/descriptorsets.html#descriptorsets-compatibility).

Optional `gpuTiming: 'timestamp-query'` requires a device created with the
`timestamp-query` feature. The default is `off`, declared in the options schema.
Timed programs retain a query set and resolve buffer, and include timestamp
readback in the existing output mapping. Vulkan GPU recordings retain and
validate the query pool as well as their buffers. Destroying a query invalidates
replay before submission. Updates preserve the selected timing mode.

Receipt schema version 5 requests queue completion and readback mapping together
and waits for both before consuming bytes. `completionMode` is `queue-and-map`
when output or timestamps need mapping, and `queue-only` otherwise. Failure
waits for both operations to settle and unmaps any successfully mapped buffer
before resource leases can be released. Cancellation checks still discard output
and invalidate submitted resident state. This scheduling applies to every
provider using the declared program interface.

Version 5 `timingMs.submitWait` includes submission and concurrent mapping;
`readback` includes byte copying, timestamp decoding, and unmapping. Versions
1–4 retain their sequential queue-then-map timing meaning. Evaluation rejects
mixed completion schedules, and historical receipts must not be relabeled.
Complete useful-operation wall time remains the application metric. The
[WebGPU promise ordering contract](https://gpuweb.github.io/gpuweb/#promise-ordering)
does not permit assuming that either independently awaited operation completes
the other; both remain explicit.

Receipt schema version 5 retains nullable `gpuTiming`: source, compute-pass scope,
begin/end values, period, counter width, and elapsed nanoseconds. Doe Vulkan
resolves queries to nanoseconds on the GPU, including when another GPU command
consumes the destination. Query-owned scratch storage and cached conversion
pipelines avoid per-resolve CPU retrieval or a queue wait. The conversion uses
the exact physical f32 period, floors the product, and retains its low u64 bits;
the versioned contract is `config/vulkan-timestamp-policy.json`.
Subtraction of normalized integer values preserves precision at large epochs.
Unrepresentable intervals, including a hardware counter wrap that cannot be
reconstructed from normalized values, fail explicitly. The evaluation harness declares
the pinned Deno/wgpu Vulkan tick behavior explicitly and binds its calibration
to a retained physical Vulkan profile and upstream implementation sources.
Nanosecond support must be explicit in the loaded Doe addon and library;
older libraries and other Doe backends fail timed preparation until supported.
The additive `doeNativeComputeProgramTimestampNanoseconds` ABI reports resolved
units; the historical calibration ABI continues to expose physical tick units.
Receipt versions 1, 2, and 3 remain readable. Version 2 Doe timings retain their
historical raw-tick interpretation; they must not be relabeled as nanoseconds.
Pass-end markers use bottom-of-pipeline completion. GPU duration excludes input
upload, scratch clearing, query resolution, and readback. Complete invocation
wall time continues to include those operations and their instrumentation cost.
Requested buffer accounting includes public timing buffers and alignment padding;
it does not measure internal query scratch or peak device allocation.

`native-recorded` records host commands and replays them in Zig. The WebGPU
control keeps allocations, pipelines, and bindings resident and encodes each
invocation. These are explicit modes, with no fallback between them.

Descriptor version 1 preserves invocation-local behavior: upload exact-size
input snapshots, clear scratch and output buffers, execute the ordered passes,
wait, then map/copy/unmap output. Version 2 adds buffer `lifetime`, defaulting to
`invocation`. With `lifetime: 'program'`, inputs may be omitted after their first
initialization, and scratch/output state persists across runs. Newly allocated
resident state starts at zero. Shapes and source cannot change in place; uniform
buffers must be inputs and bindings remain in group zero.

Prepare with `readback: 'none'` to keep output on the GPU. This removes output
copying, mapping, and readback allocation; optional timing still resolves and
maps its own query bytes. `run()` returns `output: null` and `outputHash: null`
when output bytes were not observed. The default remains `readback: 'output'`.
`program.output()` returns an opaque, same-device reference after a successful
run. Pass it as another program's input to copy on the GPU. The consumer holds
a resource lease through completion. Producer runs and updates reject while
leased; closing a producer drains its work and releases its ownership while
an already accepted consumer retains its copy source. New uses reject after
producer execution, update, close, or device loss. References never expose a
raw GPU buffer and copied or forged reference objects are rejected.

Receipt version 4 records program-instance identity, output generation,
input origins, prior resident-state origins, copied bytes, and API submission
count. A byte hash is present only when the bytes are known. Storage input roles
do not imply read-only WGSL: after execution their resident contents carry
program/generation provenance and a null input hash until uploaded again.
Uniform inputs retain known initialization hashes. Provenance identifies the
producing execution; it is not a numerical oracle or an output content hash.
The recorded path uses a preceding input-copy submission when needed; ordinary
WebGPU submits input-copy and compute command buffers together. Both wait for
completion, and receipts expose this distinction.

`update(descriptor)` validates and prepares a replacement. Identical resource
keys share allocations and compiled state; changed keys acquire replacements.
Resident contents survive only when their complete buffer declaration is
unchanged. Changed dimensions, type, role, or lifetime allocate fresh state.
Only successful preparation invalidates the prior program. Failed preparation
releases temporary resources and leaves the prior program available. Device
loss requires preparation on a new device. Programs reject overlapping runs,
and program operations serialize error-scope ownership on a shared device.
Applications must keep unrelated device operations outside a program operation.

### State-update approval migration

Descriptor versions 1 and 2 preserve their previous update behavior. Version 3
requires a nonempty, application-owned `stateFormat` on program-lifetime buffers
and rejects it on invocation-lifetime buffers. Changing a format explicitly
changes state interpretation even when the byte size is identical. Keeping a
format declares compatible interpretation; the runtime does not infer semantic
equivalence of arbitrary shader edits.

`assessUpdate(next)` runs while the program is idle and returns an immutable
assessment with retained, replaced, discarded, and created resident state.
Replaced entries include both declarations. Its schema is `updateAssessment`
under the descriptor schema. Assessment causes no allocation or GPU work beyond
host metadata. If either the old or proposed descriptor is version 3, replacing
or discarding resident buffers requires
`update(next, { assessment, reset: 'approve' })`. The default is `preserve`.
Downgrading a descriptor cannot bypass this check. Compatible edits can call
`update(next)` directly.

Approval is bound to the exact immutable proposed descriptor, original program
instance, and invocation revision. Starting another accepted run expires the
assessment, even if that run is subsequently cancelled. An invalid input rejected
before a run starts does not expire it. Serialized or copied assessments carry
information without authority. A rejected reset throws `DOE_PROGRAM_RESET_REQUIRED`
with its assessment; a foreign, copied, or stale approval throws
`DOE_PROGRAM_STALE_ASSESSMENT`. No replacement resource is acquired before these
checks. Failed replacement preparation preserves old state; its assessment can
be retried while that state remains at the assessed revision. Success closes the
old program and releases its resources only after replacement preparation.

Updates still require an idle program and own its device error scopes during
preparation. This contract does not imply background pipeline compilation or
kernel preemption.

Cancellation before submission prevents dispatch. Cancellation after submission
drains already-submitted work and discards output; it does not preempt a running
GPU kernel. A cancelled invocation that may have changed resident state
invalidates that program; continuing from an unobserved partial state requires
explicit preparation. Invocation-local programs remain reusable after drained
cancellation. Cancellation during mapping also discards output and unmaps the
readback buffer. Runs without a cancellation signal do not schedule a separate
event-loop turn solely for cancellation. `close()` prevents further runs,
drains the active invocation, and releases retained state. Use a process boundary for deadlines that must survive
a hung driver. Program allocations are requested buffer bytes, not measured
peak device memory.

## Reproduction

The packaged applications accept ASCII grayscale PGM files:

```bash
node packages/doe-gpu/examples/compute-program.js image input.pgm edges.pgm vulkan
node packages/doe-gpu/examples/compute-program.js heat input.pgm heat.pgm vulkan 32
node packages/doe-gpu/test/integration/test-integration-compute-program.js
```

`examples/compute-programs.js` supplies image denoising/edges and heat diffusion
declarations. Independent CPU oracles live under `bench/oracles/`; neither
hash equality nor the runtime provides the numerical truth.

Evaluation policy, tolerances, dimensions, sample settings, deadline, and CPU
outcome threshold live in
[`compute-program-evaluation.json`](../config/compute-program-evaluation.json).
Use `python3 bench/cli.py program evaluate --help` for the
sequential physical-device matrix. Raw results live under
`bench/out/compute-program/`. Measurements remain diagnostic until independent
fairness and outcome admission; Deno/wgpu and Node/Dawn host differences remain
explicit. Native audit traces run separately from timing samples.
The gate rechecks retained output bytes against the independent CPU oracle,
verifies native dispatch/source/backend-artifact identities, and recomputes rows.
Use `python3 bench/cli.py program verify <matrix>/summary.json`.
The evaluation policy selects the nearest-rank estimator for both the Python
aggregate and JavaScript process statistics. Historical comparison callers keep
their existing estimator. Raw samples, provider binaries, evaluation policy,
and implementation sources are retained with each new matrix. Use its retained
policy with `program verify --policy` when the repository policy has changed.
New matrices retain their resolved `policy.json`, including copied external
fixtures. Pass that policy to verification so the matrix remains independent of
the original fixture location.
Evaluation policy schema version 4 declares `gpuTiming` and
`dawnTimestampQuantization` (`default` or `disabled`); historical policies leave
timing off. Run schema version 3 records GPU duration statistics. The gate
recomputes durations from raw counter values and calibration, validates timing
buffer work, and recomputes GPU percentiles. Historical receipts and older
run schemas remain readable. Quantized timestamps and different resolve paths
must be accounted for before comparing GPU timing or instrumentation costs.
Timed Vulkan policies also select `vulkanDeviceIndex`, `wgpuTimestampUnits`,
`timestampSources`, and `timestampPeriodRelativeTolerance`. The tolerance only
accounts for decimal rounding in `vulkaninfo` JSON. Physical device selection
initializes Doe's timestamp period even when the runtime's separate diagnostic
query pool has never been created. Missing calibration, a different adapter,
an ambiguous compute-queue counter width, or a period mismatch fails the gate.
New run artifacts retain the loaded native addon and physical clock profile.
Preparation break-even uses mean preparation cost and median
invocation savings; no break-even is asserted when invocation does not improve.

### Tail experiment and diagnostic sidecars

`config/compute-program-tail-experiment.json` freezes the retained package
controls, original comparison, development and transfer applications, sampling,
acceptance thresholds, and diagnostic bounds before tuning. Run
`python3 -m bench.runners.run_compute_program_tail_experiment --help` for the
focused alternating-package experiment. Frozen sampling preserves the original
invocation policy; expanded sampling changes only process and timed-run counts.
The original comparison remains retained alongside both. Acceptance requires
the declared application median improvement, permitted slow-tail and process-cost
regressions, and repeated process improvement. Transfer uses the same correction
without application-specific retuning. These decisions remain diagnostic.

The additive, repo-only `--diagnostics=<experiment-policy.json>` option on
`bench/runners/run-compute-program.mjs` buffers host events and writes them after
measurement. It preserves the run/receipt schemas and adds an explicit
instrumentation limitation to `measurementLimits`. Instrumented runs cannot
confirm an application performance benefit. Invocation identity is the existing
`programInstance:run` pair; no public program option or receipt field is added.

Diagnostic TSV sidecar contract version 1:

- `events.tsv`: event name, invocation ordinal, monotonic `startMs`/`endMs`,
  and kind. Method kinds are synchronous return, fulfilled settlement, and
  rejected settlement, encoded as `0`, `1`, and `2`. GC kinds retain Node's
  observed GC classification; GC intervals join by time, not callback delivery.
- `invocations.tsv`: ordinal, invocation identity, start/end, live heap before
  and after, and voluntary/involuntary process context-switch deltas. Heap
  deltas are not allocation counts; process switches do not identify a thread.
- `limits.txt`: schema version, configured event bound, dropped-event count,
  and observation scope. Overflow fails diagnostic collection explicitly.
- `correlated-invocations.tsv`: receipt and wall/CPU timings joined to that
  invocation's GC overlap, heap/switch observations, and longest synchronous
  API calls. Settlement intervals overlap synchronous calls and are not summed.

The optional Linux x86-64 GDB observer
`bench/tools/trace_compute_program_storage.py` uses retained library debug
information. Its TSV records encoder identity, reuse reason, requested and
returned command/reference capacity, actual allocator allocation/resize/remap
calls and successes, contended mutex slow-path calls, and debugger-perturbed
lock-wait duration. It observes out-of-line array-growth entrypoints; inlined
sites remain outside its scope. Records are buffered until process exit.
`correlated-storage.tsv` joins serial native encoder loans to invocation IDs
only after verifying one host encoder per invocation and matching counts/order.
Debugger timing cannot establish application latency or the uninstrumented
duration of an allocation or lock wait. An empty reuse pool, actual array
growth, and observed lock contention are distinct observations.

Comparison TSVs retain complete invocation rows, process costs, p50/p95/p99
statistics, raw control/treatment ratios, and the predeclared acceptance
decision. `claimStatus` stays diagnostic. A reproducible bundle contains exact
inputs, executors, package archives, policies, and replay commands; independent
reproduction additionally requires retained results from another operator.

## External declared simulation

Prepare HoloScript through the existing external reproduction front door, then
freeze the declared simulation from the pinned Git objects:

```bash
python3 bench/cli.py program prepare-lif \
  --upstream=bench/out/external-projects/holoscript-snn-webgpu/upstream \
  --output=bench/out/compute-program/20260905-holoscript-lif-final-fixture \
  --case=large-65536x10
```

The destination must be new. The fixture retains source, license, shader,
TypeScript compiler, CPU oracle, input bytes, expected outputs, and numerical
requirements. Compilation uses the upstream package's pinned TypeScript
dependency. The membrane comparison requires both original tolerances; final
spikes must match exactly. A packing pass retains both observables in the public
program's output. Every provider executes that same pass and the same batched
ticks. This is an explicit orchestration adaptation; the unchanged application
compatibility receipts remain separate.

Use `program evaluate --policy config/compute-program-external-evaluation.json`
with the usual physical backend and executable arguments. That policy binds the
fixture hash. Alternative frozen cases require an explicit policy referencing
their generated fixture and hash. Unknown applications without a fixture fail.
The profile includes resident simulation acceptance; inspect its current
[numerical qualification state](status/reusable-compute-programs.md) before
interpreting a failed run. A failed oracle stops the matrix before timing claims.
The generic fixture loader and existing matrix handle multiple inputs and
strict external observables without a separate performance harness.

For a continuously advancing simulation, pass `--sequence-runs` to the same
`program prepare-lif` command. Freeze enough oracle states for cold execution,
every warmup, and every timed run; audits also require the post-cancellation
invocation. The sequence fixture uses program-lifetime buffers and uploads
inputs only on its first invocation. Its unchanged upstream CPU twin advances
through the same batches of ticks before any GPU run. Ordinary Doe, Dawn, and
wgpu receive the same resident declarations and input schedule as prepared Doe.
This is a distinct workload from repeatedly resetting the simulation.

## Retained package qualification

Use `python3 bench/cli.py program qualify-package --help` to retain
package archives once, install those exact archives with install scripts enabled
in fresh directories, and exercise Node, Bun, and Electron. That harness runs
the ordinary provider, repeated lifecycle, and plan regressions from the
installed package. It grants neither registry publication nor release admission.

The existing integration regressions accept `--prolonged` for sustained Linux
resource reuse and live simulation checks:

```sh
node packages/doe-gpu/test/integration/test-integration-native-resource-retention.js --prolonged
node packages/doe-gpu/test/integration/test-integration-live-simulation.js --prolonged
```

The resource fixture checks output on every invocation, post-close allocation
stability while closed programs remain reachable, and complete device cleanup.
The simulation checks each evolving frame against its independent heat reference
and retains reset, edit, cancellation, and reopening checks. Its progress deadline
restarts after each accepted frame. Logs distinguish sampled worker RSS and DRM
allocation totals from peak device residency; neither establishes driver-loss
recovery. For retained-package evidence, use the qualifier's import substitutions
and validate the installed package against its retained archives before and after
running these fixtures.

Qualification artifact version 2 stores archive and evidence filenames relative
to its own directory. Move that directory intact to reproduce elsewhere;
recorded hashes do not change. The loader rejects escaping references and checks
all retained artifacts. Version 1 preserves its original path semantics.

Pass that retained summary to the existing evaluator with
`program evaluate --package-qualification <summary.json>` instead of
`--native-library`. The evaluator installs the same wrapper and platform
archives offline with install scripts enabled, loads the installed program
executor for every provider, and loads Doe's native library from that
installation. The gate checks archive hashes, every packaged file, the
qualification's host/library agreement, and the actual loaded library. Changed
package bytes and mixed package sources fail before comparisons are admitted.
Installed files, archives, install logs, and execution artifacts remain in the
evaluation directory.
The evaluator also retains the complete qualification inputs under
`package-inputs/`, so a version 2 qualification remains usable after its original
directory is unavailable.
The Dawn control is pinned in `bench/package.json` and `bench/package-lock.json`;
`npm ci --prefix bench` installs that declared comparator dependency.

Evaluation artifact version 5 adds `packageQualification` and `packageRoot`.
Both are null for workspace-library evaluation; package evaluation binds the
qualification hash and the installed wrapper path. Earlier evaluation versions
retain their meanings and cannot carry these fields. This changes repository
evaluation artifacts, not public compute-program descriptors or run receipts.

## Migration and evidence boundaries

Evaluation policy version 5 requires an explicit `gpuActivity` value. `off`
preserves execution without host observations. `reject-observed-linux-drm`
requires Vulkan on a Linux host with a single PCI DRM render device. The generic
policy explicitly disables this platform-specific check; the AMD external
policy enables it. Earlier policy versions retain their original behavior.
Timestamp settings remain independent, with their existing grouped contract.

The Python evaluator brackets each measured child process with raw DRM fdinfo
snapshots outside the child's timing interval. The versioned
`*.gpu-activity.json` sidecar binds these observations to the evaluation hash,
policy hash, and physical device. Shared file descriptors are deduplicated by
DRM client identity. Positive foreign engine activity, disappeared clients,
missing counters, and counter regressions reject timing admission. Matrix
verification recomputes admission from the raw sidecar and requires every run
to use the matrix's policy. Numerical audit execution is unchanged.

The observer covers readable clients at process boundaries. It records unreadable
processes and cannot observe clients that start and exit between snapshots.
Passing this check does not prove exclusive access or replace an isolated
performance host. Rejected runs retain their numerical outputs and observations;
they cannot produce comparison rows. Counter identity and units follow the
[Linux DRM usage-statistics contract](https://docs.kernel.org/gpu/drm-usage-stats.html).
No public program descriptor, receipt, or package ABI changes with this policy.

The Vulkan pipeline cache now treats precomputed hashes as lookup hints, not
identity proofs. Rebuild the native library to apply this correction; public
descriptor, receipt, and ABI fields are unchanged. Earlier hash-only failures
remain retained independently of corrected physical execution.

The Vulkan compute pipeline policy is an additive build contract. Existing
package descriptors, public receipts, and native ABI versions keep their
meanings; rebuild the native library to apply the policy. Native lifecycle
regressions check shared Vulkan handles, private descriptor pools, changed code
and layouts, allocation failures, creator teardown, and device isolation with
actual dispatch/readback. Package resource counters continue to describe public
resource acquisition and must not be interpreted as native pipeline counts.

Vulkan buffer publication reserves registry capacity before native allocation
and initialization. Failed publication cannot leave a queued clear without a
resource owner. Resizing drains prior work and retains the old allocation until
its replacement is created. This ownership correction changes no descriptor,
receipt, or ABI fields; earlier failure artifacts remain historical evidence.

This is an additive contract. Existing plan/capture and Doppler Program Bundle
formats keep their meanings; they are not automatically executable programs.
The preparation counters and run receipt schemas accompany the descriptor.
No runtime checks have been removed by a proof claim.

Evaluation policy schema version 2 adds `preparedExecution` and
`percentileMethod`. Run receipts add the `gpu-recorded` execution value. Native
identity traces add `compute_program_prepared` and `compute_program_submitted`
events binding the retained recording, dispatch count, and submission index.
GPU replay audits require preparation once and matching subsequent submissions;
re-encoding dispatches on every invocation does not satisfy that contract.
`program verify-native` validates the shared native replay contract and SPIR-V
artifacts. Native object-creation records now have a schema alongside dispatch
and submission records. Its dispatch count describes encoded records; replay
submission events carry the repeated work count.
Compute pipeline release now honors retained references during program updates.

Evaluation policy schema version 3 adds hash-bound `fixtures`. Evaluation run
schema version 2 replaces the single `inputPath` with `inputPaths` and records
the optional retained fixture. Historical policy and run versions remain
readable. Public compute-program descriptors and run receipts keep their
existing versions. Fixture schema, provenance, complete oracle coverage, and
input extents are blocking validation requirements.

Fixture schema version 2 adds an explicit `sequence` with `inputs:
'initialize-once'` and ordered, hash-bound expected states. This version requires
program-lifetime buffers; mixed lifetimes and varying inputs require a future
sequence contract. Evaluation run schema version 4 retains `warmups`,
`lifecycleRuns`, and `failedRun` alongside cold and timed samples. Numerical
failures retain the actual output and receipt. The gate checks every successful
invocation's oracle, resource work, and preceding state generation, including
warmups and cancellation recovery. Timed percentiles still exclude those
untimed records. Earlier fixture and evaluation versions keep their reset
semantics and remain readable; public receipt version 4 is unchanged.

Vulkan cache insertion failures now restore active compute and descriptor
ownership. Rebuild the native library to receive the correction; cache keys,
public descriptors, and receipt fields are unchanged.

Vulkan `clearBuffer` now records a GPU fill at submission, with transfer
dependencies, instead of performing a mapped host clear during encoding.
Buffer copies also use ordered GPU commands, including copy-only submissions
after an asynchronous compute submission. Host-visible memory does not permit
a CPU copy to race an unfinished GPU producer. The unchanged UMAP workload
and the separate-submission regression exercise this boundary.
JavaScript buffer copies and clears invalidate host shadows at submission as
well as encoding; partial uploads cannot validate stale untouched bytes.
Existing command field layouts
remain unchanged; programs must be recorded again after updating the library.
Replay dispatches share one conservative compute barrier. Its source and
destination scopes already cover the former identical dependency barrier;
the shared helper clears the covered tracking state. Indirect dispatches retain
their separate argument-read dependency before that bookkeeping is cleared.
This removes duplicate barriers without claiming proof-driven elimination.

Vulkan MAP_READ allocations now use
[`vulkan-buffer-memory-policy.json`](../config/vulkan-buffer-memory-policy.json).
The policy prefers CPU-cached memory while requiring host visibility and
coherence. If no supported cached coherent type exists, selection retains the
required properties. This changes allocation policy for ordinary WebGPU and
prepared programs alike. GPU copies, completion waits, mapping, and numerical
checks still execute. The performance effect depends on physical memory types;
see the [Vulkan property contract](https://docs.vulkan.org/refpages/latest/refpages/source/VkMemoryPropertyFlagBits.html).

Remaining strategy acceptance includes a meaningful application advantage over
the strongest controls, actual peak GPU memory, independently
reproduced Metal results, a frozen external application portfolio, and external
repeat use. Repository example programs are not externally owned applications.
A reusable
host recording alone does not establish the broader program compiler envisioned
in [`thesis.md`](thesis.md).
