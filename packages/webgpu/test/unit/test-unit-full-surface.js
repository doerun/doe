import assert from 'node:assert/strict';
import { createEncoderClasses } from '../../src/shared/encoder-surface.js';
import {
  createFullSurfaceClasses,
  addDeviceEventListener,
  removeDeviceEventListener,
  dispatchDeviceEvent,
  GPUError,
  GPUValidationError,
  GPUOutOfMemoryError,
  GPUInternalError,
  GPUPipelineError,
  GPUDeviceLostInfo,
  GPUUncapturedErrorEvent,
} from '../../src/shared/full-surface.js';
import {
  failValidation,
  initResource,
  assertObject,
  assertArray,
  assertBoolean,
  assertString,
  assertNonEmptyString,
  assertIntegerInRange,
  assertOptionalIntegerInRange,
  validatePositiveInteger,
  assertLiveResource,
  destroyResource,
  describeResourceLabel,
  UINT32_MAX,
  MAX_SAFE_U64,
} from '../../src/shared/resource-lifecycle.js';

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

function makeLiveResource(label = 'GPUBuffer') {
  return { _native: {}, _destroyed: false, _resourceLabel: label };
}

// Minimal globals stub matching what createFullSurfaceClasses expects.
const stubGlobals = {
  GPUShaderStage: { VERTEX: 1, FRAGMENT: 2, COMPUTE: 4 },
};

// Minimal encoder backend stubs used by createEncoderClasses.
function createEncoderBackendStub() {
  return {
    computePassInit() {},
    computePassAssertOpen(self, path) { if (self._closed) throw new Error(`${path}: closed`); },
    computePassEnd(self) { self._closed = true; },
    computePassSetPipeline() {},
    computePassSetBindGroup() {},
    computePassSetImmediates() {},
    computePassDispatchWorkgroups() {},
    computePassDispatchWorkgroupsIndirect() {},
    computePassPushDebugGroup() {},
    computePassPopDebugGroup() {},
    computePassInsertDebugMarker() {},
    renderPassInit() {},
    renderPassAssertOpen(self, path) { if (self._closed) throw new Error(`${path}: closed`); },
    renderPassEnd(self) { self._closed = true; },
    renderPassSetPipeline() {},
    renderPassSetBindGroup() {},
    renderPassSetImmediates() {},
    renderPassSetVertexBuffer() {},
    renderPassSetIndexBuffer() {},
    renderPassDraw() {},
    renderPassDrawIndexed() {},
    renderPassDrawIndirect() {},
    renderPassDrawIndexedIndirect() {},
    renderPassSetViewport() {},
    renderPassSetScissorRect() {},
    renderPassSetBlendConstant() {},
    renderPassSetStencilReference() {},
    renderPassBeginOcclusionQuery() {},
    renderPassEndOcclusionQuery() {},
    renderPassPushDebugGroup() {},
    renderPassPopDebugGroup() {},
    renderPassInsertDebugMarker() {},
    renderPassExecuteBundles() {},
    renderBundleEncoderInit() {},
    renderBundleEncoderFinish(self, desc, classes) { return new classes.DoeGPURenderBundle({}, self); },
    renderBundleDestroy() {},
    commandEncoderInit() {},
    commandEncoderAssertOpen(self, path) { if (self._finished) throw new Error(`${path}: finished`); },
    commandEncoderBeginComputePass(self, desc, classes) { return new classes.DoeGPUComputePassEncoder({}, self); },
    commandEncoderBeginRenderPass(self, desc, classes) { return new classes.DoeGPURenderPassEncoder({}, self); },
    commandEncoderFinish(self) { self._finished = true; return { _native: {}, _batched: false }; },
    commandEncoderCopyBufferToBuffer() {},
    commandEncoderCopyBufferToTexture() {},
    commandEncoderCopyTextureToBuffer() {},
    commandEncoderCopyTextureToTexture() {},
    commandEncoderClearBuffer() {},
    commandEncoderWriteTimestamp() {},
    commandEncoderResolveQuerySet() {},
    commandEncoderPushDebugGroup() {},
    commandEncoderPopDebugGroup() {},
    commandEncoderInsertDebugMarker() {},
    commandBufferDestroy() {},
  };
}

