#!/usr/bin/env node
// Probe the Doe native WebGPU path end-to-end for one WGSL kernel.
// Records each step's outcome so the gap between "compile-valid" and
// "actually executes bit-exact" is explicit in every sweep.
//
// Reads: bench/out/dual-compile-evidence/elementwise-double/source.wgsl
// Writes: bench/out/vulkan-runtime-probe/elementwise-double/probe.json
//
// Current outcome (2026-04-19): stops at compute-dispatch. Doe's
// libwebgpu_doe.so loads, adapter/device acquire, buffers round-trip,
// preflightShaderSource passes, kernel.dispatch completes without
// error — but dst buffer keeps its pre-dispatch sentinel value.
// Storage-buffer writes from compute shaders are silently dropped.

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import {
  gpu,
  providerInfo,
  preflightShaderSource,
  requestAdapter,
} from '/home/x/deco/doe/packages/doe-gpu/src/index.js';

const REPO_ROOT = '/home/x/deco/doe';
const KERNEL = 'elementwise-double';
const WGSL_PATH = `${REPO_ROOT}/bench/out/dual-compile-evidence/${KERNEL}/source.wgsl`;
const OUT_PATH = `${REPO_ROOT}/bench/out/vulkan-runtime-probe/${KERNEL}/probe.json`;
const N = 16;

const steps = [];
function record(name, status, detail = {}) {
  steps.push({ step: name, status, ...detail });
}

const wgsl = readFileSync(WGSL_PATH, 'utf8');
record('read_wgsl', 'passed', { bytes: wgsl.length });

let info;
try {
  info = providerInfo();
  record('provider_info', 'passed', {
    loaded: info.loaded,
    doeNative: info.doeNative,
    libraryFlavor: info.libraryFlavor,
    doeLibraryPath: info.doeLibraryPath,
  });
} catch (e) {
  record('provider_info', 'failed', { error: e.message });
}

try {
  const pf = preflightShaderSource(wgsl);
  record('preflight_shader', pf.ok ? 'passed' : 'failed', {
    ok: pf.ok,
    reasons: pf.reasons ?? [],
  });
} catch (e) {
  record('preflight_shader', 'failed', { error: e.message });
}

let bound;
try {
  const adapter = await requestAdapter();
  record('request_adapter', adapter ? 'passed' : 'failed', {
    info: adapter?.info ?? null,
  });
  bound = await gpu.requestDevice();
  record('request_device', bound ? 'passed' : 'failed');
} catch (e) {
  record('request_device', 'failed', { error: e.message });
}

if (bound) {
  // Buffer round-trip.
  try {
    const input = new Float32Array(N);
    for (let i = 0; i < N; i++) input[i] = 1.0;
    const src = bound.buffer.create({ data: input, usage: 'storageRead' });
    const readback = await bound.buffer.read(src, Float32Array);
    const ok = readback.every((v) => v === 1.0);
    record('buffer_roundtrip', ok ? 'passed' : 'failed', {
      sampleFirst4: [...readback.slice(0, 4)],
    });
  } catch (e) {
    record('buffer_roundtrip', 'failed', { error: e.message });
  }

  // Dispatch test.
  try {
    const input = new Float32Array(N);
    for (let i = 0; i < N; i++) input[i] = 1.0;
    const src = bound.buffer.create({ data: input, usage: 'storageRead' });
    const dst = bound.buffer.create({
      size: input.byteLength,
      usage: 'storageReadWrite',
    });
    // Pre-fill dst with a sentinel so we can tell if the kernel wrote.
    const sentinel = new Float32Array(N).fill(99.0);
    bound.device.queue.writeBuffer(dst, 0, sentinel);
    const pre = await bound.buffer.read(dst, Float32Array);

    const kernel = bound.kernel.create({ code: wgsl, bindings: [src, dst] });
    await kernel.dispatch({ bindings: [src, dst], workgroups: N });

    const post = await bound.buffer.read(dst, Float32Array);
    const expected = 2.0;
    const writesObserved = post.some((v) => v !== 99.0);
    const allExpected = post.every((v) => v === expected);
    record('compute_dispatch', allExpected ? 'passed' : 'failed', {
      writesObserved,
      allExpected,
      dstPreSample: [...pre.slice(0, 4)],
      dstPostSample: [...post.slice(0, 4)],
      expected,
      gap: writesObserved
        ? 'partial_or_wrong_write'
        : 'no_write_detected',
    });
  } catch (e) {
    record('compute_dispatch', 'failed', { error: e.message });
  }

  bound.device.destroy();
}

const allPassedStep = (name) =>
  steps.find((s) => s.step === name)?.status === 'passed';

const probe = {
  schemaVersion: 1,
  artifactKind: 'doe_vulkan_runtime_probe',
  kernelId: KERNEL,
  generatedAt: new Date().toISOString(),
  backend: 'doe-native-webgpu',
  doeLibraryPath: info?.doeLibraryPath ?? '',
  steps,
  summary: {
    computeDispatchBitExact: allPassedStep('compute_dispatch'),
    infrastructureOk: [
      'provider_info',
      'preflight_shader',
      'request_adapter',
      'request_device',
      'buffer_roundtrip',
    ].every(allPassedStep),
    knownGap: allPassedStep('compute_dispatch')
      ? null
      : 'compute_dispatch_drops_storage_writes',
  },
  notes:
    'Probe of the Doe native WebGPU stack (libwebgpu_doe.so) against one ' +
    'WGSL kernel. Records each end-to-end step so the "compile-valid" vs ' +
    '"actually executes bit-exact" boundary is explicit. When ' +
    'summary.knownGap is set, the WGSL backend equivalence crosswalk ' +
    'should surface it under executionNotYetWired + a diagnostic pointer.',
};

mkdirSync(dirname(OUT_PATH), { recursive: true });
writeFileSync(OUT_PATH, JSON.stringify(probe, null, 2) + '\n');
console.log(
  `probe: compute_dispatch=${probe.summary.computeDispatchBitExact}, ` +
    `infrastructure_ok=${probe.summary.infrastructureOk}, ` +
    `gap=${probe.summary.knownGap ?? 'none'} -> ${OUT_PATH}`,
);
process.exit(probe.summary.infrastructureOk ? 0 : 1);
