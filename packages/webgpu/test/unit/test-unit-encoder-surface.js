import assert from 'node:assert/strict';
import { createEncoderClasses } from '../../src/shared/encoder-surface.js';

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`  PASS: ${name}`);
  } catch (error) {
    failed += 1;
    console.error(`  FAIL: ${name}`);
    console.error(`        ${error.message}`);
  }
}

// Minimal backend stub that records calls without requiring GPU hardware.
// Each method stores its invocation so tests can verify forwarding.
function createStubBackend(overrides = {}) {
  const calls = [];
  function record(name, ...args) {
    calls.push({ name, args });
  }
  const base = {
    computePassInit(self, state) { record('computePassInit', self, state); },
    computePassAssertOpen(self, path) {
      if (self._closed) throw new Error(`${path}: encoder is closed`);
    },
    computePassSetPipeline(self, native) { record('computePassSetPipeline', self, native); },
    computePassSetBindGroup(self, index, native) { record('computePassSetBindGroup', self, index, native); },
    computePassSetImmediates(self, index, data) { record('computePassSetImmediates', self, index, data); },
    computePassDispatchWorkgroups(self, x, y, z) { record('computePassDispatchWorkgroups', self, x, y, z); },
    computePassDispatchWorkgroupsIndirect(self, native, offset) { record('computePassDispatchWorkgroupsIndirect', self, native, offset); },
    computePassPushDebugGroup(self, label) { record('computePassPushDebugGroup', self, label); },
    computePassPopDebugGroup(self) { record('computePassPopDebugGroup', self); },
    computePassInsertDebugMarker(self, label) { record('computePassInsertDebugMarker', self, label); },
    computePassEnd(self) { self._closed = true; record('computePassEnd', self); },

    renderPassInit(self, state) { record('renderPassInit', self, state); },
    renderPassAssertOpen(self, path) {
      if (self._closed) throw new Error(`${path}: encoder is closed`);
    },
    renderPassSetPipeline(self, native) { record('renderPassSetPipeline', self, native); },
    renderPassSetBindGroup(self, index, native) { record('renderPassSetBindGroup', self, index, native); },
    renderPassSetImmediates(self, index, data) { record('renderPassSetImmediates', self, index, data); },
    renderPassSetVertexBuffer(self, slot, native, offset, size) { record('renderPassSetVertexBuffer', self, slot, native, offset, size); },
    renderPassSetIndexBuffer(self, native, format, offset, size) { record('renderPassSetIndexBuffer', self, native, format, offset, size); },
    renderPassDraw(self, vc, ic, fv, fi) { record('renderPassDraw', self, vc, ic, fv, fi); },
    renderPassDrawIndexed(self, ic, instC, fi, bv, fiI) { record('renderPassDrawIndexed', self, ic, instC, fi, bv, fiI); },
    renderPassDrawIndirect(self, native, offset) { record('renderPassDrawIndirect', self, native, offset); },
    renderPassDrawIndexedIndirect(self, native, offset) { record('renderPassDrawIndexedIndirect', self, native, offset); },
    renderPassSetViewport(self, x, y, w, h, minD, maxD) { record('renderPassSetViewport', self, x, y, w, h, minD, maxD); },
    renderPassSetScissorRect(self, x, y, w, h) { record('renderPassSetScissorRect', self, x, y, w, h); },
    renderPassSetBlendConstant(self, color) { record('renderPassSetBlendConstant', self, color); },
    renderPassSetStencilReference(self, ref) { record('renderPassSetStencilReference', self, ref); },
    renderPassBeginOcclusionQuery(self, qi) { record('renderPassBeginOcclusionQuery', self, qi); },
    renderPassEndOcclusionQuery(self) { record('renderPassEndOcclusionQuery', self); },
    renderPassPushDebugGroup(self, label) { record('renderPassPushDebugGroup', self, label); },
    renderPassPopDebugGroup(self) { record('renderPassPopDebugGroup', self); },
    renderPassInsertDebugMarker(self, label) { record('renderPassInsertDebugMarker', self, label); },
    renderPassExecuteBundles(self, bundles) { record('renderPassExecuteBundles', self, bundles); },
    renderPassEnd(self) { self._closed = true; record('renderPassEnd', self); },

    renderBundleEncoderInit(self, state) { record('renderBundleEncoderInit', self, state); },
    renderBundleEncoderAssertOpen(self, path) {
      if (self._finished) throw new Error(`${path}: encoder is finished`);
    },
    renderBundleEncoderSetPipeline(self, native) { record('renderBundleEncoderSetPipeline', self, native); },
    renderBundleEncoderSetBindGroup(self, index, native) { record('renderBundleEncoderSetBindGroup', self, index, native); },
    renderBundleEncoderSetImmediates(self, index, data) { record('renderBundleEncoderSetImmediates', self, index, data); },
    renderBundleEncoderSetVertexBuffer(self, slot, native, offset, size) { record('renderBundleEncoderSetVertexBuffer', self, slot, native, offset, size); },
    renderBundleEncoderSetIndexBuffer(self, native, format, offset, size) { record('renderBundleEncoderSetIndexBuffer', self, native, format, offset, size); },
    renderBundleEncoderDraw(self, vc, ic, fv, fi) { record('renderBundleEncoderDraw', self, vc, ic, fv, fi); },
    renderBundleEncoderDrawIndexed(self, ic, instC, fi, bv, fiI) { record('renderBundleEncoderDrawIndexed', self, ic, instC, fi, bv, fiI); },
    renderBundleEncoderDrawIndirect(self, native, offset) { record('renderBundleEncoderDrawIndirect', self, native, offset); },
    renderBundleEncoderDrawIndexedIndirect(self, native, offset) { record('renderBundleEncoderDrawIndexedIndirect', self, native, offset); },
    renderBundleEncoderPushDebugGroup(self, label) { record('renderBundleEncoderPushDebugGroup', self, label); },
    renderBundleEncoderPopDebugGroup(self) { record('renderBundleEncoderPopDebugGroup', self); },
    renderBundleEncoderInsertDebugMarker(self, label) { record('renderBundleEncoderInsertDebugMarker', self, label); },
    renderBundleEncoderFinish(self, descriptor, classes) {
      record('renderBundleEncoderFinish', self, descriptor);
      return new classes.DoeGPURenderBundle({}, self);
    },

    renderBundleDestroy(native) { record('renderBundleDestroy', native); },

    commandEncoderInit(self, state) { record('commandEncoderInit', self, state); },
    commandEncoderAssertOpen(self, path) {
      if (self._finished) throw new Error(`${path}: encoder is finished`);
    },
    commandEncoderBeginComputePass(self, descriptor, classes) {
      record('commandEncoderBeginComputePass', self, descriptor);
      return new classes.DoeGPUComputePassEncoder({}, self);
    },
    commandEncoderBeginRenderPass(self, descriptor, classes) {
      record('commandEncoderBeginRenderPass', self, descriptor);
      return new classes.DoeGPURenderPassEncoder({}, self);
    },
    commandEncoderCopyBufferToBuffer(self, src, srcOff, dst, dstOff, size) { record('commandEncoderCopyBufferToBuffer'); },
    commandEncoderCopyBufferToTexture(self, src, dst, size) { record('commandEncoderCopyBufferToTexture'); },
    commandEncoderCopyTextureToBuffer(self, src, dst, size) { record('commandEncoderCopyTextureToBuffer'); },
    commandEncoderCopyTextureToTexture(self, src, dst, size) { record('commandEncoderCopyTextureToTexture'); },
    commandEncoderClearBuffer(self, native, offset, size) { record('commandEncoderClearBuffer'); },
    commandEncoderWriteTimestamp(self, native, qi) { record('commandEncoderWriteTimestamp'); },
    commandEncoderResolveQuerySet(self, native, fq, qc, dst, dstOff) { record('commandEncoderResolveQuerySet'); },
    commandEncoderPushDebugGroup(self, label) { record('commandEncoderPushDebugGroup', self, label); },
    commandEncoderPopDebugGroup(self) { record('commandEncoderPopDebugGroup', self); },
    commandEncoderInsertDebugMarker(self, label) { record('commandEncoderInsertDebugMarker', self, label); },
    commandEncoderFinish(self) {
      self._finished = true;
      record('commandEncoderFinish', self);
      return { _native: {}, _batched: false };
    },

    commandBufferDestroy(native) { record('commandBufferDestroy', native); },
  };
  return { backend: { ...base, ...overrides }, calls };
}

