#!/usr/bin/env node
// Ordinary package execution must preserve the complete shader and selected entry point.

import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { setupGlobals, providerInfo } from '../../src/index.js';
import { releaseOwnedResource } from '../../src/vendor/webgpu/shared/resource-lifecycle.js';

setupGlobals();
const adapter = await navigator.gpu.requestAdapter();
assert.ok(adapter, 'shader semantics regression requires a native adapter');
const device = await adapter.requestDevice();
console.log(JSON.stringify({ provider: providerInfo(), adapter: adapter.info }));

const CLEAR = `
@group(0) @binding(0) var<storage, read_write> data: array<u32>;
@compute @workgroup_size(1) fn main() {
  for (var i: u32 = 0u; i < arrayLength(&data); i = i + 1u) { data[i] = 0u; }
  data[0] = 7u;
}`;
const CASES = [
  {
    label: 'unsigned byte unpack preserves order, zero extension, and single evaluation',
    code: `@group(0) @binding(0) var<storage, read_write> data: array<u32>;
      var<private> calls: u32;
      fn nextWord() -> u32 { calls += 1u; return 0x80ff017fu; }
      @compute @workgroup_size(1) fn main() {
        let mixed = unpack4xU8(nextWord());
        let zero = unpack4xU8(0u);
        let full = unpack4xU8(0xffffffffu);
        let low = unpack4xU8(0xf1e2d3c4u & 0x0f0f0f0fu);
        let high = unpack4xU8((0xf1e2d3c4u >> 4u) & 0x0f0f0f0fu);
        for (var i = 0u; i < 4u; i++) {
          data[i] = mixed[i]; data[4u + i] = zero[i]; data[8u + i] = full[i];
          data[12u + i] = low[i]; data[16u + i] = high[i];
        }
        data[20] = calls;
      }`,
    expected: [127, 1, 255, 128, 0, 0, 0, 0, 255, 255, 255, 255,
      4, 3, 2, 1, 12, 13, 14, 15, 1],
  },
  { label: 'clear followed by write', code: CLEAR, expected: [7, 0, 0, 0] },
  {
    label: 'additional writes', code: CLEAR.replace('data[0] = 7u;',
      'data[0] = 7u; data[3] = 19u;'), expected: [7, 0, 0, 19],
  },
  {
    label: 'selected alternate entry point', entryPoint: 'other',
    code: `${CLEAR}\n@compute @workgroup_size(1) fn other() { data[0] = 31u; }`,
    expected: [31, 5, 5, 5],
  },
  { label: 'zero dispatch', code: CLEAR, dispatch: 0, expected: [5, 5, 5, 5] },
  {
    label: 'comment match is not executable',
    code: `@group(0) @binding(0) var<storage, read_write> data: array<u32>;
      // arrayLength(&data) for (var i = 0u; i < 4u; i++) { data[i] = 0u; }
      @compute @workgroup_size(1) fn main() { data[0] = 23u; }`,
    expected: [23, 5, 5, 5],
  },
  {
    label: 'generated fill preserves extra operation',
    code: `struct OutputBuffer { value: array<u32> }
      @group(0) @binding(0) var<storage, read_write> dst : OutputBuffer;
      @compute @workgroup_size(1) fn main(@builtin(global_invocation_id) GlobalInvocationID: vec3u) {
        var xExtent: u32 = 4u * 1u;
        var yExtent: u32 = 1u * 1u;
        var zExtent: u32 = 1u * 1u;
        if (GlobalInvocationID.x > xExtent || GlobalInvocationID.y > yExtent || GlobalInvocationID.z > zExtent) { return; }
        let index = GlobalInvocationID.x;
        var val: u32 = 11u;
        dst.value[index] = val;
        dst.value[index] = dst.value[index] + 2u;
      }`, dispatch: 4, expected: [13, 13, 13, 13],
  },
  {
    label: 'texture dimensions preserve arithmetic and partial dispatch', texture: true,
    code: `@group(0) @binding(0) var texture: texture_2d<f32>;
      @group(1) @binding(0) var<storage, read_write> results: array<vec4<u32>>;
      fn getValue() -> vec4u { return vec4u(textureDimensions(texture, 0), 7u, 9u); }
      @compute @workgroup_size(1) fn main() { results[0] = getValue() + vec4u(1u); }`,
    expected: [9, 5, 8, 10, 5, 5, 5, 5],
  },
];

