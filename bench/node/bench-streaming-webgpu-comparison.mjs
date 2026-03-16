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
const RESULT_PREFIX = "FAWN_BENCH_RESULT ";

const DIRECT_RAW_WEBGPU_CONTRACT = Object.freeze({
  shader: "shared generated WGSL",
  chunk_plan: "shared createChunkPlans(workload)",
  encode_shape: "one command encoder, one compute pass, one copyBufferToBuffer",
  submit_shape: "one queue submit, one queue completion wait",
  readback_shape: "one MAP_READ buffer map and full-range readback",
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
  await state.readback.mapAsync(gpuGlobals.GPUMapMode.READ);
  const output = new Float32Array(
    state.readback.getMappedRange(0, workload.outputBytes),
  ).slice();
  state.readback.unmap();
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
  const src = gpu.buffer.create({ data: workload.input });
  const dst = gpu.buffer.create({
    size: workload.outputBytes,
    usage: ["storageReadWrite", "readback"],
  });
  const chunkPlans = createChunkPlans(workload);
  const kernels = chunkPlans.map((plan) =>
    gpu.kernel.create({
      code: plan.code,
      bindings: [src, dst],
    })
  );
  const bindingSets = kernels.map((kernel) =>
    kernel.bindings.create([src, dst])
  );

  return {
    chunkPlans,
    kernels,
    bindingSets,
    src,
    dst,
  };
}

async function runDoePreparedRound(gpu, state) {
  const encodeStartedAt = performance.now();
  const batch = gpu.compute.begin();
  for (let index = 0; index < state.kernels.length; index += 1) {
    batch.dispatch(state.kernels[index], {
      bindings: state.bindingSets[index],
      workgroups: state.chunkPlans[index].workgroups,
    });
  }
  const encodeMs = performance.now() - encodeStartedAt;

  const submitWaitStartedAt = performance.now();
  await batch.submit();
  const submitWaitMs = performance.now() - submitWaitStartedAt;

  const readbackStartedAt = performance.now();
  const output = await gpu.buffer.read({ buffer: state.dst, type: Float32Array });
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
    const [{ create }, { default: doe }] = await Promise.all([
      import("webgpu"),
      import("../../nursery/webgpu-doe/src/index.js"),
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
  const imports = await timeAsync(() => import("../../nursery/webgpu/src/native-direct.js"));
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
      import("../../nursery/webgpu/src/native-direct.js"),
      import("../../nursery/webgpu-doe/src/index.js"),
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
  console.log(
    `Versions: @simulatte/webgpu 0.3.2, @simulatte/webgpu-doe 0.3.2, webgpu 0.3.8`
  );
  console.log(
    `Workload: streaming affine transform elements=${elements.toLocaleString()} rounds=${rounds} iterations=${iterations} warmup=${warmupRuns}`
  );
  console.log(
    `Dispatch: chunkSize=${workload.chunkSize.toLocaleString()} chunkCount=${workload.chunkCount} workgroupSize=${WORKGROUP_SIZE_X}`
  );
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
