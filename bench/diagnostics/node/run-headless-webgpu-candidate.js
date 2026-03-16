import { performance } from "node:perf_hooks";
import {
  DEFAULT_ITERATIONS,
  DEFAULT_MATMUL_SIZE,
  DEFAULT_WARMUP,
  DEFAULT_WORKERS,
  compareApprox,
  createMatmulChunkPlans,
  createMatmulWorkload,
  parsePositiveInt,
  runCpuMatmulWorkers,
  summarizeSamples,
  timeAsync,
} from "./bench-workload-common.mjs";

const RESULT_PREFIX = "FAWN_BENCH_RESULT ";
const BENCH_GPU_BUFFER_USAGE = Object.freeze({
  MAP_READ: 0x0001,
  COPY_SRC: 0x0004,
  COPY_DST: 0x0008,
  STORAGE: 0x0080,
});
const BENCH_GPU_MAP_MODE = Object.freeze({
  READ: 0x0001,
});

const size = parsePositiveInt(process.argv[2], DEFAULT_MATMUL_SIZE);
const iterations = parsePositiveInt(process.argv[3], Math.min(DEFAULT_ITERATIONS, 2));
const warmupRuns = parsePositiveInt(process.argv[4], DEFAULT_WARMUP);
const workerCount = parsePositiveInt(process.argv[5], DEFAULT_WORKERS);
const candidateId =
  process.argv.find((value) => value.startsWith("--candidate="))?.split("=")[1] ?? null;

function summarizePhaseSamples(samples) {
  return {
    encodeMs: summarizeSamples(samples.map((sample) => sample.encodeMs)).meanMs,
    submitWaitMs: summarizeSamples(samples.map((sample) => sample.submitWaitMs)).meanMs,
    readbackMs: summarizeSamples(samples.map((sample) => sample.readbackMs)).meanMs,
  };
}

