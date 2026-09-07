import assert from 'node:assert/strict';
import { Worker, isMainThread, parentPort, workerData } from 'node:worker_threads';
import { requestAdapter } from 'doe-gpu/native';
import { prepareComputeProgram } from 'doe-gpu/compute-program';
const workerCount = 4;
const cycles = 8;
const runs = 32;
if (isMainThread) {
  const start = new SharedArrayBuffer(4);
  const workers = Array.from({length: workerCount}, (_, id) => new Worker(new URL(import.meta.url), {
    workerData: { id, start },
  }));
  const completed = workers.map(worker => new Promise((resolve, reject) => {
    worker.on('message', message => console.log(JSON.stringify(message)));
    worker.on('error', reject);
    worker.on('exit', code => code === 0 ? resolve() : reject(new Error(`worker exit ${code}`)));
  }));
  Atomics.store(new Int32Array(start), 0, 1);
  Atomics.notify(new Int32Array(start), 0);
  try { await Promise.all(completed); }
  finally { await Promise.all(workers.map(worker => worker.terminate())); }
  console.log('PASS: concurrent isolated devices, repeated creation, accepted outputs, and teardown');
} else {
  const {id, start} = workerData;
  Atomics.wait(new Int32Array(start), 0, 0);
  const descriptor = {
    schemaVersion: 1, id: 'concurrent_devices',
    buffers: [
      {id: 'input', size: 256, type: 'storage', role: 'input'},
      {id: 'output', size: 256, type: 'storage', role: 'output'},
    ],
    shaders: [{id: 'sum', entryPoint: 'main', code: `
      @group(0) @binding(0) var<storage, read> input: array<u32>;
      @group(0) @binding(1) var<storage, read_write> output: array<u32>;
      @compute @workgroup_size(64) fn main(@builtin(global_invocation_id) id: vec3<u32>) {
        output[id.x] = input[id.x] + id.x;
      }`}],
    steps: [{shader: 'sum', bindings: [{binding: 0, buffer: 'input'}, {binding: 1, buffer: 'output'}], workgroups: [1,1,1]}],
    output: 'output',
  };
  for (const execution of ['webgpu','native-recorded','gpu-recorded']) {
    for (let cycle=0; cycle<cycles; cycle++) {
      const adapter = await requestAdapter({backend: 'vulkan'});
      const device = await adapter.requestDevice();
      const program = await prepareComputeProgram(device, descriptor, {execution});
      try {
        for (let run=0; run<runs; run++) {
          const input = new Uint32Array(64).fill((id+1)*10000+cycle*100+run);
          const result = await program.run({input});
          const output = new Uint32Array(result.output.buffer, result.output.byteOffset, 64);
          assert(output.every((value,index) => value === input[index]+index));
        }
      } finally { await program.close(); device.destroy(); adapter.destroy(); }
    }
    parentPort.postMessage({worker: id, execution, cycles, runs, status: 'passed'});
  }
}