async function runCase({ label, code, entryPoint = 'main', dispatch = 1, expected, texture }, path) {
  const size = expected.length * Uint32Array.BYTES_PER_ELEMENT;
  const output = device.createBuffer({
    size, usage: GPUBufferUsage.STORAGE | GPUBufferUsage.COPY_SRC | GPUBufferUsage.COPY_DST,
  });
  const staging = device.createBuffer({
    size, usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ,
  });
  const inputTexture = texture ? device.createTexture({
    size: [8, 4], format: 'rgba8unorm', usage: GPUTextureUsage.TEXTURE_BINDING,
  }) : null;
  const resources = [];
  try {
    device.queue.writeBuffer(output, 0, new Uint32Array(expected.length).fill(5));
    const module = device.createShaderModule({ code });
    resources.push(module);
    const pipeline = device.createComputePipeline({
      layout: 'auto', compute: { module, entryPoint },
    });
    resources.push(pipeline);
    const layout = pipeline.getBindGroupLayout(texture ? 1 : 0);
    resources.push(layout);
    const bindings = device.createBindGroup({
      layout,
      entries: [{ binding: 0, resource: { buffer: output } }],
    });
    resources.push(bindings);
    const encoder = device.createCommandEncoder();
    const pass = path === 'native' ? encoder.beginComputePass({ label }) : encoder.beginComputePass();
    pass.setPipeline(pipeline);
    pass.setBindGroup(texture ? 1 : 0, bindings);
    if (inputTexture) {
      const view = inputTexture.createView();
      const textureLayout = pipeline.getBindGroupLayout(0);
      const textureBindings = device.createBindGroup({
        layout: textureLayout, entries: [{ binding: 0, resource: view }],
      });
      resources.push(view, textureLayout, textureBindings);
      releaseOwnedResource(textureLayout);
      pass.setBindGroup(0, textureBindings);
    }
    pass.dispatchWorkgroups(dispatch);
    pass.end();
    const copy = path === 'dispatch-copy' ? encoder : device.createCommandEncoder();
    copy.copyBufferToBuffer(output, 0, staging, 0, size);
    if (path === 'dispatch-copy') {
      device.queue.submit([encoder.finish()]);
    } else if (path === 'multi-buffer') {
      device.queue.submit([encoder.finish(), copy.finish()]);
    } else {
      // A separate submission exercises the former clear/fill substitution path.
      device.queue.submit([encoder.finish()]);
      device.queue.submit([copy.finish()]);
    }
    await staging.mapAsync(GPUMapMode.READ);
    const actual = Array.from(new Uint32Array(staging.getMappedRange().slice(0)));
    staging.unmap();
    console.log(JSON.stringify({
      label, path, sourceSha256: createHash('sha256').update(code).digest('hex'),
      entryPoint, dispatch, actual, expected,
    }));
    assert.deepEqual(actual, expected, label);
  } finally {
    for (const resource of resources.reverse()) releaseOwnedResource(resource);
    inputTexture?.destroy();
    staging.destroy();
    output.destroy();
  }
}

async function runMappedWriteCase() {
  const source = device.createBuffer({
    size: 16, usage: GPUBufferUsage.MAP_WRITE | GPUBufferUsage.COPY_SRC, mappedAtCreation: true,
  });
  const staging = device.createBuffer({
    size: 16, usage: GPUBufferUsage.MAP_READ | GPUBufferUsage.COPY_DST,
  });
  try {
    new Uint32Array(source.getMappedRange()).set([2, 3, 5, 7]);
    source.unmap();
    await source.mapAsync(GPUMapMode.WRITE);
    const mapped = new Uint32Array(source.getMappedRange());
    assert.deepEqual(Array.from(mapped), [2, 3, 5, 7], 'write mapping preserves native contents');
    mapped[1] = 13;
    source.unmap();
    const encoder = device.createCommandEncoder();
    encoder.copyBufferToBuffer(source, 0, staging, 0, 16);
    device.queue.submit([encoder.finish()]);
    await staging.mapAsync(GPUMapMode.READ);
    assert.deepEqual(Array.from(new Uint32Array(staging.getMappedRange())), [2, 13, 5, 7]);
    staging.unmap();
  } finally {
    source.destroy();
    staging.destroy();
  }
}

