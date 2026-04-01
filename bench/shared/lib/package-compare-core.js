import { mkdir, writeFile } from 'node:fs/promises';
import { parseArgs } from 'node:util';
import { RUNNER_MAX_BUFFER } from './constants.js';
import { fmt } from './format.js';
import { parseRunnerLines, selectedWorkloads } from './runner_io.js';

export function parsePackageCompareArgs() {
  return parseArgs({
    options: {
      iterations: { type: 'string', default: '50' },
      warmup: { type: 'string', default: '5' },
      workload: { type: 'string', default: '' },
      out: { type: 'string', default: '' },
    },
  }).values;
}

function hasCompleteRun(lines) {
  return lines.some((line) => line?.type === 'run_end');
}

export function makeRunnerInvoker({
  command,
  execFile,
  runnerPath,
  iterations,
  warmup,
  salvageCompleteStream = false,
}) {
  return function runProviderWorkload(provider, workloadId, extraArgs = []) {
    return new Promise((resolve, reject) => {
      const cmdArgs = [
        runnerPath,
        '--provider',
        provider,
        '--iterations',
        iterations,
        '--warmup',
        warmup,
        '--workload',
        workloadId,
        '--validate',
        ...extraArgs,
      ];
      execFile(command, cmdArgs, { maxBuffer: RUNNER_MAX_BUFFER }, (err, stdout, stderr) => {
        process.stderr.write(stderr);
        let lines;
        try {
          lines = parseRunnerLines(stdout);
        } catch (parseErr) {
          const detail = parseErr instanceof Error ? parseErr.message : String(parseErr);
          reject(new Error(`${provider} runner emitted invalid JSON: ${detail}`));
          return;
        }
        if (err) {
          if (salvageCompleteStream && hasCompleteRun(lines)) {
            process.stderr.write(
              `WARN: ${provider} runner exited non-zero after emitting complete output; using captured results\n`
            );
            resolve(lines);
            return;
          }
          reject(new Error(`${provider} runner failed: ${err.message}`));
          return;
        }
        resolve(lines);
      });
    });
  };
}

export function buildPackageComparisons({
  leftResults,
  rightResults,
  rightMissingStatus,
}) {
  const leftByWorkload = new Map();
  const rightByWorkload = new Map();

  for (const result of leftResults) {
    if (result.workload && result.samplesMs) {
      leftByWorkload.set(result.workload, result);
    }
  }
  for (const result of rightResults) {
    if (result.workload && result.samplesMs) {
      rightByWorkload.set(result.workload, result);
    }
  }

  const comparisons = [];
  const allWorkloads = new Set([...leftByWorkload.keys(), ...rightByWorkload.keys()]);

  for (const workloadId of allWorkloads) {
    const left = leftByWorkload.get(workloadId);
    const right = rightByWorkload.get(workloadId);
    const canonicalWorkloadId = left?.canonicalWorkloadId ?? right?.canonicalWorkloadId ?? workloadId;

    if (
      left?.canonicalWorkloadId &&
      right?.canonicalWorkloadId &&
      left.canonicalWorkloadId !== right.canonicalWorkloadId
    ) {
      throw new Error(
        `canonical workload mismatch for ${workloadId}: ${left.canonicalWorkloadId} vs ${right.canonicalWorkloadId}`
      );
    }

    if (!left || !right) {
      comparisons.push({
        workload: workloadId,
        canonicalWorkloadId,
        status: !left ? 'doe_missing' : rightMissingStatus,
        doeMedianMs: left?.stats?.median ?? null,
        dawnMedianMs: right?.stats?.median ?? null,
      });
      continue;
    }

    const leftMedian = left.stats.median;
    const rightMedian = right.stats.median;
    const leftP95 = left.stats.p95;
    const rightP95 = right.stats.p95;
    const speedup = rightMedian / leftMedian;
    const pctFaster = ((rightMedian - leftMedian) / rightMedian) * 100;
    const comparable = left.comparable !== false;
    const claimable =
      comparable &&
      left.stats.count >= 19 &&
      right.stats.count >= 19 &&
      leftMedian < rightMedian &&
      leftP95 < rightP95;

    comparisons.push({
      workload: workloadId,
      canonicalWorkloadId,
      domain: left.domain,
      comparable,
      status: 'compared',
      doeMedianMs: leftMedian,
      dawnMedianMs: rightMedian,
      speedup: Math.round(speedup * 100) / 100,
      pctFaster: Math.round(pctFaster * 10) / 10,
      claimable,
      doeP95Ms: leftP95,
      dawnP95Ms: rightP95,
      doeP99Ms: left.stats.p99,
      dawnP99Ms: right.stats.p99,
    });
  }

  return comparisons.sort((left, right) => (right.pctFaster ?? 0) - (left.pctFaster ?? 0));
}

