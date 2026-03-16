import { performance } from "node:perf_hooks";
import {
  DEFAULT_ELEMENTS,
  DEFAULT_ITERATIONS,
  DEFAULT_ROUNDS,
  DEFAULT_WARMUP,
  DEFAULT_WORKERS,
  compareExact,
  createChunkPlans,
  createWorkload,
  parsePositiveInt,
  runCpuWorkers,
  summarizeSamples,
  timeAsync,
} from "./bench-workload-common.mjs";

const RESULT_PREFIX = "FAWN_BENCH_RESULT ";
const TINY_READBACK_ELEMENTS = 256;
const BENCH_GPU_BUFFER_USAGE = Object.freeze({
  MAP_READ: 0x0001,
  COPY_SRC: 0x0004,
  COPY_DST: 0x0008,
  STORAGE: 0x0080,
});
const BENCH_GPU_MAP_MODE = Object.freeze({
  READ: 0x0001,
});

const elements = parsePositiveInt(process.argv[2], DEFAULT_ELEMENTS);
const rounds = parsePositiveInt(process.argv[3], DEFAULT_ROUNDS);
const iterations = parsePositiveInt(process.argv[4], DEFAULT_ITERATIONS);
const warmupRuns = parsePositiveInt(process.argv[5], DEFAULT_WARMUP);
const workerCount = parsePositiveInt(process.argv[6], DEFAULT_WORKERS);
const candidateId =
  process.argv.find((value) => value.startsWith("--candidate="))?.split("=")[1] ?? null;
const scenarioId =
  process.argv.find((value) => value.startsWith("--scenario="))?.split("=")[1] ?? "default";

function summarizePhaseSamples(samples) {
  const summary = {
    encodeMs: summarizeSamples(samples.map((sample) => sample.encodeMs)).meanMs,
    submitWaitMs: summarizeSamples(samples.map((sample) => sample.submitWaitMs)).meanMs,
    readbackMs: summarizeSamples(samples.map((sample) => sample.readbackMs)).meanMs,
    validationMs: summarizeSamples(samples.map((sample) => sample.validationMs)).meanMs,
  };
  const nativeSamples = samples
    .map((sample) => sample.nativeDirectDiagnostics)
    .filter((value) => value && typeof value === "object");
  if (nativeSamples.length > 0) {
    const meanMetric = (key) =>
      summarizeSamples(nativeSamples.map((sample) => sample[key] ?? 0)).meanMs;
    summary.nativeDirectDiagnostics = {
      submitWaitAddonMs: meanMetric("submitWaitAddonMs"),
      queueFlushAddonMs: meanMetric("queueFlushAddonMs"),
      mapAsyncAddonMs: meanMetric("mapAsyncAddonMs"),
      mapQueueFlushAddonMs: meanMetric("mapQueueFlushAddonMs"),
      getMappedRangeAddonMs: meanMetric("getMappedRangeAddonMs"),
    };
  }
  return summary;
}

function summarizeVariance(samples) {
  const summary = summarizeSamples(samples);
  const variance =
    samples.reduce((total, sample) => total + (sample - summary.meanMs) ** 2, 0) / samples.length;
  const stddevMs = Math.sqrt(variance);
  return {
    stddevMs,
    cvPercent: summary.meanMs > 0 ? (stddevMs / summary.meanMs) * 100 : 0,
    rangeMs: summary.worstMs - summary.bestMs,
  };
}

