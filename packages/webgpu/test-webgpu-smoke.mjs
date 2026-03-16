import { globals, providerInfo, requestDevice } from "./src/index.js";
import { doe } from "./src/compute.js";

const INPUT = Float32Array.of(1, 2, 3, 4);
const EXPECTED = [2, 4, 6, 8];

const DOUBLE_SHADER = `
  @group(0) @binding(0) var<storage, read> src: array<f32>;
  @group(0) @binding(1) var<storage, read_write> dst: array<f32>;

  @compute @workgroup_size(4)
  fn main(@builtin(global_invocation_id) gid: vec3u) {
    let i = gid.x;
    dst[i] = src[i] * 2.0;
  }
`;

function logSection(title) {
  console.log(`\n=== ${title} ===`);
}

function assertResult(label, actual) {
  const values = Array.from(actual);
  const ok = values.length === EXPECTED.length && values.every((value, index) => value === EXPECTED[index]);
  console.log(`${label}:`, values);
  if (!ok) {
    throw new Error(`${label} failed. Expected ${EXPECTED.join(", ")}, got ${values.join(", ")}`);
  }
}

async function runDirectDispatch(device, bindGroup, pipeline, dst, readback, bytes) {
  const encoder = device.createCommandEncoder();
  const pass = encoder.beginComputePass();
  pass.setPipeline(pipeline);
  pass.setBindGroup(0, bindGroup);
  pass.dispatchWorkgroups(1);
  pass.end();
  encoder.copyBufferToBuffer(dst, 0, readback, 0, bytes);

  device.queue.submit([encoder.finish()]);
  await device.queue.onSubmittedWorkDone();
  await readback.mapAsync(globals.GPUMapMode.READ);
  const result = new Float32Array(readback.getMappedRange().slice(0));
  readback.unmap();
  return result;
}

async function runDirectWebGpuLayer() {
  logSection("Layer 1: Direct WebGPU");
  const device = await requestDevice();
  const bytes = INPUT.byteLength;

  const src = device.createBuffer({
    size: bytes,
    usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_DST,
  });
  device.queue.writeBuffer(src, 0, INPUT);

  const dst = device.createBuffer({
    size: bytes,
    usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_SRC,
  });

  const readback = device.createBuffer({
    size: bytes,
    usage: globals.GPUBufferUsage.COPY_DST | globals.GPUBufferUsage.MAP_READ,
  });

  const pipeline = device.createComputePipeline({
    layout: "auto",
    compute: {
      module: device.createShaderModule({ code: DOUBLE_SHADER }),
      entryPoint: "main",
    },
  });

  const bindGroup = device.createBindGroup({
    layout: pipeline.getBindGroupLayout(0),
    entries: [
      { binding: 0, resource: { buffer: src } },
      { binding: 1, resource: { buffer: dst } },
    ],
  });

  await runDirectDispatch(device, bindGroup, pipeline, dst, readback, bytes);
  const result = await runDirectDispatch(device, bindGroup, pipeline, dst, readback, bytes);

  assertResult("Direct WebGPU result", result);

  src.destroy?.();
  dst.destroy?.();
  readback.destroy?.();
  device.destroy?.();
}

async function runDoeApiLayer() {
  logSection("Layer 2: Doe API");
  const gpu = await doe.requestDevice();
  const src = gpu.buffer.create({ data: INPUT });
  const dst = gpu.buffer.create({ size: src.size, usage: "storageReadWrite" });

  await gpu.kernel.run({
    code: DOUBLE_SHADER,
    bindings: [src, dst],
    workgroups: 1,
  });

  const result = await gpu.buffer.read({ buffer: dst, type: Float32Array });
  assertResult("Doe API result", result);

  src.destroy?.();
  dst.destroy?.();
  gpu.device.destroy?.();
}

async function runDoeOneShotLayer() {
  logSection("Doe API: one-shot compute");
  const gpu = await doe.requestDevice();
  const result = await gpu.compute({
    code: DOUBLE_SHADER,
    inputs: [INPUT],
    output: {
      type: Float32Array,
      size: INPUT.byteLength,
    },
    workgroups: 1,
  });

  assertResult("Doe one-shot result", result);
  gpu.device.destroy?.();
}

async function main() {
  console.log("providerInfo:", providerInfo());
  await runDirectWebGpuLayer();
  await runDoeApiLayer();
  await runDoeOneShotLayer();
  console.log("\nAll @simulatte/webgpu smoke paths passed.");
}

main().catch((error) => {
  console.error("\nWebGPU layer test failed.");
  console.error(error);
  process.exitCode = 1;
});
