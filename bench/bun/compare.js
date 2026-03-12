#!/usr/bin/env bun
// Compare Doe vs bun-webgpu at the Bun runtime level.
//
// Runs runner.js for each provider, collects NDJSON output, computes
// per-workload comparison statistics, and writes a summary report.
//
// Output shape matches bench/node/compare.js so the benchmark cube builder
// can ingest Bun reports via the same normalize_package_report path.
//
// Usage:
//   bun compare.js [--iterations 50] [--warmup 5] [--workload id] [--out dir]
//
// Validation:
//   Runs workload validation prepasses before timing so comparable package-surface
//   claims fail early on incorrect readback or contract drift.

import { execFile } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { RUNNER_MAX_BUFFER } from '../lib/constants.js';
import { fmt } from '../lib/format.js';
import { parseRunnerLines, selectedWorkloads } from '../lib/runner_io.js';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { workloads } from '../node/workloads.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const RUNNER = resolve(__dirname, 'runner.js');

const { values: args } = parseArgs({
  options: {
    iterations: { type: 'string', default: '50' },
    warmup:     { type: 'string', default: '5' },
    workload:   { type: 'string', default: '' },
    out:        { type: 'string', default: '' },
  },
});

function runProviderWorkload(provider, workloadId, extraArgs) {
  return new Promise((resolve, reject) => {
    const bunPath = typeof Bun !== 'undefined' ? process.execPath : 'bun';
    const cmdArgs = [
      RUNNER,
      '--provider', provider,
      '--iterations', args.iterations,
      '--warmup', args.warmup,
    ];
    cmdArgs.push('--workload', workloadId);
    cmdArgs.push('--validate');
    cmdArgs.push(...extraArgs);

    execFile(bunPath, cmdArgs, { maxBuffer: RUNNER_MAX_BUFFER }, (err, stdout, stderr) => {
      process.stderr.write(stderr);
      // Bun lane treats any non-zero runner exit as fatal instead of salvaging
      // a possibly partial NDJSON stream.
      if (err) return reject(new Error(`${provider} runner failed: ${err.message}`));
      const lines = parseRunnerLines(stdout);
      resolve(lines);
    });
  });
}

function buildComparison(doeResults, rightResults) {
  const doeByWorkload = new Map();
  const rightByWorkload = new Map();

  for (const r of doeResults) {
    if (r.workload && r.samplesMs) doeByWorkload.set(r.workload, r);
  }
  for (const r of rightResults) {
    if (r.workload && r.samplesMs) rightByWorkload.set(r.workload, r);
  }

  const comparisons = [];
  const allWorkloads = new Set([...doeByWorkload.keys(), ...rightByWorkload.keys()]);

  for (const id of allWorkloads) {
    const doe = doeByWorkload.get(id);
    const right = rightByWorkload.get(id);
    const canonicalWorkloadId = doe?.canonicalWorkloadId ?? right?.canonicalWorkloadId ?? id;

    if (doe?.canonicalWorkloadId && right?.canonicalWorkloadId && doe.canonicalWorkloadId !== right.canonicalWorkloadId) {
      throw new Error(
        `canonical workload mismatch for ${id}: ${doe.canonicalWorkloadId} vs ${right.canonicalWorkloadId}`
      );
    }

    if (!doe || !right) {
      comparisons.push({
        workload: id,
        canonicalWorkloadId,
        status: !doe ? 'doe_missing' : 'right_missing',
        doeMedianMs: doe?.stats?.median ?? null,
        dawnMedianMs: right?.stats?.median ?? null,
      });
      continue;
    }

    const doeMedian = doe.stats.median;
    const rightMedian = right.stats.median;
    const speedup = rightMedian / doeMedian;
    const pctFaster = ((rightMedian - doeMedian) / rightMedian) * 100;

    const doeP95 = doe.stats.p95;
    const rightP95 = right.stats.p95;
    const isComparable = doe.comparable !== false;
    const claimable = isComparable && doe.stats.count >= 19 && right.stats.count >= 19
      && doeMedian < rightMedian && doeP95 < rightP95;

    comparisons.push({
      workload: id,
      canonicalWorkloadId,
      domain: doe.domain,
      comparable: isComparable,
      status: 'compared',
      doeMedianMs: doeMedian,
      dawnMedianMs: rightMedian,
      speedup: Math.round(speedup * 100) / 100,
      pctFaster: Math.round(pctFaster * 10) / 10,
      claimable,
      doeP95Ms: doeP95,
      dawnP95Ms: rightP95,
      doeP99Ms: doe.stats.p99,
      dawnP99Ms: right.stats.p99,
    });
  }

  return comparisons.sort((a, b) => (b.pctFaster ?? 0) - (a.pctFaster ?? 0));
}

