# Longer ordinary execution sampling

This diagnostic continues the mixed application result in
`../20260907-binding-storage/README.md`. `policy.json` changes only warmup and
sample counts from the retained original application policy. Correctness,
shaders, dimensions, completion, readback, activity rejection, and previous/final
qualified packages remain unchanged. Both variants receive identical settings.
The original matrix is retained and is not reclassified or overwritten.

`compare-previous.py` uses the existing admitted child runner, alternates process
order, verifies exact package files before and after execution, and checks the
same outputs and work receipts. Shared percentiles include median and slow tails.
`alternating/process-costs.tsv` retains startup, preparation, cold execution,
cleanup, requested allocations, and process RSS separately. Warmup costs are
outside timed samples; this experiment does not erase the recorded cold costs.

The question is whether the spread in the original small application sample
persists during longer execution. No result is a release claim or a basis for
changing the correctness or fairness gates. This is a diagnostic job record,
not a new benchmark interface or policy default.

The completed `alternating/comparison.tsv` still has mixed results. Heat and
simulation wall latency improve modestly under this sampling policy, while
image-processing tails regress. These observations do not establish a general
application advantage. `run.log` records accepted numerical outputs and matching
execution receipts for every alternating process pair.

`native-memory-syscalls.txt` is a diagnostic strace summary of the native C probe
retained in `../20260907-binding-storage/native-record-cost-validated/`. The probe
loads that directory's candidate library and checks GPU output outside timing.
`profiled-native-record-cost.tsv` is profiled data, not an application comparison.
The trace includes driver and setup activity; its syscall durations must not be
interpreted as unprofiled per-invocation CPU contributions. Repeated command-array
mapping and growth in the source motivate the bounded storage experiment indexed
at `../20260907-command-storage/README.md`.
