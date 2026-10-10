import assert from 'node:assert/strict';
import { requestAdapter, createNativeDirect, globals } from '../../src/native.js';
import { loadNativeAddon } from './native-addon-test-helper.js';

const input = new Uint32Array([17, 29, 43, 71]);
const usage = globals.GPUBufferUsage;
const mode = globals.GPUMapMode;
const adapter = await requestAdapter({ backend: process.platform === 'darwin' ? 'metal' : 'vulkan' });
const device = await adapter.requestDevice();
const addon = await loadNativeAddon();
const buffer = addon.createBuffer(device._native, { size: input.byteLength, usage: usage.MAP_READ | usage.COPY_DST });
try {
  addon.queueWriteBuffer(device.queue._native, buffer, 0, input);
  for (const map of [
    () => addon.bufferMapSync(device._instance, buffer, mode.READ, 0, input.byteLength),
    () => addon.flushAndMapSync(device._instance, device.queue._native, buffer, mode.READ, 0, input.byteLength),
  ]) {
    // An error callback must settle too, leaving a subsequent valid map usable.
    assert.throws(() => addon.bufferMapSync(device._instance, buffer, mode.WRITE, 0, input.byteLength),
      error => error.code === 'DOE_BUFFER_MAP_ERROR');
    map();
    assert.deepEqual(new Uint32Array(addon.bufferReadCopy(buffer, 0, input.byteLength)), input);
    addon.bufferUnmap(buffer);
  }
  // Pumping another instance deliberately leaves the map callback pending.
  // Deliver it after timeout to exercise callback ownership beyond the call stack.
  const unrelatedInstance = addon.createInstance();
  try {
    addon.setTimeoutMs(1);
    assert.throws(() => addon.bufferMapSync(unrelatedInstance, buffer, mode.READ, 0, input.byteLength),
      error => error.code === 'DOE_BUFFER_MAP_TIMEOUT');
    addon.bufferUnmap(buffer);
    addon.setTimeoutMs(5000);
    addon.bufferMapSync(device._instance, buffer, mode.READ, 0, input.byteLength);
    assert.deepEqual(new Uint32Array(addon.bufferReadCopy(buffer, 0, input.byteLength)), input);
    addon.bufferUnmap(buffer);
  } finally {
    addon.setTimeoutMs(5000);
    addon.instanceRelease(unrelatedInstance);
  }
  const result = addon.bufferMapReadCopyUnmap(device._instance, device.queue._native,
    buffer, mode.READ, 0, input.byteLength, true);
  assert.deepEqual(new Uint32Array(result.bytes ?? result), input);
} finally {
  addon.bufferRelease(buffer);
  device.destroy();
  adapter.destroy();
}

{
  const gpu = createNativeDirect();
  const adapter = await gpu.requestAdapter();
  const device = await adapter.requestDevice();
  const buffer = device.createBuffer({ size: input.byteLength, usage: usage.MAP_READ | usage.COPY_DST });
  try {
    device.queue.writeBuffer(buffer, 0, input);
    for (let attempt = 0; attempt < 2; attempt += 1) {
      await buffer.mapAsync(mode.READ);
      assert.deepEqual(new Uint32Array(buffer.getMappedRange()).slice(), input);
      buffer.unmap();
    }
    const result = buffer._mapReadCopyUnmap(mode.READ, 0, input.byteLength);
    assert.deepEqual(new Uint32Array(result), input);
  } finally {
    buffer.destroy();
    device.destroy();
    adapter.destroy();
  }
}
{
  const adapter = await requestAdapter({ backend: process.platform === 'darwin' ? 'metal' : 'vulkan' });
  const device = await adapter.requestDevice();
  const queue = device.queue;
  const encoder = device.createCommandEncoder();
  queue.submit([encoder.finish()]);
  const pending = queue.onSubmittedWorkDone();
  device.destroy();
  try {
    await pending;
    await queue.onSubmittedWorkDone();
    await queue.onSubmittedWorkDone();
    assert.throws(() => queue.submit([]), /destroyed/);
  } finally {
    adapter.destroy();
  }
}
console.log('ok: mapping callbacks, invalid usage recovery, readback bytes, and completion across device destruction');
