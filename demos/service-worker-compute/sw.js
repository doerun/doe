// sw.js — Service worker intercepting POST requests to ./gpu-compute and
// running WebGPU compute on the payload. Demonstrates that WebGPU is fully
// available in service worker scope — no page required for GPU access.
//
// Request:  POST ./gpu-compute  body: Float32Array bytes
// Response: 200 application/octet-stream  body: Float32Array bytes (result)

self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

// GPU device is lazily initialized and reused across requests.
let device = null;

async function getDevice() {
  if (device) return device;
  if (!self.navigator?.gpu) throw new Error('WebGPU not available in this service worker');
  const adapter = await navigator.gpu.requestAdapter();
  if (!adapter) throw new Error('No WebGPU adapter');
  device = await adapter.requestDevice();
  device.addEventListener('uncapturederror', () => { device = null; });
  return device;
}

async function runCompute(inputBuffer) {
  const d = await getDevice();
  const input = new Float32Array(inputBuffer);
  const count = input.length;
  const byteSize = count * Float32Array.BYTES_PER_ELEMENT;

  const storageBuf = d.createBuffer({
    size: byteSize,
    usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC | GPUBufferUsage.COPY_DST,
  });
  const readbackBuf = d.createBuffer({
    size: byteSize,
    usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ,
  });

  d.queue.writeBuffer(storageBuf, 0, input);

  const shader = d.createShaderModule({
    code: `
      @group(0) @binding(0) var<storage, read_write> buf: array<f32>;
      @compute @workgroup_size(64)
      fn main(@builtin(global_invocation_id) id: vec3u) {
        if (id.x < arrayLength(&buf)) { buf[id.x] = buf[id.x] * 2.0; }
      }
    `,
  });
  const pipeline = d.createComputePipeline({
    layout: 'auto',
    compute: { module: shader, entryPoint: 'main' },
  });
  const bindGroup = d.createBindGroup({
    layout: pipeline.getBindGroupLayout(0),
    entries: [{ binding: 0, resource: { buffer: storageBuf } }],
  });

  const enc = d.createCommandEncoder();
  const pass = enc.beginComputePass();
  pass.setPipeline(pipeline);
  pass.setBindGroup(0, bindGroup);
  pass.dispatchWorkgroups(Math.ceil(count / 64));
  pass.end();
  enc.copyBufferToBuffer(storageBuf, 0, readbackBuf, 0, byteSize);
  d.queue.submit([enc.finish()]);
  await d.queue.onSubmittedWorkDone();

  await readbackBuf.mapAsync(GPUMapMode.READ);
  const result = readbackBuf.getMappedRange().slice(0);
  readbackBuf.unmap();
  storageBuf.destroy();
  readbackBuf.destroy();

  return result;
}

self.addEventListener('fetch', (event) => {
  if (!event.request.url.endsWith('/gpu-compute')) return;
  if (event.request.method !== 'POST') {
    event.respondWith(new Response('Method Not Allowed', { status: 405 }));
    return;
  }
  event.respondWith(
    event.request.arrayBuffer().then((body) =>
      runCompute(body).then(
        (result) => new Response(result, {
          headers: { 'content-type': 'application/octet-stream' },
        }),
        (err) => new Response(JSON.stringify({ error: err.message }), {
          status: 500,
          headers: { 'content-type': 'application/json' },
        }),
      )
    )
  );
});