// Full backend stub for createFullSurfaceClasses.
function createFullBackendStub(overrides = {}) {
  const calls = [];
  function record(name, ...args) { calls.push({ name, args }); }
  const base = {
    deviceGetQueue(native) { return {}; },
    deviceLimits(native) { return {}; },
    deviceFeatures(native) { return new Set(); },
    deviceCreateBuffer(self, desc) { record('deviceCreateBuffer'); return {}; },
    deviceCreateShaderModule(self, code, hints, label) { record('deviceCreateShaderModule'); return {}; },
    deviceCreateSampler(self, desc) { record('deviceCreateSampler'); return {}; },
    deviceCreateTexture(self, desc, size, usage) { record('deviceCreateTexture'); return {}; },
    deviceCreateComputePipeline(self, shader, ep, layout, constants, label) { record('deviceCreateComputePipeline'); return {}; },
    deviceCreateRenderPipeline(self, desc) { record('deviceCreateRenderPipeline'); return {}; },
    deviceCreateBindGroupLayout(self, entries, label) { record('deviceCreateBindGroupLayout'); return {}; },
    deviceCreateBindGroup(self, layout, entries, label) { record('deviceCreateBindGroup'); return {}; },
    deviceCreatePipelineLayout(self, layouts, label, immSize) { record('deviceCreatePipelineLayout'); return {}; },
    deviceCreateQuerySet(self, desc) { record('deviceCreateQuerySet'); return {}; },
    deviceCreateCommandEncoder(self, desc, classes) {
      record('deviceCreateCommandEncoder');
      return new classes.DoeGPUCommandEncoder({}, self);
    },
    deviceDestroy(native) { record('deviceDestroy', native); },
    adapterFeatures(native) { return new Set(); },
    adapterLimits(native) { return {}; },
    adapterRequestDevice(self, desc, classes) {
      record('adapterRequestDevice');
      return new classes.DoeGPUDevice({}, self._instance);
    },
    adapterDestroy(native) { record('adapterDestroy', native); },
    gpuRequestAdapter(self, options, classes) {
      record('gpuRequestAdapter');
      return new classes.DoeGPUAdapter({}, self._instance);
    },
    bufferDestroy(native, self) { record('bufferDestroy'); },
    bufferMapAsync(self, native, mode, offset, size) { record('bufferMapAsync'); return Promise.resolve(); },
    bufferGetMappedRange(self, native, offset, size) { record('bufferGetMappedRange'); return new ArrayBuffer(size); },
    bufferUnmap(native, self) { record('bufferUnmap'); },
    textureCreateView(self, native, desc) { record('textureCreateView'); return {}; },
    textureDestroy(native, self) { record('textureDestroy'); },
    querySetDestroy(native) { record('querySetDestroy'); },
    queueSubmit(self, native, buffers) { record('queueSubmit'); },
    queueWriteBuffer(self, native, bufNative, offset, view) { record('queueWriteBuffer'); },
    queueHasPendingSubmissions(self) { return false; },
    queueMarkSubmittedWorkDone(self) { record('queueMarkSubmittedWorkDone'); },
    preflightShaderSource(code) { return { ok: true }; },
    shaderModuleDestroy(native, self) { record('shaderModuleDestroy'); },
    computePipelineGetBindGroupLayout(self, index, classes) { return new classes.DoeGPUBindGroupLayout({}, self._device); },
    renderPipelineGetBindGroupLayout(self, index, classes) { return new classes.DoeGPUBindGroupLayout({}, self._device); },
    requireAutoLayoutEntriesFromNative() { return null; },
  };
  return { backend: { ...base, ...overrides }, calls };
}

function createClasses(backendOverrides = {}) {
  const encoderBackend = createEncoderBackendStub();
  const { backend, calls } = createFullBackendStub(backendOverrides);
  const mergedBackend = { ...encoderBackend, ...backend, ...backendOverrides };
  const encoderClasses = createEncoderClasses(mergedBackend);
  const fullClasses = createFullSurfaceClasses({
    globals: stubGlobals,
    backend: mergedBackend,
    encoderClasses,
  });
  return { classes: fullClasses, encoderClasses, calls, backend: mergedBackend };
}

// ============================================================
// resource-lifecycle — failValidation
// ============================================================
console.log('\nresource-lifecycle — failValidation');

test('failValidation throws Error with path and message', () => {
  assert.throws(
    () => failValidation('GPUDevice.createBuffer', 'size is required'),
    /GPUDevice\.createBuffer: size is required/,
  );
});

test('failValidation throws an instance of Error', () => {
  try {
    failValidation('test', 'msg');
    assert.fail('should have thrown');
  } catch (e) {
    assert.ok(e instanceof Error);
  }
});

// ============================================================
// resource-lifecycle — initResource
// ============================================================
console.log('\nresource-lifecycle — initResource');

test('initResource sets _resourceLabel, _resourceOwner, _destroyed', () => {
  const obj = {};
  const owner = { label: 'owner' };
  initResource(obj, 'GPUBuffer', owner);
  assert.strictEqual(obj._resourceLabel, 'GPUBuffer');
  assert.strictEqual(obj._resourceOwner, owner);
  assert.strictEqual(obj._destroyed, false);
});

test('initResource defaults owner to null', () => {
  const obj = {};
  initResource(obj, 'GPUDevice');
  assert.strictEqual(obj._resourceOwner, null);
  assert.strictEqual(obj._destroyed, false);
});

// ============================================================
// resource-lifecycle — describeResourceLabel
// ============================================================
console.log('\nresource-lifecycle — describeResourceLabel');

test('describeResourceLabel returns _resourceLabel if present', () => {
  const obj = { _resourceLabel: 'GPUTexture' };
  assert.strictEqual(describeResourceLabel(obj), 'GPUTexture');
});

test('describeResourceLabel returns fallback for null/undefined', () => {
  assert.strictEqual(describeResourceLabel(null, 'fallback'), 'fallback');
  assert.strictEqual(describeResourceLabel(undefined), 'resource');
});

