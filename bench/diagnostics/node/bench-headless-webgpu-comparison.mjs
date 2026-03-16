import { performance } from "node:perf_hooks";
import { spawnSync } from "node:child_process";
import {
  DEFAULT_ITERATIONS,
  DEFAULT_MATMUL_SIZE,
  DEFAULT_WARMUP,
  DEFAULT_WORKERS,
  MATMUL_COLUMNS_PER_INVOCATION,
  MATMUL_WORKGROUP_SIZE_X,
  MATMUL_WORKGROUP_SIZE_Y,
  compareApprox,
  createMatmulChunkPlans,
  createMatmulWorkload,
  formatMs,
  formatSpeedup,
  parsePositiveInt,
  runCpuMatmulWorkers,
  summarizeSamples,
  timeAsync,
} from "./bench-workload-common.mjs";

const CPU_TARGET_MIN_MS = 2_000;
const CPU_TARGET_MAX_MS = 5_000;
const CPU_TARGET_MEAN_MS = (CPU_TARGET_MIN_MS + CPU_TARGET_MAX_MS) / 2;
const MIN_AUTO_SIZE = 512;
const MAX_AUTO_SIZE = 2_048;
const AUTO_SIZE_STEP = 64;

const DIRECT_RAW_WEBGPU_CONTRACT = Object.freeze({
  shader: "shared generated WGSL",
  chunk_plan: "shared createMatmulChunkPlans(workload)",
  encode_shape: "one command encoder, one compute pass, one copyBufferToBuffer",
  submit_shape: "one queue submit, one queue completion wait",
  readback_shape: "one MAP_READ buffer map and full-range readback",
});

const sizeArg = process.argv[2] ?? "auto";
const iterations = parsePositiveInt(process.argv[3], Math.min(DEFAULT_ITERATIONS, 2));
const warmupRuns = parsePositiveInt(process.argv[4], DEFAULT_WARMUP);
const workerCount = parsePositiveInt(process.argv[5], DEFAULT_WORKERS);
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

function padCell(value, width, rightAlign = true) {
  const text = `${value}`;
  return rightAlign ? text.padStart(width) : text.padEnd(width);
}

function createTable(rows) {
  const widths = {
    label: Math.max("Runner".length, ...rows.map((row) => row.label.length)),
    load: Math.max("Load".length, ...rows.map((row) => row.load.length)),
    mean: Math.max("Mean".length, ...rows.map((row) => row.mean.length)),
    best: Math.max("Best".length, ...rows.map((row) => row.best.length)),
    worst: Math.max("Worst".length, ...rows.map((row) => row.worst.length)),
    speedup: Math.max("vs CPU".length, ...rows.map((row) => row.speedup.length)),
  };

  const divider = [
    "-".repeat(widths.label),
    "-".repeat(widths.load),
    "-".repeat(widths.mean),
    "-".repeat(widths.best),
    "-".repeat(widths.worst),
    "-".repeat(widths.speedup),
  ].join("  ");

  const lines = [
    [
      padCell("Runner", widths.label, false),
      padCell("Load", widths.load),
      padCell("Mean", widths.mean),
      padCell("Best", widths.best),
      padCell("Worst", widths.worst),
      padCell("vs CPU", widths.speedup),
    ].join("  "),
    divider,
  ];

  for (const row of rows) {
    lines.push(
      [
        padCell(row.label, widths.label, false),
        padCell(row.load, widths.load),
        padCell(row.mean, widths.mean),
        padCell(row.best, widths.best),
        padCell(row.worst, widths.worst),
        padCell(row.speedup, widths.speedup),
      ].join("  ")
    );
  }

  return lines.join("\n");
}

function createPhaseTable(rows) {
  const widths = {
    label: Math.max("Runner".length, ...rows.map((row) => row.label.length)),
    encode: Math.max("Encode".length, ...rows.map((row) => row.encode.length)),
    submit_wait: Math.max("Submit+wait".length, ...rows.map((row) => row.submit_wait.length)),
    readback: Math.max("Readback".length, ...rows.map((row) => row.readback.length)),
    total: Math.max("Total".length, ...rows.map((row) => row.total.length)),
  };

  const divider = [
    "-".repeat(widths.label),
    "-".repeat(widths.encode),
    "-".repeat(widths.submit_wait),
    "-".repeat(widths.readback),
    "-".repeat(widths.total),
  ].join("  ");

  const lines = [
    [
      padCell("Runner", widths.label, false),
      padCell("Encode", widths.encode),
      padCell("Submit+wait", widths.submit_wait),
      padCell("Readback", widths.readback),
      padCell("Total", widths.total),
    ].join("  "),
    divider,
  ];

  for (const row of rows) {
    lines.push(
      [
        padCell(row.label, widths.label, false),
        padCell(row.encode, widths.encode),
        padCell(row.submit_wait, widths.submit_wait),
        padCell(row.readback, widths.readback),
        padCell(row.total, widths.total),
      ].join("  ")
    );
  }

  return lines.join("\n");
}