function makeLiveResource(label = 'GPUBuffer') {
  return { _native: {}, _destroyed: false, _resourceLabel: label };
}

function makeLiveDevice() {
  return { _native: {}, _destroyed: false, _resourceLabel: 'GPUDevice' };
}

// ============================================================
// createEncoderClasses — class factory
// ============================================================
console.log('\ncreateEncoderClasses — class factory');

test('returns an object with all expected class constructors', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  assert.ok(classes != null && typeof classes === 'object');
  const expectedNames = [
    'DoeGPUComputePassEncoder',
    'DoeGPURenderPassEncoder',
    'DoeGPURenderBundle',
    'DoeGPURenderBundleEncoder',
    'DoeGPUCommandBuffer',
    'DoeGPUCommandEncoder',
  ];
  for (const name of expectedNames) {
    assert.ok(typeof classes[name] === 'function', `missing ${name}`);
  }
});

test('returned constructors are class functions', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  for (const [name, Ctor] of Object.entries(classes)) {
    assert.strictEqual(typeof Ctor, 'function', `${name} should be a function`);
    assert.ok(Ctor.prototype != null, `${name} should have a prototype`);
  }
});

// ============================================================
// DoeGPUComputePassEncoder — method existence
// ============================================================
console.log('\nDoeGPUComputePassEncoder — method existence');

