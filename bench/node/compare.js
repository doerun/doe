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
import { RUNNER_MAX_BUFFER } from '../lib/constants.js';
import { fmt } from '../lib/format.js';
import { parseRunnerLines, selectedWorkloads } from '../lib/runner_io.js';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { workloads } from './workloads.js';

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

function hasCompleteRun(lines) {
  return lines.some((line) => line?.type === 'run_end');
}

function runProviderWorkload(provider, workloadId, extraArgs) {
  return new Promise((resolve, reject) => {
    const cmdArgs = [
      RUNNER,
      '--provider', provider,
      '--iterations', args.iterations,
      '--warmup', args.warmup,
      '--workload', workloadId,
    ];
    cmdArgs.push('--validate');
    cmdArgs.push(...extraArgs);

    execFile(process.execPath, cmdArgs, { maxBuffer: RUNNER_MAX_BUFFER }, (err, stdout, stderr) => {
      process.stderr.write(stderr);
      let lines;
      try {
        lines = parseRunnerLines(stdout);
      } catch (parseErr) {
        const detail = parseErr instanceof Error ? parseErr.message : String(parseErr);
        return reject(new Error(`${provider} runner emitted invalid JSON: ${detail}`));
      }
      if (err) {
        // Preserve a complete stream when teardown exits non-zero after run_end.
        if (hasCompleteRun(lines)) {
          process.stderr.write(
            `WARN: ${provider} runner exited non-zero after emitting complete output; using captured results\n`
          );
          return resolve(lines);
        }
        return reject(new Error(`${provider} runner failed: ${err.message}`));
      }
      resolve(lines);
    });
  });
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
    const canonicalWorkloadId = doe?.canonicalWorkloadId ?? dawn?.canonicalWorkloadId ?? id;

    if (doe?.canonicalWorkloadId && dawn?.canonicalWorkloadId && doe.canonicalWorkloadId !== dawn.canonicalWorkloadId) {
      throw new Error(
        `canonical workload mismatch for ${id}: ${doe.canonicalWorkloadId} vs ${dawn.canonicalWorkloadId}`
      );
    }

    if (!doe || !dawn) {
      comparisons.push({
        workload: id,
        canonicalWorkloadId,
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
      canonicalWorkloadId,
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

async function main() {
  console.error('=== Node.js WebGPU Benchmark: Doe vs Dawn ===\n');
  const selected = selectedWorkloads(workloads, args.workload);
  if (selected.length === 0) {
    console.error(`No workloads matched filter: ${args.workload}`);
    process.exit(1);
  }

  console.error('Running Doe...');
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

  console.error('\nRunning Dawn...');
  const dawnResults = [];
  for (const workload of selected) {
    try {
      const lines = await runProviderWorkload('dawn', workload.id, []);
      dawnResults.push(...lines);
    } catch (err) {
      console.error(`Dawn provider failed on ${workload.id}: ${err.message}`);
      console.error('Is the webgpu npm package installed? Run: npm install webgpu');
      process.exit(1);
    }
  }

  const comparisons = buildComparison(doeResults, dawnResults);
  const claimableCount = comparisons.filter((c) => c.claimable).length;
  const comparableCount = comparisons.filter((c) => c.status === 'compared' && c.comparable).length;
  const totalCompared = comparisons.filter((c) => c.status === 'compared').length;

  const report = {
    type: 'comparison_report',
    laneId: 'node_package_compare',
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
