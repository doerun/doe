import { performance } from "node:perf_hooks";
import { spawnSync } from "node:child_process";
import {
  DEFAULT_ELEMENTS,
  DEFAULT_ITERATIONS,
  DEFAULT_ROUNDS,
  DEFAULT_WARMUP,
  DEFAULT_WORKERS,
  WORKGROUP_SIZE_X,
  compareExact,
  createChunkPlans,
  createWorkload,
  formatMs,
  formatSpeedup,
  parsePositiveInt,
  runCpuWorkers,
  summarizeSamples,
  timeAsync,
} from "./bench-workload-common.mjs";

const elements = parsePositiveInt(process.argv[2], DEFAULT_ELEMENTS);
const rounds = parsePositiveInt(process.argv[3], DEFAULT_ROUNDS);
const iterations = parsePositiveInt(process.argv[4], DEFAULT_ITERATIONS);
const warmupRuns = parsePositiveInt(process.argv[5], DEFAULT_WARMUP);
const workerCount = parsePositiveInt(process.argv[6], DEFAULT_WORKERS);
const scenarioId =
  process.argv.find((value) => value.startsWith("--scenario="))?.split("=")[1] ?? "default";
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

const DIRECT_RAW_WEBGPU_CONTRACT = Object.freeze({
  shader: "shared generated WGSL",
  chunk_plan: "shared createChunkPlans(workload)",
  encode_shape: "one command encoder, one compute pass, one copyBufferToBuffer",
  submit_shape: "one queue submit, one queue completion wait",
  readback_shape: "one MAP_READ buffer map and scenario-sized readback",
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
    validation: Math.max("Validation".length, ...rows.map((row) => row.validation.length)),
    total: Math.max("Total+validation".length, ...rows.map((row) => row.total.length)),
  };

  const divider = [
    "-".repeat(widths.label),
    "-".repeat(widths.encode),
    "-".repeat(widths.submit_wait),
    "-".repeat(widths.readback),
    "-".repeat(widths.validation),
    "-".repeat(widths.total),
  ].join("  ");

  const lines = [
    [
      padCell("Runner", widths.label, false),
      padCell("Encode", widths.encode),
      padCell("Submit+wait", widths.submit_wait),
      padCell("Readback", widths.readback),
      padCell("Validation", widths.validation),
      padCell("Total+validation", widths.total),
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
        padCell(row.validation, widths.validation),
        padCell(row.total, widths.total),
      ].join("  ")
    );
  }

  return lines.join("\n");
}

function createVarianceTable(rows) {
  const widths = {
    label: Math.max("Runner".length, ...rows.map((row) => row.label.length)),
    stddev: Math.max("Stddev".length, ...rows.map((row) => row.stddev.length)),
    cv: Math.max("CV".length, ...rows.map((row) => row.cv.length)),
    range: Math.max("Range".length, ...rows.map((row) => row.range.length)),
  };

  const divider = [
    "-".repeat(widths.label),
    "-".repeat(widths.stddev),
    "-".repeat(widths.cv),
    "-".repeat(widths.range),
  ].join("  ");

  const lines = [
    [
      padCell("Runner", widths.label, false),
      padCell("Stddev", widths.stddev),
      padCell("CV", widths.cv),
      padCell("Range", widths.range),
    ].join("  "),
    divider,
  ];

  for (const row of rows) {
    lines.push(
      [
        padCell(row.label, widths.label, false),
        padCell(row.stddev, widths.stddev),
        padCell(row.cv, widths.cv),
        padCell(row.range, widths.range),
      ].join("  ")
    );
  }

  return lines.join("\n");
}

