// Provider-agnostic WebGPU benchmark workloads.
// Each workload: (device, queue, globals) => { setup, run, teardown, validate? }
//
// Comparability note: Dawn queue.submit() is non-blocking; Doe is synchronous.
// "fire-and-forget" dispatch workloads are NOT comparable across providers.
// End-to-end workloads (dispatch + readback) ARE comparable because both
// providers must wait for GPU completion.

export const workloads = [
  // ================================================================
  // Upload workloads (comparable: writeBuffer is synchronous in both)
  // ================================================================
  {
    id: 'buffer_upload_1kb',
    domain: 'upload',
    comparable: true,
    description: 'Write 1 KB to GPU buffer via queue.writeBuffer',
    factory: (device, queue, G) => {
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
    },
  },
  {
    id: 'buffer_upload_64kb',
    domain: 'upload',
    comparable: true,
    description: 'Write 64 KB to GPU buffer via queue.writeBuffer',
    factory: (device, queue, G) => {
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
    },
  },
  {
    id: 'buffer_upload_1mb',
    domain: 'upload',
    comparable: true,
    description: 'Write 1 MB to GPU buffer via queue.writeBuffer',
    factory: (device, queue, G) => {
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
    },
  },
  {
    id: 'buffer_upload_16mb',
    domain: 'upload',
    comparable: true,
    description: 'Write 16 MB to GPU buffer via queue.writeBuffer',
    factory: (device, queue, G) => {
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
    },
  },
  {
    id: 'buffer_map_write_unmap',
    domain: 'upload',
    comparable: true,
    description: 'Map buffer for writing, fill 64 KB, unmap',
    factory: (device, queue, G) => {
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
    },
  },

  // ================================================================
  // End-to-end compute (comparable: both wait for GPU completion)
  // ================================================================
  {
    id: 'compute_e2e_256',
    domain: 'compute',
    comparable: true,
    description: 'End-to-end: dispatch 256 threads + readback',
    factory: makeComputeE2E(256, 64),
  },
  {
    id: 'compute_e2e_4096',
    domain: 'compute',
    comparable: true,
    description: 'End-to-end: dispatch 4096 threads + readback',
    factory: makeComputeE2E(4096, 256),
  },
  {
    id: 'compute_e2e_65536',
    domain: 'compute',
    comparable: true,
    description: 'End-to-end: dispatch 65536 threads + readback',
    factory: makeComputeE2E(65536, 256),
  },

  // ================================================================
  // Dispatch-only (NOT comparable: Dawn async vs Doe sync)
  // ================================================================
  {
    id: 'compute_dispatch_simple',
    domain: 'compute',
    comparable: false,
    description: 'Dispatch 256-thread compute (Dawn async, Doe sync — not comparable)',
    factory: (device, queue, G) => {
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
    },
  },

  // ================================================================
  // Overhead workloads
  // ================================================================
  {
    id: 'submit_empty',
    domain: 'overhead',
    comparable: false,
    description: 'Submit empty command buffer (Dawn async vs Doe sync)',
    factory: (device, queue, G) => ({
      setup() {},
      run() {
        const enc = device.createCommandEncoder();
        queue.submit([enc.finish()]);
      },
      teardown() {},
    }),
  },
  {
    id: 'pipeline_create',
    domain: 'pipeline',
    comparable: false,
    description: 'Create compute pipeline from WGSL (Doe: MSL compile, Dawn: cached)',
    factory: (device, queue, G) => {
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
    },
  },
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
    let storageBuf, stagingBuf, shader, pipeline, bindGroupLayout, bindGroup, pipelineLayout, input;
    const validateBytes = Math.min(size, VALIDATE_FLOATS * Float32Array.BYTES_PER_ELEMENT);
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
        stagingBuf.getMappedRange();
        stagingBuf.unmap();
      },
      async validate() {
        await this.run();
        await stagingBuf.mapAsync(G.GPUMapMode.READ, 0, validateBytes);
        const mapped = new Float32Array(stagingBuf.getMappedRange(0, validateBytes));
        for (let i = 0; i < Math.min(VALIDATE_FLOATS, threadCount); i++) {
          if (mapped[i] !== 1.0) {
            stagingBuf.unmap();
            return { ok: false, detail: `expected readback[${i}] === 1, got ${mapped[i]}` };
          }
        }
        stagingBuf.unmap();
        queue.writeBuffer(storageBuf, 0, input);
        return { ok: true };
      },
      teardown() {
        storageBuf.destroy();
        stagingBuf.destroy();
      },
    };
  };
}
