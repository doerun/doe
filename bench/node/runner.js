#!/usr/bin/env node
// Runs WebGPU benchmark workloads against a single provider.
// Output: NDJSON to stdout (one JSON object per sample).
//
// Usage:
//   node runner.js --provider doe [--workload id] [--iterations 50] [--warmup 5]
//   node runner.js --provider dawn [--workload id] [--iterations 50] [--warmup 5]

import { workloads } from './workloads.js';
import { DOE_READBACK_RETRY_LIMIT } from '../lib/constants.js';
import { shouldRetryDoeReadback } from '../lib/doe_util.js';
import { stats } from '../lib/stats.js';
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
    const doe = await import('../../nursery/webgpu/src/index.js');
    return { create: doe.create, globals: doe.globals, name: '@simulatte/webgpu' };
  }
  if (name === 'dawn') {
    // The `webgpu` npm package uses: import { create, globals } from 'webgpu';
    const dawn = await import('webgpu');
    return { create: dawn.create, globals: dawn.globals, name: 'webgpu (dawn)' };
  }
  throw new Error(`Unknown provider: ${name}. Use 'doe' or 'dawn'.`);
}

async function runWorkload(workload, device, queue, globals) {
  const w = workload.factory(device, queue, globals);

  // Setup (not timed).
  if (w.setup) await w.setup();

  // Validation pass.
  if (args.validate && w.validate) {
    const v = await w.validate();
    if (!v.ok) {
      process.stderr.write(`VALIDATION FAIL [${workload.id}]: ${v.detail}\n`);
      if (w.teardown) await w.teardown();
      return null;
    }
  }

  // Warmup (not recorded).
  for (let i = 0; i < WARMUP; i++) {
    if (w.prepareSample) await w.prepareSample();
    await w.run();
  }

  // Timed iterations.
  const samples = [];
  for (let i = 0; i < ITERATIONS; i++) {
    if (w.prepareSample) await w.prepareSample();
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
    nodeVersion: process.version,
  };
  process.stdout.write(JSON.stringify(meta) + '\n');

  for (const workload of selected) {
    let attempt = 0;
    let result = null;
    let lastError = null;
    while (attempt < DOE_READBACK_RETRY_LIMIT) {
      try {
        result = await runWorkload(workload, device, device.queue, provider.globals);
        lastError = null;
        break;
      } catch (err) {
        lastError = err;
        attempt += 1;
        if (!shouldRetryDoeReadback(PROVIDER, workload, err) || attempt >= DOE_READBACK_RETRY_LIMIT) break;
        process.stderr.write(
          `  ${workload.id}: retrying Doe readback after transient mismatch (${attempt}/${DOE_READBACK_RETRY_LIMIT})\n`
        );
      }
    }
    if (lastError) {
      const errRecord = {
        workload: workload.id,
        canonicalWorkloadId: workload.canonicalWorkloadId ?? workload.id,
        provider: PROVIDER,
        error: lastError.message,
        type: 'workload_error',
      };
      process.stdout.write(JSON.stringify(errRecord) + '\n');
      process.stderr.write(`  ${workload.id}: ERROR — ${lastError.message}\n`);
      continue;
    }
    if (result) {
      process.stdout.write(JSON.stringify(result) + '\n');
      process.stderr.write(
        `  ${workload.id}: ${result.stats.median.toFixed(3)}ms median (${result.stats.count} samples)\n`
      );
    }
  }

  const done = { type: 'run_end', timestamp: new Date().toISOString() };
  process.stdout.write(JSON.stringify(done) + '\n');

  // The Dawn-backed `webgpu` package on macOS can segfault during explicit
  // device teardown after all benchmark output has already been emitted.
  // Let process shutdown reclaim the device instead of crashing the lane.
  if (PROVIDER !== 'dawn') {
    device.destroy();
  }
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${err.message}\n${err.stack}\n`);
  process.exit(1);
});