function formatTable(comparisons) {
  const header = '| Workload | Domain | Doe p50 | Right p50 | Speedup | Claim |';
  const sep =    '|----------|--------|---------|-----------|---------|-------|';
  const rows = comparisons.map((c) => {
    if (c.status !== 'compared') {
      return `| ${c.workload} | - | ${fmt(c.doeMedianMs)} | ${fmt(c.dawnMedianMs)} | - | ${c.status} |`;
    }
    let claim;
    if (c.claimable) claim = 'YES';
    else if (!c.comparable) claim = 'n/c';
    else claim = 'no';
    return `| ${c.workload} | ${c.domain} | ${fmt(c.doeMedianMs)} | ${fmt(c.dawnMedianMs)} | ${c.speedup}x | ${claim} |`;
  });
  return [header, sep, ...rows].join('\n');
}

async function main() {
  console.error('=== Bun WebGPU Benchmark: Doe vs bun-webgpu ===\n');
  const selected = selectedWorkloads(workloads, args.workload);
  if (selected.length === 0) {
    console.error(`No workloads matched filter: ${args.workload}`);
    process.exit(1);
  }

  console.error('Running Doe (package-default Bun runtime)...');
  const doeResults = [];
  for (const workload of selected) {
    try {
      const lines = await runProviderWorkload('doe', workload.id, []);
      doeResults.push(...lines);
    } catch (err) {
      console.error(`Doe provider failed on ${workload.id}: ${err.message}`);
      process.exit(1);
    }
  }

  console.error('\nRunning bun-webgpu...');
  const rightResults = [];
  for (const workload of selected) {
    try {
      const lines = await runProviderWorkload('bun-webgpu', workload.id, []);
      rightResults.push(...lines);
    } catch (err) {
      console.error(`bun-webgpu provider failed on ${workload.id}: ${err.message}`);
      console.error('Install bun-webgpu in this environment before running the Bun compare lane.');
      process.exit(1);
    }
  }

  const comparisons = buildComparison(doeResults, rightResults);
  const claimableCount = comparisons.filter((c) => c.claimable).length;
  const comparableCount = comparisons.filter((c) => c.status === 'compared' && c.comparable).length;
  const totalCompared = comparisons.filter((c) => c.status === 'compared').length;

  const report = {
    type: 'comparison_report',
    laneId: 'bun_package_compare',
    timestamp: new Date().toISOString(),
    iterations: parseInt(args.iterations, 10),
    warmup: parseInt(args.warmup, 10),
    platform: process.platform,
    arch: process.arch,
    bunVersion: typeof Bun !== 'undefined' ? Bun.version : 'unknown',
    claimable: claimableCount,
    total: totalCompared,
    comparisons,
  };

  process.stdout.write(JSON.stringify(report, null, 2) + '\n');

  console.error('\n' + formatTable(comparisons));
  console.error(`\nClaimable: ${claimableCount}/${comparableCount} comparable (${totalCompared} total, n/c = not comparable)`);

  if (args.out) {
    const outDir = resolve(args.out);
    await mkdir(outDir, { recursive: true });
    const ts = new Date().toISOString().replace(/[:.]/g, '');
    await writeFile(resolve(outDir, `doe-vs-bun-webgpu-${ts}.json`), JSON.stringify(report, null, 2));
    await writeFile(resolve(outDir, `doe-raw-${ts}.ndjson`), doeResults.map((r) => JSON.stringify(r)).join('\n') + '\n');
    await writeFile(resolve(outDir, `bun-webgpu-raw-${ts}.ndjson`), rightResults.map((r) => JSON.stringify(r)).join('\n') + '\n');
    console.error(`Artifacts written to ${outDir}`);
  }
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${err.message}\n${err.stack}\n`);
  process.exit(1);
});
