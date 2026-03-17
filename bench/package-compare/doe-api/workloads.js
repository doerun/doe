// Workloads for webgpu-doe helper API benchmarks.
// Left (doe-api): uses createDoeNamespace().bind(device) helpers.
// Right (raw WebGPU): uses standard WebGPU API directly.
// Both sides perform identical GPU work — dispatch compute + readback.
//
// Comparability: all kernel/batch workloads are comparable because both sides
// wait for GPU completion via mapAsync readback. compute_once is not comparable
// because it includes shader compilation per call (varies by implementation).

import { createDoeNamespace } from '../../../packages/webgpu-doe/src/index.js';

const SHADER_MULTIPLY = `
@group(0) @binding(0) var<storage, read> input: array<f32>;
@group(0) @binding(1) var<storage, read_write> output: array<f32>;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) gid: vec3u) {
  let i = gid.x;
  if (i < arrayLength(&input)) {
    output[i] = input[i] * 2.0;
  }
}`;

function defineWorkload(id, domain, comparable, factory) {
  return { id, canonicalWorkloadId: id, domain, comparable, factory };
}

function makeInputData(elements) {
  const data = new Float32Array(elements);
  for (let i = 0; i < elements; i++) data[i] = i + 1;
  return data;
}

function makeKernelDispatch(elements) {
  const WORKGROUPS = Math.ceil(elements / 64);
  const BYTE_SIZE = elements * 4;

  return (device, queue, G) => {
    const inputData = makeInputData(elements);

    if (G.doeApi) {
      const gpu = createDoeNamespace().bind(device);
      let srcBuf, dstBuf, kernel;
      return {
        setup() {
          srcBuf = gpu.buffer.create({ data: inputData, usage: 'storageRead' });
          dstBuf = gpu.buffer.create({ size: BYTE_SIZE, usage: 'storageReadWrite' });
          kernel = gpu.kernel.create({ code: SHADER_MULTIPLY, bindings: [srcBuf, dstBuf] });
        },
        async run() {
          await kernel.dispatch({ bindings: [srcBuf, dstBuf], workgroups: WORKGROUPS });
          await gpu.buffer.read(dstBuf, Float32Array);
        },
        teardown() {
          dstBuf.destroy();
          srcBuf.destroy();
        },
      };
    }

    let pipeline, srcBuf, dstBuf, readBuf, bindGroup;
    return {
      setup() {
        const shader = device.createShaderModule({ code: SHADER_MULTIPLY });
        const bgl = device.createBindGroupLayout({
          entries: [
            { binding: 0, visibility: G.GPUShaderStage.COMPUTE, buffer: { type: 'read-only-storage' } },
            { binding: 1, visibility: G.GPUShaderStage.COMPUTE, buffer: { type: 'storage' } },
          ],
        });
        pipeline = device.createComputePipeline({
          layout: device.createPipelineLayout({ bindGroupLayouts: [bgl] }),
          compute: { module: shader, entryPoint: 'main' },
        });
        srcBuf = device.createBuffer({ size: BYTE_SIZE, usage: G.GPUBufferUsage.STORAGE | G.GPUBufferUsage.COPY_DST });
        dstBuf = device.createBuffer({ size: BYTE_SIZE, usage: G.GPUBufferUsage.STORAGE | G.GPUBufferUsage.COPY_SRC });
        readBuf = device.createBuffer({ size: BYTE_SIZE, usage: G.GPUBufferUsage.MAP_READ | G.GPUBufferUsage.COPY_DST });
        queue.writeBuffer(srcBuf, 0, inputData);
        bindGroup = device.createBindGroup({
          layout: bgl,
          entries: [
            { binding: 0, resource: { buffer: srcBuf } },
            { binding: 1, resource: { buffer: dstBuf } },
          ],
        });
      },
      async run() {
        const enc = device.createCommandEncoder();
        const pass = enc.beginComputePass();
        pass.setPipeline(pipeline);
        pass.setBindGroup(0, bindGroup);
        pass.dispatchWorkgroups(WORKGROUPS);
        pass.end();
        enc.copyBufferToBuffer(dstBuf, 0, readBuf, 0, BYTE_SIZE);
        queue.submit([enc.finish()]);
        await readBuf.mapAsync(G.GPUMapMode.READ);
        readBuf.getMappedRange().slice(0);
        readBuf.unmap();
      },
      teardown() {
        srcBuf.destroy();
        dstBuf.destroy();
        readBuf.destroy();
      },
    };
  };
}

