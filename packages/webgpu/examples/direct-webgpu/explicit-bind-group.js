import { globals, requestDevice } from "@simulatte/webgpu";

const device = await requestDevice();

const input = new Float32Array([1, 2, 3, 4]);
const inputBuffer = device.createBuffer({
  size: input.byteLength,
  usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_DST,
});
device.queue.writeBuffer(inputBuffer, 0, input);

const outputBuffer = device.createBuffer({
  size: input.byteLength,
  usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_SRC,
});

const readbackBuffer = device.createBuffer({
  size: input.byteLength,
  usage: globals.GPUBufferUsage.COPY_DST | globals.GPUBufferUsage.MAP_READ,
});

const shader = device.createShaderModule({
  code: `
    @group(0) @binding(0) var<storage, read> src: array<f32>;
    @group(0) @binding(1) var<storage, read_write> dst: array<f32>;

    @compute @workgroup_size(4)
    fn main(@builtin(global_invocation_id) gid: vec3u) {
      let i = gid.x;
      dst[i] = src[i] * 4.0;
    }
  `,
});

const bindGroupLayout = device.createBindGroupLayout({
  entries: [
    {
      binding: 0,
      visibility: globals.GPUShaderStage.COMPUTE,
      buffer: { type: "read-only-storage" },
    },
    {
      binding: 1,
      visibility: globals.GPUShaderStage.COMPUTE,
      buffer: { type: "storage" },
    },
  ],
});

const pipelineLayout = device.createPipelineLayout({
  bindGroupLayouts: [bindGroupLayout],
});

const pipeline = device.createComputePipeline({
  layout: pipelineLayout,
  compute: {
    module: shader,
    entryPoint: "main",
  },
});

const bindGroup = device.createBindGroup({
  layout: bindGroupLayout,
  entries: [
    { binding: 0, resource: { buffer: inputBuffer } },
    { binding: 1, resource: { buffer: outputBuffer } },
  ],
});

const encoder = device.createCommandEncoder();
const pass = encoder.beginComputePass();
pass.setPipeline(pipeline);
pass.setBindGroup(0, bindGroup);
pass.dispatchWorkgroups(1);
pass.end();
encoder.copyBufferToBuffer(outputBuffer, 0, readbackBuffer, 0, input.byteLength);

device.queue.submit([encoder.finish()]);
await device.queue.onSubmittedWorkDone();

await readbackBuffer.mapAsync(globals.GPUMapMode.READ);
const result = new Float32Array(readbackBuffer.getMappedRange().slice(0));
readbackBuffer.unmap();

console.log(JSON.stringify(Array.from(result)));