test('has all expected WebGPU compute pass methods', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  const expectedMethods = [
    'setPipeline',
    'setBindGroup',
    'setImmediates',
    'dispatchWorkgroups',
    'dispatchWorkgroupsIndirect',
    'pushDebugGroup',
    'popDebugGroup',
    'insertDebugMarker',
    'end',
  ];
  for (const method of expectedMethods) {
    assert.strictEqual(typeof pass[method], 'function', `missing method ${method}`);
  }
});

// ============================================================
// DoeGPURenderPassEncoder — method existence
// ============================================================
console.log('\nDoeGPURenderPassEncoder — method existence');

test('has all expected WebGPU render pass methods', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginRenderPass({ colorAttachments: [] });
  const expectedMethods = [
    'setPipeline',
    'setBindGroup',
    'setImmediates',
    'setVertexBuffer',
    'setIndexBuffer',
    'draw',
    'drawIndexed',
    'drawIndirect',
    'drawIndexedIndirect',
    'setViewport',
    'setScissorRect',
    'setBlendConstant',
    'setStencilReference',
    'beginOcclusionQuery',
    'endOcclusionQuery',
    'pushDebugGroup',
    'popDebugGroup',
    'insertDebugMarker',
    'executeBundles',
    'end',
  ];
  for (const method of expectedMethods) {
    assert.strictEqual(typeof pass[method], 'function', `missing method ${method}`);
  }
});

// ============================================================
// DoeGPUCommandEncoder — method existence
// ============================================================
console.log('\nDoeGPUCommandEncoder — method existence');

test('has all expected WebGPU command encoder methods', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const expectedMethods = [
    'beginComputePass',
    'beginRenderPass',
    'copyBufferToBuffer',
    'copyBufferToTexture',
    'copyTextureToBuffer',
    'copyTextureToTexture',
    'clearBuffer',
    'writeTimestamp',
    'resolveQuerySet',
    'pushDebugGroup',
    'popDebugGroup',
    'insertDebugMarker',
    'finish',
  ];
  for (const method of expectedMethods) {
    assert.strictEqual(typeof encoder[method], 'function', `missing method ${method}`);
  }
});

// ============================================================
// DoeGPURenderBundleEncoder — method existence
// ============================================================
console.log('\nDoeGPURenderBundleEncoder — method existence');

test('has all expected WebGPU render bundle encoder methods', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const rbe = new classes.DoeGPURenderBundleEncoder({}, device);
  const expectedMethods = [
    'setPipeline',
    'setBindGroup',
    'setImmediates',
    'setVertexBuffer',
    'setIndexBuffer',
    'draw',
    'drawIndexed',
    'drawIndirect',
    'drawIndexedIndirect',
    'pushDebugGroup',
    'popDebugGroup',
    'insertDebugMarker',
    'finish',
  ];
  for (const method of expectedMethods) {
    assert.strictEqual(typeof rbe[method], 'function', `missing method ${method}`);
  }
});

// ============================================================
// DoeGPUCommandBuffer — method existence and state
// ============================================================
console.log('\nDoeGPUCommandBuffer — construction and state');

test('DoeGPUCommandBuffer has destroy method', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const cb = new classes.DoeGPUCommandBuffer({ _batched: false, _native: {} }, makeLiveDevice());
  assert.strictEqual(typeof cb.destroy, 'function');
});

test('DoeGPUCommandBuffer has label property', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const cb = new classes.DoeGPUCommandBuffer({ _batched: false, _native: {} }, makeLiveDevice());
  assert.strictEqual(cb.label, '');
});

