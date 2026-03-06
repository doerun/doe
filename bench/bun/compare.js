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

import { execFile } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

const __dirname = dirname(fileURLToPath(import.meta.url));
const RUNNER = resolve(__dirname, 'runner.js');

const { values: args } = parseArgs({
  options: {
    iterations: { type: 'string', default: '50' },
    warmup:     { type: 'string', default: '5' },
    workload:   { type: 'string', default: '' },
    out:        { type: 'string', default: '' },
    validate:   { type: 'boolean', default: false },
  },
});

function runProvider(provider, extraArgs) {
  return new Promise((resolve, reject) => {
    const bunPath = typeof Bun !== 'undefined' ? process.execPath : 'bun';
    const cmdArgs = [
      RUNNER,
      '--provider', provider,
      '--iterations', args.iterations,
      '--warmup', args.warmup,
    ];
    if (args.workload) cmdArgs.push('--workload', args.workload);
    if (args.validate) cmdArgs.push('--validate');
    cmdArgs.push(...extraArgs);

    execFile(bunPath, cmdArgs, { maxBuffer: 64 * 1024 * 1024 }, (err, stdout, stderr) => {
      process.stderr.write(stderr);
      if (err) return reject(new Error(`${provider} runner failed: ${err.message}`));
      const lines = stdout.trim().split('\n').map((l) => JSON.parse(l));
      resolve(lines);
    });
  });
}

function percentile(sorted, p) {
  const idx = Math.ceil(p / 100 * sorted.length) - 1;
  return sorted[Math.max(0, idx)];
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

    if (!doe || !right) {
      comparisons.push({
        workload: id,
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

function fmt(ms) {
  if (ms == null) return '-';
  if (ms < 0.01) return (ms * 1000).toFixed(1) + 'us';
  return ms.toFixed(3) + 'ms';
}

async function main() {
  console.error('=== Bun WebGPU Benchmark: Doe vs bun-webgpu ===\n');

  console.error('Running Doe (FFI)...');
  let doeResults;
  try {
    doeResults = await runProvider('doe', []);
  } catch (err) {
    console.error(`Doe provider failed: ${err.message}`);
    process.exit(1);
  }

  console.error('\nRunning bun-webgpu...');
  let rightResults;
  try {
    rightResults = await runProvider('bun-webgpu', []);
  } catch (err) {
    console.error(`bun-webgpu provider failed: ${err.message}`);
    console.error('Install bun-webgpu in this environment before running the Bun compare lane.');
    process.exit(1);
  }

  const comparisons = buildComparison(doeResults, rightResults);
  const claimableCount = comparisons.filter((c) => c.claimable).length;
  const comparableCount = comparisons.filter((c) => c.status === 'compared' && c.comparable).length;
  const totalCompared = comparisons.filter((c) => c.status === 'compared').length;

  const report = {
    type: 'comparison_report',
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