function buildScenario(workload, id) {
  if (id === "default") {
    return {
      id,
      description:
        "64 dispatches, full-range 16 MiB readback, raw shared bind group, helper per-kernel binding sets",
      chunkSize: workload.chunkSize,
      readbackElements: workload.elements,
      rawBindGroupMode: "shared",
    };
  }
  if (id === "single-dispatch-full-readback") {
    return {
      id,
      description: "1 dispatch, full-range 16 MiB readback, raw shared bind group",
      chunkSize: workload.elements,
      readbackElements: workload.elements,
      rawBindGroupMode: "shared",
    };
  }
  if (id === "many-dispatches-tiny-readback") {
    return {
      id,
      description: `64 dispatches, ${TINY_READBACK_ELEMENTS * Float32Array.BYTES_PER_ELEMENT} B readback, raw shared bind group`,
      chunkSize: workload.chunkSize,
      readbackElements: TINY_READBACK_ELEMENTS,
      rawBindGroupMode: "shared",
    };
  }
  if (id === "raw-per-pipeline-bindgroups") {
    return {
      id,
      description:
        "64 dispatches, full-range 16 MiB readback, direct path creates and rebinds one bind group per pipeline",
      chunkSize: workload.chunkSize,
      readbackElements: workload.elements,
      rawBindGroupMode: "per-pipeline",
    };
  }
  throw new Error(`Unknown scenario: ${id}`);
}

function applyScenarioToWorkload(workload, scenario) {
  const readbackElements = Math.min(workload.elements, scenario.readbackElements);
  return {
    ...workload,
    chunkSize: scenario.chunkSize,
    chunkCount: Math.ceil(workload.elements / scenario.chunkSize),
    readbackElements,
    readbackBytes: readbackElements * Float32Array.BYTES_PER_ELEMENT,
    rawBindGroupMode: scenario.rawBindGroupMode,
    scenario,
  };
}

function readNativeDirectDiagnostics(queue, buffer) {
  const readMetric = (target, key) =>
    target && typeof target[key] === "number" ? target[key] : null;
  const diagnostics = {
    submitWaitAddonMs: readMetric(queue, "__doe_diag_submit_wait_ms"),
    queueFlushAddonMs: readMetric(queue, "__doe_diag_queue_flush_ms"),
    mapAsyncAddonMs: readMetric(buffer, "__doe_diag_map_async_ms"),
    mapQueueFlushAddonMs: readMetric(buffer, "__doe_diag_map_queue_flush_ms"),
    getMappedRangeAddonMs: readMetric(buffer, "__doe_diag_get_mapped_range_ms"),
  };
  if (Object.values(diagnostics).every((value) => value === null)) {
    return null;
  }
  return diagnostics;
}

function prepareRawState(device, gpuGlobals, workload) {
  const chunkPlans = createChunkPlans(workload);
  const src = device.createBuffer({
    size: workload.outputBytes,
    usage: gpuGlobals.GPUBufferUsage.STORAGE | gpuGlobals.GPUBufferUsage.COPY_DST,
  });
  device.queue.writeBuffer(src, 0, workload.input);

  const dst = device.createBuffer({
    size: workload.outputBytes,
    usage: gpuGlobals.GPUBufferUsage.STORAGE | gpuGlobals.GPUBufferUsage.COPY_SRC,
  });

  const readback = device.createBuffer({
    size: workload.readbackBytes,
    usage: gpuGlobals.GPUBufferUsage.COPY_DST | gpuGlobals.GPUBufferUsage.MAP_READ,
  });

  const bindGroupLayout = device.createBindGroupLayout({
    entries: [
      {
        binding: 0,
        visibility: gpuGlobals.GPUShaderStage.COMPUTE,
        buffer: { type: "read-only-storage" },
      },
      {
        binding: 1,
        visibility: gpuGlobals.GPUShaderStage.COMPUTE,
        buffer: { type: "storage" },
      },
    ],
  });
  const pipelineLayout = device.createPipelineLayout({
    bindGroupLayouts: [bindGroupLayout],
  });
  const bindGroupEntries = [
    { binding: 0, resource: { buffer: src } },
    { binding: 1, resource: { buffer: dst } },
  ];
  const bindGroup = device.createBindGroup({
    layout: bindGroupLayout,
    entries: bindGroupEntries,
  });
  const pipelines = chunkPlans.map((plan) =>
    device.createComputePipeline({
      layout: pipelineLayout,
      compute: {
        module: device.createShaderModule({ code: plan.code }),
        entryPoint: "main",
      },
    })
  );
  const bindGroups =
    workload.rawBindGroupMode === "per-pipeline"
      ? chunkPlans.map(() =>
          device.createBindGroup({
            layout: bindGroupLayout,
            entries: bindGroupEntries,
          })
        )
      : null;

  return {
    chunkPlans,
    pipelines,
    bindGroup,
    bindGroups,
    src,
    dst,
    readback,
  };
}

