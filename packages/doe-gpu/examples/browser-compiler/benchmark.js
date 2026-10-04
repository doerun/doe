// Application-owned resources; shader adaptation never changes submission work.
import { createDoeShaderAdapter } from '../../src/browser-compiler.js';
import { compareParticles, renderWGSL } from './particles.js';
import { sha256 } from '../../src/browser-compiler-cache.js';

export const modes = ['browser', 'disabled', 'enabled'];

export async function createParticleSession({ device, context, format, code, compiler,
  mode, initial, contract, timestamps = false }) {
  const resources = [];
  function buffer(descriptor) {
    const value = device.createBuffer(descriptor);
    resources.push(value);
    return value;
  }
  let query;
  let preparationScope = true;
  device.pushErrorScope('validation');
  try {
    const preparationStart = performance.now();
    let prepared;
    if (mode === 'browser' || mode === 'offline') {
      const module = device.createShaderModule({ code });
      const info = await module.getCompilationInfo();
      if (info.messages.some((message) => message.type === 'error')) {
        throw new Error(info.messages.map((message) => message.message).join('\n'));
      }
      prepared = { module, wgsl: code, rewrites: 0, compileMs: 0, workerRoundTripMs: 0 };
    } else {
      prepared = await createDoeShaderAdapter({ device, compiler, optimize: mode === 'enabled' })
        .createShaderModule({ code });
    }
    const browserPreparationStart = performance.now();
    const compute = await device.createComputePipelineAsync({
      layout: 'auto', compute: { module: prepared.module, entryPoint: 'main' },
    });
    const renderModule = device.createShaderModule({ code: renderWGSL });
    const render = await device.createRenderPipelineAsync({
      layout: 'auto', vertex: { module: renderModule, entryPoint: 'vertex' },
      fragment: { module: renderModule, entryPoint: 'fragment', targets: [{ format,
        blend: { color: { srcFactor: 'one', dstFactor: 'one', operation: 'add' },
          alpha: { srcFactor: 'one', dstFactor: 'one', operation: 'add' } },
      }] },
      primitive: { topology: 'triangle-list' },
    });
    const browserPipelineMs = performance.now() - browserPreparationStart;
    const pipelinePreparationMs = performance.now() - preparationStart;
    const allocationStart = performance.now();
    const usage = GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST | GPUBufferUsage.COPY_SRC;
    const particles = [buffer({ size: initial.byteLength, usage }),
      buffer({ size: initial.byteLength, usage })];
    device.queue.writeBuffer(particles[0], 0, initial);
    const uniform = buffer({ size: 16, usage: GPUBufferUsage.UNIFORM | GPUBufferUsage.COPY_DST });
    device.queue.writeBuffer(uniform, 0, new Float32Array([contract.dt, 0, 0, 0]));
    const computeBindings = particles.map((value, index) => device.createBindGroup({
      layout: compute.getBindGroupLayout(0), entries: [
        { binding: 0, resource: { buffer: value } },
        { binding: 1, resource: { buffer: particles[1 - index] } },
        { binding: 2, resource: { buffer: uniform } },
      ],
    }));
    const renderBindings = particles.map((value) => device.createBindGroup({
      layout: render.getBindGroupLayout(0), entries: [{ binding: 0, resource: { buffer: value } }],
    }));
    const readback = buffer({ size: initial.byteLength,
      usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ });
    let queryResolve;
    let queryRead;
    if (timestamps) {
      if (!device.features.has('timestamp-query')) throw new Error('GPU timestamps unavailable');
      query = device.createQuerySet({ type: 'timestamp', count: 2 });
      queryResolve = buffer({ size: 16, usage: GPUBufferUsage.QUERY_RESOLVE | GPUBufferUsage.COPY_SRC });
      queryRead = buffer({ size: 16, usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ });
    }
    const allocationUploadMs = performance.now() - allocationStart;
    await device.queue.onSubmittedWorkDone();
    const validation = await device.popErrorScope();
    preparationScope = false;
    if (validation) throw new Error(validation.message);
    let current = 0;
    let closed = false;
    let busy = false;
    const preparation = {
      pipelinePreparationMs, browserPipelineMs, compileMs: prepared.compileMs,
      workerRoundTripMs: prepared.workerRoundTripMs, allocationUploadMs,
      rewrites: prepared.rewrites, wgslHash: await sha256(new TextEncoder().encode(prepared.wgsl)),
      ownedBufferBytes: resources.reduce((sum, value) => sum + value.size, 0),
    };
    return {
      preparation,
      async snapshot() {
        if (closed || busy) throw new Error('Particle session is closed or busy');
        busy = true;
        try {
          await device.queue.onSubmittedWorkDone();
          const encoder = device.createCommandEncoder();
          encoder.copyBufferToBuffer(particles[current], 0, readback, 0, initial.byteLength);
          device.queue.submit([encoder.finish()]);
          await readback.mapAsync(GPUMapMode.READ);
          try {
            return new Float32Array(readback.getMappedRange().slice(0));
          } finally {
            readback.unmap();
          }
        } finally {
          busy = false;
        }
      },
      async run(steps, snapshot = true) {
        if (closed || busy) throw new Error('Particle session is closed or busy');
        if (!Number.isSafeInteger(steps) || steps < 1) throw new Error('Invalid step count');
        busy = true;
        let executionScope = true;
        device.pushErrorScope('validation');
        try {
          const operationStart = performance.now();
          const encoder = device.createCommandEncoder();
          const pass = encoder.beginComputePass(query ? { timestampWrites: {
            querySet: query, beginningOfPassWriteIndex: 0, endOfPassWriteIndex: 1,
          } } : {});
          pass.setPipeline(compute);
          for (let step = 0; step < steps; step++) {
            pass.setBindGroup(0, computeBindings[current]);
            pass.dispatchWorkgroups(Math.ceil(initial.length / 4 / contract.workgroupSize));
            current = 1 - current;
          }
          pass.end();
          const drawing = encoder.beginRenderPass({ colorAttachments: [{
            view: context.getCurrentTexture().createView(),
            clearValue: { r: 0.006, g: 0.012, b: 0.025, a: 1 },
            loadOp: 'clear', storeOp: 'store',
          }] });
          drawing.setPipeline(render);
          drawing.setBindGroup(0, renderBindings[current]);
          drawing.draw(6, initial.length / 4);
          drawing.end();
          if (snapshot) encoder.copyBufferToBuffer(particles[current], 0, readback, 0, initial.byteLength);
          if (query) {
            encoder.resolveQuerySet(query, 0, 2, queryResolve, 0);
            encoder.copyBufferToBuffer(queryResolve, 0, queryRead, 0, 16);
          }
          const command = encoder.finish();
          const recordMs = performance.now() - operationStart;
          const submitStart = performance.now();
          device.queue.submit([command]);
          const submitMs = performance.now() - submitStart;
          const completionStart = performance.now();
          await device.queue.onSubmittedWorkDone();
          const completionMs = performance.now() - completionStart;
          const readStart = performance.now();
          let positions = null;
          if (snapshot) {
            await readback.mapAsync(GPUMapMode.READ);
            positions = new Float32Array(readback.getMappedRange().slice(0));
            readback.unmap();
          }
          let gpuComputeMs = null;
          if (query) {
            await queryRead.mapAsync(GPUMapMode.READ);
            const values = new BigUint64Array(queryRead.getMappedRange());
            gpuComputeMs = Number(values[1] - values[0]) / 1e6;
            queryRead.unmap();
          }
          const readbackMs = performance.now() - readStart;
          const completeOperationMs = performance.now() - operationStart;
          const validation = await device.popErrorScope();
          executionScope = false;
          if (validation) throw new Error(validation.message);
          return { positions, metrics: { recordMs, submitMs, completionMs, readbackMs,
            completeOperationMs, gpuComputeMs, dispatches: steps, draws: 1,
            workgroupsPerDispatch: Math.ceil(initial.length / 4 / contract.workgroupSize),
            copiedParticleBytes: snapshot ? initial.byteLength : 0 } };
        } catch (error) {
          if (executionScope) await device.popErrorScope().catch(() => {});
          throw error;
        } finally {
          busy = false;
        }
      },
      async close() {
        if (closed) return;
        closed = true;
        // Completion failure remains a failure; WebGPU owns in-flight lifetimes.
        try {
          await device.queue.onSubmittedWorkDone();
        } finally {
          for (const resource of resources) resource.destroy();
          query?.destroy();
        }
      },
    };
  } catch (error) {
    if (preparationScope) await device.popErrorScope().catch(() => {});
    for (const resource of resources) resource.destroy();
    query?.destroy();
    throw error;
  }
}

export async function measureMode(options, expected, baseline) {
  const start = performance.now();
  const session = await createParticleSession(options);
  try {
    const result = await session.run(options.contract.steps);
    const applicationMs = performance.now() - start;
    const oracle = compareParticles(result.positions, expected, options.contract.tolerance);
    const parity = baseline ? compareParticles(result.positions, baseline, options.contract.tolerance) : null;
    if (!oracle.passed || (parity && !parity.passed)) throw new Error('Particle numerical verification failed');
    return { positions: result.positions, row: { mode: options.mode, ...session.preparation,
      ...result.metrics, applicationMs, oracle, parity,
      finalStateHash: await sha256(result.positions), timestamps: options.timestamps } };
  } finally {
    await session.close();
  }
}
