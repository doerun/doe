# Cerebras 31B hardware ask email draft

Subject: Gemma 4 31B dense smoke validation request on Cerebras hardware

Hi <name>,

We have a software evidence bundle for Doe's Gemma 4 on Cerebras lane and would
like to validate the first 31B dense hardware rung on WSE/WSC.

The primary ask is intentionally small:

```bash
cs_python bench/runners/csl-runners/gemma_4_31b_layer_block_smoke.py \
  --num-layers 1 \
  --size 1024 \
  --compile-out bench/out/hardware-run/compile \
  --trace-out  bench/out/hardware-run/trace.json \
  --cmaddr <operator-supplied>
```

This is a Gemma 4 31B dense layer-block smoke run. It is not a full 31B
manifest-shape claim and not a performance claim. The goal is to prove the
31B runner, CSL source, SDK environment, compile path, hardware execution, and
receipt shape with a bounded tensor contract before we climb to the 61-layer
smoke chain and later manifest-shape streaming.

There are two acceptable paths:

1. We get temporary endpoint access and run the command with `--cmaddr`.
2. A Cerebras engineer runs the attached bundle internally and returns the
   receipt JSON, with endpoint fields redacted as needed.

Please return:

- `hardware.endpoint`, `hardware.jobId`, `hardware.sdkVersion`,
  `hardware.fabricId`, and `hardware.deviceArch`, redacted where required.
- `executedRun.status`.
- `executedRun.output.sha256`.
- `executedRun.numericalParity.maxAbsErr` and per-layer comparison fields from
  the runner trace.
- Any compile/runtime failure taxonomy if the run does not complete.

Bundle pointer:

- `<fill with docs/cerebras-evidence-bundle-pointer.md after clean rebuild>`

Current local gate verdict:

- `<fill with clean verdict, or explicitly mark internal-only if still failed>`

Notes:

- E2B evidence remains in the bundle as smaller control evidence and regression
  isolation, but it is not a prerequisite for this 31B L1 hardware ask.
- We will not publish endpoint identity, fabric identity, queue details, timing,
  or performance comparisons without written approval.
- If the 31B L1 smoke run succeeds, the natural follow-up is the same runner
  with `--num-layers 61`, still labeled smoke-shape evidence.

Thanks,
<sender>