async function runRawPreparedRound(device, gpuGlobals, workload, state) {
  const encodeStartedAt = performance.now();
  const encoder = device.createCommandEncoder();
  const pass = encoder.beginComputePass();
  if (!state.bindGroups) {
    pass.setBindGroup(0, state.bindGroup);
  }

  for (let index = 0; index < state.pipelines.length; index += 1) {
    if (state.bindGroups) {
      pass.setBindGroup(0, state.bindGroups[index]);
    }
    pass.setPipeline(state.pipelines[index]);
    pass.dispatchWorkgroups(state.chunkPlans[index].workgroups);
  }

  pass.end();
  encoder.copyBufferToBuffer(state.dst, 0, state.readback, 0, workload.readbackBytes);
  const commandBuffer = encoder.finish();
  const encodeMs = performance.now() - encodeStartedAt;

  const submitWaitStartedAt = performance.now();
  device.queue.submit([commandBuffer]);
  await device.queue.onSubmittedWorkDone?.();
  const submitWaitMs = performance.now() - submitWaitStartedAt;

  const readbackStartedAt = performance.now();
  let output;
  if (typeof state.readback._mapReadCopyUnmap === 'function') {
    const buf = state.readback._mapReadCopyUnmap(gpuGlobals.GPUMapMode.READ, 0, workload.readbackBytes);
    output = new Float32Array(buf);
  } else {
    await state.readback.mapAsync(gpuGlobals.GPUMapMode.READ);
    output = new Float32Array(
      state.readback.getMappedRange(0, workload.readbackBytes),
    ).slice();
    state.readback.unmap();
  }
  const readbackMs = performance.now() - readbackStartedAt;

  return {
    output,
    ms: encodeMs + submitWaitMs + readbackMs,
    phases: {
      encodeMs,
      submitWaitMs,
      readbackMs,
      nativeDirectDiagnostics: readNativeDirectDiagnostics(device.queue, state.readback),
    },
  };
}

function prepareDoeState(gpu, workload) {
  const src = gpu.device.createBuffer({
    size: workload.outputBytes,
    usage: BENCH_GPU_BUFFER_USAGE.STORAGE | BENCH_GPU_BUFFER_USAGE.COPY_DST,
  });
  gpu.device.queue.writeBuffer(src, 0, workload.input);
  const dst = gpu.device.createBuffer({
    size: workload.outputBytes,
    usage: BENCH_GPU_BUFFER_USAGE.STORAGE | BENCH_GPU_BUFFER_USAGE.COPY_SRC,
  });
  const readback = gpu.device.createBuffer({
    size: workload.readbackBytes,
    usage: BENCH_GPU_BUFFER_USAGE.COPY_DST | BENCH_GPU_BUFFER_USAGE.MAP_READ,
  });
  const srcBinding = { buffer: src, access: "storageRead" };
  const dstBinding = { buffer: dst, access: "storageReadWrite" };
  const chunkPlans = createChunkPlans(workload);
  const kernels = chunkPlans.map((plan) =>
    gpu.kernel.create({
      code: plan.code,
      bindings: [srcBinding, dstBinding],
    })
  );
  const bindingSets = kernels.map((kernel) => kernel.bindings.create([srcBinding, dstBinding]));

  return {
    chunkPlans,
    src,
    kernels,
    bindingSets,
    dst,
    readback,
  };
}