function createNativeDirectTable(rows) {
  const widths = {
    label: Math.max("Runner".length, ...rows.map((row) => row.label.length)),
    submit_wait: Math.max("Addon submit+wait".length, ...rows.map((row) => row.submit_wait.length)),
    queue_flush: Math.max("Queue flush".length, ...rows.map((row) => row.queue_flush.length)),
    map_async: Math.max("mapAsync".length, ...rows.map((row) => row.map_async.length)),
    map_queue_flush: Math.max("mapAsync queue flush".length, ...rows.map((row) => row.map_queue_flush.length)),
    get_mapped_range: Math.max("getMappedRange".length, ...rows.map((row) => row.get_mapped_range.length)),
  };

  const divider = [
    "-".repeat(widths.label),
    "-".repeat(widths.submit_wait),
    "-".repeat(widths.queue_flush),
    "-".repeat(widths.map_async),
    "-".repeat(widths.map_queue_flush),
    "-".repeat(widths.get_mapped_range),
  ].join("  ");

  const lines = [
    [
      padCell("Runner", widths.label, false),
      padCell("Addon submit+wait", widths.submit_wait),
      padCell("Queue flush", widths.queue_flush),
      padCell("mapAsync", widths.map_async),
      padCell("mapAsync queue flush", widths.map_queue_flush),
      padCell("getMappedRange", widths.get_mapped_range),
    ].join("  "),
    divider,
  ];

  for (const row of rows) {
    lines.push(
      [
        padCell(row.label, widths.label, false),
        padCell(row.submit_wait, widths.submit_wait),
        padCell(row.queue_flush, widths.queue_flush),
        padCell(row.map_async, widths.map_async),
        padCell(row.map_queue_flush, widths.map_queue_flush),
        padCell(row.get_mapped_range, widths.get_mapped_range),
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
      state.value.src.destroy?.();
      state.value.dst.destroy?.();
      state.value.readback.destroy?.();
      device.destroy?.();
    },
  };
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
      { binding: 0, resource: { buffer: src } },
      { binding: 1, resource: { buffer: dst } },
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
    pipelines,
    bindGroup,
    src,
    dst,
    readback,
  };
}

