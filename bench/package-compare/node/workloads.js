// Provider-agnostic WebGPU benchmark workloads.
// Each workload: (device, queue, globals) => { setup, run, teardown, validate? }
//
// Comparability note: Dawn queue.submit() is non-blocking; Doe is synchronous.
// "fire-and-forget" dispatch workloads are NOT comparable across providers.
// End-to-end workloads (dispatch + readback) ARE comparable because both
// providers must wait for GPU completion.

import { packageWorkloadContract } from './workload_contracts.js';

const VALIDATE_RETRY_LIMIT = 6;
const COPY_VALIDATE_BYTES = 64;

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
  defineWorkload('compute_e2e_262144', true, makeComputeE2E(262144, 256)),
  defineWorkload('copy_buffer_to_buffer_4kb', true, makeCopyBufferToBufferE2E(4096)),
  defineWorkload('copy_buffer_to_buffer_64kb', true, makeCopyBufferToBufferE2E(65536)),
  defineWorkload('copy_buffer_to_buffer_1mb', true, makeCopyBufferToBufferE2E(1024 * 1024)),

  // ================================================================
  // Texture copy roundtrip (comparable: GPU copy + readback, both wait)
  // ================================================================
  defineWorkload('texture_copy_roundtrip_64x64', true, makeTextureCopyRoundtripE2E(64, 64)),
  defineWorkload('texture_copy_roundtrip_256x256', true, makeTextureCopyRoundtripE2E(256, 256)),

  // MAP_READ lifecycle (comparable: both wait for mapAsync completion)
  defineWorkload('buffer_map_read_unmap', true, (device, queue, G) => {
      const size = 65536;
      const pattern = new Uint8Array(size);
      for (let i = 0; i < size; i++) pattern[i] = i & 0xff;
      let srcBuf, readBuf;
      return {
        setup() {
          srcBuf = device.createBuffer({
            size,
            usage: G.GPUBufferUsage.COPY_SRC | G.GPUBufferUsage.COPY_DST,
          });
          readBuf = device.createBuffer({
            size,
            usage: G.GPUBufferUsage.MAP_READ | G.GPUBufferUsage.COPY_DST,
          });
          queue.writeBuffer(srcBuf, 0, pattern);
        },
        async run() {
          const enc = device.createCommandEncoder();
          enc.copyBufferToBuffer(srcBuf, 0, readBuf, 0, size);
          queue.submit([enc.finish()]);
          await queue.onSubmittedWorkDone();
          await readBuf.mapAsync(G.GPUMapMode.READ);
          const mapped = new Uint8Array(readBuf.getMappedRange());
          if (mapped[0] !== 0 || mapped[255] !== 255) {
            throw new Error(`MAP_READ validation failed: [0]=${mapped[0]}, [255]=${mapped[255]}`);
          }
          readBuf.unmap();
        },
        teardown() {
          srcBuf.destroy();
          readBuf.destroy();
        },
      };
    }),

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
  // ================================================================
  // Shader compilation (not comparable: varies by compiler architecture)
  // ================================================================
  defineWorkload('shader_module_create', false, (device, _queue, _G) => {
      let iter = 0;
      return {
        run() {
          const n = iter++;
          device.createShaderModule({
            code: `
              @group(0) @binding(0) var<storage, read_write> data: array<f32>;
              @compute @workgroup_size(64)
              fn main(@builtin(global_invocation_id) id: vec3u) {
                data[id.x] = data[id.x] + ${n}.0;
              }
            `,
          });
        },
        teardown() {},
      };
    }),
  defineWorkload('pipeline_create', false, (device, queue, G) => {
      const wgsl = `
        @group(0) @binding(0) var<storage, read_write> data: array<f32>;
        @compute @workgroup_size(64)
        fn main(@builtin(global_invocation_id) id: vec3u) {
          data[id.x] = data[id.x] + 1.0;
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

  // ================================================================
  // Comparable replacements for directional-only JS-boundary rows
  // ================================================================
  defineWorkload('submit_trivial_and_wait', true, makeSubmitTrivialAndWait()),
  defineWorkload('compute_dispatch_and_wait_simple', true, makeComputeDispatchAndWaitSimple()),
  defineWorkload('pipeline_first_use_e2e', true, makePipelineFirstUseE2E()),

  // ================================================================
  // Render workloads (comparable: both sides wait for GPU completion via readback)
  // ================================================================
  defineWorkload('render_triangle_solid', true, makeRenderTriangleSolid()),
  defineWorkload('render_indexed_quad', true, makeRenderIndexedQuad()),
  defineWorkload('render_pass_switching', true, makeRenderPassSwitching()),

  // ================================================================
  // Texture copy: texture-to-texture (comparable: readback validates)
  // ================================================================
  defineWorkload('texture_to_texture_copy', true, makeTextureToTextureCopy()),

  // ================================================================
  // Sampler lifecycle (not comparable: creation timing varies)
  // ================================================================
  defineWorkload('sampler_create_destroy', false, (device, _queue, _G) => {
      return {
        run() {
          const filters = ['nearest', 'linear'];
          const modes = ['clamp-to-edge', 'repeat', 'mirror-repeat'];
          for (const magFilter of filters) {
            for (const addressModeU of modes) {
              device.createSampler({ magFilter, minFilter: 'nearest', addressModeU });
            }
          }
        },
        teardown() {},
      };
    }),

  // ================================================================
  // Timestamp query (not comparable: resolution differs by impl)
  // ================================================================
  defineWorkload('timestamp_query', false, makeTimestampQuery()),

  // ================================================================
  // Advanced compute: indirect dispatch (comparable: readback validates)
  // ================================================================
  defineWorkload('dispatch_indirect', true, makeDispatchIndirect()),

  // ================================================================
  // Render bundles (not comparable: bundle overhead differs)
  // ================================================================
  defineWorkload('render_bundle_replay', false, makeRenderBundleReplay()),
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
    async function resetInput() {
      queue.writeBuffer(storageBuf, 0, input);
      await queue.onSubmittedWorkDone?.();
    }
    function assertReadbackMatchesPreparedInput() {
      const validateCount = Math.min(VALIDATE_FLOATS, threadCount);
      if (typeof stagingBuf.assertMappedPrefixF32 === 'function') {
        stagingBuf.assertMappedPrefixF32(1, validateCount);
        return;
      }
      const mapped = new Float32Array(stagingBuf.getMappedRange(0, validateBytes));
      for (let i = 0; i < validateCount; i++) {
        if (mapped[i] !== 1) {
          throw new Error(`expected readback[${i}] === 1, got ${mapped[i]}`);
        }
      }
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
        return queue.onSubmittedWorkDone?.();
      },
      async prepareSample() {
        await resetInput();
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
        assertReadbackMatchesPreparedInput();
        stagingBuf.unmap();
      },
      async validate() {
        let lastError = null;
        // Validation budget is separate from timed-run readback retries.
        for (let attempt = 0; attempt < VALIDATE_RETRY_LIMIT; attempt++) {
          try {
            await this.prepareSample();
            await this.run();
            return { ok: true };
          } catch (err) {
            lastError = err;
          }
        }
        return { ok: false, detail: lastError?.message || 'validation retry budget exhausted' };
      },
      teardown() {
        storageBuf.destroy();
        stagingBuf.destroy();
      },
    };
  };
}

function makeSubmitTrivialAndWait() {
  return (device, queue, G) => {
    const size = Uint32Array.BYTES_PER_ELEMENT;
    const pattern = new Uint32Array([0x12345678]);
    let srcBuf, stagingBuf;

    async function assertReadbackMatchesSource() {
      await stagingBuf.mapAsync(G.GPUMapMode.READ, 0, size);
      const mapped = new Uint32Array(stagingBuf.getMappedRange(0, size));
      if (mapped[0] !== pattern[0]) {
        throw new Error(`submit_trivial_and_wait: expected ${pattern[0]}, got ${mapped[0]}`);
      }
      stagingBuf.unmap();
    }

    return {
      setup() {
        srcBuf = device.createBuffer({
          size,
          usage: G.GPUBufferUsage.COPY_SRC | G.GPUBufferUsage.COPY_DST,
        });
        stagingBuf = device.createBuffer({
          size,
          usage: G.GPUBufferUsage.COPY_DST | G.GPUBufferUsage.MAP_READ,
        });
        queue.writeBuffer(srcBuf, 0, pattern);
        return queue.onSubmittedWorkDone?.();
      },
      async run() {
        const enc = device.createCommandEncoder();
        enc.copyBufferToBuffer(srcBuf, 0, stagingBuf, 0, size);
        queue.submit([enc.finish()]);
        await queue.onSubmittedWorkDone();
        await assertReadbackMatchesSource();
      },
      async validate() {
        await this.run();
        return { ok: true };
      },
      teardown() {
        srcBuf.destroy();
        stagingBuf.destroy();
      },
    };
  };
}

function makeComputeDispatchAndWaitSimple() {
  return (device, queue, G) => {
    const COUNT = 256;
    const size = COUNT * Float32Array.BYTES_PER_ELEMENT;
    const validateBytes = 4 * Float32Array.BYTES_PER_ELEMENT;
    const wgsl = `
      @group(0) @binding(0) var<storage, read_write> data: array<f32>;
      @compute @workgroup_size(64)
      fn main(@builtin(global_invocation_id) id: vec3u) {
        data[id.x] = data[id.x] * 2.0;
      }
    `;
    let storageBuf, stagingBuf, shader, pipeline, bindGroupLayout, bindGroup, pipelineLayout, input;

    async function resetInput() {
      queue.writeBuffer(storageBuf, 0, input);
      await queue.onSubmittedWorkDone?.();
    }

    function assertReadbackMatchesPreparedInput() {
      const mapped = new Float32Array(stagingBuf.getMappedRange(0, validateBytes));
      for (let i = 0; i < 4; i++) {
        if (mapped[i] !== input[i] * 2.0) {
          throw new Error(`compute_dispatch_and_wait_simple: expected readback[${i}] === ${input[i] * 2.0}, got ${mapped[i]}`);
        }
      }
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
        input = new Float32Array(COUNT);
        for (let i = 0; i < COUNT; i++) {
          input[i] = i;
        }
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
        return queue.onSubmittedWorkDone?.();
      },
      async prepareSample() {
        await resetInput();
      },
      async run() {
        const enc = device.createCommandEncoder();
        const pass = enc.beginComputePass();
        pass.setPipeline(pipeline);
        pass.setBindGroup(0, bindGroup);
        pass.dispatchWorkgroups(COUNT / 64);
        pass.end();
        enc.copyBufferToBuffer(storageBuf, 0, stagingBuf, 0, validateBytes);
        queue.submit([enc.finish()]);
        await queue.onSubmittedWorkDone();
        await stagingBuf.mapAsync(G.GPUMapMode.READ, 0, validateBytes);
        assertReadbackMatchesPreparedInput();
        stagingBuf.unmap();
      },
      async validate() {
        let lastError = null;
        for (let attempt = 0; attempt < VALIDATE_RETRY_LIMIT; attempt++) {
          try {
            await this.prepareSample();
            await this.run();
            return { ok: true };
          } catch (err) {
            lastError = err;
          }
        }
        return { ok: false, detail: lastError?.message || 'validation retry budget exhausted' };
      },
      teardown() {
        storageBuf.destroy();
        stagingBuf.destroy();
      },
    };
  };
}

function makePipelineFirstUseE2E() {
  return (device, queue, G) => {
    const COUNT = 256;
    const size = COUNT * Float32Array.BYTES_PER_ELEMENT;
    const validateBytes = 4 * Float32Array.BYTES_PER_ELEMENT;
    let storageBuf, stagingBuf, input, iteration = 0;

    async function resetInput() {
      input.fill(0);
      queue.writeBuffer(storageBuf, 0, input);
      await queue.onSubmittedWorkDone?.();
    }

    function shaderSource(addend) {
      return `
        @group(0) @binding(0) var<storage, read_write> data: array<f32>;
        @compute @workgroup_size(64)
        fn main(@builtin(global_invocation_id) id: vec3u) {
          data[id.x] = data[id.x] + ${addend}.0;
        }
      `;
    }

    function assertReadbackMatches(addend) {
      const mapped = new Float32Array(stagingBuf.getMappedRange(0, validateBytes));
      for (let i = 0; i < 4; i++) {
        if (mapped[i] !== addend) {
          throw new Error(`pipeline_first_use_e2e: expected readback[${i}] === ${addend}, got ${mapped[i]}`);
        }
      }
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
        input = new Float32Array(COUNT);
        queue.writeBuffer(storageBuf, 0, input);
        return queue.onSubmittedWorkDone?.();
      },
      async prepareSample() {
        await resetInput();
      },
      async run() {
        const addend = ++iteration;
        const shader = device.createShaderModule({ code: shaderSource(addend) });
        const bindGroupLayout = device.createBindGroupLayout({
          entries: [{ binding: 0, visibility: G.GPUShaderStage.COMPUTE, buffer: { type: 'storage' } }],
        });
        const pipelineLayout = device.createPipelineLayout({ bindGroupLayouts: [bindGroupLayout] });
        const pipeline = device.createComputePipeline({
          layout: pipelineLayout,
          compute: { module: shader, entryPoint: 'main' },
        });
        const bindGroup = device.createBindGroup({
          layout: bindGroupLayout,
          entries: [{ binding: 0, resource: { buffer: storageBuf } }],
        });

        const enc = device.createCommandEncoder();
        const pass = enc.beginComputePass();
        pass.setPipeline(pipeline);
        pass.setBindGroup(0, bindGroup);
        pass.dispatchWorkgroups(COUNT / 64);
        pass.end();
        enc.copyBufferToBuffer(storageBuf, 0, stagingBuf, 0, validateBytes);
        queue.submit([enc.finish()]);
        await queue.onSubmittedWorkDone();
        await stagingBuf.mapAsync(G.GPUMapMode.READ, 0, validateBytes);
        assertReadbackMatches(addend);
        stagingBuf.unmap();
      },
      async validate() {
        let lastError = null;
        for (let attempt = 0; attempt < VALIDATE_RETRY_LIMIT; attempt++) {
          try {
            await this.prepareSample();
            await this.run();
            return { ok: true };
          } catch (err) {
            lastError = err;
          }
        }
        return { ok: false, detail: lastError?.message || 'validation retry budget exhausted' };
      },
      teardown() {
        storageBuf.destroy();
        stagingBuf.destroy();
      },
    };
  };
}

// Helper: texture write (buffer→texture→buffer) E2E roundtrip.
// width and height must satisfy: width * 4 is a multiple of 256 (bytesPerRow alignment).
// 64×64 = 256 bytes/row, 256×256 = 1024 bytes/row — both are 256-aligned.
function makeTextureCopyRoundtripE2E(width, height) {
  return (device, queue, G) => {
    const bytesPerRow = width * 4;  // RGBA8: 4 bytes/texel; both dims chosen to be 256-aligned
    const bufSize = bytesPerRow * height;
    const validateBytes = Math.min(bufSize, COPY_VALIDATE_BYTES);
    const sourceBytes = new Uint8Array(bufSize);
    for (let i = 0; i < bufSize; i++) sourceBytes[i] = i & 0xff;

    let texture, srcBuf, stagingBuf;

    async function assertReadbackMatchesSource() {
      await stagingBuf.mapAsync(G.GPUMapMode.READ, 0, validateBytes);
      const mapped = new Uint8Array(stagingBuf.getMappedRange(0, validateBytes));
      for (let i = 0; i < validateBytes; i++) {
        if (mapped[i] !== sourceBytes[i]) {
          throw new Error(`texture roundtrip byte ${i}: expected ${sourceBytes[i]}, got ${mapped[i]}`);
        }
      }
      stagingBuf.unmap();
    }

    return {
      setup() {
        texture = device.createTexture({
          size: { width, height, depthOrArrayLayers: 1 },
          format: 'rgba8unorm',
          usage: G.GPUTextureUsage.COPY_SRC | G.GPUTextureUsage.COPY_DST,
        });
        srcBuf = device.createBuffer({
          size: bufSize,
          usage: G.GPUBufferUsage.COPY_SRC | G.GPUBufferUsage.COPY_DST,
        });
        stagingBuf = device.createBuffer({
          size: bufSize,
          usage: G.GPUBufferUsage.COPY_DST | G.GPUBufferUsage.MAP_READ,
        });
        queue.writeBuffer(srcBuf, 0, sourceBytes);
        return queue.onSubmittedWorkDone?.();
      },
      async run() {
        const enc = device.createCommandEncoder();
        enc.copyBufferToTexture(
          { buffer: srcBuf, offset: 0, bytesPerRow, rowsPerImage: height },
          { texture, origin: { x: 0, y: 0, z: 0 } },
          { width, height, depthOrArrayLayers: 1 },
        );
        enc.copyTextureToBuffer(
          { texture, origin: { x: 0, y: 0, z: 0 } },
          { buffer: stagingBuf, offset: 0, bytesPerRow, rowsPerImage: height },
          { width, height, depthOrArrayLayers: 1 },
        );
        queue.submit([enc.finish()]);
        await queue.onSubmittedWorkDone();
        await assertReadbackMatchesSource();
      },
      async validate() {
        await this.run();
        return { ok: true };
      },
      teardown() {
        texture.destroy();
        srcBuf.destroy();
        stagingBuf.destroy();
      },
    };
  };
}

// WGSL shaders for render workloads.
const RENDER_VERTEX_WGSL = `
  @vertex fn main(@builtin(vertex_index) vi: u32) -> @builtin(position) vec4f {
    var pos = array<vec2f, 3>(vec2f(0, 0.5), vec2f(-0.5, -0.5), vec2f(0.5, -0.5));
    return vec4f(pos[vi], 0, 1);
  }
`;

const RENDER_FRAGMENT_WGSL = `
  @fragment fn main() -> @location(0) vec4f {
    return vec4f(1, 0, 0, 1);
  }
`;

const RENDER_VERTEX_PASSTHROUGH_WGSL = `
  struct VOut {
    @builtin(position) pos: vec4f,
    @location(0) color: vec4f,
  };
  @vertex fn main(@location(0) pos: vec2f, @location(1) color: vec4f) -> VOut {
    var out: VOut;
    out.pos = vec4f(pos, 0, 1);
    out.color = color;
    return out;
  }
`;

const RENDER_FRAGMENT_VERTEX_COLOR_WGSL = `
  @fragment fn main(@location(0) color: vec4f) -> @location(0) vec4f {
    return color;
  }
`;

// Render: solid triangle to 64x64 texture, readback center pixel.
function makeRenderTriangleSolid() {
  return (device, queue, G) => {
    const WIDTH = 64;
    const HEIGHT = 64;
    const bytesPerRow = WIDTH * 4;
    const bufSize = bytesPerRow * HEIGHT;
    let texture, stagingBuf, pipeline;

    return {
      setup() {
        texture = device.createTexture({
          size: { width: WIDTH, height: HEIGHT, depthOrArrayLayers: 1 },
          format: 'rgba8unorm',
          usage: G.GPUTextureUsage.RENDER_ATTACHMENT | G.GPUTextureUsage.COPY_SRC,
        });
        stagingBuf = device.createBuffer({
          size: bufSize,
          usage: G.GPUBufferUsage.COPY_DST | G.GPUBufferUsage.MAP_READ,
        });
        const vertModule = device.createShaderModule({ code: RENDER_VERTEX_WGSL });
        const fragModule = device.createShaderModule({ code: RENDER_FRAGMENT_WGSL });
        pipeline = device.createRenderPipeline({
          layout: 'auto',
          vertex: { module: vertModule, entryPoint: 'main' },
          fragment: {
            module: fragModule,
            entryPoint: 'main',
            targets: [{ format: 'rgba8unorm' }],
          },
          primitive: { topology: 'triangle-list' },
        });
        return queue.onSubmittedWorkDone?.();
      },
      async run() {
        const enc = device.createCommandEncoder();
        const pass = enc.beginRenderPass({
          colorAttachments: [{
            view: texture.createView(),
            clearValue: { r: 0, g: 0, b: 0, a: 1 },
            loadOp: 'clear',
            storeOp: 'store',
          }],
        });
        pass.setPipeline(pipeline);
        pass.draw(3);
        pass.end();
        enc.copyTextureToBuffer(
          { texture, origin: { x: 0, y: 0, z: 0 } },
          { buffer: stagingBuf, offset: 0, bytesPerRow, rowsPerImage: HEIGHT },
          { width: WIDTH, height: HEIGHT, depthOrArrayLayers: 1 },
        );
        queue.submit([enc.finish()]);
        await queue.onSubmittedWorkDone();
        // Validate center pixel is red (triangle covers center of 64x64).
        const centerRow = Math.floor(HEIGHT / 2);
        const centerCol = Math.floor(WIDTH / 2);
        const centerOffset = (centerRow * bytesPerRow) + (centerCol * 4);
        await stagingBuf.mapAsync(G.GPUMapMode.READ, centerOffset, 4);
        const pixel = new Uint8Array(stagingBuf.getMappedRange(centerOffset, 4));
        if (pixel[0] < 200 || pixel[1] > 10 || pixel[2] > 10) {
          throw new Error(`render_triangle_solid: center pixel not red: [${pixel[0]}, ${pixel[1]}, ${pixel[2]}, ${pixel[3]}]`);
        }
        stagingBuf.unmap();
      },
      async validate() {
        await this.run();
        return { ok: true };
      },
      teardown() {
        texture.destroy();
        stagingBuf.destroy();
      },
    };
  };
}

// Render: indexed quad (4 vertices, 6 indices), readback center pixel.
function makeRenderIndexedQuad() {
  return (device, queue, G) => {
    const WIDTH = 64;
    const HEIGHT = 64;
    const bytesPerRow = WIDTH * 4;
    const bufSize = bytesPerRow * HEIGHT;
    // Quad covers [-0.5, -0.5] to [0.5, 0.5], green color.
    // Each vertex: vec2f position + vec4f color = 6 floats = 24 bytes.
    const vertices = new Float32Array([
      // pos x,y       color r,g,b,a
      -0.5, -0.5,      0, 1, 0, 1,
       0.5, -0.5,      0, 1, 0, 1,
       0.5,  0.5,      0, 1, 0, 1,
      -0.5,  0.5,      0, 1, 0, 1,
    ]);
    const indices = new Uint16Array([0, 1, 2, 0, 2, 3]);
    let texture, stagingBuf, pipeline, vertexBuf, indexBuf;

    return {
      setup() {
        texture = device.createTexture({
          size: { width: WIDTH, height: HEIGHT, depthOrArrayLayers: 1 },
          format: 'rgba8unorm',
          usage: G.GPUTextureUsage.RENDER_ATTACHMENT | G.GPUTextureUsage.COPY_SRC,
        });
        stagingBuf = device.createBuffer({
          size: bufSize,
          usage: G.GPUBufferUsage.COPY_DST | G.GPUBufferUsage.MAP_READ,
        });
        vertexBuf = device.createBuffer({
          size: vertices.byteLength,
          usage: G.GPUBufferUsage.VERTEX | G.GPUBufferUsage.COPY_DST,
        });
        queue.writeBuffer(vertexBuf, 0, vertices);
        indexBuf = device.createBuffer({
          size: indices.byteLength,
          usage: G.GPUBufferUsage.INDEX | G.GPUBufferUsage.COPY_DST,
        });
        queue.writeBuffer(indexBuf, 0, indices);
        const vertModule = device.createShaderModule({ code: RENDER_VERTEX_PASSTHROUGH_WGSL });
        const fragModule = device.createShaderModule({ code: RENDER_FRAGMENT_VERTEX_COLOR_WGSL });
        pipeline = device.createRenderPipeline({
          layout: 'auto',
          vertex: {
            module: vertModule,
            entryPoint: 'main',
            buffers: [{
              arrayStride: 24,
              attributes: [
                { shaderLocation: 0, offset: 0, format: 'float32x2' },
                { shaderLocation: 1, offset: 8, format: 'float32x4' },
              ],
            }],
          },
          fragment: {
            module: fragModule,
            entryPoint: 'main',
            targets: [{ format: 'rgba8unorm' }],
          },
          primitive: { topology: 'triangle-list' },
        });
        return queue.onSubmittedWorkDone?.();
      },
      async run() {
        const enc = device.createCommandEncoder();
        const pass = enc.beginRenderPass({
          colorAttachments: [{
            view: texture.createView(),
            clearValue: { r: 0, g: 0, b: 0, a: 1 },
            loadOp: 'clear',
            storeOp: 'store',
          }],
        });
        pass.setPipeline(pipeline);
        pass.setVertexBuffer(0, vertexBuf);
        pass.setIndexBuffer(indexBuf, 'uint16');
        pass.drawIndexed(6);
        pass.end();
        enc.copyTextureToBuffer(
          { texture, origin: { x: 0, y: 0, z: 0 } },
          { buffer: stagingBuf, offset: 0, bytesPerRow, rowsPerImage: HEIGHT },
          { width: WIDTH, height: HEIGHT, depthOrArrayLayers: 1 },
        );
        queue.submit([enc.finish()]);
        await queue.onSubmittedWorkDone();
        const centerRow = Math.floor(HEIGHT / 2);
        const centerCol = Math.floor(WIDTH / 2);
        const centerOffset = (centerRow * bytesPerRow) + (centerCol * 4);
        await stagingBuf.mapAsync(G.GPUMapMode.READ, centerOffset, 4);
        const pixel = new Uint8Array(stagingBuf.getMappedRange(centerOffset, 4));
        if (pixel[0] > 10 || pixel[1] < 200 || pixel[2] > 10) {
          throw new Error(`render_indexed_quad: center pixel not green: [${pixel[0]}, ${pixel[1]}, ${pixel[2]}, ${pixel[3]}]`);
        }
        stagingBuf.unmap();
      },
      async validate() {
        await this.run();
        return { ok: true };
      },
      teardown() {
        texture.destroy();
        stagingBuf.destroy();
        vertexBuf.destroy();
        indexBuf.destroy();
      },
    };
  };
}

// Render: 3 render passes with different clear colors, readback final result.
function makeRenderPassSwitching() {
  return (device, queue, G) => {
    const WIDTH = 64;
    const HEIGHT = 64;
    const bytesPerRow = WIDTH * 4;
    const bufSize = bytesPerRow * HEIGHT;
    const clearColors = [
      { r: 1, g: 0, b: 0, a: 1 },
      { r: 0, g: 1, b: 0, a: 1 },
      { r: 0, g: 0, b: 1, a: 1 },
    ];
    let texture, stagingBuf, pipeline;

    return {
      setup() {
        texture = device.createTexture({
          size: { width: WIDTH, height: HEIGHT, depthOrArrayLayers: 1 },
          format: 'rgba8unorm',
          usage: G.GPUTextureUsage.RENDER_ATTACHMENT | G.GPUTextureUsage.COPY_SRC,
        });
        stagingBuf = device.createBuffer({
          size: bufSize,
          usage: G.GPUBufferUsage.COPY_DST | G.GPUBufferUsage.MAP_READ,
        });
        const vertModule = device.createShaderModule({ code: RENDER_VERTEX_WGSL });
        const fragModule = device.createShaderModule({ code: RENDER_FRAGMENT_WGSL });
        pipeline = device.createRenderPipeline({
          layout: 'auto',
          vertex: { module: vertModule, entryPoint: 'main' },
          fragment: {
            module: fragModule,
            entryPoint: 'main',
            targets: [{ format: 'rgba8unorm' }],
          },
          primitive: { topology: 'triangle-list' },
        });
        return queue.onSubmittedWorkDone?.();
      },
      async run() {
        const enc = device.createCommandEncoder();
        const view = texture.createView();
        for (const clearValue of clearColors) {
          const pass = enc.beginRenderPass({
            colorAttachments: [{
              view,
              clearValue,
              loadOp: 'clear',
              storeOp: 'store',
            }],
          });
          pass.setPipeline(pipeline);
          pass.draw(3);
          pass.end();
        }
        enc.copyTextureToBuffer(
          { texture, origin: { x: 0, y: 0, z: 0 } },
          { buffer: stagingBuf, offset: 0, bytesPerRow, rowsPerImage: HEIGHT },
          { width: WIDTH, height: HEIGHT, depthOrArrayLayers: 1 },
        );
        queue.submit([enc.finish()]);
        await queue.onSubmittedWorkDone();
        // Last clear was blue; corner pixel (outside triangle) should be blue.
        await stagingBuf.mapAsync(G.GPUMapMode.READ, 0, 4);
        const pixel = new Uint8Array(stagingBuf.getMappedRange(0, 4));
        if (pixel[0] > 10 || pixel[1] > 10 || pixel[2] < 200) {
          throw new Error(`render_pass_switching: corner pixel not blue: [${pixel[0]}, ${pixel[1]}, ${pixel[2]}, ${pixel[3]}]`);
        }
        stagingBuf.unmap();
      },
      async validate() {
        await this.run();
        return { ok: true };
      },
      teardown() {
        texture.destroy();
        stagingBuf.destroy();
      },
    };
  };
}

// Texture: create two textures, copy tex1→tex2, readback tex2 and validate.
function makeTextureToTextureCopy() {
  return (device, queue, G) => {
    const WIDTH = 64;
    const HEIGHT = 64;
    const bytesPerRow = WIDTH * 4;
    const bufSize = bytesPerRow * HEIGHT;
    const sourceBytes = new Uint8Array(bufSize);
    for (let i = 0; i < bufSize; i++) sourceBytes[i] = i & 0xff;
    const validateBytes = Math.min(bufSize, COPY_VALIDATE_BYTES);
    let texSrc, texDst, srcBuf, stagingBuf;

    return {
      setup() {
        const texDesc = {
          size: { width: WIDTH, height: HEIGHT, depthOrArrayLayers: 1 },
          format: 'rgba8unorm',
          usage: G.GPUTextureUsage.COPY_SRC | G.GPUTextureUsage.COPY_DST,
        };
        texSrc = device.createTexture(texDesc);
        texDst = device.createTexture(texDesc);
        srcBuf = device.createBuffer({
          size: bufSize,
          usage: G.GPUBufferUsage.COPY_SRC | G.GPUBufferUsage.COPY_DST,
        });
        stagingBuf = device.createBuffer({
          size: bufSize,
          usage: G.GPUBufferUsage.COPY_DST | G.GPUBufferUsage.MAP_READ,
        });
        queue.writeBuffer(srcBuf, 0, sourceBytes);
        return queue.onSubmittedWorkDone?.();
      },
      async run() {
        const enc = device.createCommandEncoder();
        // buffer → texSrc
        enc.copyBufferToTexture(
          { buffer: srcBuf, offset: 0, bytesPerRow, rowsPerImage: HEIGHT },
          { texture: texSrc, origin: { x: 0, y: 0, z: 0 } },
          { width: WIDTH, height: HEIGHT, depthOrArrayLayers: 1 },
        );
        // texSrc → texDst
        enc.copyTextureToTexture(
          { texture: texSrc, origin: { x: 0, y: 0, z: 0 } },
          { texture: texDst, origin: { x: 0, y: 0, z: 0 } },
          { width: WIDTH, height: HEIGHT, depthOrArrayLayers: 1 },
        );
        // texDst → staging buffer
        enc.copyTextureToBuffer(
          { texture: texDst, origin: { x: 0, y: 0, z: 0 } },
          { buffer: stagingBuf, offset: 0, bytesPerRow, rowsPerImage: HEIGHT },
          { width: WIDTH, height: HEIGHT, depthOrArrayLayers: 1 },
        );
        queue.submit([enc.finish()]);
        await queue.onSubmittedWorkDone();
        await stagingBuf.mapAsync(G.GPUMapMode.READ, 0, validateBytes);
        const mapped = new Uint8Array(stagingBuf.getMappedRange(0, validateBytes));
        for (let i = 0; i < validateBytes; i++) {
          if (mapped[i] !== sourceBytes[i]) {
            throw new Error(`texture_to_texture_copy byte ${i}: expected ${sourceBytes[i]}, got ${mapped[i]}`);
          }
        }
        stagingBuf.unmap();
      },
      async validate() {
        await this.run();
        return { ok: true };
      },
      teardown() {
        texSrc.destroy();
        texDst.destroy();
        srcBuf.destroy();
        stagingBuf.destroy();
      },
    };
  };
}

// Timestamp query: create query set, write timestamps around compute, resolve, readback.
function makeTimestampQuery() {
  return (device, queue, G) => {
    const COUNT = 256;
    const size = COUNT * 4;
    const wgsl = `
      @group(0) @binding(0) var<storage, read_write> data: array<f32>;
      @compute @workgroup_size(64)
      fn main(@builtin(global_invocation_id) id: vec3u) {
        data[id.x] = data[id.x] + 1.0;
      }
    `;
    let storageBuf, querySet, queryBuf, stagingBuf;
    let shader, pipeline, bindGroupLayout, bindGroup, pipelineLayout;

    return {
      setup() {
        storageBuf = device.createBuffer({
          size,
          usage: G.GPUBufferUsage.STORAGE | G.GPUBufferUsage.COPY_DST,
        });
        const input = new Float32Array(COUNT);
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
        querySet = device.createQuerySet({ type: 'timestamp', count: 2 });
        // Each timestamp is a u64 (8 bytes); 2 timestamps = 16 bytes.
        queryBuf = device.createBuffer({
          size: 16,
          usage: G.GPUBufferUsage.QUERY_RESOLVE | G.GPUBufferUsage.COPY_SRC,
        });
        stagingBuf = device.createBuffer({
          size: 16,
          usage: G.GPUBufferUsage.COPY_DST | G.GPUBufferUsage.MAP_READ,
        });
        return queue.onSubmittedWorkDone?.();
      },
      async run() {
        const enc = device.createCommandEncoder();
        const pass = enc.beginComputePass({
          timestampWrites: {
            querySet,
            beginningOfPassWriteIndex: 0,
            endOfPassWriteIndex: 1,
          },
        });
        pass.setPipeline(pipeline);
        pass.setBindGroup(0, bindGroup);
        pass.dispatchWorkgroups(COUNT / 64);
        pass.end();
        enc.resolveQuerySet(querySet, 0, 2, queryBuf, 0);
        enc.copyBufferToBuffer(queryBuf, 0, stagingBuf, 0, 16);
        queue.submit([enc.finish()]);
        await queue.onSubmittedWorkDone();
        await stagingBuf.mapAsync(G.GPUMapMode.READ);
        const timestamps = new BigUint64Array(stagingBuf.getMappedRange());
        // Sanity: end timestamp >= begin timestamp.
        if (timestamps[1] < timestamps[0]) {
          throw new Error(`timestamp_query: end (${timestamps[1]}) < begin (${timestamps[0]})`);
        }
        stagingBuf.unmap();
      },
      async validate() {
        try {
          await this.run();
          return { ok: true };
        } catch (err) {
          return { ok: false, detail: err?.message || 'timestamp_query validation failed' };
        }
      },
      teardown() {
        storageBuf.destroy();
        queryBuf.destroy();
        stagingBuf.destroy();
        querySet.destroy();
      },
    };
  };
}

// Advanced compute: indirect dispatch from GPU buffer, readback validate.
function makeDispatchIndirect() {
  return (device, queue, G) => {
    const WORKGROUP_COUNT = 4;
    const WORKGROUP_SIZE = 64;
    const threadCount = WORKGROUP_COUNT * WORKGROUP_SIZE;
    const size = threadCount * 4;
    const wgsl = `
      @group(0) @binding(0) var<storage, read_write> data: array<f32>;
      @compute @workgroup_size(${WORKGROUP_SIZE})
      fn main(@builtin(global_invocation_id) id: vec3u) {
        data[id.x] = data[id.x] + 1.0;
      }
    `;
    let storageBuf, stagingBuf, indirectBuf;
    let shader, pipeline, bindGroupLayout, bindGroup, pipelineLayout, input;

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
        // Indirect dispatch buffer: 3 x uint32 (workgroupCountX, Y, Z).
        indirectBuf = device.createBuffer({
          size: 12,
          usage: G.GPUBufferUsage.INDIRECT | G.GPUBufferUsage.COPY_DST,
        });
        queue.writeBuffer(indirectBuf, 0, new Uint32Array([WORKGROUP_COUNT, 1, 1]));
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
        return queue.onSubmittedWorkDone?.();
      },
      async prepareSample() {
        queue.writeBuffer(storageBuf, 0, input);
        await queue.onSubmittedWorkDone?.();
      },
      async run() {
        const enc = device.createCommandEncoder();
        const pass = enc.beginComputePass();
        pass.setPipeline(pipeline);
        pass.setBindGroup(0, bindGroup);
        pass.dispatchWorkgroupsIndirect(indirectBuf, 0);
        pass.end();
        enc.copyBufferToBuffer(storageBuf, 0, stagingBuf, 0, size);
        queue.submit([enc.finish()]);
        await queue.onSubmittedWorkDone();
        await stagingBuf.mapAsync(G.GPUMapMode.READ);
        const mapped = new Float32Array(stagingBuf.getMappedRange());
        const validateCount = Math.min(4, threadCount);
        for (let i = 0; i < validateCount; i++) {
          if (mapped[i] !== 1) {
            throw new Error(`dispatch_indirect: expected readback[${i}] === 1, got ${mapped[i]}`);
          }
        }
        stagingBuf.unmap();
      },
      async validate() {
        let lastError = null;
        for (let attempt = 0; attempt < VALIDATE_RETRY_LIMIT; attempt++) {
          try {
            await this.prepareSample();
            await this.run();
            return { ok: true };
          } catch (err) {
            lastError = err;
          }
        }
        return { ok: false, detail: lastError?.message || 'validation retry budget exhausted' };
      },
      teardown() {
        storageBuf.destroy();
        stagingBuf.destroy();
        indirectBuf.destroy();
      },
    };
  };
}

// Render bundle: record 10 draw calls in a bundle, replay in render pass.
function makeRenderBundleReplay() {
  return (device, queue, G) => {
    const WIDTH = 64;
    const HEIGHT = 64;
    const bytesPerRow = WIDTH * 4;
    const bufSize = bytesPerRow * HEIGHT;
    const BUNDLE_DRAW_COUNT = 10;
    let texture, stagingBuf, pipeline, renderBundle;

    return {
      setup() {
        texture = device.createTexture({
          size: { width: WIDTH, height: HEIGHT, depthOrArrayLayers: 1 },
          format: 'rgba8unorm',
          usage: G.GPUTextureUsage.RENDER_ATTACHMENT | G.GPUTextureUsage.COPY_SRC,
        });
        stagingBuf = device.createBuffer({
          size: bufSize,
          usage: G.GPUBufferUsage.COPY_DST | G.GPUBufferUsage.MAP_READ,
        });
        const vertModule = device.createShaderModule({ code: RENDER_VERTEX_WGSL });
        const fragModule = device.createShaderModule({ code: RENDER_FRAGMENT_WGSL });
        pipeline = device.createRenderPipeline({
          layout: 'auto',
          vertex: { module: vertModule, entryPoint: 'main' },
          fragment: {
            module: fragModule,
            entryPoint: 'main',
            targets: [{ format: 'rgba8unorm' }],
          },
          primitive: { topology: 'triangle-list' },
        });
        // Record render bundle with BUNDLE_DRAW_COUNT draw calls.
        const bundleEncoder = device.createRenderBundleEncoder({
          colorFormats: ['rgba8unorm'],
        });
        bundleEncoder.setPipeline(pipeline);
        for (let i = 0; i < BUNDLE_DRAW_COUNT; i++) {
          bundleEncoder.draw(3);
        }
        renderBundle = bundleEncoder.finish();
        return queue.onSubmittedWorkDone?.();
      },
      async run() {
        const enc = device.createCommandEncoder();
        const pass = enc.beginRenderPass({
          colorAttachments: [{
            view: texture.createView(),
            clearValue: { r: 0, g: 0, b: 0, a: 1 },
            loadOp: 'clear',
            storeOp: 'store',
          }],
        });
        pass.executeBundles([renderBundle]);
        pass.end();
        enc.copyTextureToBuffer(
          { texture, origin: { x: 0, y: 0, z: 0 } },
          { buffer: stagingBuf, offset: 0, bytesPerRow, rowsPerImage: HEIGHT },
          { width: WIDTH, height: HEIGHT, depthOrArrayLayers: 1 },
        );
        queue.submit([enc.finish()]);
        await queue.onSubmittedWorkDone();
        // Validate center pixel is red from the drawn triangle(s).
        const centerRow = Math.floor(HEIGHT / 2);
        const centerCol = Math.floor(WIDTH / 2);
        const centerOffset = (centerRow * bytesPerRow) + (centerCol * 4);
        await stagingBuf.mapAsync(G.GPUMapMode.READ, centerOffset, 4);
        const pixel = new Uint8Array(stagingBuf.getMappedRange(centerOffset, 4));
        if (pixel[0] < 200 || pixel[1] > 10 || pixel[2] > 10) {
          throw new Error(`render_bundle_replay: center pixel not red: [${pixel[0]}, ${pixel[1]}, ${pixel[2]}, ${pixel[3]}]`);
        }
        stagingBuf.unmap();
      },
      async validate() {
        await this.run();
        return { ok: true };
      },
      teardown() {
        texture.destroy();
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

    // Validate only a small prefix to bound map/readback cost in the harness.
    const validateBytes = Math.min(size, COPY_VALIDATE_BYTES);
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
