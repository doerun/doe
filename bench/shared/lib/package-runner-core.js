import { performance } from 'node:perf_hooks';
import { parseArgs } from 'node:util';
import { DOE_READBACK_RETRY_LIMIT } from './constants.js';
import { shouldRetryDoeReadback } from './doe_util.js';
import { selectedWorkloads } from './runner_io.js';
import { stats } from './stats.js';

export function parsePackageRunnerArgs() {
  return parseArgs({
    options: {
      provider: { type: 'string', default: 'doe' },
      workload: { type: 'string', default: '' },
      iterations: { type: 'string', default: '50' },
      warmup: { type: 'string', default: '5' },
      validate: { type: 'boolean', default: false },
    },
  }).values;
}

async function runWorkload(workload, device, queue, globals, args) {
  const runtime = workload.factory(device, queue, globals);

  if (runtime.setup) {
    await runtime.setup();
  }

  if (args.validate && runtime.validate) {
    const validation = await runtime.validate();
    if (!validation.ok) {
      process.stderr.write(`VALIDATION FAIL [${workload.id}]: ${validation.detail}\n`);
      if (runtime.teardown) {
        await runtime.teardown();
      }
      return null;
    }
  }

  const warmup = parseInt(args.warmup, 10);
  for (let iteration = 0; iteration < warmup; iteration += 1) {
    if (runtime.prepareSample) {
      await runtime.prepareSample();
    }
    await runtime.run();
  }

  const timedIterations = parseInt(args.iterations, 10);
  const samples = [];
  for (let iteration = 0; iteration < timedIterations; iteration += 1) {
    if (runtime.prepareSample) {
      await runtime.prepareSample();
    }
    const start = performance.now();
    await runtime.run();
    const end = performance.now();
    samples.push(end - start);
  }

  if (runtime.teardown) {
    await runtime.teardown();
  }

  return {
    workload: workload.id,
    canonicalWorkloadId: workload.canonicalWorkloadId ?? workload.id,
    domain: workload.domain,
    comparable: workload.comparable ?? true,
    provider: args.provider,
    iterations: timedIterations,
    warmup,
    timingSource: 'performance.now',
    timingClass: 'operation',
    samplesMs: samples,
    stats: stats(samples),
  };
}

export async function executePackageRunner({
  args,
  workloads,
  loadProvider,
  runtimeInfo,
  shouldDestroyDevice,
}) {
  const provider = await loadProvider(args.provider);
  const gpu = provider.create([]);
  const adapter = await gpu.requestAdapter();
  if (!adapter) {
    process.stderr.write(`No adapter found for provider ${args.provider}\n`);
    process.exit(1);
  }
  const device = await adapter.requestDevice();
  const selected = selectedWorkloads(workloads, args.workload);

  if (selected.length === 0) {
    process.stderr.write(`No workloads matched filter: ${args.workload}\n`);
    process.exit(1);
  }

  process.stdout.write(
    JSON.stringify({
      type: 'run_start',
      provider: provider.name,
      providerKey: args.provider,
      timestamp: new Date().toISOString(),
      iterations: parseInt(args.iterations, 10),
      warmup: parseInt(args.warmup, 10),
      workloadCount: selected.length,
      platform: process.platform,
      arch: process.arch,
      ...runtimeInfo,
    }) + '\n'
  );

  for (const workload of selected) {
    let attempt = 0;
    let result = null;
    let lastError = null;

    while (attempt < DOE_READBACK_RETRY_LIMIT) {
      try {
        result = await runWorkload(workload, device, device.queue, provider.globals, args);
        lastError = null;
        break;
      } catch (err) {
        lastError = err;
        attempt += 1;
        if (
          !shouldRetryDoeReadback(args.provider, workload, err) ||
          attempt >= DOE_READBACK_RETRY_LIMIT
        ) {
          break;
        }
        process.stderr.write(
          `  ${workload.id}: retrying Doe readback after transient mismatch (${attempt}/${DOE_READBACK_RETRY_LIMIT})\n`
        );
      }
    }

    if (lastError) {
      process.stdout.write(
        JSON.stringify({
          workload: workload.id,
          canonicalWorkloadId: workload.canonicalWorkloadId ?? workload.id,
          provider: args.provider,
          error: lastError.message,
          type: 'workload_error',
        }) + '\n'
      );
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

  process.stdout.write(JSON.stringify({ type: 'run_end', timestamp: new Date().toISOString() }) + '\n');

  if (shouldDestroyDevice(args.provider)) {
    device.destroy();
  }
}
