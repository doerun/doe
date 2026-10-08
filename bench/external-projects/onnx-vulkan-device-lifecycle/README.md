# ONNX Vulkan device lifecycle qualification

This successor correctness campaign exercises descriptor device loss,
DeviceDestroy, external versus internal device references and stable issued loss
futures through the pinned consumer's Dawn procedure-table ABI. It retains
preceding Doe failures, source-built Dawn controls, new native controls, unchanged
ONNX application recovery and native/oracle negative controls. It makes no timing
or adoption claim and preserves previous campaign decisions.

[Contract and migration](../../../docs/native-device-lifecycle-contract.md) and
[retained report](../../../reports/benchmarks/amd-vulkan/20261008-onnx-vulkan-device-lifecycle/README.md)
own the tested boundary and replay. Spontaneous callbacks obey the pinned header's
reentry restrictions. Reentrant release is exercised during WaitAny delivery.

## Execution

Build the native drop-in library with the pinned Zig toolchain. Supply immutable
native, preceding native, source-built Dawn, bridge and generated-header paths:

```bash
python3 bench/external-projects/onnx-vulkan-device-lifecycle/run.py --help
python3 bench/external-projects/onnx-vulkan-device-lifecycle/qualify.py --help
```

`run.py` compiles the same C++ fixture and runs each selected implementation in
separate sequential processes. The fixture selects Vulkan and explicitly enables
TimedWaitAny and MultipleDevicesPerAdapter; implementations keep their own
preparation and synchronization. Destruction after submission is tested alongside
an independent exact copy/readback oracle, completion settlement and aborted
post-loss mapping. Async pipeline requests delivered after loss return inert error
objects; native submission validation independently rejects them.

`qualify.py` uses the unchanged prepared upstream SqueezeNet executable, source
provider and frozen application oracle from the original ONNX Vulkan preparation.
CPU fallback is disabled and actual operator placement is profiled. The existing
callback runner and native async C fixture must qualify the same selected bytes.
Never rebuild those bytes while a qualification process is running. Producers
retain unfavorable outputs and input identities before and after child processes.

`bundle.py` seals a new report and local binary custody archive. It retains rejected
prior attempts as diagnostics, independently of final admission. `verify.py`
replays reasons, callback phase, future identity, raw output, recovery, provider
placement, native selection and oracle sensitivity. Hash resealing cannot change
those semantic requirements. Local binary archive verification is optional for
portable report replay and required for local custody qualification:

```bash
python3 bench/external-projects/onnx-vulkan-device-lifecycle/verify.py \
  --report reports/benchmarks/amd-vulkan/20261008-onnx-vulkan-device-lifecycle \
  --check-current --with-custody
```

Failed-creation callbacks are physically qualified in ProcessEvents and spontaneous
modes. Failed creation exposes no device loss future through the public API, so
WaitAnyOnly failed-creation delivery and instance abandonment remain outside this
fixture. Real driver loss, arbitrary concurrent API use and other backends remain
separate obligations.