function makeBatchDispatch(dispatchCount, elementsPerDispatch) {
  const WORKGROUPS = Math.ceil(elementsPerDispatch / 64);
  const BYTE_SIZE = elementsPerDispatch * 4;

  return (device, queue, G) => {
    const inputs = [];
    for (let i = 0; i < dispatchCount; i++) {
      inputs.push(makeInputData(elementsPerDispatch));
    }

    if (G.doeApi) {
      const gpu = createDoeNamespace().bind(device);
      let kernel;
      const srcBufs = [];
      const dstBufs = [];
      const bindingSets = [];
      return {
        setup() {
          for (let i = 0; i < dispatchCount; i++) {
            srcBufs.push(gpu.buffer.create({ data: inputs[i], usage: 'storageRead' }));
            dstBufs.push(gpu.buffer.create({ size: BYTE_SIZE, usage: 'storageReadWrite' }));
          }
          kernel = gpu.kernel.create({ code: SHADER_MULTIPLY, bindings: [srcBufs[0], dstBufs[0]] });
          for (let i = 0; i < dispatchCount; i++) {
            bindingSets.push(kernel.bindings.create([srcBufs[i], dstBufs[i]]));
          }
        },
        async run() {
          const batch = gpu.compute.begin();
          for (let i = 0; i < dispatchCount; i++) {
            batch.dispatch(kernel, { bindings: bindingSets[i], workgroups: WORKGROUPS });
          }
          await batch.submit();
          await gpu.buffer.read(dstBufs[dispatchCount - 1], Float32Array);
        },
        teardown() {
          for (const b of [...srcBufs, ...dstBufs]) b.destroy();
        },
      };
    }

    let pipeline;
    const srcBufs = [];
    const dstBufs = [];
    const bindGroups = [];
    let readBuf;
    return {
      setup() {
        const shader = device.createShaderModule({ code: SHADER_MULTIPLY });
        const bgl = device.createBindGroupLayout({
          entries: [
            { binding: 0, visibility: G.GPUShaderStage.COMPUTE, buffer: { type: 'read-only-storage' } },
            { binding: 1, visibility: G.GPUShaderStage.COMPUTE, buffer: { type: 'storage' } },
          ],
        });
        pipeline = device.createComputePipeline({
          layout: device.createPipelineLayout({ bindGroupLayouts: [bgl] }),
          compute: { module: shader, entryPoint: 'main' },
        });
        for (let i = 0; i < dispatchCount; i++) {
          const src = device.createBuffer({ size: BYTE_SIZE, usage: G.GPUBufferUsage.STORAGE | G.GPUBufferUsage.COPY_DST });
          const dst = device.createBuffer({ size: BYTE_SIZE, usage: G.GPUBufferUsage.STORAGE | G.GPUBufferUsage.COPY_SRC });
          queue.writeBuffer(src, 0, inputs[i]);
          srcBufs.push(src);
          dstBufs.push(dst);
          bindGroups.push(device.createBindGroup({
            layout: bgl,
            entries: [
              { binding: 0, resource: { buffer: src } },
              { binding: 1, resource: { buffer: dst } },
            ],
          }));
        }
        readBuf = device.createBuffer({ size: BYTE_SIZE, usage: G.GPUBufferUsage.MAP_READ | G.GPUBufferUsage.COPY_DST });
      },
      async run() {
        const enc = device.createCommandEncoder();
        const pass = enc.beginComputePass();
        for (let i = 0; i < dispatchCount; i++) {
          pass.setPipeline(pipeline);
          pass.setBindGroup(0, bindGroups[i]);
          pass.dispatchWorkgroups(WORKGROUPS);
        }
        pass.end();
        enc.copyBufferToBuffer(dstBufs[dispatchCount - 1], 0, readBuf, 0, BYTE_SIZE);
        queue.submit([enc.finish()]);
        await readBuf.mapAsync(G.GPUMapMode.READ);
        readBuf.getMappedRange().slice(0);
        readBuf.unmap();
      },
      teardown() {
        for (const b of [...srcBufs, ...dstBufs]) b.destroy();
        readBuf.destroy();
      },
    };
  };
}

