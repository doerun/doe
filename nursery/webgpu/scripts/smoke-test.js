#!/usr/bin/env node
// Clean-machine smoke test for @simulatte/webgpu.
// Verifies the package loads, finds native artifacts, and can request a GPU device.
//
// Usage:
//   node scripts/smoke-test.js
//
// Exit codes:
//   0  All checks passed
//   1  A check failed (actionable error printed)

import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));

let passed = 0;
let failed = 0;

function check(label, condition, detail) {
  if (condition) {
    passed++;
    console.log(`  ok: ${label}`);
  } else {
    failed++;
    console.error(`  FAIL: ${label}${detail ? ' — ' + detail : ''}`);
  }
}

console.log('=== @simulatte/webgpu smoke test ===\n');

// 1. Import the package.
let mod;
try {
  mod = await import('../src/index.js');
  check('import succeeds', true);
} catch (err) {
  check('import succeeds', false, err.message);
  process.exit(1);
}

// 2. providerInfo shape.
const info = mod.providerInfo();
console.log('\nproviderInfo:', JSON.stringify(info, null, 2), '\n');
check('providerInfo.module', info.module === '@simulatte/webgpu');
check('providerInfo.loaded', info.loaded === true, `got ${info.loaded}`);
check('providerInfo.loadError empty', info.loadError === '', `got "${info.loadError}"`);
check('providerInfo.libraryFlavor', info.libraryFlavor === 'doe-dropin', `got "${info.libraryFlavor}"`);
check('providerInfo.doeNative', info.doeNative === true, `got ${info.doeNative}`);

// 3. globals present.
check('globals.GPUBufferUsage', mod.globals.GPUBufferUsage != null);
check('globals.GPUShaderStage', mod.globals.GPUShaderStage != null);

// 4. create() returns GPU object.
let gpu;
try {
  gpu = mod.create();
  check('create() succeeds', gpu != null);
} catch (err) {
  check('create() succeeds', false, err.message);
  console.log(`\nResults: ${passed} passed, ${failed} failed`);
  process.exitCode = failed > 0 ? 1 : 0;
  process.exit(process.exitCode);
}

// 5. requestAdapter.
let adapter;
try {
  adapter = await gpu.requestAdapter();
  check('requestAdapter()', adapter != null);
} catch (err) {
  check('requestAdapter()', false, err.message);
  console.log(`\nResults: ${passed} passed, ${failed} failed`);
  process.exitCode = failed > 0 ? 1 : 0;
  process.exit(process.exitCode);
}

// 6. requestDevice.
let device;
try {
  device = await adapter.requestDevice();
  check('requestDevice()', device != null);
  check('device.queue exists', device.queue != null);
} catch (err) {
  check('requestDevice()', false, err.message);
}

// 7. Basic buffer round-trip.
if (device) {
  try {
    const buf = device.createBuffer({
      size: 64,
      usage: mod.globals.GPUBufferUsage.COPY_DST | mod.globals.GPUBufferUsage.MAP_READ,
    });
    const data = new Float32Array([1.0, 2.0, 3.0, 4.0]);
    device.queue.writeBuffer(buf, 0, data);
    await buf.mapAsync(mod.globals.GPUMapMode.READ, 0, 16);
    const result = new Float32Array(buf.getMappedRange(0, 16));
    check('buffer round-trip', result[0] === 1.0 && result[3] === 4.0,
      `got [${result[0]}, ${result[1]}, ${result[2]}, ${result[3]}]`);
    buf.unmap();
    buf.destroy();
  } catch (err) {
    check('buffer round-trip', false, err.message);
  }
}

if (device) {
  device.destroy();
}

console.log(`\nResults: ${passed} passed, ${failed} failed`);
process.exitCode = failed > 0 ? 1 : 0;