function prepareRawState(device, gpuGlobals, workload) {
  const chunkPlans = createMatmulChunkPlans(workload);
  const left = device.createBuffer({
    size: workload.outputBytes,
    usage: gpuGlobals.GPUBufferUsage.STORAGE | gpuGlobals.GPUBufferUsage.COPY_DST,
  });
  device.queue.writeBuffer(left, 0, workload.left);

  const right = device.createBuffer({
    size: workload.outputBytes,
    usage: gpuGlobals.GPUBufferUsage.STORAGE | gpuGlobals.GPUBufferUsage.COPY_DST,
  });
  device.queue.writeBuffer(right, 0, workload.right);

  const output = device.createBuffer({
    size: workload.outputBytes,
    usage: gpuGlobals.GPUBufferUsage.STORAGE | gpuGlobals.GPUBufferUsage.COPY_SRC,
  });

  const readback = device.createBuffer({
    size: workload.outputBytes,
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
        buffer: { type: "read-only-storage" },
      },
      {
        binding: 2,
        visibility: gpuGlobals.GPUShaderStage.COMPUTE,
        buffer: { type: "storage" },
      },
    ],
  });
  const pipelineLayout = device.createPipelineLayout({
    bindGroupLayouts: [bindGroupLayout],
  });
  const bindGroup = device.createBindGroup({
    layout: bindGroupLayout,
    entries: [
      { binding: 0, resource: { buffer: left } },
      { binding: 1, resource: { buffer: right } },
      { binding: 2, resource: { buffer: output } },
    ],
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

  return {
    chunkPlans,
    output,
    readback,
    bindGroup,
    pipelines,
  };
}

async function runRawPreparedRound(device, gpuGlobals, workload, state) {
  const encodeStartedAt = performance.now();
  const encoder = device.createCommandEncoder();
  const pass = encoder.beginComputePass();
  pass.setBindGroup(0, state.bindGroup);
  for (let index = 0; index < state.pipelines.length; index += 1) {
    const plan = state.chunkPlans[index];
    pass.setPipeline(state.pipelines[index]);
    pass.dispatchWorkgroups(plan.workgroupsX, plan.workgroupsY, 1);
  }
  pass.end();

  encoder.copyBufferToBuffer(state.output, 0, state.readback, 0, workload.outputBytes);
  const commandBuffer = encoder.finish();
  const encodeMs = performance.now() - encodeStartedAt;

  const submitWaitStartedAt = performance.now();
  device.queue.submit([commandBuffer]);
  await device.queue.onSubmittedWorkDone?.();
  const submitWaitMs = performance.now() - submitWaitStartedAt;

  const readbackStartedAt = performance.now();
  let output;
  if (typeof state.readback._mapReadCopyUnmap === 'function') {
    const buf = state.readback._mapReadCopyUnmap(gpuGlobals.GPUMapMode.READ, 0, workload.outputBytes);
    output = new Float32Array(buf);
  } else {
    await state.readback.mapAsync(gpuGlobals.GPUMapMode.READ);
    output = new Float32Array(
      state.readback.getMappedRange(0, workload.outputBytes),
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
    },
  };
}

function prepareDoeState(gpu, workload) {
  const chunkPlans = createMatmulChunkPlans(workload);
  const left = gpu.device.createBuffer({
    size: workload.outputBytes,
    usage: BENCH_GPU_BUFFER_USAGE.STORAGE | BENCH_GPU_BUFFER_USAGE.COPY_DST,
  });
  gpu.device.queue.writeBuffer(left, 0, workload.left);
  const right = gpu.device.createBuffer({
    size: workload.outputBytes,
    usage: BENCH_GPU_BUFFER_USAGE.STORAGE | BENCH_GPU_BUFFER_USAGE.COPY_DST,
  });
  gpu.device.queue.writeBuffer(right, 0, workload.right);
  const output = gpu.device.createBuffer({
    size: workload.outputBytes,
    usage: BENCH_GPU_BUFFER_USAGE.STORAGE | BENCH_GPU_BUFFER_USAGE.COPY_SRC,
  });
  const readback = gpu.device.createBuffer({
    size: workload.outputBytes,
    usage: BENCH_GPU_BUFFER_USAGE.COPY_DST | BENCH_GPU_BUFFER_USAGE.MAP_READ,
  });
  const leftBinding = { buffer: left, access: "storageRead" };
  const rightBinding = { buffer: right, access: "storageRead" };
  const outputBinding = { buffer: output, access: "storageReadWrite" };
  const kernels = chunkPlans.map((plan) =>
    gpu.kernel.create({
      code: plan.code,
      bindings: [leftBinding, rightBinding, outputBinding],
    })
  );
  const bindingSets = kernels.map((kernel) =>
    kernel.bindings.create([leftBinding, rightBinding, outputBinding])
  );

  return {
    chunkPlans,
    output,
    readback,
    kernels,
    bindingSets,
  };
}

async function runDoePreparedRound(gpu, state) {
  const encodeStartedAt = performance.now();
  const encoder = gpu.device.createCommandEncoder();
  const pass = encoder.beginComputePass();
  for (let index = 0; index < state.kernels.length; index += 1) {
    const plan = state.chunkPlans[index];
    const kernel = state.kernels[index];
    const bindingSet = state.bindingSets[index];
    pass.setPipeline(kernel.pipeline);
    if (bindingSet.bindGroup) {
      pass.setBindGroup(0, bindingSet.bindGroup);
    }
    pass.dispatchWorkgroups(plan.workgroupsX, plan.workgroupsY, 1);
  }
  pass.end();
  encoder.copyBufferToBuffer(state.output, 0, state.readback, 0, state.readback.size);
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
    },
  };
}

async function measureCpu(workload) {
  let referenceOutput = null;

  for (let index = 0; index < warmupRuns; index += 1) {
    const result = await runCpuMatmulWorkers(
      workload.left,
      workload.right,
      workload.size,
      workerCount
    );
    referenceOutput = result.output;
  }

  const samples = [];
  for (let index = 0; index < iterations; index += 1) {
    const result = await runCpuMatmulWorkers(
      workload.left,
      workload.right,
      workload.size,
      workerCount
    );
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
    compareApprox(expectedOutput, result.output);
    referenceOutput = result.output;
  }

  const samples = [];
  for (let index = 0; index < iterations; index += 1) {
    const result = await run();
    compareApprox(expectedOutput, result.output);
    referenceOutput = result.output;
    samples.push(result.ms);
    phaseSamples.push(result.phases);
  }

  return {
    label,
    loadMs: load,
    timings: summarizeSamples(samples),
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

  const workload = createMatmulWorkload(size);
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
      phaseTimings: result.phaseTimings,
      adapterInfo: setup.adapterInfo ?? null,
      provider: setup.provider ?? null,
    })}\n`
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
