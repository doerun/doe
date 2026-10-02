// Focused physical Vulkan preparation diagnostic. The UMAP application
// comparison remains the separate unchanged-workload acceptance path.
import assert from 'node:assert/strict';
import { create, globals } from '../../packages/doe-gpu/src/index.js';

const { GPUBufferUsage, GPUMapMode } = globals;
const gpu = create([]);
const adapter = await gpu.requestAdapter();
assert(adapter);
const device = await adapter.requestDevice();
const code = `
@group(0) @binding(0) var<storage, read> input: array<u32>;
@group(0) @binding(1) var<storage, read_write> first_output: array<u32>;
@group(0) @binding(2) var<storage, read_write> second_output: array<u32>;
@id(4) override SCALE: u32 = 2u;
@compute @workgroup_size(1) fn first() { first_output[0] = input[0] + 1u; }
@compute @workgroup_size(1) fn second() { second_output[0] = input[0] * SCALE; }
`;
const shader = device.createShaderModule({ code });
const input = device.createBuffer({ size: 4, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST });
const firstOutput = device.createBuffer({ size: 4, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC });
const secondOutput = device.createBuffer({ size: 4, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC });
const readback = device.createBuffer({ size: 4, usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ });
device.queue.writeBuffer(input, 0, new Uint32Array([7]));

async function run(entryPoint, constants, target, expected) {
  const pipeline = device.createComputePipeline({ layout: 'auto', compute: { module: shader, entryPoint, ...(constants && { constants }) } });
  const bindGroup = device.createBindGroup({
    layout: pipeline.getBindGroupLayout(0),
    entries: [
      { binding: 0, resource: { buffer: input } },
      { binding: entryPoint === 'first' ? 1 : 2, resource: { buffer: target } },
    ],
  });
  const encoder = device.createCommandEncoder();
  const pass = encoder.beginComputePass();
  pass.setPipeline(pipeline);
  pass.setBindGroup(0, bindGroup);
  pass.dispatchWorkgroups(1);
  pass.end();
  encoder.copyBufferToBuffer(target, 0, readback, 0, 4);
  device.queue.submit([encoder.finish()]);
  await readback.mapAsync(GPUMapMode.READ);
  const result = new Uint32Array(readback.getMappedRange().slice(0))[0];
  readback.unmap();
  assert.equal(result, expected);
  return result;
}

const outputs = [
  await run('first', null, firstOutput, 8),
  await run('first', null, firstOutput, 8),
  await run('second', null, secondOutput, 14),
  await run('second', { 4: 3 }, secondOutput, 21),
  await run('second', { 4: 4 }, secondOutput, 28),
];
const repeatedPipelines = [];
const preparationStart = performance.now();
for (let index = 0; index < 200; index += 1) {
  repeatedPipelines.push(device.createComputePipeline({ layout: 'auto', compute: { module: shader, entryPoint: 'first' } }));
}
const repeatedPipelineMs = performance.now() - preparationStart;
assert.equal(repeatedPipelines.length, 200);
assert.throws(() => device.createComputePipeline({ layout: 'auto', compute: { module: shader, entryPoint: 'missing' } }));
let unknownOverrideRejected = false;
try {
  device.createComputePipeline({ layout: 'auto', compute: { module: shader, entryPoint: 'second', constants: { UNKNOWN: 3 } } });
} catch {
  unknownOverrideRejected = true;
}
if (process.argv.includes('--require-override-rejection')) assert(unknownOverrideRejected);
let namedIdOverrideRejected = false;
try {
  device.createComputePipeline({ layout: 'auto', compute: { module: shader, entryPoint: 'second', constants: { SCALE: 3 } } });
} catch {
  namedIdOverrideRejected = true;
}
if (process.argv.includes('--require-override-rejection')) assert(namedIdOverrideRejected);
console.log(JSON.stringify({
  outputs,
  repeatedPipelineMs,
  unknownOverrideRejected,
  namedIdOverrideRejected,
  adapter: adapter.info ?? null,
  provider: 'doe-gpu',
}));

readback.destroy();
firstOutput.destroy();
secondOutput.destroy();
input.destroy();
device.destroy();