export function formatPackageComparisonTable(comparisons, rightLabel) {
  const header = `| Workload | Domain | Doe p50 | ${rightLabel} p50 | Speedup | Claim |`;
  const separator = '|----------|--------|---------|-----------|---------|-------|';
  const rows = comparisons.map((comparison) => {
    if (comparison.status !== 'compared') {
      return `| ${comparison.workload} | - | ${fmt(comparison.doeMedianMs)} | ${fmt(comparison.dawnMedianMs)} | - | ${comparison.status} |`;
    }
    const claim = comparison.claimable ? 'YES' : comparison.comparable ? 'no' : 'n/c';
    return `| ${comparison.workload} | ${comparison.domain} | ${fmt(comparison.doeMedianMs)} | ${fmt(comparison.dawnMedianMs)} | ${comparison.speedup}x | ${claim} |`;
  });
  return [header, separator, ...rows].join('\n');
}

export async function executePackageCompare({
  args,
  workloads,
  laneId,
  banner,
  rightRunnerLabel,
  rightErrorHint,
  rightTableLabel,
  reportFilePrefix,
  rightMissingStatus,
  rightRawPrefix,
  runtimeInfo,
  runProviderWorkload,
}) {
  console.error(`${banner}\n`);
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
      console.error(`  skipping ${workload.id} for Doe`);
    }
  }

  console.error(`\nRunning ${rightRunnerLabel}...`);
  const rightResults = [];
  for (const workload of selected) {
    try {
      const lines = await runProviderWorkload(rightRunnerLabel, workload.id, []);
      rightResults.push(...lines);
    } catch (err) {
      console.error(`${rightRunnerLabel} provider failed on ${workload.id}: ${err.message}`);
      if (rightErrorHint) {
        console.error(rightErrorHint);
      }
      console.error(`  skipping ${workload.id} for ${rightRunnerLabel}`);
    }
  }

  const comparisons = buildPackageComparisons({
    leftResults: doeResults,
    rightResults,
    rightMissingStatus,
  });
  const claimableCount = comparisons.filter((comparison) => comparison.claimable).length;
  const comparableCount = comparisons.filter(
    (comparison) => comparison.status === 'compared' && comparison.comparable
  ).length;
  const totalCompared = comparisons.filter((comparison) => comparison.status === 'compared').length;

  const report = {
    type: 'comparison_report',
    laneId,
    timestamp: new Date().toISOString(),
    iterations: parseInt(args.iterations, 10),
    warmup: parseInt(args.warmup, 10),
    platform: process.platform,
    arch: process.arch,
    ...runtimeInfo,
    claimable: claimableCount,
    total: totalCompared,
    comparisons,
  };

  process.stdout.write(JSON.stringify(report, null, 2) + '\n');
  console.error(`\n${formatPackageComparisonTable(comparisons, rightTableLabel)}`);
  console.error(
    `\nClaimable: ${claimableCount}/${comparableCount} comparable (${totalCompared} total, n/c = not comparable)`
  );

  if (args.out) {
    await mkdir(args.out, { recursive: true });
    const timestamp = new Date().toISOString().replace(/[:.]/g, '');
    await writeFile(
      `${args.out}/${reportFilePrefix}-${timestamp}.json`,
      JSON.stringify(report, null, 2)
    );
    await writeFile(
      `${args.out}/doe-raw-${timestamp}.ndjson`,
      doeResults.map((result) => JSON.stringify(result)).join('\n') + '\n'
    );
    await writeFile(
      `${args.out}/${rightRawPrefix}-${timestamp}.ndjson`,
      rightResults.map((result) => JSON.stringify(result)).join('\n') + '\n'
    );
    console.error(`Artifacts written to ${args.out}`);
  }
}
