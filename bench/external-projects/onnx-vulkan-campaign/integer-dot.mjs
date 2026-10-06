// Independent exact integer oracle, including signed and unsigned wraparound.
import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';
const [modulePath, nativePath, output] = process.argv.slice(2);
process.env.DOE_WEBGPU_LIB = nativePath;
const provider = await import(pathToFileURL(modulePath).href);
Object.assign(globalThis, provider.globals);
const device = await (await provider.create(['backend=vulkan']).requestAdapter()).requestDevice();
const source = `
@group(0) @binding(0) var<storage,read> values: array<vec4<i32>>;
@group(0) @binding(1) var<storage,read_write> result: array<u32>;
@compute @workgroup_size(1) fn main() {
  result[0] = bitcast<u32>(dot(values[0].xy, values[1].xy));
  result[1] = bitcast<u32>(dot(values[0].xyz, values[1].xyz));
  result[2] = bitcast<u32>(dot(values[0], values[1]));
  result[3] = dot(bitcast<vec2u>(values[0].xy), bitcast<vec2u>(values[1].xy));
  result[4] = dot(bitcast<vec3u>(values[0].xyz), bitcast<vec3u>(values[1].xyz));
  result[5] = dot(bitcast<vec4u>(values[0]), bitcast<vec4u>(values[1]));
}`;
const buffers = [];
try {
  const input = device.createBuffer({ size: 32, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_DST });
  const result = device.createBuffer({ size: 24, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC });
  const readback = device.createBuffer({ size: 24, usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST });
  buffers.push(input, result, readback);
  const values = new Int32Array([-2147483648, 1073741825, -7, 13, -1, 4, -3, 1073741824]);
  device.queue.writeBuffer(input, 0, values);
  const shader = device.createShaderModule({ code: source });
  const pipeline = await device.createComputePipelineAsync({ layout: 'auto', compute: { module: shader, entryPoint: 'main' } });
  const group = device.createBindGroup({ layout: pipeline.getBindGroupLayout(0), entries: [
    { binding: 0, resource: { buffer: input } }, { binding: 1, resource: { buffer: result } },
  ] });
  const encoder = device.createCommandEncoder();
  const pass = encoder.beginComputePass();
  pass.setPipeline(pipeline); pass.setBindGroup(0, group); pass.dispatchWorkgroups(1); pass.end();
  encoder.copyBufferToBuffer(result, 0, readback, 0, 24);
  device.queue.submit([encoder.finish()]);
  await readback.mapAsync(GPUMapMode.READ);
  const observed = Array.from(new Uint32Array(readback.getMappedRange().slice(0)));
  readback.unmap();
  const expected = [];
  for (const unsigned of [false, true]) for (const lanes of [2, 3, 4]) {
    let total = 0n;
    for (let lane = 0; lane < lanes; lane++) total += BigInt(unsigned ? values[lane] >>> 0 : values[lane])
      * BigInt(unsigned ? values[lane + 4] >>> 0 : values[lane + 4]);
    expected.push(Number(BigInt.asUintN(32, total)));
  }
  assert.deepEqual(observed, expected);
  await writeFile(output, JSON.stringify({ schemaVersion: 1, passed: true, observed, expected,
    shaderSha256: createHash('sha256').update(source).digest('hex'),
    nativeSha256: createHash('sha256').update(await readFile(nativePath)).digest('hex') }, null, 2) + '\n');
} finally {
  await device.queue.onSubmittedWorkDone();
  for (const buffer of buffers) buffer.destroy();
  device.destroy();
}
