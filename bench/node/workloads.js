// Provider-agnostic WebGPU benchmark workloads.
// Each workload: (device, queue, globals) => { setup, run, teardown, validate? }
//
// Comparability note: Dawn queue.submit() is non-blocking; Doe is synchronous.
// "fire-and-forget" dispatch workloads are NOT comparable across providers.
// End-to-end workloads (dispatch + readback) ARE comparable because both
// providers must wait for GPU completion.

import { packageWorkloadContract } from './workload_contracts.js';

function defineWorkload(id, comparable, factory) {
  return {
    ...packageWorkloadContract(id, comparable),
    factory,
  };
}

export const workloads = [
  // ================================================================
  // Upload workloads (comparable: writeBuffer is synchronous in both)
  // ================================================================
  defineWorkload('buffer_upload_1kb', true, (device, queue, G) => {
      const size = 1024;
      const data = new Uint8Array(size);
      let buf;
      return {
        setup() {
          buf = device.createBuffer({ size, usage: G.GPUBufferUsage.STORAGE | G.GPUBufferUsage.COPY_DST });
        },
        run() { queue.writeBuffer(buf, 0, data); },
        teardown() { buf.destroy(); },
      };
    }),
  defineWorkload('buffer_upload_64kb', true, (device, queue, G) => {
      const size = 65536;
      const data = new Uint8Array(size);
      let buf;
      return {
        setup() {
          buf = device.createBuffer({ size, usage: G.GPUBufferUsage.STORAGE | G.GPUBufferUsage.COPY_DST });
        },
        run() { queue.writeBuffer(buf, 0, data); },
        teardown() { buf.destroy(); },
      };
    }),
  defineWorkload('buffer_upload_1mb', true, (device, queue, G) => {
      const size = 1024 * 1024;
      const data = new Uint8Array(size);
      let buf;
      return {
        setup() {
          buf = device.createBuffer({ size, usage: G.GPUBufferUsage.STORAGE | G.GPUBufferUsage.COPY_DST });
        },
        run() { queue.writeBuffer(buf, 0, data); },
        teardown() { buf.destroy(); },
      };
    }),
  defineWorkload('buffer_upload_16mb', true, (device, queue, G) => {
      const size = 16 * 1024 * 1024;
      const data = new Uint8Array(size);
      let buf;
      return {
        setup() {
          buf = device.createBuffer({ size, usage: G.GPUBufferUsage.STORAGE | G.GPUBufferUsage.COPY_DST });
        },
        run() { queue.writeBuffer(buf, 0, data); },
        teardown() { buf.destroy(); },
      };
    }),
  defineWorkload('buffer_map_write_unmap', true, (device, queue, G) => {
      const size = 65536;
      let buf;
      return {
        setup() {
          buf = device.createBuffer({
            size,
            usage: G.GPUBufferUsage.MAP_WRITE | G.GPUBufferUsage.COPY_SRC,
            mappedAtCreation: true,
          });
          buf.unmap();
        },
        async run() {
          await buf.mapAsync(G.GPUMapMode.WRITE);
          const range = buf.getMappedRange();
          new Uint8Array(range).fill(0xAB);
          buf.unmap();
        },
        teardown() { buf.destroy(); },
      };
    }),

  // ================================================================
  // End-to-end compute (comparable: both wait for GPU completion)
  // ================================================================
  defineWorkload('compute_e2e_256', true, makeComputeE2E(256, 64)),
  defineWorkload('compute_e2e_4096', true, makeComputeE2E(4096, 256)),
  defineWorkload('compute_e2e_65536', true, makeComputeE2E(65536, 256)),
  defineWorkload('copy_buffer_to_buffer_4kb', true, makeCopyBufferToBufferE2E(4096)),

  // ================================================================
  // Dispatch-only (NOT comparable: Dawn async vs Doe sync)
  // ================================================================
  defineWorkload('compute_dispatch_simple', false, (device, queue, G) => {
      const COUNT = 256;
      const size = COUNT * 4;
      const wgsl = `
        @group(0) @binding(0) var<storage, read_write> data: array<f32>;
        @compute @workgroup_size(64)
        fn main(@builtin(global_invocation_id) id: vec3u) {
          data[id.x] = data[id.x] * 2.0;
        }
      `;
      let storageBuf, shader, pipeline, bindGroupLayout, bindGroup, pipelineLayout;
      return {
        setup() {
          storageBuf = device.createBuffer({
            size,
            usage: G.GPUBufferUsage.STORAGE | G.GPUBufferUsage.COPY_SRC | G.GPUBufferUsage.COPY_DST,
          });
          const input = new Float32Array(COUNT);
          for (let i = 0; i < COUNT; i++) input[i] = i;
          queue.writeBuffer(storageBuf, 0, input);
          shader = device.createShaderModule({ code: wgsl });
          bindGroupLayout = device.createBindGroupLayout({
            entries: [{ binding: 0, visibility: G.GPUShaderStage.COMPUTE, buffer: { type: 'storage' } }],
          });
          pipelineLayout = device.createPipelineLayout({ bindGroupLayouts: [bindGroupLayout] });
          pipeline = device.createComputePipeline({
            layout: pipelineLayout,
            compute: { module: shader, entryPoint: 'main' },
          });
          bindGroup = device.createBindGroup({
            layout: bindGroupLayout,
            entries: [{ binding: 0, resource: { buffer: storageBuf } }],
          });
        },
        run() {
          const enc = device.createCommandEncoder();
          const pass = enc.beginComputePass();
          pass.setPipeline(pipeline);
          pass.setBindGroup(0, bindGroup);
          pass.dispatchWorkgroups(COUNT / 64);
          pass.end();
          queue.submit([enc.finish()]);
        },
        teardown() { storageBuf.destroy(); },
      };
    }),

  // ================================================================
  // Overhead workloads
  // ================================================================
  defineWorkload('submit_empty', false, (device, queue, G) => ({
      setup() {},
      run() {
        const enc = device.createCommandEncoder();
        queue.submit([enc.finish()]);
      },
      teardown() {},
    })),
  defineWorkload('pipeline_create', false, (device, queue, G) => {
      const wgsl = `
        @group(0) @binding(0) var<storage, read_write> out: array<u32>;
        @compute @workgroup_size(64)
        fn main(@builtin(global_invocation_id) id: vec3u) {
          out[id.x] = id.x * 7u;
        }
      `;
      let shader, bindGroupLayout, pipelineLayout;
      return {
        setup() {
          shader = device.createShaderModule({ code: wgsl });
          bindGroupLayout = device.createBindGroupLayout({
            entries: [{ binding: 0, visibility: G.GPUShaderStage.COMPUTE, buffer: { type: 'storage' } }],
          });
          pipelineLayout = device.createPipelineLayout({ bindGroupLayouts: [bindGroupLayout] });
        },
        run() {
          device.createComputePipeline({
            layout: pipelineLayout,
            compute: { module: shader, entryPoint: 'main' },
          });
        },
        teardown() {},
      };
    }),
];

