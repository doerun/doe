# ONNX Vulkan CPU attribution

This repo-only investigation attributes the completed SqueezeNet campaign's CPU
regression without changing the consumer, model, native libraries or shader
source. It stops without a runtime correction or performance claim. See the
[retained report](../../../reports/benchmarks/amd-vulkan/20261008-onnx-vulkan-cpu-attribution/README.md),
[frozen policy](../../../config/onnx-vulkan-cpu-investigation.json) and
[contract migration](../../../docs/onnx-vulkan-cpu-investigation.md).

## Collection

Use the exact safety-qualified application and native artifacts from the
[completed campaign](../onnx-vulkan-campaign/README.md). All output paths must be
new. `probe.py build` copies the qualified application source, inserts clocks
around complete `Session.Run` calls through a private header, and instruments a
private bridge copy. It snapshots the executed builder and sampler sources.
Production source and native binaries are unchanged.

```sh
python3 bench/external-projects/onnx-vulkan-cpu/probe.py build --source "$QUALIFIED/application-matched" --out "$DIAGNOSTIC"
python3 bench/external-projects/onnx-vulkan-campaign/safety.py --help
python3 bench/external-projects/onnx-vulkan-cpu/probe.py run --help
python3 bench/external-projects/onnx-vulkan-cpu/collect.py --qualified "$QUALIFIED" --diagnostic "$DIAGNOSTIC" --out "$RUN/collection"
python3 bench/external-projects/onnx-vulkan-cpu/collect.py --qualified "$QUALIFIED" --diagnostic "$DIAGNOSTIC" --out "$RUN/caller-collection" --callers
```

Before collecting with a new diagnostic bridge, rerun the campaign recovery
harness against both native arms and that bridge. Run the diagnostic application's
`--negative native` and `--negative oracle` controls for each arm. The retained
run includes those controls. A failed control stops qualification.

Each child gets its own HOME, XDG and Mesa cache scope. Warmup precedes the
measured population; this is a warm CPU investigation, with no new cold-cache
performance claim. Each native retains its normal preparation and synchronization.
The full-output oracle runs on every invocation, and CPU fallback stays disabled.
Original-application and timer-disabled controls bound diagnostic overhead.

`sampler.c` uses Linux main-thread CPU timers and fixed binary signal-handler
writes. It does not modify profiling permissions. Its API-site markers avoid
per-call clocks in the accepted cohort. Optional inclusive/exclusive clocks
remain an intrusive diagnostic; the retained rejected control prevents their
promotion to comparative attribution.

## Analysis and replay

```sh
python3 bench/external-projects/onnx-vulkan-cpu/analyze.py --run "$PROCESS" --out "$PROCESS/profile-final.json"
python3 bench/external-projects/onnx-vulkan-cpu/decision.py --run "$RUN" --out "$RUN/decision-final.json"
python3 bench/external-projects/onnx-vulkan-cpu/retain.py --run "$RUN" --report "$REPORT" --custody "$CUSTODY"
python3 bench/external-projects/onnx-vulkan-cpu/verify.py --report "$REPORT" --with-custody
python3 -m unittest bench.tests.test_onnx_vulkan_cpu
```

ELF executable load segments determine each sampled address's load bias; file
offsets alone do not. Main-thread/process clocks bound coverage separately from
PC sampling. Timer overruns are retained and never assigned to the current PC.
Bounded frame-pointer walks are caller candidates, not complete unwinds. Nearby
exported symbols in stripped libraries do not establish the executing function
or imply CPU operator fallback.

The semantic verifier replays raw CPU/wall medians, native-work counts, executable
PC mapping, caller candidates, call-site counts, overhead admission, projection
arithmetic and the stopping decision. Lossless compressed evidence supports replay
without local executables. Optional local custody validates exact observed binary
bytes; reproducing execution requires the pinned dependencies and tested GPU.
Earlier sampler prototypes remain exploratory, with their source-custody gaps
explicit. The accepted final build has its executed source snapshots retained.