function summarizePhaseSamples(samples) {
  return {
    encodeMs: summarizeSamples(samples.map((sample) => sample.encodeMs)).meanMs,
    submitWaitMs: summarizeSamples(samples.map((sample) => sample.submitWaitMs)).meanMs,
    readbackMs: summarizeSamples(samples.map((sample) => sample.readbackMs)).meanMs,
  };
}

async function setupRawCandidate({
  label,
  load,
  device,
  gpuGlobals,
  workload,
  adapterInfo = undefined,
  provider = undefined,
}) {
  const state = await timeAsync(() =>
    Promise.resolve(prepareRawState(device, gpuGlobals, workload))
  );
  const prime = await timeAsync(() =>
    primePreparedState(() => runRawPreparedRound(device, gpuGlobals, workload, state.value))
  );

  return {
    label,
    load: load + state.ms + prime.ms,
    adapterInfo,
    provider,
    directContract: DIRECT_RAW_WEBGPU_CONTRACT,
    async run() {
      return runRawPreparedRound(device, gpuGlobals, workload, state.value);
    },
    async destroy() {
      state.value.left.destroy?.();
      state.value.right.destroy?.();
      state.value.output.destroy?.();
      state.value.readback.destroy?.();
      device.destroy?.();
    },
  };
}

function clampToAutoWindow(size) {
  const clamped = Math.min(MAX_AUTO_SIZE, Math.max(MIN_AUTO_SIZE, size));
  return Math.ceil(clamped / AUTO_SIZE_STEP) * AUTO_SIZE_STEP;
}

async function probeCpuMs(size) {
  const workload = createMatmulWorkload(size);
  const result = await runCpuMatmulWorkers(
    workload.left,
    workload.right,
    workload.size,
    workerCount
  );
  return {
    size,
    ms: result.ms,
  };
}

function predictSizeFromProbe(size, ms) {
  const safeMs = Math.max(ms, 1);
  const scaled = size * Math.cbrt(CPU_TARGET_MEAN_MS / safeMs);
  return clampToAutoWindow(Math.round(scaled));
}

