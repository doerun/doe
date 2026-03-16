import os from "node:os";
import { Worker } from "node:worker_threads";
import { performance } from "node:perf_hooks";

export const WORKGROUP_SIZE_X = 256;
export const MAX_CHUNK_WORKGROUPS = 256;
export const MAX_CHUNK_ELEMENTS = WORKGROUP_SIZE_X * MAX_CHUNK_WORKGROUPS;
export const DEFAULT_ELEMENTS = 1 << 22;
export const DEFAULT_ROUNDS = 64;
export const DEFAULT_ITERATIONS = 4;
export const DEFAULT_WARMUP = 1;
export const MATMUL_WORKGROUP_SIZE_X = 16;
export const MATMUL_WORKGROUP_SIZE_Y = 8;
export const MATMUL_COLUMNS_PER_INVOCATION = 4;
export const DEFAULT_MATMUL_SIZE = 1024;
export const DEFAULT_WORKERS = Math.min(
  Math.max(os.availableParallelism?.() ?? os.cpus().length, 1),
  8
);

const transformWorkerUrl = new URL("./cpu-transform-worker.mjs", import.meta.url);
const matmulWorkerUrl = new URL("./cpu-matmul-worker.mjs", import.meta.url);

export function parsePositiveInt(value, fallback) {
  const parsed = Number.parseInt(value ?? `${fallback}`, 10);
  if (!Number.isInteger(parsed) || parsed < 1) {
    throw new Error(`Expected a positive integer, received: ${value}`);
  }
  return parsed;
}

export function buildInput(count) {
  const data = new Float32Array(count);
  for (let i = 0; i < count; i += 1) {
    data[i] = i % 2;
  }
  return data;
}

export function buildMatrix(size, seed) {
  const data = new Float32Array(size * size);
  for (let row = 0; row < size; row += 1) {
    for (let col = 0; col < size; col += 1) {
      const value = (((row * 17 + col * 29 + seed * 31) % 97) - 48) / 17;
      data[row * size + col] = Math.fround(value);
    }
  }
  return data;
}

export function createWorkload(elements, rounds) {
  return {
    elements,
    rounds,
    input: buildInput(elements),
    outputBytes: elements * Float32Array.BYTES_PER_ELEMENT,
    chunkSize: MAX_CHUNK_ELEMENTS,
    chunkCount: Math.ceil(elements / MAX_CHUNK_ELEMENTS),
  };
}

export function createMatmulWorkload(size) {
  const elements = size * size;
  const workgroupsX = Math.ceil(
    size / (MATMUL_WORKGROUP_SIZE_X * MATMUL_COLUMNS_PER_INVOCATION)
  );
  const workgroupsY = Math.ceil(size / MATMUL_WORKGROUP_SIZE_Y);
  return {
    size,
    left: buildMatrix(size, 1),
    right: buildMatrix(size, 7),
    outputBytes: elements * Float32Array.BYTES_PER_ELEMENT,
    workgroupsX,
    workgroupsY,
    chunkWorkgroupsY: Math.max(1, Math.floor(MAX_CHUNK_WORKGROUPS / workgroupsX)),
  };
}

export function chunkWorkgroupsForLength(length) {
  return Math.ceil(length / WORKGROUP_SIZE_X);
}

export function buildChunkShader(roundCount, startOffset, elementCount) {
  const lines = [
    "@group(0) @binding(0) var<storage, read> src: array<f32>;",
    "@group(0) @binding(1) var<storage, read_write> dst: array<f32>;",
    `@compute @workgroup_size(${WORKGROUP_SIZE_X})`,
    "fn main(@builtin(global_invocation_id) gid: vec3u) {",
    "  let localIndex = gid.x;",
    `  if (localIndex >= ${elementCount}u) {`,
    "    return;",
    "  }",
    `  let index = ${startOffset}u + localIndex;`,
    "  var a = src[index];",
    "  var b = src[index] + 1.0;",
    "  var c = src[index] + 2.0;",
    "  var d = src[index] + 3.0;",
  ];

  for (let round = 0; round < roundCount; round += 1) {
    lines.push("  a = a * 2.0 + 1.0;");
    lines.push("  b = b * 2.0 + 1.0;");
    lines.push("  c = c * 2.0 + 1.0;");
    lines.push("  d = d * 2.0 + 1.0;");
  }

  lines.push("  dst[index] = a + b + c + d;");
  lines.push("}");

  return lines.join("\n");
}