function makeBufferRoundtrip(bytes) {
  const elements = bytes / 4;

  return (device, queue, G) => {
    const inputData = makeInputData(elements);

    if (G.doeApi) {
      const gpu = createDoeNamespace().bind(device);
      let buf;
      return {
        setup() {
          buf = gpu.buffer.create({
            data: inputData,
            usage: ['storageRead', 'readback'],
          });
        },
        async run() {
          await gpu.buffer.read(buf, Float32Array);
        },
        teardown() {
          buf.destroy();
        },
      };
    }

    let srcBuf, readBuf;
    return {
      setup() {
        srcBuf = device.createBuffer({
          size: bytes,
          usage: G.GPUBufferUsage.STORAGE | G.GPUBufferUsage.COPY_DST | G.GPUBufferUsage.COPY_SRC,
        });
        readBuf = device.createBuffer({
          size: bytes,
          usage: G.GPUBufferUsage.MAP_READ | G.GPUBufferUsage.COPY_DST,
        });
        queue.writeBuffer(srcBuf, 0, inputData);
      },
      async run() {
        const enc = device.createCommandEncoder();
        enc.copyBufferToBuffer(srcBuf, 0, readBuf, 0, bytes);
        queue.submit([enc.finish()]);
        await readBuf.mapAsync(G.GPUMapMode.READ);
        readBuf.getMappedRange().slice(0);
        readBuf.unmap();
      },
      teardown() {
        srcBuf.destroy();
        readBuf.destroy();
      },
    };
  };
}

function makeComputeOnce(elements) {
  const WORKGROUPS = Math.ceil(elements / 64);
  const BYTE_SIZE = elements * 4;

  return (device, queue, G) => {
    const inputData = makeInputData(elements);

    if (G.doeApi) {
      const gpu = createDoeNamespace().bind(device);
      return {
        async run() {
          await gpu.compute({
            code: SHADER_MULTIPLY,
            inputs: [inputData],
            output: { type: Float32Array },
            workgroups: WORKGROUPS,
          });
        },
      };
    }

    return {
      async run() {
        const shader = device.createShaderModule({ code: SHADER_MULTIPLY });
        const bgl = device.createBindGroupLayout({
          entries: [
            { binding: 0, visibility: G.GPUShaderStage.COMPUTE, buffer: { type: 'read-only-storage' } },
            { binding: 1, visibility: G.GPUShaderStage.COMPUTE, buffer: { type: 'storage' } },
          ],
        });
        const pl = device.createComputePipeline({
          layout: device.createPipelineLayout({ bindGroupLayouts: [bgl] }),
          compute: { module: shader, entryPoint: 'main' },
        });
        const srcBuf = device.createBuffer({ size: BYTE_SIZE, usage: G.GPUBufferUsage.STORAGE | G.GPUBufferUsage.COPY_DST });
        const dstBuf = device.createBuffer({ size: BYTE_SIZE, usage: G.GPUBufferUsage.STORAGE | G.GPUBufferUsage.COPY_SRC });
        const readBuf = device.createBuffer({ size: BYTE_SIZE, usage: G.GPUBufferUsage.MAP_READ | G.GPUBufferUsage.COPY_DST });
        queue.writeBuffer(srcBuf, 0, inputData);
        const bg = device.createBindGroup({
          layout: bgl,
          entries: [
            { binding: 0, resource: { buffer: srcBuf } },
            { binding: 1, resource: { buffer: dstBuf } },
          ],
        });
        const enc = device.createCommandEncoder();
        const pass = enc.beginComputePass();
        pass.setPipeline(pl);
        pass.setBindGroup(0, bg);
        pass.dispatchWorkgroups(WORKGROUPS);
        pass.end();
        enc.copyBufferToBuffer(dstBuf, 0, readBuf, 0, BYTE_SIZE);
        queue.submit([enc.finish()]);
        await readBuf.mapAsync(G.GPUMapMode.READ);
        readBuf.getMappedRange().slice(0);
        readBuf.unmap();
        srcBuf.destroy();
        dstBuf.destroy();
        readBuf.destroy();
      },
    };
  };
}

export const workloads = [
  // Reusable kernel dispatch (comparable: both sides wait for GPU via readback)
  defineWorkload('doe_api_kernel_dispatch_4096', 'compute', true, makeKernelDispatch(4096)),
  defineWorkload('doe_api_kernel_dispatch_65536', 'compute', true, makeKernelDispatch(65536)),
  defineWorkload('doe_api_kernel_dispatch_262144', 'compute', true, makeKernelDispatch(262144)),

  // Batched dispatch (comparable: both sides wait for GPU via readback)
  defineWorkload('doe_api_batch_4x4096', 'compute', true, makeBatchDispatch(4, 4096)),
  defineWorkload('doe_api_batch_10x4096', 'compute', true, makeBatchDispatch(10, 4096)),

  // Buffer roundtrip (comparable: both sides do GPU copy + readback)
  defineWorkload('doe_api_buffer_roundtrip_16kb', 'copy', true, makeBufferRoundtrip(16384)),
  defineWorkload('doe_api_buffer_roundtrip_64kb', 'copy', true, makeBufferRoundtrip(65536)),

  // One-shot compute (not comparable: includes per-call shader compilation)
  defineWorkload('doe_api_compute_once_4096', 'compute', false, makeComputeOnce(4096)),
];