// ============================================================
// resource-lifecycle — assertObject
// ============================================================
console.log('\nresource-lifecycle — assertObject');

test('assertObject passes for plain object', () => {
  const result = assertObject({ a: 1 }, 'path', 'label');
  assert.deepStrictEqual(result, { a: 1 });
});

test('assertObject rejects null', () => {
  assert.throws(() => assertObject(null, 'p', 'l'), /must be an object/);
});

test('assertObject rejects array', () => {
  assert.throws(() => assertObject([1], 'p', 'l'), /must be an object/);
});

test('assertObject rejects string', () => {
  assert.throws(() => assertObject('str', 'p', 'l'), /must be an object/);
});

test('assertObject rejects number', () => {
  assert.throws(() => assertObject(42, 'p', 'l'), /must be an object/);
});

// ============================================================
// resource-lifecycle — assertArray
// ============================================================
console.log('\nresource-lifecycle — assertArray');

test('assertArray passes for array', () => {
  const result = assertArray([1, 2], 'path', 'label');
  assert.deepStrictEqual(result, [1, 2]);
});

test('assertArray rejects object', () => {
  assert.throws(() => assertArray({}, 'p', 'l'), /must be an array/);
});

test('assertArray rejects null', () => {
  assert.throws(() => assertArray(null, 'p', 'l'), /must be an array/);
});

// ============================================================
// resource-lifecycle — assertBoolean
// ============================================================
console.log('\nresource-lifecycle — assertBoolean');

test('assertBoolean passes for true', () => {
  assert.strictEqual(assertBoolean(true, 'p', 'l'), true);
});

test('assertBoolean passes for false', () => {
  assert.strictEqual(assertBoolean(false, 'p', 'l'), false);
});

test('assertBoolean rejects number', () => {
  assert.throws(() => assertBoolean(1, 'p', 'l'), /must be a boolean/);
});

test('assertBoolean rejects string', () => {
  assert.throws(() => assertBoolean('true', 'p', 'l'), /must be a boolean/);
});

// ============================================================
// resource-lifecycle — assertString / assertNonEmptyString
// ============================================================
console.log('\nresource-lifecycle — assertString / assertNonEmptyString');

test('assertString passes for string', () => {
  assert.strictEqual(assertString('hello', 'p', 'l'), 'hello');
});

test('assertString rejects number', () => {
  assert.throws(() => assertString(42, 'p', 'l'), /must be a string/);
});

test('assertNonEmptyString passes for non-empty string', () => {
  assert.strictEqual(assertNonEmptyString('ok', 'p', 'l'), 'ok');
});

test('assertNonEmptyString rejects empty string', () => {
  assert.throws(() => assertNonEmptyString('', 'p', 'l'), /must not be empty/);
});

// ============================================================
// resource-lifecycle — assertIntegerInRange
// ============================================================
console.log('\nresource-lifecycle — assertIntegerInRange');

test('assertIntegerInRange passes for integer in range', () => {
  assert.strictEqual(assertIntegerInRange(5, 'p', 'l', { min: 0, max: 10 }), 5);
});

test('assertIntegerInRange rejects float', () => {
  assert.throws(() => assertIntegerInRange(1.5, 'p', 'l', { min: 0 }), /must be an integer/);
});

test('assertIntegerInRange rejects below min', () => {
  assert.throws(() => assertIntegerInRange(-1, 'p', 'l', { min: 0 }), /must be an integer/);
});

test('assertIntegerInRange rejects above max', () => {
  assert.throws(() => assertIntegerInRange(100, 'p', 'l', { min: 0, max: 10 }), /must be an integer/);
});

test('assertIntegerInRange accepts boundary values', () => {
  assert.strictEqual(assertIntegerInRange(0, 'p', 'l', { min: 0, max: 10 }), 0);
  assert.strictEqual(assertIntegerInRange(10, 'p', 'l', { min: 0, max: 10 }), 10);
});

test('assertIntegerInRange uses default max of MAX_SAFE_U64', () => {
  assert.strictEqual(assertIntegerInRange(Number.MAX_SAFE_INTEGER, 'p', 'l', { min: 0 }), Number.MAX_SAFE_INTEGER);
});

// ============================================================
// resource-lifecycle — assertOptionalIntegerInRange
// ============================================================
console.log('\nresource-lifecycle — assertOptionalIntegerInRange');

test('assertOptionalIntegerInRange returns undefined for undefined', () => {
  assert.strictEqual(assertOptionalIntegerInRange(undefined, 'p', 'l', { min: 0 }), undefined);
});

test('assertOptionalIntegerInRange validates provided value', () => {
  assert.strictEqual(assertOptionalIntegerInRange(5, 'p', 'l', { min: 0, max: 10 }), 5);
});

test('assertOptionalIntegerInRange rejects invalid value', () => {
  assert.throws(() => assertOptionalIntegerInRange(-1, 'p', 'l', { min: 0 }), /must be an integer/);
});

// ============================================================
// resource-lifecycle — validatePositiveInteger
// ============================================================
console.log('\nresource-lifecycle — validatePositiveInteger');

