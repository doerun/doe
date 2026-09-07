import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../../..');
const lane = process.argv[2];
assert(['W0', 'D0'].includes(lane));
const shaderPath = resolve(process.argv[3] ?? resolve(here, 'attention.wgsl'));
const outputPath = resolve(process.argv[4] ?? resolve(here, `${lane}-isolated.f32`));
const packageDirectory = process.argv[5] === 'native' ? 'native-retained' : 'retained';
const modulePath = lane === 'D0'
  ? resolve(here, packageDirectory, 'installed-package/node_modules/doe-gpu/src/compute.js')
  : resolve(root, 'bench/out/external-projects/doppler/upstream/node_modules/webgpu/index.js');
const provider = await import(pathToFileURL(modulePath));
const toggles = process.argv[5] === 'dump' ? 'allow_unsafe_apis,dump_shaders' : 'allow_unsafe_apis';
const gpu = provider.create(['backend=vulkan', `enable-dawn-features=${toggles}`]);
const adapter = await gpu.requestAdapter({ backend: 'vulkan' });
assert(adapter);
const device = await adapter.requestDevice({ requiredFeatures: ['shader-f16', 'subgroups'] });
const { GPUBufferUsage: U, GPUMapMode: M } = provider.globals;
const buffers = [];
let shader, pipeline, layout, group;
try {
  const code = readFileSync(shaderPath, 'utf8');
  shader = device.createShaderModule({ code });
  const messages = (await shader.getCompilationInfo()).messages;
  assert(!messages.some(m => m.type === 'error'), JSON.stringify(messages));
  pipeline = device.createComputePipeline({ layout: 'auto', compute: { module: shader, entryPoint: 'main' } });
  const inputNames = ['uniform.bin', 'q.f32', 'k.f16', 'v.f16', null, null, null];
  const capture = code.includes('@binding(7)');
  if (capture) inputNames.push(null);
  for (let binding = 0; binding < inputNames.length; binding++) {
    const data = inputNames[binding] ? readFileSync(resolve(here, inputNames[binding])) : null;
    const buffer = device.createBuffer({
      size: data?.byteLength ?? (binding === 4 || binding === 7 ? 4096 : 4),
      usage: (binding === 0 ? U.UNIFORM : U.STORAGE) | U.COPY_DST | U.COPY_SRC,
    });
    buffers.push(buffer);
    if (data) device.queue.writeBuffer(buffer, 0, data);
  }
  layout = pipeline.getBindGroupLayout(0);
  group = device.createBindGroup({ layout, entries: buffers.map((buffer, binding) => ({ binding, resource: { buffer } })) });
  const readback = device.createBuffer({ size: 4096, usage: U.MAP_READ | U.COPY_DST });
  const debugReadback = capture ? device.createBuffer({ size: 4096, usage: U.MAP_READ | U.COPY_DST }) : null;
  buffers.push(readback);
  if (debugReadback) buffers.push(debugReadback);
  const encoder = device.createCommandEncoder();
  const pass = encoder.beginComputePass();
  pass.setPipeline(pipeline);
  pass.setBindGroup(0, group);
  pass.dispatchWorkgroups(4);
  pass.end();
  encoder.copyBufferToBuffer(buffers[4], 0, readback, 0, 4096);
  if (debugReadback) encoder.copyBufferToBuffer(buffers[7], 0, debugReadback, 0, 4096);
  device.queue.submit([encoder.finish()]);
  await readback.mapAsync(M.READ);
  const output = Buffer.from(new Uint8Array(readback.getMappedRange()));
  writeFileSync(outputPath, output);
  readback.unmap();
  if (debugReadback) {
    await debugReadback.mapAsync(M.READ);
    writeFileSync(`${outputPath}.debug`, Buffer.from(new Uint8Array(debugReadback.getMappedRange())));
    debugReadback.unmap();
  }
  await device.queue.onSubmittedWorkDone();
  console.log(lane, 'shader sha256', createHash('sha256').update(code).digest('hex'));
  console.log('provider module', modulePath);
  console.log('adapter', JSON.stringify(adapter.info));
  console.log('output sha256', createHash('sha256').update(output).digest('hex'));
  const expected = readFileSync(resolve(here, `${lane}-model.f32`));
  let max = 0, changed = 0;
  for (let i = 0; i < output.length; i += 4) {
    const actual = output.readFloatLE(i), wanted = expected.readFloatLE(i);
    assert(Number.isFinite(actual));
    max = Math.max(max, Math.abs(actual - wanted));
    if (output.readUInt32LE(i) !== expected.readUInt32LE(i)) changed++;
  }
  console.log('against retained model output', JSON.stringify({ changed, maxAbsoluteError: max }));
} finally {
  group?.destroy?.(); layout?.destroy?.(); pipeline?.destroy?.(); shader?.destroy?.();
  for (const buffer of buffers) buffer.destroy();
  device.destroy(); adapter.destroy?.(); gpu.destroy?.();
}
