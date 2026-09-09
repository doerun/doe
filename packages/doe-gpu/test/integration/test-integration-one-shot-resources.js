import assert from 'node:assert/strict';
import { gpu, globals, requestAdapter } from '../../src/native.js';

const CYCLES = 8;
const INPUT = new Float32Array([1, 2, 3, 4]);
const CODE = `
@group(0) @binding(0) var<storage, read> input: array<f32>;
@group(0) @binding(1) var<storage, read_write> output: array<f32>;
@compute @workgroup_size(4) fn main(@builtin(global_invocation_id) id: vec3u) {
  output[id.x] = input[id.x] * 2.0;
}`;

const adapter = await requestAdapter();
assert(adapter);
let device, borrowed;
try {
  device = await adapter.requestDevice();
  const bound = gpu.bind(device);
  const compute = input => bound.compute({
    code: CODE, inputs: [input], output: { type: Float32Array, size: INPUT.byteLength }, workgroups: 1,
  });
  for (let cycle = 0; cycle < CYCLES; cycle += 1) {
    const inputs = [INPUT.map(value => value + cycle), INPUT.map(value => value + cycle + CYCLES)];
    const outputs = await Promise.all(inputs.map(compute));
    for (let index = 0; index < inputs.length; index += 1) {
      assert.deepEqual(Array.from(outputs[index]), Array.from(inputs[index], value => value * 2));
    }
  }
  const original = device.createComputePipeline;
  const failure = new Error('injected pipeline creation failure');
  device.createComputePipeline = () => { throw failure; };
  try {
    await assert.rejects(compute(INPUT), error => error === failure);
  } finally {
    device.createComputePipeline = original;
  }
  await assert.rejects(bound.compute({ inputs: [INPUT, null] }));
  assert.deepEqual(Array.from(await compute(INPUT)), [2, 4, 6, 8]);
  borrowed = device.createBuffer({
    size: INPUT.byteLength, usage: globals.GPUBufferUsage.STORAGE | globals.GPUBufferUsage.COPY_DST,
  });
  device.queue.writeBuffer(borrowed, 0, INPUT);
  assert.deepEqual(Array.from(await compute({ buffer: borrowed, access: 'read' })), [2, 4, 6, 8]);
  device.queue.writeBuffer(borrowed, 0, INPUT.map(value => value * 2));
  assert.deepEqual(Array.from(await compute({ buffer: borrowed, access: 'read' })), [4, 8, 12, 16]);
} finally {
  borrowed?.destroy();
  device?.destroy();
  adapter.destroy?.();
}
console.log('ok: one-shot outputs, concurrent calls, rejected creation, recovery, and borrowed-buffer reuse');
