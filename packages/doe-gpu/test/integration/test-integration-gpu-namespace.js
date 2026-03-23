#!/usr/bin/env node
// Integration test for doe-gpu namespace.
// Verifies that the gpu namespace works end-to-end with a real device.
// Requires a GPU (or working native addon); tests that cannot acquire a device
// are skipped with an actionable message.
//
// Usage:
//   node test/integration/test-integration-gpu-namespace.js
//
// Exit codes:
//   0  All checks passed (or skipped due to no GPU)
//   1  A check failed (actionable error printed)

let passed = 0;
let failed = 0;
let skipped = 0;

function check(label, condition, detail) {
  if (condition) {
    passed++;
    console.log(`  ok: ${label}`);
  } else {
    failed++;
    console.error(`  FAIL: ${label}${detail ? ' -- ' + detail : ''}`);
  }
}

function skip(label) {
  skipped++;
  console.log(`  SKIP: ${label}`);
}

function isDeviceUnavailableError(err) {
  const msg = err?.message ?? '';
  return (
    msg.includes('not found') ||
    msg.includes('unavailable') ||
    msg.includes('No adapter') ||
    msg.includes('no adapter') ||
    msg.includes('not supported') ||
    msg.includes('ENOENT') ||
    msg.includes('Could not load')
  );
}

console.log('=== doe-gpu integration: gpu namespace ===\n');

// ── Import ──────────────────────────────────────────────────────────────

let mod;
try {
  mod = await import('../../src/index.js');
  check('import doe-gpu succeeds', true);
} catch (err) {
  check('import doe-gpu succeeds', false, err.message);
  process.exit(1);
}

const { gpu, createGpuNamespace, requestDevice } = mod;

// ── 1. gpu.requestDevice() — bound namespace shape ──────────────────────

console.log('\n1. gpu.requestDevice() — bound namespace shape');

try {
  const bound = await gpu.requestDevice();
  check('gpu.requestDevice() resolves', true);
  check('bound.device exists', bound.device != null && typeof bound.device === 'object');
  check('bound.buffer is object', bound.buffer != null && typeof bound.buffer === 'object');
  check('bound.buffer.create is function', typeof bound.buffer.create === 'function');
  check('bound.buffer.read is function', typeof bound.buffer.read === 'function');
  check('bound.kernel is object', bound.kernel != null && typeof bound.kernel === 'object');
  check('bound.kernel.create is function', typeof bound.kernel.create === 'function');
  check('bound.kernel.run is function', typeof bound.kernel.run === 'function');
  check('bound.compute is function', typeof bound.compute === 'function');
  check('bound.compute.begin is function', typeof bound.compute.begin === 'function');
  check('bound.commandEncoder is object', bound.commandEncoder != null && typeof bound.commandEncoder === 'object');
  check('bound.commandEncoder.create is function', typeof bound.commandEncoder.create === 'function');
  bound.device.destroy();
} catch (err) {
  if (isDeviceUnavailableError(err)) {
    skip('gpu.requestDevice() (no GPU available)');
  } else {
    check('gpu.requestDevice() resolves', false, err.message);
  }
}

// ── 2. gpu.bind(device) — manual bind ───────────────────────────────────

console.log('\n2. gpu.bind(device) — manual bind');

try {
  const rawDevice = await requestDevice();
  check('raw requestDevice() resolves', true);
  check('raw device is object', rawDevice != null && typeof rawDevice === 'object');

  const bound = gpu.bind(rawDevice);
  check('gpu.bind(device) returns object', bound != null && typeof bound === 'object');
  check('bound.device is same raw device', bound.device === rawDevice);
  check('bound.buffer.create is function', typeof bound.buffer.create === 'function');
  check('bound.buffer.read is function', typeof bound.buffer.read === 'function');
  check('bound.kernel is object', bound.kernel != null && typeof bound.kernel === 'object');
  check('bound.compute is function', typeof bound.compute === 'function');
  check('bound.commandEncoder is object', bound.commandEncoder != null && typeof bound.commandEncoder === 'object');
  rawDevice.destroy();
} catch (err) {
  if (isDeviceUnavailableError(err)) {
    skip('gpu.bind(device) (no GPU available)');
  } else {
    check('gpu.bind(device)', false, err.message);
  }
}

// ── 3. buffer.create() — various usage tokens ───────────────────────────

console.log('\n3. buffer.create() — various usage tokens');