test('DoeGPUCommandBuffer tracks submitted state', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const cb = new classes.DoeGPUCommandBuffer({ _batched: false, _native: {} }, makeLiveDevice());
  assert.strictEqual(cb._submitted, false);
});

// ============================================================
// Input validation — integer range checks
// ============================================================
console.log('\nInput validation — integer range checks');

test('computePass.setBindGroup rejects negative index', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  assert.throws(
    () => pass.setBindGroup(-1, makeLiveResource('GPUBindGroup')),
    /must be an integer/,
  );
});

test('computePass.setBindGroup rejects non-integer index', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  assert.throws(
    () => pass.setBindGroup(1.5, makeLiveResource('GPUBindGroup')),
    /must be an integer/,
  );
});

test('computePass.dispatchWorkgroups rejects negative x', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  assert.throws(
    () => pass.dispatchWorkgroups(-1),
    /must be an integer/,
  );
});

test('computePass.dispatchWorkgroups accepts 0', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  pass.dispatchWorkgroups(0, 0, 0);
});

test('renderPass.draw rejects negative vertexCount', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginRenderPass({ colorAttachments: [] });
  assert.throws(
    () => pass.draw(-1),
    /must be an integer/,
  );
});

test('renderPass.setScissorRect rejects non-integer width', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginRenderPass({ colorAttachments: [] });
  assert.throws(
    () => pass.setScissorRect(0, 0, 2.5, 100),
    /must be an integer/,
  );
});

test('renderPass.setStencilReference rejects negative reference', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginRenderPass({ colorAttachments: [] });
  assert.throws(
    () => pass.setStencilReference(-1),
    /must be an integer/,
  );
});

test('commandEncoder.copyBufferToBuffer rejects size of 0', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  assert.throws(
    () => encoder.copyBufferToBuffer(makeLiveResource(), 0, makeLiveResource(), 0, 0),
    /must be an integer/,
  );
});

test('commandEncoder.copyBufferToBuffer rejects negative srcOffset', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  assert.throws(
    () => encoder.copyBufferToBuffer(makeLiveResource(), -1, makeLiveResource(), 0, 4),
    /must be an integer/,
  );
});

test('renderPass.drawIndexed rejects non-integer instanceCount', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginRenderPass({ colorAttachments: [] });
  assert.throws(
    () => pass.drawIndexed(3, 1.5),
    /must be an integer/,
  );
});

// ============================================================
// Input validation — resource liveness
// ============================================================
console.log('\nInput validation — resource liveness');

test('computePass.setPipeline rejects destroyed resource', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  const deadPipeline = { _native: null, _destroyed: true, _resourceLabel: 'GPUComputePipeline' };
  assert.throws(
    () => pass.setPipeline(deadPipeline),
    /was destroyed/,
  );
});

test('computePass.setBindGroup rejects destroyed bind group', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  const deadBG = { _native: null, _destroyed: true, _resourceLabel: 'GPUBindGroup' };
  assert.throws(
    () => pass.setBindGroup(0, deadBG),
    /was destroyed/,
  );
});

test('renderPass.setPipeline rejects destroyed resource', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginRenderPass({ colorAttachments: [] });
  const deadPipeline = { _native: null, _destroyed: true, _resourceLabel: 'GPURenderPipeline' };
  assert.throws(
    () => pass.setPipeline(deadPipeline),
    /was destroyed/,
  );
});

test('renderPass.setVertexBuffer rejects destroyed buffer', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginRenderPass({ colorAttachments: [] });
  const deadBuffer = { _native: null, _destroyed: true, _resourceLabel: 'GPUBuffer' };
  assert.throws(
    () => pass.setVertexBuffer(0, deadBuffer),
    /was destroyed/,
  );
});

test('commandEncoder.clearBuffer rejects destroyed buffer', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const deadBuffer = { _native: null, _destroyed: true, _resourceLabel: 'GPUBuffer' };
  assert.throws(
    () => encoder.clearBuffer(deadBuffer, 0, 4),
    /was destroyed/,
  );
});

test('commandEncoder.beginRenderPass requires descriptor object', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  assert.throws(
    () => encoder.beginRenderPass(null),
    /must be an object/,
  );
});

// ============================================================
// Input validation — setImmediates data
// ============================================================
console.log('\nInput validation — setImmediates data');

test('computePass.setImmediates accepts Uint8Array', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  pass.setImmediates(0, new Uint8Array([1, 2, 3, 4]));
});