test('validatePositiveInteger passes for 1', () => {
  validatePositiveInteger(1, 'count');
});

test('validatePositiveInteger rejects 0', () => {
  assert.throws(() => validatePositiveInteger(0, 'count'), /must be a positive integer/);
});

test('validatePositiveInteger rejects negative', () => {
  assert.throws(() => validatePositiveInteger(-3, 'count'), /must be a positive integer/);
});

test('validatePositiveInteger rejects float', () => {
  assert.throws(() => validatePositiveInteger(1.5, 'count'), /must be a positive integer/);
});

// ============================================================
// resource-lifecycle — assertLiveResource
// ============================================================
console.log('\nresource-lifecycle — assertLiveResource');

test('assertLiveResource returns native for live resource', () => {
  const nativeObj = {};
  const resource = { _native: nativeObj, _destroyed: false, _resourceLabel: 'GPUBuffer', _resourceOwner: null };
  assert.strictEqual(assertLiveResource(resource, 'path', 'GPUBuffer'), nativeObj);
});

test('assertLiveResource throws for destroyed resource', () => {
  const resource = { _native: null, _destroyed: true, _resourceLabel: 'GPUBuffer' };
  assert.throws(() => assertLiveResource(resource, 'path', 'GPUBuffer'), /was destroyed/);
});

test('assertLiveResource throws for non-Doe object', () => {
  assert.throws(() => assertLiveResource('not-an-object', 'path', 'GPUBuffer'), /must be a Doe WebGPU object/);
});

test('assertLiveResource throws for null', () => {
  assert.throws(() => assertLiveResource(null, 'path', 'GPUBuffer'), /must be a Doe WebGPU object/);
});

test('assertLiveResource throws when owner is destroyed', () => {
  const owner = { _native: null, _destroyed: true, _resourceLabel: 'GPUDevice' };
  const resource = { _native: {}, _destroyed: false, _resourceLabel: 'GPUBuffer', _resourceOwner: owner };
  assert.throws(() => assertLiveResource(resource, 'path', 'GPUBuffer'), /cannot be used after/);
});

test('assertLiveResource error message includes resource label', () => {
  const resource = { _native: null, _destroyed: true, _resourceLabel: 'GPUTexture' };
  try {
    assertLiveResource(resource, 'GPUDevice.createView', 'GPUTexture');
    assert.fail('should have thrown');
  } catch (e) {
    assert.ok(e.message.includes('GPUTexture'));
    assert.ok(e.message.includes('was destroyed'));
  }
});

// ============================================================
// resource-lifecycle — destroyResource
// ============================================================
console.log('\nresource-lifecycle — destroyResource');

test('destroyResource calls release and marks destroyed', () => {
  let released = null;
  const native = {};
  const resource = { _native: native, _destroyed: false };
  destroyResource(resource, (n) => { released = n; });
  assert.strictEqual(released, native);
  assert.strictEqual(resource._destroyed, true);
  assert.strictEqual(resource._native, null);
});

test('destroyResource is idempotent', () => {
  let callCount = 0;
  const resource = { _native: {}, _destroyed: false };
  destroyResource(resource, () => { callCount += 1; });
  destroyResource(resource, () => { callCount += 1; });
  assert.strictEqual(callCount, 1);
});

test('destroyResource does nothing when native is null', () => {
  let callCount = 0;
  const resource = { _native: null, _destroyed: false };
  destroyResource(resource, () => { callCount += 1; });
  assert.strictEqual(callCount, 0);
});

// ============================================================
// UINT32_MAX and MAX_SAFE_U64 constants
// ============================================================
console.log('\nresource-lifecycle — constants');

test('UINT32_MAX is 0xFFFFFFFF', () => {
  assert.strictEqual(UINT32_MAX, 0xFFFF_FFFF);
});

test('MAX_SAFE_U64 is Number.MAX_SAFE_INTEGER', () => {
  assert.strictEqual(MAX_SAFE_U64, Number.MAX_SAFE_INTEGER);
});

// ============================================================
// createFullSurfaceClasses — class factory
// ============================================================
console.log('\ncreateFullSurfaceClasses — class factory');

test('returns an object with all expected class constructors', () => {
  const { classes } = createClasses();
  const expectedNames = [
    'DoeGPUBuffer',
    'DoeGPUQueue',
    'DoeGPUTexture',
    'DoeGPUTextureView',
    'DoeGPUSampler',
    'DoeGPURenderPipeline',
    'DoeGPUShaderModule',
    'DoeGPUComputePipeline',
    'DoeGPUBindGroupLayout',
    'DoeGPUBindGroup',
    'DoeGPUPipelineLayout',
    'DoeGPUQuerySet',
    'DoeGPUDevice',
    'DoeGPUAdapter',
    'DoeGPU',
  ];
  for (const name of expectedNames) {
    assert.ok(typeof classes[name] === 'function', `missing ${name}`);
  }
});

test('class count matches expected', () => {
  const { classes } = createClasses();
  assert.strictEqual(Object.keys(classes).length, 15);
});

