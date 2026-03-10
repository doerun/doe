#!/usr/bin/env bun
// Runs WebGPU benchmark workloads against a single provider under Bun.
// Output: NDJSON to stdout (one JSON object per sample).
//
// Usage:
//   bun runner.js --provider doe [--workload id] [--iterations 50] [--warmup 5]
//   bun runner.js --provider bun-webgpu [--workload id] [--iterations 50] [--warmup 5]

import { workloads } from '../node/workloads.js';
import { performance } from 'node:perf_hooks';
import { parseArgs } from 'node:util';

const { values: args } = parseArgs({
  options: {
    provider:   { type: 'string', default: 'doe' },
    workload:   { type: 'string', default: '' },
    iterations: { type: 'string', default: '50' },
    warmup:     { type: 'string', default: '5' },
    validate:   { type: 'boolean', default: false },
  },
});

const ITERATIONS = parseInt(args.iterations, 10);
const WARMUP = parseInt(args.warmup, 10);
const PROVIDER = args.provider;
const WORKLOAD_FILTER = args.workload;

async function loadProvider(name) {
  if (name === 'doe') {
    const doe = await import('../../nursery/webgpu/src/bun.js');
    return { create: doe.create, globals: doe.globals, name: '@simulatte/webgpu (bun default)' };
  }
  if (name === 'bun-webgpu') {
    // Community Bun WebGPU package: installs navigator.gpu via setupGlobals().
    const mod = await import('bun-webgpu');
    if (typeof mod.setupGlobals !== 'function') {
      throw new Error('bun-webgpu does not export setupGlobals()');
    }
    mod.setupGlobals();
    if (typeof navigator === 'undefined' || !navigator.gpu) {
      throw new Error('bun-webgpu did not install navigator.gpu');
    }
    const gpu = navigator.gpu;
    const globals = {
      GPUBufferUsage:  globalThis.GPUBufferUsage,
      GPUShaderStage:  globalThis.GPUShaderStage,
      GPUMapMode:      globalThis.GPUMapMode,
      GPUTextureUsage: globalThis.GPUTextureUsage,
    };
    return {
      create: () => gpu,
      globals,
      name: 'bun-webgpu (package)',
    };
  }
  throw new Error(`Unknown provider: ${name}. Use 'doe' or 'bun-webgpu'.`);
}

function percentile(sorted, p) {
  const idx = Math.ceil(p / 100 * sorted.length) - 1;
  return sorted[Math.max(0, idx)];
}

function stats(samples) {
  const sorted = [...samples].sort((a, b) => a - b);
  const sum = sorted.reduce((a, b) => a + b, 0);
  return {
    count: sorted.length,
    mean: sum / sorted.length,
    min: sorted[0],
    max: sorted[sorted.length - 1],
    median: percentile(sorted, 50),
    p95: percentile(sorted, 95),
    p99: percentile(sorted, 99),
  };
}

async function runWorkload(workload, device, queue, globals) {
  const w = workload.factory(device, queue, globals);

  if (w.setup) await w.setup();

  if (args.validate && w.validate) {
    const v = await w.validate();
    if (!v.ok) {
      process.stderr.write(`VALIDATION FAIL [${workload.id}]: ${v.detail}\n`);
      if (w.teardown) await w.teardown();
      return null;
    }
  }

  for (let i = 0; i < WARMUP; i++) {
    await w.run();
  }

  const samples = [];
  for (let i = 0; i < ITERATIONS; i++) {
    const t0 = performance.now();
    await w.run();
    const t1 = performance.now();
    samples.push(t1 - t0);
  }

  if (w.teardown) await w.teardown();

  return {
    workload: workload.id,
    canonicalWorkloadId: workload.canonicalWorkloadId ?? workload.id,
    domain: workload.domain,
    comparable: workload.comparable ?? true,
    provider: PROVIDER,
    iterations: ITERATIONS,
    warmup: WARMUP,
    timingSource: 'performance.now',
    timingClass: 'operation',
    samplesMs: samples,
    stats: stats(samples),
  };
}

async function main() {
  const provider = await loadProvider(PROVIDER);
  const gpu = provider.create([]);
  const adapter = await gpu.requestAdapter();
  if (!adapter) {
    process.stderr.write(`No adapter found for provider ${PROVIDER}\n`);
    process.exit(1);
  }
  const device = await adapter.requestDevice();

  const selected = WORKLOAD_FILTER
    ? workloads.filter((w) => w.id === WORKLOAD_FILTER || w.domain === WORKLOAD_FILTER)
    : workloads;

  if (selected.length === 0) {
    process.stderr.write(`No workloads matched filter: ${WORKLOAD_FILTER}\n`);
    process.exit(1);
  }

  const meta = {
    type: 'run_start',
    provider: provider.name,
    providerKey: PROVIDER,
    timestamp: new Date().toISOString(),
    iterations: ITERATIONS,
    warmup: WARMUP,
    workloadCount: selected.length,
    platform: process.platform,
    arch: process.arch,
    bunVersion: typeof Bun !== 'undefined' ? Bun.version : 'unknown',
  };
  process.stdout.write(JSON.stringify(meta) + '\n');

  for (const workload of selected) {
    try {
      const result = await runWorkload(workload, device, device.queue, provider.globals);
      if (result) {
        process.stdout.write(JSON.stringify(result) + '\n');
        process.stderr.write(
          `  ${workload.id}: ${result.stats.median.toFixed(3)}ms median (${result.stats.count} samples)\n`
        );
      }
    } catch (err) {
      const errRecord = {
        workload: workload.id,
        canonicalWorkloadId: workload.canonicalWorkloadId ?? workload.id,
        provider: PROVIDER,
        error: err.message,
        type: 'workload_error',
      };
      process.stdout.write(JSON.stringify(errRecord) + '\n');
      process.stderr.write(`  ${workload.id}: ERROR — ${err.message}\n`);
    }
  }

  const done = { type: 'run_end', timestamp: new Date().toISOString() };
  process.stdout.write(JSON.stringify(done) + '\n');

  device.destroy();
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${err.message}\n${err.stack}\n`);
  process.exit(1);
});
