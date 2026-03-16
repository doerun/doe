#!/usr/bin/env bun

import { execFile } from 'node:child_process';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  executePackageCompare,
  makeRunnerInvoker,
  parsePackageCompareArgs,
} from '../lib/package-compare-core.js';
import { workloads } from '../node/workloads.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const RUNNER = resolve(__dirname, 'runner.js');
const args = parsePackageCompareArgs();

async function main() {
  const bunPath = typeof Bun !== 'undefined' ? process.execPath : 'bun';
  await executePackageCompare({
    args: { ...args, out: args.out ? resolve(args.out) : '' },
    workloads,
    laneId: 'bun_package_compare',
    banner: '=== Bun WebGPU Benchmark: Doe vs bun-webgpu ===',
    rightRunnerLabel: 'bun-webgpu',
    rightErrorHint: 'Install bun-webgpu in this environment before running the Bun compare lane.',
    rightTableLabel: 'Right',
    reportFilePrefix: 'doe-vs-bun-webgpu',
    rightMissingStatus: 'right_missing',
    rightRawPrefix: 'bun-webgpu-raw',
    runtimeInfo: { bunVersion: typeof Bun !== 'undefined' ? Bun.version : 'unknown' },
    runProviderWorkload: makeRunnerInvoker({
      command: bunPath,
      execFile,
      runnerPath: RUNNER,
      iterations: args.iterations,
      warmup: args.warmup,
    }),
  });
}

main().catch((err) => {
  process.stderr.write(`Fatal: ${err.message}\n${err.stack}\n`);
  process.exit(1);
});