// ============================================================
// DoeGPU — method existence
// ============================================================
console.log('\nDoeGPU — method existence');

test('DoeGPU has requestAdapter and getPreferredCanvasFormat', () => {
  const { classes } = createClasses();
  const gpu = new classes.DoeGPU({});
  assert.strictEqual(typeof gpu.requestAdapter, 'function');
  assert.strictEqual(typeof gpu.getPreferredCanvasFormat, 'function');
});

test('DoeGPU.getPreferredCanvasFormat returns bgra8unorm', () => {
  const { classes } = createClasses();
  const gpu = new classes.DoeGPU({});
  assert.strictEqual(gpu.getPreferredCanvasFormat(), 'bgra8unorm');
});

test('DoeGPU.wgslLanguageFeatures is a frozen Set', () => {
  const { classes } = createClasses();
  const gpu = new classes.DoeGPU({});
  const features = gpu.wgslLanguageFeatures;
  assert.ok(features instanceof Set);
  assert.ok(features.has('readonly-and-readwrite-storage-textures'));
  assert.ok(Object.isFrozen(features));
});

// ============================================================
// DoeGPUAdapter — method existence
// ============================================================
console.log('\nDoeGPUAdapter — method existence');

test('DoeGPUAdapter has requestDevice and destroy', () => {
  const { classes, backend } = createClasses();
  const adapter = new classes.DoeGPUAdapter({}, {});
  assert.strictEqual(typeof adapter.requestDevice, 'function');
  assert.strictEqual(typeof adapter.destroy, 'function');
});

test('DoeGPUAdapter has info getter with default shape', () => {
  const { classes } = createClasses();
  const adapter = new classes.DoeGPUAdapter({}, {});
  const info = adapter.info;
  assert.ok(info != null && typeof info === 'object');
  assert.strictEqual(typeof info.vendor, 'string');
  assert.strictEqual(typeof info.architecture, 'string');
  assert.strictEqual(typeof info.device, 'string');
  assert.strictEqual(typeof info.description, 'string');
});

test('DoeGPUAdapter.info is cached on second access', () => {
  const { classes } = createClasses();
  const adapter = new classes.DoeGPUAdapter({}, {});
  const info1 = adapter.info;
  const info2 = adapter.info;
  assert.strictEqual(info1, info2);
});

test('DoeGPUAdapter has features and limits', () => {
  const { classes } = createClasses();
  const adapter = new classes.DoeGPUAdapter({}, {});
  assert.ok(adapter.features instanceof Set);
  assert.ok(adapter.limits != null);
});

// ============================================================
// DoeGPUDevice — method existence
// ============================================================
console.log('\nDoeGPUDevice — method existence');

test('DoeGPUDevice has all expected creation methods', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const expectedMethods = [
    'createBuffer',
    'createShaderModule',
    'createComputePipeline',
    'createComputePipelineAsync',
    'createRenderPipeline',
    'createRenderPipelineAsync',
    'createBindGroupLayout',
    'createBindGroup',
    'createPipelineLayout',
    'createTexture',
    'createSampler',
    'createQuerySet',
    'createCommandEncoder',
    'createRenderBundleEncoder',
    'importExternalTexture',
    'pushErrorScope',
    'popErrorScope',
    'addEventListener',
    'removeEventListener',
    'destroy',
  ];
  for (const method of expectedMethods) {
    assert.strictEqual(typeof device[method], 'function', `missing method ${method}`);
  }
});

test('DoeGPUDevice has queue property', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  assert.ok(device.queue != null);
  assert.ok(device.queue instanceof classes.DoeGPUQueue);
});

test('DoeGPUDevice has limits and features', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  assert.ok(device.limits != null);
  assert.ok(device.features instanceof Set);
});

test('DoeGPUDevice has lost getter', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const lost = device.lost;
  assert.ok(lost instanceof Promise);
});

test('DoeGPUDevice has adapterInfo getter', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const info = device.adapterInfo;
  assert.ok(info != null && typeof info === 'object');
});

// ============================================================
// DoeGPUDevice — error scope validation
// ============================================================
console.log('\nDoeGPUDevice — error scope validation');

test('pushErrorScope rejects invalid filter', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  assert.throws(
    () => device.pushErrorScope('bogus'),
    /invalid filter/,
  );
});

test('pushErrorScope accepts validation filter', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  device.pushErrorScope('validation');
});

test('pushErrorScope accepts out-of-memory filter', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  device.pushErrorScope('out-of-memory');
});

test('pushErrorScope accepts internal filter', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  device.pushErrorScope('internal');
});

// ============================================================
// DoeGPUDevice — onuncapturederror
// ============================================================
console.log('\nDoeGPUDevice — onuncapturederror');

test('onuncapturederror defaults to null', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  assert.strictEqual(device.onuncapturederror, null);
});

test('onuncapturederror accepts a function', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const handler = () => {};
  device.onuncapturederror = handler;
  assert.strictEqual(device.onuncapturederror, handler);
});

test('onuncapturederror rejects non-function non-null', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  assert.throws(
    () => { device.onuncapturederror = 'not-a-function'; },
    /must be a function or null/,
  );
});

