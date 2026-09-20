# Doppler retained reranker on Doe

Component: WGSL compiler, ordinary native package execution, external application evidence.
Intent: preserved.
Boundary effects: frontend typing and shared IR lowering; no host shader substitution, Capsule changes, or accepted package replacement.

This is a diagnostic integration checkpoint, not a release qualification or speed comparison. The caller uses installed `doppler-gpu/host` to open the already accepted Node Capsule and rerank twice through one resident session. Reference evaluation and complete host teardown use internal modules from that same installed archive; this is not a claim that every host setup/cleanup operation is public API.

## Retained inputs and replay

- Doe source base: `d30589560ba85ec476172e10357d54024770f979`, plus the compiler diff retained in `compiler.patch`.
- Installed Doppler archive: `/var/tmp/doppler-startup-reuse-20260920/doppler-gpu-0.6.2.tgz`; its installation receipt is retained alongside it.
- Capsule and signed release inputs: `/var/tmp/doppler-release-20260907-restored-02/retained/node-capsule/`.
- Independent source reference: `/var/tmp/doppler-release-20260907-restored-02/retained/references/reranker-reference.json`.
- The probe uses current release evaluation time and the existing retained-local-use permission; it does not rewrite signatures, plan qualification, acceptance lists, checkpoints, precision, or tolerances. Observed checkpoints are written separately.

Run from `/var/tmp/doppler-startup-reuse-20260920/consumer`:

```bash
DOE_WEBGPU_LIB=/home/x/deco/doe/bench/out/doppler-search/20260920-admission/native-final/lib/libwebgpu_doe.so \
  timeout 240s node --input-type=module \
  < /home/x/deco/doe/bench/out/doppler-search/20260920-admission/reranker-probe.mjs
```

The script's paths intentionally identify this retained experiment. Copy the evidence directory before replaying: the diagnostic result and checkpoint files are replaced by a replay. Model shards remain in their existing artifact store; no additional model download is needed. Fetch is disabled during inference. This observes attempted fetches in this process, not OS-enforced network isolation or a full application privacy audit.

## First mismatch and repair

`node-reranker.log` captures the predecessor's rejection of `unpack4xU8` in the unchanged Q4 matmul shader. The frontend now checks the unsigned argument and vector result. IR construction lowers the builtin into unsigned vector shift and mask operations, evaluating the argument once. The existing emitters consume those operations. No model-specific recognizer or replacement output was added.

`reranker-final.log` and `reranker-result.json` retain actual inference receipts and the original reference evaluator's token, logit, probability, score, and exact-ranking decisions. The latter is a local diagnostic snapshot, not an input to release or claim gates. `identities.json` and `SHA256SUMS` bind the retained source patch, scripts, libraries, package receipt, reference, and logs.

## Acceptance evidence

- `host-tests.log`: Debug WGSL and aggregate suites, including structural gates. This precedes the added abstract-integer range check.
- `final-build-tests.log`: final ReleaseFast WGSL and aggregate suites plus isolated drop-in build; executed counts and skips are in the log.
- `shader-semantics-final.log`: physical AMD/Vulkan byte order, zero extension, Q4 nibble extraction, and single argument evaluation through the existing submission paths.
- `shader-semantics-head.log`: unchanged-source HEAD control, built from copied production sources with both changed compiler files restored from HEAD. It rejects unpacking and reproduces the separate render-output failure.
- `baseline-build.log`: isolated unchanged-source control build. `shader-semantics-baseline.log` instead uses the older preexisting library and is not a HEAD control.
- `reranker-first-result.json` and `reranker-fixed.log`: initial successful numerical run, with a shutdown warning. The probe destroyed the device before explicitly destroying the device-owned buffer pool.
- `reranker-final.log`: final library, explicit pool destruction before queue drain and device destruction, with cleanup outcomes retained. This is bounded teardown evidence, not a general leak or device-loss qualification.
- `admission-esm.log`: existing browser-qualified model descriptors reject Node as intended.

The full shader-semantics command still fails its texture-dimensions render case. It is not reported as passing; the exact same failure appears in the unchanged-source control. It did not prevent the independent reranker oracle from executing, but remains an ordinary-provider correctness obligation.

## Remaining work

Obtain or produce a genuinely Node-qualified embedding Capsule through Doppler's preparation and release process, then exercise the complete document-search application with both models retained. Do not bypass the browser Capsule's admission check. Application cancellation, recovery, installed Doe package qualification, independent reproduction, and physical Metal/D3D12 coverage remain unperformed. No audit scopes receive automatic verification credit from these supporting edits.
