// worker-compute.js — WebGPU compute task runner in a Node.js worker thread.
//
// Accepts messages: { data: Float32Array | number[] }
// Posts results:    { result: ArrayBuffer }  (transferable, caller wraps in Float32Array)
//
// The GPU device is initialized once and reused across messages — callers can
// dispatch multiple jobs to the same worker to amortize initialization cost.
import { parentPort } from 'node:worker_threads';
import { globals, requestDevice } from '@simulatte/webgpu';

const device = await requestDevice();
const { GPUBufferUsage, GPUMapMode } = globals;

parentPort.on('message', async ({ data }) => {
  const input = new Float32Array(data);
  const count = input.length;
  const byteSize = count * Float32Array.BYTES_PER_ELEMENT;

  const storageBuf = device.createBuffer({
    size: byteSize,
    usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC | GPUBufferUsage.COPY_DST,
  });
  const readbackBuf = device.createBuffer({
    size: byteSize,
    usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ,
  });

  device.queue.writeBuffer(storageBuf, 0, input);

  const shader = device.createShaderModule({
    code: `
      @group(0) @binding(0) var<storage, read_write> buf: array<f32>;
      @compute @workgroup_size(64)
      fn main(@builtin(global_invocation_id) id: vec3u) {
        if (id.x < arrayLength(&buf)) { buf[id.x] = buf[id.x] * 2.0; }
      }
    `,
  });

  const pipeline = device.createComputePipeline({
    layout: 'auto',
    compute: { module: shader, entryPoint: 'main' },
  });

  const bindGroup = device.createBindGroup({
    layout: pipeline.getBindGroupLayout(0),
    entries: [{ binding: 0, resource: { buffer: storageBuf } }],
  });

  const enc = device.createCommandEncoder();
  const pass = enc.beginComputePass();
  pass.setPipeline(pipeline);
  pass.setBindGroup(0, bindGroup);
  pass.dispatchWorkgroups(Math.ceil(count / 64));
  pass.end();
  enc.copyBufferToBuffer(storageBuf, 0, readbackBuf, 0, byteSize);
  device.queue.submit([enc.finish()]);
  await device.queue.onSubmittedWorkDone();

  await readbackBuf.mapAsync(GPUMapMode.READ);
  const result = readbackBuf.getMappedRange().slice(0);
  readbackBuf.unmap();

  storageBuf.destroy();
  readbackBuf.destroy();

  parentPort.postMessage({ result }, [result]);
});