test('onuncapturederror can be reset to null', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  device.onuncapturederror = () => {};
  device.onuncapturederror = null;
  assert.strictEqual(device.onuncapturederror, null);
});

// ============================================================
// DoeGPUQueue — method existence
// ============================================================
console.log('\nDoeGPUQueue — method existence');

test('DoeGPUQueue has expected methods', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const queue = device.queue;
  const expectedMethods = [
    'submit',
    'writeBuffer',
    'writeTexture',
    'onSubmittedWorkDone',
    'copyExternalImageToTexture',
    'hasPendingSubmissions',
    'markSubmittedWorkDone',
  ];
  for (const method of expectedMethods) {
    assert.strictEqual(typeof queue[method], 'function', `missing method ${method}`);
  }
});

// ============================================================
// DoeGPUBuffer — method existence
// ============================================================
console.log('\nDoeGPUBuffer — method existence');

test('DoeGPUBuffer has expected methods', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const buffer = new classes.DoeGPUBuffer({}, {}, 256, 0x0040, device.queue, device);
  const expectedMethods = [
    'mapAsync',
    'getMappedRange',
    'unmap',
    'destroy',
    'assertMappedPrefixF32',
  ];
  for (const method of expectedMethods) {
    assert.strictEqual(typeof buffer[method], 'function', `missing method ${method}`);
  }
});

test('DoeGPUBuffer has size and usage properties', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const buffer = new classes.DoeGPUBuffer({}, {}, 256, 0x0048, device.queue, device);
  assert.strictEqual(buffer.size, 256);
  assert.strictEqual(buffer.usage, 0x0048);
});

test('DoeGPUBuffer.mapState defaults to unmapped', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const buffer = new classes.DoeGPUBuffer({}, {}, 256, 0x0040, device.queue, device);
  assert.strictEqual(buffer.mapState, 'unmapped');
});

// ============================================================
// DoeGPUBuffer — destroy lifecycle
// ============================================================
console.log('\nDoeGPUBuffer — destroy lifecycle');

test('DoeGPUBuffer.destroy marks resource as destroyed', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const buffer = new classes.DoeGPUBuffer({}, {}, 256, 0x0040, device.queue, device);
  assert.strictEqual(buffer._destroyed, false);
  buffer.destroy();
  assert.strictEqual(buffer._destroyed, true);
  assert.strictEqual(buffer._native, null);
});

test('DoeGPUBuffer.destroy is idempotent', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const buffer = new classes.DoeGPUBuffer({}, {}, 256, 0x0040, device.queue, device);
  buffer.destroy();
  buffer.destroy();
  assert.strictEqual(buffer._destroyed, true);
});

test('destroyed buffer rejects mapAsync', async () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const buffer = new classes.DoeGPUBuffer({}, {}, 256, 0x0001, device.queue, device);
  buffer.destroy();
  await assert.rejects(
    () => buffer.mapAsync(1, 0, 256),
    /was destroyed/,
  );
});

test('destroyed buffer rejects getMappedRange', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const buffer = new classes.DoeGPUBuffer({}, {}, 256, 0x0001, device.queue, device);
  buffer.destroy();
  assert.throws(
    () => buffer.getMappedRange(0, 4),
    /was destroyed/,
  );
});

test('destroyed buffer rejects unmap', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const buffer = new classes.DoeGPUBuffer({}, {}, 256, 0x0001, device.queue, device);
  buffer.destroy();
  assert.throws(
    () => buffer.unmap(),
    /was destroyed/,
  );
});

// ============================================================
// DoeGPUTexture — lifecycle
// ============================================================
console.log('\nDoeGPUTexture — lifecycle');

test('DoeGPUTexture has createView and destroy', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const texture = new classes.DoeGPUTexture({}, device, { width: 64, height: 64 });
  assert.strictEqual(typeof texture.createView, 'function');
  assert.strictEqual(typeof texture.destroy, 'function');
});

test('DoeGPUTexture stores metadata', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const texture = new classes.DoeGPUTexture({}, device, {
    width: 128, height: 256, depthOrArrayLayers: 3,
    mipLevelCount: 4, sampleCount: 1, dimension: '2d',
    format: 'rgba8unorm', usage: 0x10,
  });
  assert.strictEqual(texture.width, 128);
  assert.strictEqual(texture.height, 256);
  assert.strictEqual(texture.depthOrArrayLayers, 3);
  assert.strictEqual(texture.mipLevelCount, 4);
  assert.strictEqual(texture.sampleCount, 1);
  assert.strictEqual(texture.dimension, '2d');
  assert.strictEqual(texture.format, 'rgba8unorm');
  assert.strictEqual(texture.usage, 0x10);
});

test('DoeGPUTexture.destroy marks resource as destroyed', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const texture = new classes.DoeGPUTexture({}, device, { width: 64, height: 64 });
  texture.destroy();
  assert.strictEqual(texture._destroyed, true);
  assert.strictEqual(texture._native, null);
});

