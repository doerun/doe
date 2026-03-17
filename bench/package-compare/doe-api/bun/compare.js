#!/usr/bin/env bun

import { execFile } from 'node:child_process';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  executePackageCompare,
  makeRunnerInvoker,
  parsePackageCompareArgs,
} from '../../../shared/lib/package-compare-core.js';
import { workloads } from '../workloads.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const RUNNER = resolve(__dirname, 'runner.js');
const args = parsePackageCompareArgs();

async function main() {
  const bunPath = typeof Bun !== 'undefined' ? process.execPath : 'bun';
  await executePackageCompare({
    args: { ...args, out: args.out ? resolve(args.out) : '' },
    workloads,
    laneId: 'doe_api_bun_package_compare',
    banner: '=== Bun Doe API Benchmark: webgpu-doe vs raw bun-webgpu ===',
    rightRunnerLabel: 'bun-webgpu',
    rightErrorHint: 'Install bun-webgpu before running the Bun doe-api compare lane.',
    rightTableLabel: 'bun-webgpu raw',
    reportFilePrefix: 'doe-api-vs-bun-webgpu',
    rightMissingStatus: 'bun_webgpu_missing',
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