test('computePass.setImmediates accepts ArrayBuffer', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  pass.setImmediates(0, new ArrayBuffer(16));
});

test('computePass.setImmediates rejects non-buffer data', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  assert.throws(
    () => pass.setImmediates(0, 'not-a-buffer'),
    /data must be/,
  );
});

test('computePass.setImmediates rejects out-of-range data slice', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  assert.throws(
    () => pass.setImmediates(0, new Uint8Array(4), 0, 8),
    /exceeds source byteLength/,
  );
});

test('computePass.setImmediates rejects negative dataOffset', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  assert.throws(
    () => pass.setImmediates(0, new Uint8Array(4), -1),
    /must be an integer/,
  );
});

// ============================================================
// State machine — compute pass open/closed
// ============================================================
console.log('\nState machine — compute pass open/closed');

test('computePass methods work before end()', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  pass.dispatchWorkgroups(1, 1, 1);
  pass.end();
});

test('computePass.dispatchWorkgroups throws after end()', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  pass.end();
  assert.throws(
    () => pass.dispatchWorkgroups(1, 1, 1),
    /encoder is closed/,
  );
});

test('computePass.setPipeline throws after end()', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  pass.end();
  assert.throws(
    () => pass.setPipeline(makeLiveResource('GPUComputePipeline')),
    /encoder is closed/,
  );
});

test('computePass.setBindGroup throws after end()', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  pass.end();
  assert.throws(
    () => pass.setBindGroup(0, makeLiveResource('GPUBindGroup')),
    /encoder is closed/,
  );
});

// ============================================================
// State machine — render pass open/closed
// ============================================================
console.log('\nState machine — render pass open/closed');

test('renderPass methods work before end()', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginRenderPass({ colorAttachments: [] });
  pass.draw(3);
  pass.end();
});

test('renderPass.draw throws after end()', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginRenderPass({ colorAttachments: [] });
  pass.end();
  assert.throws(
    () => pass.draw(3),
    /encoder is closed/,
  );
});

test('renderPass.setPipeline throws after end()', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginRenderPass({ colorAttachments: [] });
  pass.end();
  assert.throws(
    () => pass.setPipeline(makeLiveResource('GPURenderPipeline')),
    /encoder is closed/,
  );
});

test('renderPass.setVertexBuffer throws after end()', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginRenderPass({ colorAttachments: [] });
  pass.end();
  assert.throws(
    () => pass.setVertexBuffer(0, makeLiveResource('GPUBuffer')),
    /encoder is closed/,
  );
});

// ============================================================
// State machine — command encoder open/finished
// ============================================================
console.log('\nState machine — command encoder open/finished');

test('commandEncoder.finish returns a DoeGPUCommandBuffer', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const cmdBuf = encoder.finish();
  assert.ok(cmdBuf instanceof classes.DoeGPUCommandBuffer);
});

test('commandEncoder methods throw after finish()', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  encoder.finish();
  assert.throws(
    () => encoder.beginComputePass(),
    /encoder is finished/,
  );
});

test('commandEncoder.finish sets label from descriptor', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const cmdBuf = encoder.finish({ label: 'my-commands' });
  assert.strictEqual(cmdBuf.label, 'my-commands');
});

// ============================================================
// State machine — command encoder device liveness
// ============================================================
console.log('\nState machine — command encoder device liveness');

test('commandEncoder methods throw when device is destroyed', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  device._destroyed = true;
  device._native = null;
  assert.throws(
    () => encoder.beginComputePass(),
    /was destroyed/,
  );
});

// ============================================================
// DoeGPURenderBundle — lifecycle
// ============================================================
console.log('\nDoeGPURenderBundle — lifecycle');

test('DoeGPURenderBundle has destroy method', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const bundle = new classes.DoeGPURenderBundle({}, makeLiveDevice());
  assert.strictEqual(typeof bundle.destroy, 'function');
});

test('DoeGPURenderBundle.destroy calls backend', () => {
  const { backend, calls } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const bundle = new classes.DoeGPURenderBundle({}, makeLiveDevice());
  bundle.destroy();
  assert.ok(calls.some(c => c.name === 'renderBundleDestroy'));
});

test('DoeGPURenderBundle.destroy is idempotent', () => {
  const { backend, calls } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const bundle = new classes.DoeGPURenderBundle({}, makeLiveDevice());
  bundle.destroy();
  const countAfterFirst = calls.filter(c => c.name === 'renderBundleDestroy').length;
  bundle.destroy();
  const countAfterSecond = calls.filter(c => c.name === 'renderBundleDestroy').length;
  assert.strictEqual(countAfterFirst, countAfterSecond);
});

