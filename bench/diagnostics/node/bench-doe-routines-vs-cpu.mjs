import { doe, providerInfo } from "../../../packages/webgpu/src/compute.js";
import {
  DEFAULT_ELEMENTS,
  DEFAULT_ROUNDS,
  DEFAULT_WORKERS,
  WORKGROUP_SIZE_X,
  compareExact,
  createChunkPlans,
  createWorkload,
  formatMs,
  formatSpeedup,
  parsePositiveInt,
  runCpuWorkers,
} from "./bench-workload-common.mjs";

const elements = parsePositiveInt(process.argv[2], DEFAULT_ELEMENTS);
const rounds = parsePositiveInt(process.argv[3], DEFAULT_ROUNDS);
const workerCount = parsePositiveInt(process.argv[4], DEFAULT_WORKERS);

async function runGpuDoeRoutines(workload) {
  const gpu = await doe.requestDevice();
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
  const dispatchAll = async () => {
    const batch = gpu.compute.begin();
    for (let index = 0; index < kernels.length; index += 1) {
      batch.dispatch(kernels[index], {
        bindings: bindingSets[index],
        workgroups: chunkPlans[index].workgroups,
      });
    }
    await batch.submit();
  };

  try {
    await dispatchAll();
    await gpu.buffer.read({ buffer: dst, type: Float32Array });

    const startedAt = performance.now();
    await dispatchAll();
    const output = await gpu.buffer.read({ buffer: dst, type: Float32Array });

    return {
      output,
      ms: performance.now() - startedAt,
    };
  } finally {
    src.destroy?.();
    dst.destroy?.();
    gpu.device.destroy?.();
  }
}

async function main() {
  const workload = createWorkload(elements, rounds);

  console.log("providerInfo:", providerInfo());
  console.log(
    `\nDoe routines benchmark: elements=${elements.toLocaleString()} rounds=${rounds} workers=${workerCount}`
  );
  console.log(
    `Dispatch: chunkSize=${workload.chunkSize.toLocaleString()} chunkCount=${workload.chunkCount} workgroupSize=${WORKGROUP_SIZE_X}`
  );
  console.log(
    "Workload: exact f32 affine transforms over four accumulators per element"
  );

  const cpu = await runCpuWorkers(workload.input, rounds, workerCount);
  console.log(`CPU workers: ${formatMs(cpu.ms)}`);

  const gpu = await runGpuDoeRoutines(workload);
  console.log(`Doe routines GPU: ${formatMs(gpu.ms)}`);

  compareExact(cpu.output, gpu.output);
  console.log("Exact match: yes");
  console.log(`Speedup: ${formatSpeedup(cpu.ms, gpu.ms)}`);
  console.log(
    `Sample outputs: [${Array.from(gpu.output.subarray(0, 8)).join(", ")}]`
  );
}

main().catch((error) => {
  console.error("\nDoe routines vs CPU benchmark failed.");
  console.error(error);
  process.exitCode = 1;
});
