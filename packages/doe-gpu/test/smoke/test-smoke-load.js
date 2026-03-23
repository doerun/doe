#!/usr/bin/env node
// Smoke test for doe-gpu.
// Verifies the package loads and key exports have the expected shape.
// No GPU required — pure export/shape validation only.
//
// Usage:
//   node test/smoke/test-smoke-load.js
//
// Exit codes:
//   0  All checks passed
//   1  A check failed (actionable error printed)

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

console.log('=== doe-gpu smoke test ===\n');

// ── 1. Import the main package surface ──────────────────────────────────

let mod;
try {
  mod = await import('../../src/index.js');
  check('import succeeds', true);
} catch (err) {
  check('import succeeds', false, err.message);
  process.exit(1);
}

// ── 2. Key named exports exist ──────────────────────────────────────────

check('exports gpu', mod.gpu != null);
check('exports createGpuNamespace', typeof mod.createGpuNamespace === 'function');
check('exports createDoeNamespace', typeof mod.createDoeNamespace === 'function');
check('exports create', typeof mod.create === 'function');
check('exports requestDevice', typeof mod.requestDevice === 'function');
check('exports requestAdapter', typeof mod.requestAdapter === 'function');
check('exports providerInfo', typeof mod.providerInfo === 'function');
check('exports globals', mod.globals != null && typeof mod.globals === 'object');

// ── 3. gpu namespace shape ──────────────────────────────────────────────

console.log('\ngpu namespace shape:');
check('gpu is an object', typeof mod.gpu === 'object');
check('gpu.requestDevice is a function', typeof mod.gpu.requestDevice === 'function');
check('gpu.bind is a function', typeof mod.gpu.bind === 'function');

// ── 4. globals has standard WebGPU enum objects ─────────────────────────

console.log('\nglobals shape:');
const g = mod.globals;
check('globals.GPUBufferUsage exists', g.GPUBufferUsage != null);
check('globals.GPUBufferUsage.STORAGE', typeof g.GPUBufferUsage?.STORAGE === 'number');
check('globals.GPUShaderStage exists', g.GPUShaderStage != null);
check('globals.GPUShaderStage.COMPUTE', typeof g.GPUShaderStage?.COMPUTE === 'number');
check('globals.GPUMapMode exists', g.GPUMapMode != null);
check('globals.GPUMapMode.READ', typeof g.GPUMapMode?.READ === 'number');

// ── 5. createGpuNamespace returns same shape as gpu ─────────────────────

console.log('\ncreateGpuNamespace shape:');
const ns = mod.createGpuNamespace();
check('createGpuNamespace() returns object', typeof ns === 'object' && ns != null);
check('namespace.requestDevice', typeof ns.requestDevice === 'function');
check('namespace.bind', typeof ns.bind === 'function');

// ── 6. Compute surface ──────────────────────────────────────────────────

console.log('\ncompute surface:');
let compute;
try {
  compute = await import('../../src/compute.js');
  check('compute import succeeds', true);
} catch (err) {
  check('compute import succeeds', false, err.message);
}

if (compute) {
  check('compute.gpu exists', compute.gpu != null);
  check('compute.createGpuNamespace', typeof compute.createGpuNamespace === 'function');
  check('compute.create', typeof compute.create === 'function');
  check('compute.requestDevice', typeof compute.requestDevice === 'function');
  check('compute.requestAdapter', typeof compute.requestAdapter === 'function');
  check('compute.providerInfo', typeof compute.providerInfo === 'function');
  check('compute.globals exists', compute.globals != null && typeof compute.globals === 'object');
  check('compute.gpu.requestDevice', typeof compute.gpu?.requestDevice === 'function');
  check('compute.gpu.bind', typeof compute.gpu?.bind === 'function');
}

// ── Results ─────────────────────────────────────────────────────────────

console.log(`\nResults: ${passed} passed, ${failed} failed`);
process.exitCode = failed > 0 ? 1 : 0;