async function runDoePreparedRound(gpu, state) {
  const encodeStartedAt = performance.now();
  const encoder = gpu.device.createCommandEncoder();
  const pass = encoder.beginComputePass();
  for (let index = 0; index < state.kernels.length; index += 1) {
    const kernel = state.kernels[index];
    const bindingSet = state.bindingSets[index];
    pass.setPipeline(kernel.pipeline);
    if (bindingSet.bindGroup) {
      pass.setBindGroup(0, bindingSet.bindGroup);
    }
    pass.dispatchWorkgroups(state.chunkPlans[index].workgroups);
  }
  pass.end();
  encoder.copyBufferToBuffer(state.dst, 0, state.readback, 0, state.readback.size);
  const commandBuffer = encoder.finish();
  const encodeMs = performance.now() - encodeStartedAt;

  const submitWaitStartedAt = performance.now();
  gpu.device.queue.submit([commandBuffer]);
  await gpu.device.queue.onSubmittedWorkDone?.();
  const submitWaitMs = performance.now() - submitWaitStartedAt;

  const readbackStartedAt = performance.now();
  let output;
  if (typeof state.readback._mapReadCopyUnmap === 'function') {
    const buf = state.readback._mapReadCopyUnmap(BENCH_GPU_MAP_MODE.READ, 0, state.readback.size);
    output = new Float32Array(buf);
  } else {
    await state.readback.mapAsync(BENCH_GPU_MAP_MODE.READ);
    output = new Float32Array(
      state.readback.getMappedRange(0, state.readback.size),
    ).slice();
    state.readback.unmap();
  }
  const readbackMs = performance.now() - readbackStartedAt;

  return {
    output,
    ms: encodeMs + submitWaitMs + readbackMs,
    phases: {
      encodeMs,
      submitWaitMs,
      readbackMs,
      nativeDirectDiagnostics: readNativeDirectDiagnostics(gpu.device.queue, state.readback),
    },
  };
}

async function measureCpu(workload) {
  let referenceOutput = null;

  for (let index = 0; index < warmupRuns; index += 1) {
    const result = await runCpuWorkers(workload.input, workload.rounds, workerCount);
    referenceOutput = result.output;
  }

  const samples = [];
  for (let index = 0; index < iterations; index += 1) {
    const result = await runCpuWorkers(workload.input, workload.rounds, workerCount);
    referenceOutput = result.output;
    samples.push(result.ms);
  }

  return {
    output: referenceOutput,
    timings: summarizeSamples(samples),
  };
}

async function measureCandidate({ label, load, run }, expectedOutput) {
  let referenceOutput = null;
  const phaseSamples = [];

  for (let index = 0; index < warmupRuns; index += 1) {
    const result = await run();
    compareExact(expectedOutput.subarray(0, result.output.length), result.output);
    referenceOutput = result.output;
  }

  const samples = [];
  for (let index = 0; index < iterations; index += 1) {
    const result = await run();
    const validationStartedAt = performance.now();
    compareExact(expectedOutput.subarray(0, result.output.length), result.output);
    const validationMs = performance.now() - validationStartedAt;
    referenceOutput = result.output;
    samples.push(result.ms);
    phaseSamples.push({
      ...result.phases,
      validationMs,
    });
  }

  return {
    label,
    loadMs: load,
    timings: summarizeSamples(samples),
    variance: summarizeVariance(samples),
    phaseTimings: summarizePhaseSamples(phaseSamples),
    output: referenceOutput,
  };
}

async function setupDawnRaw(workload) {
  const imports = await timeAsync(() => import("webgpu"));
  const { create, globals } = imports.value;
  const navigatorGpu = create([]);
  const adapter = await timeAsync(() => navigatorGpu.requestAdapter());
  const device = await timeAsync(() => adapter.value.requestDevice());
  const state = await timeAsync(() =>
    Promise.resolve(prepareRawState(device.value, globals, workload))
  );

  return {
    label: "dawn direct",
    load: imports.ms + adapter.ms + device.ms + state.ms,
    adapterInfo: adapter.value.info,
    async run() {
      return runRawPreparedRound(device.value, globals, workload, state.value);
    },
  };
}

