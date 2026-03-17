// compute-worker.js — Browser dedicated Web Worker running WebGPU compute.
//
// Receives: { data: ArrayBuffer }  (Float32Array backing store)
// Posts:    { result: ArrayBuffer } (transferable) or { error: string }
self.addEventListener('message', async ({ data: msg }) => {
  try {
    if (!navigator.gpu) throw new Error('WebGPU not available in this worker context');
    const adapter = await navigator.gpu.requestAdapter();
    if (!adapter) throw new Error('No WebGPU adapter');
    const device = await adapter.requestDevice();

    const input = new Float32Array(msg.data);
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
    device.destroy();

    self.postMessage({ result }, [result]);
  } catch (e) {
    self.postMessage({ error: e.message });
  }
});
