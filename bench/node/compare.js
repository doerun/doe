#!/usr/bin/env node
// Compare Doe vs Dawn at the Node.js WebGPU API level.
//
// Runs runner.js for each provider, collects NDJSON output, computes
// per-workload comparison statistics, and writes a summary report.
//
// Usage:
//   node compare.js [--iterations 50] [--warmup 5] [--workload id] [--out dir]
//
// Validation:
//   Runs workload validation prepasses before timing so comparable package-surface
//   claims fail early on incorrect readback or contract drift.
//
// Requirements:
//   - `webgpu` npm package installed (npm install webgpu)
//   - `@simulatte/webgpu` available via nursery path

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
  },
});

function runProvider(provider, extraArgs) {
  return new Promise((resolve, reject) => {
    const cmdArgs = [
      RUNNER,
      '--provider', provider,
      '--iterations', args.iterations,
      '--warmup', args.warmup,
    ];
    if (args.workload) cmdArgs.push('--workload', args.workload);
    cmdArgs.push('--validate');
    cmdArgs.push(...extraArgs);

    execFile(process.execPath, cmdArgs, { maxBuffer: 64 * 1024 * 1024 }, (err, stdout, stderr) => {
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

function buildComparison(doeResults, dawnResults) {
  const doeByWorkload = new Map();
  const dawnByWorkload = new Map();

  for (const r of doeResults) {
    if (r.workload && r.samplesMs) doeByWorkload.set(r.workload, r);
  }
  for (const r of dawnResults) {
    if (r.workload && r.samplesMs) dawnByWorkload.set(r.workload, r);
  }

  const comparisons = [];
  const allWorkloads = new Set([...doeByWorkload.keys(), ...dawnByWorkload.keys()]);

  for (const id of allWorkloads) {
    const doe = doeByWorkload.get(id);
    const dawn = dawnByWorkload.get(id);

    if (!doe || !dawn) {
      comparisons.push({
        workload: id,
        status: !doe ? 'doe_missing' : 'dawn_missing',
        doeMedianMs: doe?.stats?.median ?? null,
        dawnMedianMs: dawn?.stats?.median ?? null,
      });
      continue;
    }

    const doeMedian = doe.stats.median;
    const dawnMedian = dawn.stats.median;
    const speedup = dawnMedian / doeMedian;
    const pctFaster = ((dawnMedian - doeMedian) / dawnMedian) * 100;

    // Claimability: workload must be comparable, have enough samples, and Doe faster at p50+p95.
    const doeP95 = doe.stats.p95;
    const dawnP95 = dawn.stats.p95;
    const isComparable = doe.comparable !== false;
    const claimable = isComparable && doe.stats.count >= 19 && dawn.stats.count >= 19
      && doeMedian < dawnMedian && doeP95 < dawnP95;

    comparisons.push({
      workload: id,
      domain: doe.domain,
      comparable: isComparable,
      status: 'compared',
      doeMedianMs: doeMedian,
      dawnMedianMs: dawnMedian,
      speedup: Math.round(speedup * 100) / 100,
      pctFaster: Math.round(pctFaster * 10) / 10,
      claimable,
      doeP95Ms: doeP95,
      dawnP95Ms: dawnP95,
      doeP99Ms: doe.stats.p99,
      dawnP99Ms: dawn.stats.p99,
    });
  }

  return comparisons.sort((a, b) => (b.pctFaster ?? 0) - (a.pctFaster ?? 0));
}

function formatTable(comparisons) {
  const header = '| Workload | Domain | Doe p50 | Dawn p50 | Speedup | Claim |';
  const sep =    '|----------|--------|---------|----------|---------|-------|';
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
  console.error('=== Node.js WebGPU Benchmark: Doe vs Dawn ===\n');

  console.error('Running Doe...');
  let doeResults;
  try {
    doeResults = await runProvider('doe', []);
  } catch (err) {
    console.error(`Doe provider failed: ${err.message}`);
    process.exit(1);
  }

  console.error('\nRunning Dawn...');
  let dawnResults;
  try {
    dawnResults = await runProvider('dawn', []);
  } catch (err) {
    console.error(`Dawn provider failed: ${err.message}`);
    console.error('Is the webgpu npm package installed? Run: npm install webgpu');
    process.exit(1);
  }

  const comparisons = buildComparison(doeResults, dawnResults);
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
    nodeVersion: process.version,
    claimable: claimableCount,
    total: totalCompared,
    comparisons,
  };

  // Output JSON report to stdout.
  process.stdout.write(JSON.stringify(report, null, 2) + '\n');

  // Summary to stderr.
  console.error('\n' + formatTable(comparisons));
  console.error(`\nClaimable: ${claimableCount}/${comparableCount} comparable (${totalCompared} total, n/c = not comparable)`);

  // Optionally write artifacts.
  if (args.out) {
    const outDir = resolve(args.out);
    await mkdir(outDir, { recursive: true });
    const ts = new Date().toISOString().replace(/[:.]/g, '');
    await writeFile(resolve(outDir, `doe-vs-dawn-node-${ts}.json`), JSON.stringify(report, null, 2));
    await writeFile(resolve(outDir, `doe-raw-${ts}.ndjson`), doeResults.map((r) => JSON.stringify(r)).join('\n') + '\n');
    await writeFile(resolve(outDir, `dawn-raw-${ts}.ndjson`), dawnResults.map((r) => JSON.stringify(r)).join('\n') + '\n');
    console.error(`Artifacts written to ${outDir}`);
  }
}

main().catch((err) => {
  console.error(`Fatal: ${err.message}\n${err.stack}`);
  process.exit(1);
});