// Helper: create end-to-end compute workload (dispatch + copy + mapAsync readback).
function makeComputeE2E(threadCount, workgroupSize) {
  return (device, queue, G) => {
    const size = threadCount * 4;
    const VALIDATE_FLOATS = 4;
    const wgsl = `
      @group(0) @binding(0) var<storage, read_write> data: array<f32>;
      @compute @workgroup_size(${workgroupSize})
      fn main(@builtin(global_invocation_id) id: vec3u) {
        data[id.x] = data[id.x] + 1.0;
      }
    `;
    let storageBuf, stagingBuf, shader, pipeline, bindGroupLayout, bindGroup, pipelineLayout, input, expectedValue;
    const validateBytes = Math.min(size, VALIDATE_FLOATS * Float32Array.BYTES_PER_ELEMENT);
    function assertReadbackMatchesCurrentIteration() {
      const mapped = new Float32Array(stagingBuf.getMappedRange(0, validateBytes));
      for (let i = 0; i < Math.min(VALIDATE_FLOATS, threadCount); i++) {
        if (mapped[i] !== expectedValue) {
          throw new Error(`expected readback[${i}] === ${expectedValue}, got ${mapped[i]}`);
        }
      }
      expectedValue += 1;
    }
    return {
      setup() {
        storageBuf = device.createBuffer({
          size,
          usage: G.GPUBufferUsage.STORAGE | G.GPUBufferUsage.COPY_SRC | G.GPUBufferUsage.COPY_DST,
        });
        stagingBuf = device.createBuffer({
          size,
          usage: G.GPUBufferUsage.MAP_READ | G.GPUBufferUsage.COPY_DST,
        });
        input = new Float32Array(threadCount);
        expectedValue = 1;
        queue.writeBuffer(storageBuf, 0, input);
        shader = device.createShaderModule({ code: wgsl });
        bindGroupLayout = device.createBindGroupLayout({
          entries: [{ binding: 0, visibility: G.GPUShaderStage.COMPUTE, buffer: { type: 'storage' } }],
        });
        pipelineLayout = device.createPipelineLayout({ bindGroupLayouts: [bindGroupLayout] });
        pipeline = device.createComputePipeline({
          layout: pipelineLayout,
          compute: { module: shader, entryPoint: 'main' },
        });
        bindGroup = device.createBindGroup({
          layout: bindGroupLayout,
          entries: [{ binding: 0, resource: { buffer: storageBuf } }],
        });
      },
      async run() {
        const enc = device.createCommandEncoder();
        const pass = enc.beginComputePass();
        pass.setPipeline(pipeline);
        pass.setBindGroup(0, bindGroup);
        pass.dispatchWorkgroups(threadCount / workgroupSize);
        pass.end();
        enc.copyBufferToBuffer(storageBuf, 0, stagingBuf, 0, size);
        queue.submit([enc.finish()]);
        await queue.onSubmittedWorkDone();
        await stagingBuf.mapAsync(G.GPUMapMode.READ);
        assertReadbackMatchesCurrentIteration();
        stagingBuf.unmap();
      },
      async validate() {
        await this.run();
        queue.writeBuffer(storageBuf, 0, input);
        expectedValue = 1;
        return { ok: true };
      },
      teardown() {
        storageBuf.destroy();
        stagingBuf.destroy();
      },
    };
  };
}