test('destroyed texture rejects createView', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const texture = new classes.DoeGPUTexture({}, device, { width: 64, height: 64 });
  texture.destroy();
  assert.throws(
    () => texture.createView(),
    /was destroyed/,
  );
});

// ============================================================
// DoeGPUQuerySet — lifecycle
// ============================================================
console.log('\nDoeGPUQuerySet — lifecycle');

test('DoeGPUQuerySet stores type and count', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const qs = new classes.DoeGPUQuerySet({}, 'occlusion', 32, device);
  assert.strictEqual(qs.type, 'occlusion');
  assert.strictEqual(qs.count, 32);
});

test('DoeGPUQuerySet.destroy marks resource as destroyed', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const qs = new classes.DoeGPUQuerySet({}, 'timestamp', 8, device);
  qs.destroy();
  assert.strictEqual(qs._destroyed, true);
});

// ============================================================
// DoeGPUShaderModule — lifecycle
// ============================================================
console.log('\nDoeGPUShaderModule — lifecycle');

test('DoeGPUShaderModule stores code', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const sm = new classes.DoeGPUShaderModule({}, '@compute fn main() {}', device);
  assert.strictEqual(sm._code, '@compute fn main() {}');
});

test('DoeGPUShaderModule has getCompilationInfo', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const sm = new classes.DoeGPUShaderModule({}, '@compute fn main() {}', device);
  assert.strictEqual(typeof sm.getCompilationInfo, 'function');
});

test('DoeGPUShaderModule.destroy marks resource as destroyed', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const sm = new classes.DoeGPUShaderModule({}, '@compute fn main() {}', device);
  sm.destroy();
  assert.strictEqual(sm._destroyed, true);
});

// ============================================================
// DoeGPUDevice — destroy lifecycle
// ============================================================
console.log('\nDoeGPUDevice — destroy lifecycle');

test('DoeGPUDevice.destroy marks device as destroyed', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  assert.strictEqual(device._destroyed, false);
  device.destroy();
  assert.strictEqual(device._destroyed, true);
});

test('destroyed device rejects createCommandEncoder', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  device.destroy();
  assert.throws(
    () => device.createCommandEncoder(),
    /was destroyed/,
  );
});

test('destroyed device rejects pushErrorScope', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  device.destroy();
  assert.throws(
    () => device.pushErrorScope('validation'),
    /was destroyed/,
  );
});

// ============================================================
// DoeGPUAdapter — destroy lifecycle
// ============================================================
console.log('\nDoeGPUAdapter — destroy lifecycle');

test('DoeGPUAdapter.destroy marks adapter as destroyed', () => {
  const { classes } = createClasses();
  const adapter = new classes.DoeGPUAdapter({}, {});
  assert.strictEqual(adapter._destroyed, false);
  adapter.destroy();
  assert.strictEqual(adapter._destroyed, true);
});

// ============================================================
// GPUError hierarchy
// ============================================================
console.log('\nGPUError hierarchy');

test('GPUValidationError extends GPUError extends Error', () => {
  const err = new GPUValidationError('bad input');
  assert.ok(err instanceof GPUValidationError);
  assert.ok(err instanceof GPUError);
  assert.ok(err instanceof Error);
  assert.strictEqual(err.name, 'GPUValidationError');
  assert.strictEqual(err.message, 'bad input');
});

test('GPUOutOfMemoryError extends GPUError', () => {
  const err = new GPUOutOfMemoryError('oom');
  assert.ok(err instanceof GPUError);
  assert.strictEqual(err.name, 'GPUOutOfMemoryError');
});

test('GPUOutOfMemoryError defaults to empty message', () => {
  const err = new GPUOutOfMemoryError();
  assert.strictEqual(err.message, '');
});

test('GPUInternalError extends GPUError', () => {
  const err = new GPUInternalError('internal failure');
  assert.ok(err instanceof GPUError);
  assert.strictEqual(err.name, 'GPUInternalError');
});

test('GPUPipelineError has reason property', () => {
  const err = new GPUPipelineError('shader failed', { reason: 'validation' });
  assert.strictEqual(err.reason, 'validation');
});

test('GPUPipelineError defaults reason to internal', () => {
  const err = new GPUPipelineError('shader failed');
  assert.strictEqual(err.reason, 'internal');
});

// ============================================================
// GPUDeviceLostInfo
// ============================================================
console.log('\nGPUDeviceLostInfo');

test('GPUDeviceLostInfo stores reason and message', () => {
  const info = new GPUDeviceLostInfo('destroyed', 'user called destroy');
  assert.strictEqual(info.reason, 'destroyed');
  assert.strictEqual(info.message, 'user called destroy');
});

test('GPUDeviceLostInfo defaults reason to unknown', () => {
  const info = new GPUDeviceLostInfo();
  assert.strictEqual(info.reason, 'unknown');
  assert.strictEqual(info.message, '');
});

// ============================================================
// GPUUncapturedErrorEvent
// ============================================================
console.log('\nGPUUncapturedErrorEvent');