async function runRawPreparedRound(device, gpuGlobals, workload, state) {
  const encodeStartedAt = performance.now();
  const encoder = device.createCommandEncoder();
  const pass = encoder.beginComputePass();
  pass.setBindGroup(0, state.bindGroup);

  for (let index = 0; index < state.pipelines.length; index += 1) {
    pass.setPipeline(state.pipelines[index]);
    pass.dispatchWorkgroups(state.chunkPlans[index].workgroups);
  }

  pass.end();
  encoder.copyBufferToBuffer(state.dst, 0, state.readback, 0, workload.outputBytes);
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
    size: workload.outputBytes,
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
  const bindingSets = kernels.map((kernel) =>
    kernel.bindings.create([srcBinding, dstBinding])
  );

  return {
    chunkPlans,
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
      compareExact(expectedOutput, result.output);
      referenceOutput = result.output;
    }

    const samples = [];
    for (let index = 0; index < iterations; index += 1) {
      const result = await run();
      compareExact(expectedOutput, result.output);
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
      return runCpuWorkers(workload.input, workload.rounds, workerCount);
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
    const [{ create }, { gpu: doe }] = await Promise.all([
      import("webgpu"),
      import("../../../packages/doe-gpu/src/index.js"),
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
      state.value.src.destroy?.();
      state.value.dst.destroy?.();
      device.value.destroy?.();
    },
  };
}

async function setupSimulatteRaw(workload) {
  const imports = await timeAsync(() => import("../../../packages/doe-gpu/src/index.js"));
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
    const { requestDevice, providerInfo, gpu: doe } =
      await import("../../../packages/doe-gpu/src/index.js");
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
      state.value.src.destroy?.();
      state.value.dst.destroy?.();
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

function runCandidateSubprocess(candidateId) {
  const child = spawnSync(
    process.execPath,
    [
      new URL("./run-streaming-webgpu-candidate.js", import.meta.url).pathname,
      `${elements}`,
      `${rounds}`,
      `${iterations}`,
      `${warmupRuns}`,
      `${workerCount}`,
      `--candidate=${candidateId}`,
      `--scenario=${scenarioId}`,
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

async function main() {
  const workload = createWorkload(elements, rounds);
  const displayChunkSize =
    scenarioId === "single-dispatch-full-readback" ? workload.elements : workload.chunkSize;
  const displayChunkCount =
    scenarioId === "single-dispatch-full-readback" ? 1 : workload.chunkCount;
  const displayReadbackBytes =
    scenarioId === "many-dispatches-tiny-readback"
      ? 256 * Float32Array.BYTES_PER_ELEMENT
      : workload.outputBytes;
  console.log(
    `Versions: doe-gpu 0.3.4, webgpu 0.3.8`
  );
  console.log(
    `Workload: streaming affine transform elements=${elements.toLocaleString()} rounds=${rounds} iterations=${iterations} warmup=${warmupRuns}`
  );
  console.log(`Scenario: ${scenarioId}`);
  console.log(
    `Dispatch: chunkSize=${displayChunkSize.toLocaleString()} chunkCount=${displayChunkCount} workgroupSize=${WORKGROUP_SIZE_X}`
  );
  console.log(`Readback: ${displayReadbackBytes.toLocaleString()} bytes per sample`);
  console.log(
    "Arithmetic: exact f32 affine transforms over four accumulators per element"
  );
  console.log(
    `Direct raw WebGPU contract: ${DIRECT_RAW_WEBGPU_CONTRACT.encode_shape}; ${DIRECT_RAW_WEBGPU_CONTRACT.submit_shape}; ${DIRECT_RAW_WEBGPU_CONTRACT.readback_shape}`
  );

  const cpuResult = await measureCpu(workload);

  const candidates = createCandidateDefinitions(workload);

  const results = [];
  const phaseResults = [];
  const nativeDirectResults = [];
  const varianceResults = [];
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
      const result = runCandidateSubprocess(candidate.id);
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
          validation: formatMs(result.phaseTimings.validationMs),
          total: formatMs(
            result.phaseTimings.encodeMs
              + result.phaseTimings.submitWaitMs
              + result.phaseTimings.readbackMs
              + result.phaseTimings.validationMs
          ),
        });
        if (result.phaseTimings.nativeDirectDiagnostics) {
          const diagnostics = result.phaseTimings.nativeDirectDiagnostics;
          nativeDirectResults.push({
            label: result.label,
            submit_wait: formatMs(diagnostics.submitWaitAddonMs),
            queue_flush: formatMs(diagnostics.queueFlushAddonMs),
            map_async: formatMs(diagnostics.mapAsyncAddonMs),
            map_queue_flush: formatMs(diagnostics.mapQueueFlushAddonMs),
            get_mapped_range: formatMs(diagnostics.getMappedRangeAddonMs),
          });
        }
      }
      if (result.variance) {
        varianceResults.push({
          label: result.label,
          stddev: formatMs(result.variance.stddevMs),
          cv: `${result.variance.cvPercent.toFixed(1)}%`,
          range: formatMs(result.variance.rangeMs),
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
  if (nativeDirectResults.length > 0) {
    console.log(`\nNative-direct addon timing means:\n${createNativeDirectTable(nativeDirectResults)}`);
  }
  if (varianceResults.length > 0) {
    console.log(`\nTimed-sample variance (GPU candidates only):\n${createVarianceTable(varianceResults)}`);
  }
  console.log(
    `\nCPU sample outputs: [${Array.from(cpuExpected.subarray(0, 8)).join(", ")}]`
  );
  if (candidateMetadata[0]?.scenario?.description) {
    console.log(`\nScenario detail: ${candidateMetadata[0].scenario.description}`);
  }
  if (failures.length === 0) {
    console.log("\nAll GPU candidates matched the CPU reference exactly.");
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
  console.error("\nStreaming WebGPU comparison failed.");
  console.error(error);
  process.exitCode = 1;
});