// ============================================================
// DoeGPUCommandBuffer — destroy lifecycle
// ============================================================
console.log('\nDoeGPUCommandBuffer — destroy lifecycle');

test('DoeGPUCommandBuffer.destroy calls backend.commandBufferDestroy', () => {
  const { backend, calls } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const cb = new classes.DoeGPUCommandBuffer({ _batched: false, _native: {} }, makeLiveDevice());
  cb.destroy();
  assert.ok(calls.some(c => c.name === 'commandBufferDestroy'));
  assert.strictEqual(cb._destroyed, true);
  assert.strictEqual(cb._native, null);
});

test('DoeGPUCommandBuffer.destroy is idempotent', () => {
  const { backend, calls } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const cb = new classes.DoeGPUCommandBuffer({ _batched: false, _native: {} }, makeLiveDevice());
  cb.destroy();
  const countAfterFirst = calls.filter(c => c.name === 'commandBufferDestroy').length;
  cb.destroy();
  const countAfterSecond = calls.filter(c => c.name === 'commandBufferDestroy').length;
  assert.strictEqual(countAfterFirst, countAfterSecond);
});

test('DoeGPUCommandBuffer.destroy clears commands array', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const cb = new classes.DoeGPUCommandBuffer({ _batched: true, _commands: ['a', 'b'] }, makeLiveDevice());
  assert.strictEqual(cb._commands.length, 2);
  cb.destroy();
  assert.strictEqual(cb._commands.length, 0);
});

// ============================================================
// Label assignment
// ============================================================
console.log('\nLabel assignment');

test('computePass label defaults to empty string', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass();
  assert.strictEqual(pass.label, '');
});

test('computePass label set from descriptor', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginComputePass({ label: 'my-compute' });
  assert.strictEqual(pass.label, 'my-compute');
});

test('renderPass label set from descriptor', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const pass = encoder.beginRenderPass({ colorAttachments: [], label: 'my-render' });
  assert.strictEqual(pass.label, 'my-render');
});

test('commandEncoder label defaults to empty string', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  assert.strictEqual(encoder.label, '');
});

// ============================================================
// writeTimestamp / resolveQuerySet validation
// ============================================================
console.log('\nwriteTimestamp / resolveQuerySet validation');

test('writeTimestamp rejects queryIndex exceeding querySet count', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const querySet = { _native: {}, _destroyed: false, _resourceLabel: 'GPUQuerySet', count: 4 };
  assert.throws(
    () => encoder.writeTimestamp(querySet, 5),
    /exceeds querySet count/,
  );
});

test('writeTimestamp accepts valid queryIndex', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const querySet = { _native: {}, _destroyed: false, _resourceLabel: 'GPUQuerySet', count: 4 };
  encoder.writeTimestamp(querySet, 3);
});

test('resolveQuerySet rejects range exceeding querySet count', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const encoder = new classes.DoeGPUCommandEncoder({}, device);
  const querySet = { _native: {}, _destroyed: false, _resourceLabel: 'GPUQuerySet', count: 4 };
  const destBuffer = makeLiveResource('GPUBuffer');
  assert.throws(
    () => encoder.resolveQuerySet(querySet, 2, 3, destBuffer, 0),
    /exceeds querySet count/,
  );
});

// ============================================================
// renderBundleEncoder finish state
// ============================================================
console.log('\nRenderBundleEncoder — finish state');

test('renderBundleEncoder.finish returns a DoeGPURenderBundle', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const rbe = new classes.DoeGPURenderBundleEncoder({}, device);
  const bundle = rbe.finish();
  assert.ok(bundle instanceof classes.DoeGPURenderBundle);
});

test('renderBundleEncoder.finish sets label from descriptor', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const rbe = new classes.DoeGPURenderBundleEncoder({}, device);
  const bundle = rbe.finish({ label: 'my-bundle' });
  assert.strictEqual(bundle.label, 'my-bundle');
});

test('renderBundleEncoder methods throw after finish()', () => {
  const { backend } = createStubBackend();
  const classes = createEncoderClasses(backend);
  const device = makeLiveDevice();
  const rbe = new classes.DoeGPURenderBundleEncoder({}, device);
  rbe.finish();
  assert.throws(
    () => rbe.draw(3),
    /encoder is finished/,
  );
});

// ============================================================
// Summary
// ============================================================
console.log(`\nResults: ${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exitCode = 1;
}