export function buildMatmulShader(size, rowStart) {
  const lines = [
    `const MATRIX_SIZE: u32 = ${size}u;`,
    `const COLUMNS_PER_INVOCATION: u32 = ${MATMUL_COLUMNS_PER_INVOCATION}u;`,
    "@group(0) @binding(0) var<storage, read> left: array<f32>;",
    "@group(0) @binding(1) var<storage, read> right: array<f32>;",
    "@group(0) @binding(2) var<storage, read_write> output: array<f32>;",
    `@compute @workgroup_size(${MATMUL_WORKGROUP_SIZE_X}, ${MATMUL_WORKGROUP_SIZE_Y}, 1)`,
    "fn main(",
    "  @builtin(global_invocation_id) gid: vec3u,",
    "  @builtin(local_invocation_id) _lid: vec3u",
    ") {",
    "  let baseCol = gid.x * COLUMNS_PER_INVOCATION;",
    `  let row = ${rowStart}u + gid.y;`,
    "  if (row >= MATRIX_SIZE) {",
    "    return;",
    "  }",
    "  var sum0 = 0.0;",
    "  var sum1 = 0.0;",
    "  var sum2 = 0.0;",
    "  var sum3 = 0.0;",
    "  for (var k = 0u; k < MATRIX_SIZE; k = k + 1u) {",
    "    let leftValue = left[row * MATRIX_SIZE + k];",
    "    if (baseCol < MATRIX_SIZE) {",
    "      sum0 = f32(sum0 + f32(leftValue * right[k * MATRIX_SIZE + baseCol]));",
    "    }",
    "    if (baseCol + 1u < MATRIX_SIZE) {",
    "      sum1 = f32(sum1 + f32(leftValue * right[k * MATRIX_SIZE + baseCol + 1u]));",
    "    }",
    "    if (baseCol + 2u < MATRIX_SIZE) {",
    "      sum2 = f32(sum2 + f32(leftValue * right[k * MATRIX_SIZE + baseCol + 2u]));",
    "    }",
    "    if (baseCol + 3u < MATRIX_SIZE) {",
    "      sum3 = f32(sum3 + f32(leftValue * right[k * MATRIX_SIZE + baseCol + 3u]));",
    "    }",
    "  }",
    "  if (baseCol < MATRIX_SIZE) {",
    "    output[row * MATRIX_SIZE + baseCol] = sum0;",
    "  }",
    "  if (baseCol + 1u < MATRIX_SIZE) {",
    "    output[row * MATRIX_SIZE + baseCol + 1u] = sum1;",
    "  }",
    "  if (baseCol + 2u < MATRIX_SIZE) {",
    "    output[row * MATRIX_SIZE + baseCol + 2u] = sum2;",
    "  }",
    "  if (baseCol + 3u < MATRIX_SIZE) {",
    "    output[row * MATRIX_SIZE + baseCol + 3u] = sum3;",
    "  }",
    "}",
  ];

  return lines.join("\n");
}

export function createMatmulChunkPlans(workload) {
  const plans = [];
  for (
    let groupRowStart = 0;
    groupRowStart < workload.workgroupsY;
    groupRowStart += workload.chunkWorkgroupsY
  ) {
    const workgroupsY = Math.min(
      workload.chunkWorkgroupsY,
      workload.workgroupsY - groupRowStart
    );
    plans.push({
      rowStart: groupRowStart * MATMUL_WORKGROUP_SIZE_Y,
      workgroupsX: workload.workgroupsX,
      workgroupsY,
      code: buildMatmulShader(workload.size, groupRowStart * MATMUL_WORKGROUP_SIZE_Y),
    });
  }
  return plans;
}

export function* chunkRanges(length, chunkSize) {
  for (let start = 0; start < length; start += chunkSize) {
    yield {
      start,
      end: Math.min(length, start + chunkSize),
    };
  }
}

export function createChunkPlans(workload) {
  return Array.from(chunkRanges(workload.elements, workload.chunkSize), ({ start, end }) => ({
    start,
    end,
    length: end - start,
    workgroups: chunkWorkgroupsForLength(end - start),
    code: buildChunkShader(workload.rounds, start, end - start),
  }));
}

export function formatMs(ms) {
  return `${ms.toFixed(2)} ms`;
}

export function formatSpeedup(cpuMs, candidateMs) {
  if (!(cpuMs > 0) || !(candidateMs > 0)) {
    return "n/a";
  }
  return `${(cpuMs / candidateMs).toFixed(2)}x`;
}