async function resolveMatrixSize() {
  if (sizeArg !== "auto") {
    return {
      size: parsePositiveInt(sizeArg, DEFAULT_MATMUL_SIZE),
      probes: [],
      selectedBy: "explicit",
    };
  }

  const probes = [];
  let probe = await probeCpuMs(MIN_AUTO_SIZE);
  probes.push(probe);

  for (let attempt = 0; attempt < 2; attempt += 1) {
    if (probe.ms >= CPU_TARGET_MIN_MS && probe.ms <= CPU_TARGET_MAX_MS) {
      return {
        size: probe.size,
        probes,
        selectedBy: "auto",
      };
    }

    const nextSize = predictSizeFromProbe(probe.size, probe.ms);
    if (nextSize === probe.size || probes.some((entry) => entry.size === nextSize)) {
      break;
    }
    probe = await probeCpuMs(nextSize);
    probes.push(probe);
  }

  const bestProbe = probes.reduce((best, entry) => {
    const bestDelta = Math.abs(best.ms - CPU_TARGET_MEAN_MS);
    const entryDelta = Math.abs(entry.ms - CPU_TARGET_MEAN_MS);
    return entryDelta < bestDelta ? entry : best;
  });

  return {
    size: bestProbe.size,
    probes,
    selectedBy: "auto",
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
    left,
    right,
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

async function primePreparedState(run) {
  await run();
}

async function measureCandidate({ label, load, run, destroy }, expectedOutput) {
  let referenceOutput = null;
  const phaseSamples = [];

  try {
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
      if (result.phases) {
        phaseSamples.push(result.phases);
      }
    }

    return {
      label,
      loadMs: load,
      timings: summarizeSamples(samples),
      phaseTimings: phaseSamples.length > 0 ? summarizePhaseSamples(phaseSamples) : null,
      output: referenceOutput,
    };
  } finally {
    await destroy?.();
  }
}

async function setupCpu(workload) {
  return {
    label: `cpu/${workerCount} workers`,
    load: 0,
    async run() {
      return runCpuMatmulWorkers(workload.left, workload.right, workload.size, workerCount);
    },
  };
}

async function measureCpu(workload) {
  const setup = await setupCpu(workload);
  let referenceOutput = null;

  for (let index = 0; index < warmupRuns; index += 1) {
    const result = await setup.run();
    referenceOutput = result.output;
  }

  const samples = [];
  for (let index = 0; index < iterations; index += 1) {
    const result = await setup.run();
    referenceOutput = result.output;
    samples.push(result.ms);
  }

  return {
    label: setup.label,
    loadMs: setup.load,
    timings: summarizeSamples(samples),
    output: referenceOutput,
  };
}

async function setupDawnRaw(workload) {
  const imports = await timeAsync(() => import("webgpu"));
  const { create, globals } = imports.value;
  const navigatorGpu = create([]);
  const adapter = await timeAsync(() => navigatorGpu.requestAdapter());
  const device = await timeAsync(() => adapter.value.requestDevice());
  return setupRawCandidate({
    label: "dawn direct",
    load: imports.ms + adapter.ms + device.ms,
    device: device.value,
    gpuGlobals: globals,
    workload,
    adapterInfo: adapter.value.info,
  });
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
  const prime = await timeAsync(() =>
    primePreparedState(() => runDoePreparedRound(gpu, state.value))
  );

  return {
    label: "dawn + doe helpers",
    load: imports.ms + adapter.ms + device.ms + state.ms + prime.ms,
    adapterInfo: adapter.value.info,
    async run() {
      return runDoePreparedRound(gpu, state.value);
    },
    async destroy() {
      state.value.left.destroy?.();
      state.value.right.destroy?.();
      state.value.output.destroy?.();
      device.value.destroy?.();
    },
  };
}

async function setupSimulatteRaw(workload) {
  const imports = await timeAsync(() => import("../../../packages/webgpu/src/native-direct.js"));
  const { globals, providerInfo, requestDevice } = imports.value;
  const device = await timeAsync(() => requestDevice());
  return setupRawCandidate({
    label: "simulatte direct",
    load: imports.ms + device.ms,
    device: device.value,
    gpuGlobals: globals,
    workload,
    provider: providerInfo(),
  });
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
  const state = await timeAsync(() =>
    Promise.resolve(prepareDoeState(gpu.value, workload))
  );
  const prime = await timeAsync(() =>
    primePreparedState(() => runDoePreparedRound(gpu.value, state.value))
  );

  return {
    label: "simulatte + doe helpers",
    load: imports.ms + gpu.ms + state.ms + prime.ms,
    provider: imports.value.providerInfo(),
    async run() {
      return runDoePreparedRound(gpu.value, state.value);
    },
    async destroy() {
      state.value.left.destroy?.();
      state.value.right.destroy?.();
      state.value.output.destroy?.();
      gpu.value.device.destroy?.();
    },
  };
}

function createCandidateDefinitions(workload) {
  return [
    {
      id: "dawn-direct",
      label: "dawn direct",
      setup: () => setupDawnRaw(workload),
    },
    {
      id: "dawn-doe",
      label: "dawn + doe helpers",
      setup: () => setupDawnDoe(workload),
    },
    {
      id: "simulatte-direct",
      label: "simulatte direct",
      setup: () => setupSimulatteRaw(workload),
    },
    {
      id: "simulatte-doe",
      label: "simulatte + doe helpers",
      setup: () => setupSimulatteDoe(workload),
    },
  ];
}

function parseCandidateResult(stdout) {
  const line = stdout
    .split("\n")
    .find((value) => value.startsWith(RESULT_PREFIX));
  if (!line) {
    throw new Error("Candidate subprocess did not emit a benchmark result record");
  }
  return JSON.parse(line.slice(RESULT_PREFIX.length));
}

function runCandidateSubprocess(candidateId, size) {
  const child = spawnSync(
    process.execPath,
    [
      new URL("./run-headless-webgpu-candidate.js", import.meta.url).pathname,
      `${size}`,
      `${iterations}`,
      `${warmupRuns}`,
      `${workerCount}`,
      `--candidate=${candidateId}`,
    ],
    {
      cwd: process.cwd(),
      encoding: "utf8",
      maxBuffer: 64 * 1024 * 1024,
    }
  );

  if (child.status !== 0) {
    throw new Error(
      (child.stderr || child.stdout || `Candidate exited with status ${child.status}`).trim()
    );
  }

  return parseCandidateResult(child.stdout);
}

function formatProbe(probe) {
  return `${probe.size}x${probe.size} -> ${formatMs(probe.ms)}`;
}

async function main() {
  const sizeSelection = await resolveMatrixSize();
  const workload = createMatmulWorkload(sizeSelection.size);

  console.log(
    `Versions: @simulatte/webgpu 0.3.2, @simulatte/webgpu-doe 0.3.2, webgpu 0.3.8`
  );
  console.log(
    `Workload: tiled matmul size=${workload.size}x${workload.size} iterations=${iterations} warmup=${warmupRuns}`
  );
  console.log(
    `Dispatch: ${createMatmulChunkPlans(workload).length} compute dispatches per round, workgroup=${MATMUL_WORKGROUP_SIZE_X}x${MATMUL_WORKGROUP_SIZE_Y}, colsPerInvocation=${MATMUL_COLUMNS_PER_INVOCATION}, workgroups=${workload.workgroupsX}x${workload.workgroupsY}, chunkWorkgroupsY=${workload.chunkWorkgroupsY}`
  );
  console.log(
    "Arithmetic: f32 matrix multiply with approximate validation against the CPU baseline"
  );
  console.log(
    `Direct raw WebGPU contract: ${DIRECT_RAW_WEBGPU_CONTRACT.encode_shape}; ${DIRECT_RAW_WEBGPU_CONTRACT.submit_shape}; ${DIRECT_RAW_WEBGPU_CONTRACT.readback_shape}`
  );
  if (sizeSelection.selectedBy === "auto") {
    console.log(
      `CPU target window: ${formatMs(CPU_TARGET_MIN_MS)} to ${formatMs(CPU_TARGET_MAX_MS)}`
    );
    console.log(
      `Auto-size probes: ${sizeSelection.probes.map(formatProbe).join(", ")}`
    );
  }

  const cpuResult = await measureCpu(workload);

  const candidates = createCandidateDefinitions(workload);

  const results = [];
  const phaseResults = [];
  const failures = [];
  const candidateMetadata = [];
  const cpuExpected = cpuResult.output;
  results.push({
    label: cpuResult.label,
    load: formatMs(cpuResult.loadMs),
    mean: formatMs(cpuResult.timings.meanMs),
    best: formatMs(cpuResult.timings.bestMs),
    worst: formatMs(cpuResult.timings.worstMs),
    speedup: "1.00x",
  });

  for (const candidate of candidates) {
    try {
      console.log(`Running ${candidate.label}...`);
      const result = runCandidateSubprocess(candidate.id, workload.size);
      results.push({
        label: result.label,
        load: formatMs(result.loadMs),
        mean: formatMs(result.timings.meanMs),
        best: formatMs(result.timings.bestMs),
        worst: formatMs(result.timings.worstMs),
        speedup: formatSpeedup(cpuResult.timings.meanMs, result.timings.meanMs),
      });
      if (result.phaseTimings) {
        phaseResults.push({
          label: result.label,
          encode: formatMs(result.phaseTimings.encodeMs),
          submit_wait: formatMs(result.phaseTimings.submitWaitMs),
          readback: formatMs(result.phaseTimings.readbackMs),
          total: formatMs(
            result.phaseTimings.encodeMs
              + result.phaseTimings.submitWaitMs
              + result.phaseTimings.readbackMs
          ),
        });
      }
      candidateMetadata.push(result);
    } catch (error) {
      results.push({
        label: candidate.label,
        load: formatMs(0),
        mean: "FAIL",
        best: "FAIL",
        worst: "FAIL",
        speedup: "n/a",
      });
      failures.push(`${candidate.label}: ${error.message}`);
    }
  }

  console.log(`\n${createTable(results)}`);
  if (phaseResults.length > 0) {
    console.log(`\nPhase means (GPU candidates only):\n${createPhaseTable(phaseResults)}`);
  }
  console.log(
    `\nCPU sample outputs: [${Array.from(cpuExpected.subarray(0, 8)).join(", ")}]`
  );
  if (failures.length === 0) {
    console.log("\nAll GPU candidates matched the CPU reference within tolerance.");
  } else {
    console.log("\nFailures:");
    for (const failure of failures) {
      console.log(`- ${failure}`);
    }
  }

  for (const setup of candidateMetadata) {
    if (setup.adapterInfo) {
      console.log(`Adapter ${setup.label}:`, setup.adapterInfo);
    }
    if (setup.provider) {
      console.log(`Provider ${setup.label}:`, setup.provider);
    }
  }
}

main().catch((error) => {
  console.error("\nHeadless WebGPU comparison failed.");
  console.error(error);
  process.exitCode = 1;
});