async function setupDawnDoe(workload) {
  const imports = await timeAsync(async () => {
    const [{ create }, { default: doe }] = await Promise.all([
      import("webgpu"),
      import("../../../packages/webgpu-doe/src/index.js"),
    ]);
    return { create, doe };
  });
  const navigatorGpu = imports.value.create([]);
  const adapter = await timeAsync(() => navigatorGpu.requestAdapter());
  const device = await timeAsync(() => adapter.value.requestDevice());
  const gpu = imports.value.doe.bind(device.value);
  const state = await timeAsync(() => Promise.resolve(prepareDoeState(gpu, workload)));

  return {
    label: "dawn + doe helpers",
    load: imports.ms + adapter.ms + device.ms + state.ms,
    adapterInfo: adapter.value.info,
    async run() {
      return runDoePreparedRound(gpu, state.value);
    },
  };
}

async function setupSimulatteRaw(workload) {
  const imports = await timeAsync(() => import("../../../packages/webgpu/src/native-direct.js"));
  const { globals, providerInfo, requestDevice } = imports.value;
  const device = await timeAsync(() => requestDevice());
  const state = await timeAsync(() =>
    Promise.resolve(prepareRawState(device.value, globals, workload))
  );

  return {
    label: "simulatte direct",
    load: imports.ms + device.ms + state.ms,
    provider: providerInfo(),
    async run() {
      return runRawPreparedRound(device.value, globals, workload, state.value);
    },
  };
}

async function setupSimulatteDoe(workload) {
  const imports = await timeAsync(async () => {
    const [{ requestDevice, providerInfo }, { default: doe }] = await Promise.all([
      import("../../../packages/webgpu/src/native-direct.js"),
      import("../../../packages/webgpu-doe/src/index.js"),
    ]);
    return { requestDevice, providerInfo, doe };
  });
  const device = await timeAsync(() => imports.value.requestDevice());
  const gpu = { ms: device.ms, value: imports.value.doe.bind(device.value) };
  const state = await timeAsync(() => Promise.resolve(prepareDoeState(gpu.value, workload)));

  return {
    label: "simulatte + doe helpers",
    load: imports.ms + gpu.ms + state.ms,
    provider: imports.value.providerInfo(),
    async run() {
      return runDoePreparedRound(gpu.value, state.value);
    },
  };
}

async function main() {
  if (!candidateId) {
    throw new Error("Expected --candidate=<id>");
  }

  const baseWorkload = createWorkload(elements, rounds);
  const scenario = buildScenario(baseWorkload, scenarioId);
  const workload = applyScenarioToWorkload(baseWorkload, scenario);
  const cpuResult = await measureCpu(workload);

  const setupMap = {
    "dawn-direct": () => setupDawnRaw(workload),
    "dawn-doe": () => setupDawnDoe(workload),
    "simulatte-direct": () => setupSimulatteRaw(workload),
    "simulatte-doe": () => setupSimulatteDoe(workload),
  };

  const setupFactory = setupMap[candidateId];
  if (!setupFactory) {
    throw new Error(`Unknown candidate: ${candidateId}`);
  }

  const setup = await setupFactory();
  const result = await measureCandidate(setup, cpuResult.output);

  process.stdout.write(
    `${RESULT_PREFIX}${JSON.stringify({
      label: result.label,
      loadMs: result.loadMs,
      timings: result.timings,
      variance: result.variance,
      phaseTimings: result.phaseTimings,
      adapterInfo: setup.adapterInfo ?? null,
      provider: setup.provider ?? null,
      scenario,
    })}\n`
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