export function summarizeSamples(samples) {
  const total = samples.reduce((sum, value) => sum + value, 0);
  return {
    meanMs: total / samples.length,
    bestMs: Math.min(...samples),
    worstMs: Math.max(...samples),
  };
}

export async function timeAsync(callback) {
  const startedAt = performance.now();
  const value = await callback();
  return {
    value,
    ms: performance.now() - startedAt,
  };
}

export async function runCpuWorkers(input, rounds, workerCount) {
  const chunkSize = Math.ceil(input.length / workerCount);
  const sharedInputBuffer = new SharedArrayBuffer(input.byteLength);
  new Float32Array(sharedInputBuffer).set(input);

  const jobs = [];
  const startedAt = performance.now();

  for (let index = 0; index < workerCount; index += 1) {
    const start = index * chunkSize;
    const end = Math.min(input.length, start + chunkSize);
    if (start >= end) {
      break;
    }

    jobs.push(
      new Promise((resolve, reject) => {
        const worker = new Worker(transformWorkerUrl, {
          type: "module",
          workerData: {
            inputBuffer: sharedInputBuffer,
            start,
            end,
            rounds,
          },
        });

        let settled = false;

        worker.once("message", (value) => {
          settled = true;
          resolve(value);
        });
        worker.once("error", (error) => {
          settled = true;
          reject(error);
        });
        worker.once("exit", (code) => {
          if (!settled && code !== 0) {
            reject(new Error(`CPU worker exited with code ${code}`));
          }
        });
      })
    );
  }

  const results = await Promise.all(jobs);
  const output = new Float32Array(input.length);
  for (const result of results) {
    output.set(new Float32Array(result.outputBuffer), result.start);
  }

  return {
    output,
    ms: performance.now() - startedAt,
  };
}

export async function runCpuMatmulWorkers(left, right, size, workerCount) {
  const rowChunkSize = Math.ceil(size / workerCount);
  const sharedLeftBuffer = new SharedArrayBuffer(left.byteLength);
  const sharedRightBuffer = new SharedArrayBuffer(right.byteLength);
  new Float32Array(sharedLeftBuffer).set(left);
  new Float32Array(sharedRightBuffer).set(right);

  const jobs = [];
  const startedAt = performance.now();

  for (let index = 0; index < workerCount; index += 1) {
    const startRow = index * rowChunkSize;
    const endRow = Math.min(size, startRow + rowChunkSize);
    if (startRow >= endRow) {
      break;
    }

    jobs.push(
      new Promise((resolve, reject) => {
        const worker = new Worker(matmulWorkerUrl, {
          type: "module",
          workerData: {
            leftBuffer: sharedLeftBuffer,
            rightBuffer: sharedRightBuffer,
            size,
            startRow,
            endRow,
          },
        });

        let settled = false;

        worker.once("message", (value) => {
          settled = true;
          resolve(value);
        });
        worker.once("error", (error) => {
          settled = true;
          reject(error);
        });
        worker.once("exit", (code) => {
          if (!settled && code !== 0) {
            reject(new Error(`CPU matmul worker exited with code ${code}`));
          }
        });
      })
    );
  }

  const results = await Promise.all(jobs);
  const output = new Float32Array(size * size);
  for (const result of results) {
    output.set(new Float32Array(result.outputBuffer), result.startRow * size);
  }

  return {
    output,
    ms: performance.now() - startedAt,
  };
}

export function compareExact(expected, actual) {
  if (expected.length !== actual.length) {
    throw new Error(`Length mismatch: expected ${expected.length}, got ${actual.length}`);
  }

  for (let i = 0; i < expected.length; i += 1) {
    if (expected[i] !== actual[i]) {
      throw new Error(
        `Mismatch at index ${i}: expected ${expected[i]}, got ${actual[i]}`
      );
    }
  }
}

export function compareApprox(expected, actual, absTolerance = 1e-3, relTolerance = 1e-3) {
  if (expected.length !== actual.length) {
    throw new Error(`Length mismatch: expected ${expected.length}, got ${actual.length}`);
  }

  for (let i = 0; i < expected.length; i += 1) {
    const left = expected[i];
    const right = actual[i];
    const diff = Math.abs(left - right);
    const scale = Math.max(Math.abs(left), Math.abs(right), 1);
    if (diff > absTolerance && diff > relTolerance * scale) {
      throw new Error(
        `Mismatch at index ${i}: expected ${left}, got ${right}, diff=${diff}`
      );
    }
  }
}