function makeCopyBufferToBufferE2E(size) {
  return (device, queue, G) => {
    const sourceBytes = new Uint8Array(size);
    for (let i = 0; i < sourceBytes.length; i++) {
      sourceBytes[i] = i & 0xff;
    }

    const validateBytes = Math.min(size, 64);
    let srcBuf, dstBuf;

    async function assertReadbackMatchesSource() {
      await dstBuf.mapAsync(G.GPUMapMode.READ, 0, validateBytes);
      const mapped = new Uint8Array(dstBuf.getMappedRange(0, validateBytes));
      for (let i = 0; i < validateBytes; i++) {
        if (mapped[i] !== sourceBytes[i]) {
          throw new Error(`expected copied byte ${i} === ${sourceBytes[i]}, got ${mapped[i]}`);
        }
      }
      dstBuf.unmap();
    }

    return {
      setup() {
        srcBuf = device.createBuffer({
          size,
          usage: G.GPUBufferUsage.COPY_SRC | G.GPUBufferUsage.COPY_DST,
        });
        dstBuf = device.createBuffer({
          size,
          usage: G.GPUBufferUsage.COPY_DST | G.GPUBufferUsage.MAP_READ,
        });
        queue.writeBuffer(srcBuf, 0, sourceBytes);
      },
      async run() {
        const encoder = device.createCommandEncoder();
        encoder.copyBufferToBuffer(srcBuf, 0, dstBuf, 0, size);
        queue.submit([encoder.finish()]);
        await queue.onSubmittedWorkDone();
        await assertReadbackMatchesSource();
      },
      async validate() {
        await this.run();
        return { ok: true };
      },
      teardown() {
        srcBuf.destroy();
        dstBuf.destroy();
      },
    };
  };
}
