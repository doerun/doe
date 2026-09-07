// Exercise independent N-API environments against one retained native library.
import assert from 'node:assert/strict';
import { Worker, isMainThread, parentPort, workerData } from 'node:worker_threads';
import { createNativeDirect, globals, requestAdapter } from '../../src/native.js';
import { prepareComputeProgram } from '../../src/compute-program.js';

if (process.platform !== 'linux') {
  console.log('skip: concurrent device regression requires Linux Vulkan');
  process.exit(0);
}

const WORKER_COUNT = 4;
const WORKER_GENERATIONS = 2;
const DEVICE_CYCLES = 8;
const RUNS = 32;
const WORD_COUNT = 64;
const BUFFER_BYTES = WORD_COUNT * Uint32Array.BYTES_PER_ELEMENT;
const EXECUTIONS = Object.freeze(['webgpu', 'native-recorded', 'gpu-recorded']);

function inputFor(worker, cycle, run) {
  return new Uint32Array(WORD_COUNT).fill((worker + 1) * 10000 + cycle * 100 + run);
}

async function copyWithNativeDirect(device, input) {
  const usage = globals.GPUBufferUsage;
  const source = device.createBuffer({
    size: BUFFER_BYTES, usage: usage.COPY_SRC | usage.COPY_DST,
  });
  const output = device.createBuffer({
    size: BUFFER_BYTES, usage: usage.COPY_DST | usage.MAP_READ,
  });
  try {
    device.queue.writeBuffer(source, 0, input);
    const encoder = device.createCommandEncoder();
    encoder.copyBufferToBuffer(source, 0, output, 0, BUFFER_BYTES);
    device.queue.submit([encoder.finish()]);
    await Promise.all([
      device.queue.onSubmittedWorkDone(),
      output.mapAsync(globals.GPUMapMode.READ),
    ]);
    assert.deepEqual(new Uint32Array(output.getMappedRange()).slice(), input);
    output.unmap();
  } finally {
    source.destroy();
    output.destroy();
  }
}

async function runWorkerGeneration(generation) {
  const start = new SharedArrayBuffer(Int32Array.BYTES_PER_ELEMENT);
  const workers = Array.from({ length: WORKER_COUNT }, (_, id) => new Worker(
    new URL(import.meta.url), { workerData: { id, generation, start } }
  ));
  let ready = 0;
  const completed = workers.map(worker => new Promise((resolve, reject) => {
    worker.on('message', message => {
      if (message.phase === 'ready') {
        ready += 1;
        if (ready === WORKER_COUNT) {
          Atomics.store(new Int32Array(start), 0, 1);
          Atomics.notify(new Int32Array(start), 0);
        }
      } else {
        console.log(JSON.stringify(message));
      }
    });
    worker.on('error', reject);
    worker.on('exit', code => code === 0 ? resolve() : reject(new Error(`worker exit ${code}`)));
  }));
  try {
    await Promise.all(completed);
  } finally {
    await Promise.all(workers.map(worker => worker.terminate()));
  }
}

if (isMainThread) {
  const adapter = await createNativeDirect().requestAdapter();
  const device = await adapter.requestDevice();
  try {
    for (let generation = 0; generation < WORKER_GENERATIONS; generation += 1) {
      await runWorkerGeneration(generation);
      await copyWithNativeDirect(device, inputFor(WORKER_COUNT, generation, 0));
    }
  } finally {
    device.destroy();
    adapter.destroy();
  }
  console.log('ok: isolated worker devices, exact outputs, recreated environments, surviving parent');
} else {
  const { id, generation, start } = workerData;
  parentPort.postMessage({ phase: 'ready' });
  Atomics.wait(new Int32Array(start), 0, 0);
  const descriptor = {
    schemaVersion: 1, id: 'concurrent_devices',
    buffers: [
      { id: 'input', size: BUFFER_BYTES, type: 'storage', role: 'input' },
      { id: 'output', size: BUFFER_BYTES, type: 'storage', role: 'output' },
    ],
    shaders: [{
      id: 'sum', entryPoint: 'main', code: `
        @group(0) @binding(0) var<storage, read> input: array<u32>;
        @group(0) @binding(1) var<storage, read_write> output: array<u32>;
        @compute @workgroup_size(64) fn main(@builtin(global_invocation_id) id: vec3<u32>) {
          output[id.x] = input[id.x] + id.x;
        }`,
    }],
    steps: [{
      shader: 'sum',
      bindings: [{ binding: 0, buffer: 'input' }, { binding: 1, buffer: 'output' }],
      workgroups: [1, 1, 1],
    }],
    output: 'output',
  };
  for (const execution of EXECUTIONS) {
    for (let cycle = 0; cycle < DEVICE_CYCLES; cycle += 1) {
      const adapter = await requestAdapter({ backend: 'vulkan' });
      const device = await adapter.requestDevice();
      let program;
      try {
        program = await prepareComputeProgram(device, descriptor, { execution });
        for (let run = 0; run < RUNS; run += 1) {
          const input = inputFor(id, cycle, run);
          const result = await program.run({ input });
          const output = new Uint32Array(
            result.output.buffer, result.output.byteOffset, WORD_COUNT
          );
          assert(output.every((value, index) => value === input[index] + index));
        }
      } finally {
        await program?.close();
        device.destroy();
        adapter.destroy();
      }
    }
    parentPort.postMessage({
      worker: id, generation, execution, cycles: DEVICE_CYCLES, runs: RUNS, status: 'passed',
    });
  }
  for (let cycle = 0; cycle < DEVICE_CYCLES; cycle += 1) {
    const adapter = await createNativeDirect().requestAdapter();
    const device = await adapter.requestDevice();
    try {
      await copyWithNativeDirect(device, inputFor(id, cycle, 0));
    } finally {
      device.destroy();
      adapter.destroy();
    }
  }
  parentPort.postMessage({ worker: id, generation, execution: 'native-direct', status: 'passed' });
}