try {
  const bound = await gpu.requestDevice();

  const uploadBuf = bound.buffer.create({ size: 64, usage: 'upload' });
  check('buffer.create upload succeeds', uploadBuf != null);
  check('upload buffer has size', uploadBuf.size === 64);

  const readbackBuf = bound.buffer.create({ size: 128, usage: 'readback' });
  check('buffer.create readback succeeds', readbackBuf != null);
  check('readback buffer has size', readbackBuf.size === 128);

  const storageBuf = bound.buffer.create({ size: 256, usage: 'storageReadWrite' });
  check('buffer.create storageReadWrite succeeds', storageBuf != null);
  check('storageReadWrite buffer has size', storageBuf.size === 256);

  // buffer.create with data
  const dataBuf = bound.buffer.create({ data: new Float32Array([1, 2, 3, 4]) });
  check('buffer.create with data succeeds', dataBuf != null);
  check('data buffer has correct size', dataBuf.size === 16);

  uploadBuf.destroy();
  readbackBuf.destroy();
  storageBuf.destroy();
  dataBuf.destroy();
  bound.device.destroy();
} catch (err) {
  if (isDeviceUnavailableError(err)) {
    skip('buffer.create (no GPU available)');
  } else {
    check('buffer.create', false, err.message);
  }
}

// ── 4. createGpuNamespace() — custom namespace ──────────────────────────

console.log('\n4. createGpuNamespace() — custom namespace');

{
  const ns = createGpuNamespace();
  check('createGpuNamespace() returns object', typeof ns === 'object' && ns != null);
  check('namespace.requestDevice is function', typeof ns.requestDevice === 'function');
  check('namespace.bind is function', typeof ns.bind === 'function');
}

{
  // namespace created with a custom requestDevice
  const ns = createGpuNamespace({ requestDevice });
  check('custom namespace has requestDevice', typeof ns.requestDevice === 'function');
  check('custom namespace has bind', typeof ns.bind === 'function');

  try {
    const bound = await ns.requestDevice();
    check('custom namespace requestDevice resolves', true);
    check('custom namespace bound has device', bound.device != null);
    check('custom namespace bound has buffer', bound.buffer != null);
    check('custom namespace bound has kernel', bound.kernel != null);
    check('custom namespace bound has compute', typeof bound.compute === 'function');
    check('custom namespace bound has commandEncoder', bound.commandEncoder != null);
    bound.device.destroy();
  } catch (err) {
    if (isDeviceUnavailableError(err)) {
      skip('custom namespace requestDevice (no GPU available)');
    } else {
      check('custom namespace requestDevice', false, err.message);
    }
  }
}

// ── 5. Error cases ──────────────────────────────────────────────────────

console.log('\n5. Error cases');

// 5a. namespace without requestDevice impl throws on requestDevice()
{
  const emptyNs = createGpuNamespace();
  try {
    await emptyNs.requestDevice();
    check('empty namespace requestDevice throws', false, 'did not throw');
  } catch (err) {
    check(
      'empty namespace requestDevice throws',
      err.message.includes('unavailable'),
      err.message,
    );
  }
}

// 5b. buffer.create with invalid usage token
try {
  const bound = await gpu.requestDevice();
  try {
    bound.buffer.create({ size: 64, usage: 'invalidToken' });
    check('buffer.create invalid usage throws', false, 'did not throw');
  } catch (err) {
    check(
      'buffer.create invalid usage throws',
      err.message.includes('Unknown') || err.message.includes('unknown') || err.message.includes('usage'),
      err.message,
    );
  }
  bound.device.destroy();
} catch (err) {
  if (isDeviceUnavailableError(err)) {
    skip('buffer.create invalid usage (no GPU available)');
  } else {
    check('buffer.create invalid usage', false, err.message);
  }
}

// 5c. buffer.create without required options
try {
  const bound = await gpu.requestDevice();
  try {
    bound.buffer.create(null);
    check('buffer.create null throws', false, 'did not throw');
  } catch (err) {
    check(
      'buffer.create null throws',
      err.message.includes('object') || err.message.includes('options'),
      err.message,
    );
  }
  bound.device.destroy();
} catch (err) {
  if (isDeviceUnavailableError(err)) {
    skip('buffer.create null (no GPU available)');
  } else {
    check('buffer.create null', false, err.message);
  }
}

// ── Results ─────────────────────────────────────────────────────────────

console.log(`\nResults: ${passed} passed, ${failed} failed, ${skipped} skipped`);
process.exitCode = failed > 0 ? 1 : 0;