test('GPUUncapturedErrorEvent extends Event and has error', () => {
  const gpuErr = new GPUValidationError('bad');
  const evt = new GPUUncapturedErrorEvent('uncapturederror', { error: gpuErr });
  assert.ok(evt instanceof Event);
  assert.strictEqual(evt.error, gpuErr);
  assert.strictEqual(evt.type, 'uncapturederror');
});

test('GPUUncapturedErrorEvent defaults error to null', () => {
  const evt = new GPUUncapturedErrorEvent('uncapturederror');
  assert.strictEqual(evt.error, null);
});

// ============================================================
// Device event listeners
// ============================================================
console.log('\nDevice event listeners');

test('addDeviceEventListener and dispatchDeviceEvent work', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  let received = null;
  addDeviceEventListener(device, 'uncapturederror', (event) => { received = event; });
  const evt = { type: 'uncapturederror', error: new GPUValidationError('test') };
  dispatchDeviceEvent(device, 'uncapturederror', evt);
  assert.strictEqual(received, evt);
});

test('removeDeviceEventListener stops delivery', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  let callCount = 0;
  const handler = () => { callCount += 1; };
  addDeviceEventListener(device, 'uncapturederror', handler);
  dispatchDeviceEvent(device, 'uncapturederror', {});
  assert.strictEqual(callCount, 1);
  removeDeviceEventListener(device, 'uncapturederror', handler);
  dispatchDeviceEvent(device, 'uncapturederror', {});
  assert.strictEqual(callCount, 1);
});

test('addDeviceEventListener ignores non-function listener', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  addDeviceEventListener(device, 'uncapturederror', 'not-a-function');
  dispatchDeviceEvent(device, 'uncapturederror', {});
});

test('dispatchDeviceEvent is safe on device with no listeners', () => {
  const obj = { _eventListeners: null };
  dispatchDeviceEvent(obj, 'uncapturederror', {});
});

test('removeDeviceEventListener is safe on device with no listeners', () => {
  const obj = {};
  removeDeviceEventListener(obj, 'uncapturederror', () => {});
});

// ============================================================
// DoeGPUQueue — input validation
// ============================================================
console.log('\nDoeGPUQueue — input validation');

test('queue.submit rejects non-array commandBuffers', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  assert.throws(
    () => device.queue.submit('not-an-array'),
    /must be an array/,
  );
});

test('queue.submit accepts empty array without error', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  device.queue.submit([]);
});

test('queue.writeBuffer rejects destroyed queue (via device destroy)', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const queue = device.queue;
  const buffer = new classes.DoeGPUBuffer({}, {}, 256, 0x0048, queue, device);
  device.destroy();
  assert.throws(
    () => queue.writeBuffer(buffer, 0, new Uint8Array(4)),
    /was destroyed|cannot be used after/,
  );
});

// ============================================================
// DoeGPUBuffer — mapAsync range validation
// ============================================================
console.log('\nDoeGPUBuffer — mapAsync range validation');

test('mapAsync rejects range exceeding buffer size', async () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const buffer = new classes.DoeGPUBuffer({}, {}, 64, 0x0001, device.queue, device);
  await assert.rejects(
    () => buffer.mapAsync(1, 0, 128),
    /exceeds buffer size/,
  );
});

test('getMappedRange rejects range exceeding buffer size', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  const buffer = new classes.DoeGPUBuffer({}, {}, 64, 0x0001, device.queue, device);
  assert.throws(
    () => buffer.getMappedRange(0, 128),
    /exceeds buffer size/,
  );
});

// ============================================================
// Label defaults
// ============================================================
console.log('\nLabel defaults');

test('all surface classes default label to empty string', () => {
  const { classes } = createClasses();
  const device = new classes.DoeGPUDevice({}, {});
  assert.strictEqual(device.label, '');
  assert.strictEqual(device.queue.label, '');

  const buffer = new classes.DoeGPUBuffer({}, {}, 64, 0, device.queue, device);
  assert.strictEqual(buffer.label, '');

  const texture = new classes.DoeGPUTexture({}, device, {});
  assert.strictEqual(texture.label, '');

  const tv = new classes.DoeGPUTextureView({}, device);
  assert.strictEqual(tv.label, '');

  const sampler = new classes.DoeGPUSampler({}, device);
  assert.strictEqual(sampler.label, '');

  const bgl = new classes.DoeGPUBindGroupLayout({}, device);
  assert.strictEqual(bgl.label, '');

  const bg = new classes.DoeGPUBindGroup({}, device);
  assert.strictEqual(bg.label, '');

  const pl = new classes.DoeGPUPipelineLayout({}, device);
  assert.strictEqual(pl.label, '');

  const qs = new classes.DoeGPUQuerySet({}, 'timestamp', 4, device);
  assert.strictEqual(qs.label, '');

  const sm = new classes.DoeGPUShaderModule({}, 'code', device);
  assert.strictEqual(sm.label, '');

  const adapter = new classes.DoeGPUAdapter({}, {});
  assert.strictEqual(adapter.label, '');
});

// ============================================================
// Summary
// ============================================================
console.log(`\nResults: ${passed} passed, ${failed} failed`);
if (failed > 0) {
  process.exitCode = 1;
}