async function runTextureRenderCase() {
  const rowBytes = 256;
  const source = device.createTexture({
    size: [8, 4], format: 'rgba8unorm', usage: GPUTextureUsage.TEXTURE_BINDING,
  });
  const target = device.createTexture({
    size: [1, 1], format: 'rgba32uint',
    usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.COPY_SRC,
  });
  const staging = device.createBuffer({
    size: rowBytes, usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ,
  });
  const resources = [];
  try {
    const code = `@group(0) @binding(0) var texture: texture_2d<f32>;
      fn getValue() -> vec4u { return vec4u(textureDimensions(texture, 0), 7u, 9u); }
      @vertex fn vertexMain(@builtin(vertex_index) index: u32) -> @builtin(position) vec4f {
        var x = -1.0; var y = -1.0;
        if (index == 1u) { x = 3.0; }
        if (index == 2u) { y = 3.0; }
        return vec4f(x, y, 0.0, 1.0);
      }
      @fragment fn fragmentMain() -> @location(0) vec4u { return getValue() + vec4u(1u); }`;
    const module = device.createShaderModule({ code });
    resources.push(module);
    const pipeline = device.createRenderPipeline({
      layout: 'auto', vertex: { module, entryPoint: 'vertexMain' },
      fragment: { module, entryPoint: 'fragmentMain', targets: [{ format: 'rgba32uint' }] },
      primitive: { topology: 'triangle-list' },
    });
    resources.push(pipeline);
    const layout = pipeline.getBindGroupLayout(0);
    const sourceView = source.createView();
    const targetView = target.createView();
    const group = device.createBindGroup({
      layout, entries: [{ binding: 0, resource: sourceView }],
    });
    resources.push(layout, sourceView, targetView, group);
    const encoder = device.createCommandEncoder();
    const pass = encoder.beginRenderPass({ colorAttachments: [{
      view: targetView, loadOp: 'clear', storeOp: 'store', clearValue: [0, 0, 0, 0],
    }] });
    pass.setPipeline(pipeline);
    pass.setBindGroup(0, group);
    pass.draw(3);
    pass.end();
    encoder.copyTextureToBuffer({ texture: target }, {
      buffer: staging, bytesPerRow: rowBytes, rowsPerImage: 1,
    }, [1, 1, 1]);
    device.queue.submit([encoder.finish()]);
    await staging.mapAsync(GPUMapMode.READ);
    const actual = Array.from(new Uint32Array(staging.getMappedRange(), 0, 4));
    staging.unmap();
    console.log(JSON.stringify({
      label: 'texture dimensions in rendering',
      sourceSha256: createHash('sha256').update(code).digest('hex'), actual,
    }));
    assert.deepEqual(actual, [9, 5, 8, 10]);
  } finally {
    for (const resource of resources.reverse()) releaseOwnedResource(resource);
    source.destroy();
    target.destroy();
    staging.destroy();
  }
}

let failures = 0;
try {
  const checks = [
    ...CASES.flatMap(testCase => ['batched', 'native', 'dispatch-copy', 'multi-buffer'].map(path => ({
      label: `${testCase.label} / ${path}`, run: () => runCase(testCase, path),
    }))),
    { label: 'mapped writes use native contents', run: runMappedWriteCase },
    { label: 'texture dimensions in rendering', run: runTextureRenderCase },
  ];
  for (const testCase of checks) {
    try {
      await testCase.run();
      console.log(`ok: ${testCase.label}`);
    } catch (error) {
      failures += 1;
      console.error(`FAIL: ${testCase.label}: ${error.stack}`);
    }
  }
} finally {
  device.destroy();
  adapter.destroy?.();
}
assert.equal(failures, 0, 'ordinary native shader semantics');
